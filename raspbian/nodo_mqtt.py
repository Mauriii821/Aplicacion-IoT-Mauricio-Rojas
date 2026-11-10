"""
nodo_mqtt.py - Dispositivo IoT en la Raspberry Pi (física o VM Raspbian)
=======================================================================
Equivale a DEVICE1 (sensor de humedad/temperatura) y DEVICE2 (sensor de
movimiento) del taller de Packet Tracer.

- Publica lecturas por MQTT a AWS IoT Core (broker en la nube), con TLS
  mutuo: certificado del dispositivo + llave privada + CA raíz de Amazon
  (el kit de conexión que se descarga desde la consola de AWS IoT).
- Una regla de AWS IoT Core guarda cada mensaje en DynamoDB.
- Recibe comandos para los actuadores (led, ventilador).
- Cada mensaje va firmado con HMAC-SHA256; los comandos sin firma válida,
  antiguos (>30 s) o con valores no permitidos se descartan.
- Sin conexión: guarda las lecturas en SQLite y las reenvía al reconectar.
- Reconexión automática con espera progresiva (1 s ... 60 s).
- Last Will: si el nodo se cae, el broker avisa "online": false.
- Ahorro de energía: intervalo configurable y solo publica si los valores
  cambian (o cada N ciclos como latido). El movimiento se envía al instante.

Uso:  python3 nodo_mqtt.py
"""
import os
import random
import sqlite3
import ssl
import time

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from seguridad import desempaquetar, firmar_plano

load_dotenv()

BROKER = os.environ["IOT_ENDPOINT"]     # ej: xxxxxxxx-ats.iot.us-east-1.amazonaws.com
PUERTO = int(os.getenv("MQTT_PORT", "8883"))
CLAVE_HMAC = os.environ["HMAC_KEY"].encode()
DISPOSITIVO = os.getenv("DEVICE_ID", "raspbian01")
CLIENT_ID = os.getenv("IOT_CLIENT_ID", DISPOSITIVO)  # debe coincidir con la política de IoT
INTERVALO_S = int(os.getenv("INTERVALO_S", "5"))
UMBRAL = 0.5          # cambio mínimo para volver a publicar
LATIDO_CICLOS = 6     # publica igual cada 6 ciclos

T_TELEMETRIA = f"iot/{DISPOSITIVO}/telemetria"
T_COMANDOS = f"iot/{DISPOSITIVO}/comandos"
T_ESTADO = f"iot/{DISPOSITIVO}/estado"

# Actuadores (en una Raspberry física aquí se manejarían los GPIO)
actuadores = {"led": False, "ventilador": False}
PERMITIDOS = set(actuadores)

# ---------------- Almacenamiento temporal ----------------
db = sqlite3.connect(os.path.join(os.path.dirname(__file__), "buffer_offline.db"), check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS pendientes (id INTEGER PRIMARY KEY, topic TEXT, msg TEXT)")
db.commit()


def guardar_pendiente(topic, msg):
    db.execute("INSERT INTO pendientes (topic, msg) VALUES (?, ?)", (topic, msg))
    db.commit()
    n = db.execute("SELECT COUNT(*) FROM pendientes").fetchone()[0]
    print(f"[OFFLINE] lectura guardada localmente ({n} pendientes)")


def reenviar_pendientes(client):
    filas = db.execute("SELECT id, topic, msg FROM pendientes ORDER BY id").fetchall()
    enviados = 0
    for fila_id, topic, msg in filas:
        if client.publish(topic, msg, qos=1).rc != mqtt.MQTT_ERR_SUCCESS:
            break
        db.execute("DELETE FROM pendientes WHERE id = ?", (fila_id,))
        enviados += 1
    db.commit()
    if enviados:
        print(f"[SYNC] {enviados} lecturas pendientes reenviadas")


# ---------------- MQTT ----------------
conectado = False


def publicar_estado(client):
    msg = firmar_plano(CLAVE_HMAC, {"dispositivo": DISPOSITIVO, "online": True, **actuadores})
    client.publish(T_ESTADO, msg, qos=1)


def on_connect(client, userdata, flags, reason_code, properties):
    global conectado
    if reason_code == 0:
        conectado = True
        print("[MQTT] conectado a AWS IoT Core (TLS mutuo con certificados)")
        client.subscribe(T_COMANDOS, qos=1)
        publicar_estado(client)
        reenviar_pendientes(client)
    else:
        print(f"[MQTT] conexión rechazada: {reason_code}")


def on_disconnect(client, userdata, flags, reason_code, properties):
    global conectado
    conectado = False
    print(f"[MQTT] desconectado ({reason_code}); reintentando...")


def on_message(client, userdata, msg):
    cmd = desempaquetar(CLAVE_HMAC, msg.payload.decode("utf-8", "replace"), exigir_reciente=True)
    if cmd is None:
        print("[SEGURIDAD] comando con firma inválida o expirado: descartado")
        return
    actuador, valor = cmd.get("actuador"), cmd.get("valor")
    if actuador not in PERMITIDOS or not isinstance(valor, bool):
        print(f"[SEGURIDAD] comando no permitido: {cmd}")
        return
    actuadores[actuador] = valor
    print(f"[ACTUADOR] {actuador} -> {'ENCENDIDO' if valor else 'APAGADO'}")
    publicar_estado(client)


# ---------------- Sensores virtuales ----------------
def leer_sensores():
    base = 21.0 if actuadores["ventilador"] else 25.0  # el ventilador enfría
    return {
        "temperatura": round(base + random.uniform(-2, 2), 1),
        "humedad": round(random.uniform(40, 60), 1),
        "movimiento": random.random() < 0.15,
    }


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    # TLS mutuo: AWS IoT Core valida nuestro certificado y nosotros el de Amazon
    client.tls_set(ca_certs=os.environ["IOT_ROOT_CA"],     # AmazonRootCA1.pem
                   certfile=os.environ["IOT_CERT"],        # xxxx-certificate.pem.crt
                   keyfile=os.environ["IOT_KEY"],          # xxxx-private.pem.key
                   cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    # Last Will (firmado): el broker lo publica si el nodo se cae sin avisar
    client.will_set(T_ESTADO, firmar_plano(CLAVE_HMAC, {"dispositivo": DISPOSITIVO, "online": False, **actuadores}),
                    qos=1)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.connect_async(BROKER, PUERTO, keepalive=60)
    client.loop_start()

    ultima, ciclo = None, 0
    try:
        while True:
            lectura = leer_sensores()
            ciclo += 1
            cambio = (ultima is None
                      or lectura["movimiento"] != ultima["movimiento"]
                      or abs(lectura["temperatura"] - ultima["temperatura"]) > UMBRAL
                      or abs(lectura["humedad"] - ultima["humedad"]) > UMBRAL)
            if cambio or ciclo % LATIDO_CICLOS == 0:
                msg = firmar_plano(CLAVE_HMAC, {"dispositivo": DISPOSITIVO, **lectura})
                if conectado and client.publish(T_TELEMETRIA, msg, qos=1).rc == mqtt.MQTT_ERR_SUCCESS:
                    print(f"[TX] {lectura}")
                else:
                    guardar_pendiente(T_TELEMETRIA, msg)
                ultima = lectura
            time.sleep(INTERVALO_S)
    except KeyboardInterrupt:
        print("Deteniendo nodo...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
