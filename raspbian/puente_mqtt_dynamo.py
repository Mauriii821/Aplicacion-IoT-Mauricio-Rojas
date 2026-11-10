"""
puente_mqtt_dynamo.py - Puente MQTT -> Amazon DynamoDB (BD no estructurada)
===========================================================================
Flujo de la guía: SENSOR RECIBE LECTURAS -> ENVÍA MENSAJES POR MQTT ->
RECIBE BROKER -> GUARDA EN DB NO ESTRUCTURADA -> RESCATA MENSAJES LA APP

- Se suscribe a la telemetría y al estado del nodo en el broker Mosquitto.
- Verifica la firma HMAC: los mensajes alterados se descartan.
- Guarda cada lectura como un documento en DynamoDB.
- Si AWS no responde (sin internet, credenciales vencidas), guarda en un
  buffer local SQLite y lo sincroniza automáticamente cuando vuelve.

Uso:  python3 puente_mqtt_dynamo.py
"""
import json
import os
import sqlite3
import ssl
import threading
import time

import paho.mqtt.client as mqtt
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

import dynamo
from seguridad import desempaquetar

load_dotenv()

CLAVE_HMAC = os.environ["HMAC_KEY"].encode()
DISPOSITIVO = os.getenv("DEVICE_ID", "raspbian01")

lock = threading.Lock()  # el hilo MQTT y el hilo principal comparten el buffer
buffer = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "buffer_dynamo.db"),
                         check_same_thread=False)
buffer.execute("CREATE TABLE IF NOT EXISTS pendientes (id INTEGER PRIMARY KEY, tipo TEXT, datos TEXT)")
buffer.commit()

GUARDAR = {"lectura": dynamo.guardar_lectura, "estado": dynamo.guardar_estado}


def guardar(tipo, datos):
    """Intenta guardar en DynamoDB; si falla la conexión, queda en el buffer local."""
    try:
        GUARDAR[tipo](datos)
        return True
    except (BotoCoreError, ClientError) as e:
        print(f"[DYNAMO] no disponible ({type(e).__name__}); guardado en buffer local")
        with lock:
            buffer.execute("INSERT INTO pendientes (tipo, datos) VALUES (?, ?)", (tipo, json.dumps(datos)))
            buffer.commit()
        return False


def sincronizar_buffer():
    with lock:
        filas = buffer.execute("SELECT id, tipo, datos FROM pendientes ORDER BY id LIMIT 100").fetchall()
    enviados = 0
    for fila_id, tipo, datos in filas:
        try:
            GUARDAR[tipo](json.loads(datos))
        except (BotoCoreError, ClientError):
            break  # AWS sigue sin responder; se reintenta en el próximo ciclo
        with lock:
            buffer.execute("DELETE FROM pendientes WHERE id = ?", (fila_id,))
            buffer.commit()
        enviados += 1
    if enviados:
        print(f"[SYNC] {enviados} registros pendientes enviados a DynamoDB")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[MQTT] puente conectado al broker con TLS")
        client.subscribe(f"iot/{DISPOSITIVO}/telemetria", qos=1)
        client.subscribe(f"iot/{DISPOSITIVO}/estado", qos=1)
    else:
        print(f"[MQTT] conexión rechazada: {reason_code}")


def on_message(client, userdata, msg):
    datos = desempaquetar(CLAVE_HMAC, msg.payload.decode("utf-8", "replace"))
    if datos is None:
        print("[SEGURIDAD] mensaje con firma inválida: descartado")
        return
    if msg.topic.endswith("/telemetria"):
        try:
            float(datos["temperatura"]), float(datos["humedad"]), int(datos["ts"]), str(datos["dispositivo"])
        except (KeyError, TypeError, ValueError):
            print(f"[VALIDACIÓN] lectura incompleta descartada: {datos}")
            return
        if guardar("lectura", datos):
            print(f"[DYNAMO] {datos['temperatura']} °C, {datos['humedad']} %, movimiento={datos.get('movimiento')}")
    else:
        if guardar("estado", datos):
            print(f"[ESTADO] led={datos.get('led')} ventilador={datos.get('ventilador')} online={datos.get('online')}")


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"puente-{os.getpid()}")
    # El puente usa su propio usuario MQTT (solo lectura según el ACL del broker)
    client.username_pw_set(os.getenv("PUENTE_MQTT_USER", "puente"), os.environ["PUENTE_MQTT_PASS"])
    client.tls_set(ca_certs=os.getenv("MQTT_CA") or None, cert_reqs=ssl.CERT_REQUIRED,
                   tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(os.environ["MQTT_HOST"], int(os.getenv("MQTT_PORT", "8883")), keepalive=60)
    client.loop_start()
    print("Puente MQTT -> DynamoDB activo. Ctrl+C para salir.")
    try:
        while True:
            time.sleep(15)
            sincronizar_buffer()
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()


if __name__ == "__main__":
    main()
