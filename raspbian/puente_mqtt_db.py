"""
puente_mqtt_db.py - Puente MQTT -> base de datos (AWS RDS MySQL)
================================================================
Flujo de la guía: sensor -> MQTT -> broker -> BD -> la app rescata los datos.

- Se suscribe a la telemetría y al estado del nodo.
- Verifica la firma HMAC: los mensajes alterados se descartan.
- Guarda las lecturas y el estado de los actuadores con consultas
  parametrizadas (sin inyección SQL) y conexión TLS a RDS si hay certificado.
- Si la BD no responde, guarda en un buffer local y reintenta (continuidad).

Uso:  python3 puente_mqtt_db.py
"""
import json
import os
import sqlite3
import ssl
import threading
import time

import paho.mqtt.client as mqtt
import pymysql
from dotenv import load_dotenv

from seguridad import desempaquetar

load_dotenv()

CLAVE_HMAC = os.environ["HMAC_KEY"].encode()
DISPOSITIVO = os.getenv("DEVICE_ID", "raspbian01")


# ---------------- Base de datos ----------------
def conectar_bd():
    ca = os.getenv("DB_SSL_CA")  # ej: global-bundle.pem de AWS RDS
    return pymysql.connect(
        host=os.environ["DB_HOST"], user=os.environ["DB_USER"], password=os.environ["DB_PASS"],
        database=os.getenv("DB_NAME", "iot_db"), autocommit=True, connect_timeout=5,
        ssl={"ca": ca} if ca else None,
    )


bd = None
lock = threading.RLock()  # el hilo MQTT y el hilo principal comparten la BD
buffer = sqlite3.connect(os.path.join(os.path.dirname(__file__), "buffer_bd.db"), check_same_thread=False)
buffer.execute("CREATE TABLE IF NOT EXISTS pendientes (id INTEGER PRIMARY KEY, sql TEXT, params TEXT)")
buffer.commit()

SQL_LECTURA = ("INSERT INTO registros_clima (dispositivo, temperatura, humedad, movimiento, fecha) "
               "VALUES (%s, %s, %s, %s, FROM_UNIXTIME(%s))")
SQL_ESTADO = ("INSERT INTO estado_actuadores (dispositivo, led, ventilador, online) VALUES (%s, %s, %s, %s) "
              "ON DUPLICATE KEY UPDATE led=VALUES(led), ventilador=VALUES(ventilador), "
              "online=VALUES(online), actualizado=CURRENT_TIMESTAMP")


def ejecutar(sql, params):
    """Ejecuta en RDS; si falla la conexión, guarda localmente para reintentar."""
    with lock:
        return _ejecutar(sql, params)


def _ejecutar(sql, params):
    global bd
    try:
        if bd is None or not bd.open:
            bd = conectar_bd()
        with bd.cursor() as cur:
            cur.execute(sql, params)
        return True
    except (pymysql.ProgrammingError, pymysql.IntegrityError, pymysql.DataError) as e:
        print(f"[BD] error en los datos, registro descartado: {e}")
        return True  # no tiene sentido reintentarlo
    except pymysql.MySQLError as e:
        print(f"[BD] sin conexión ({e.args[0] if e.args else e}); guardado en buffer local")
        bd = None
        buffer.execute("INSERT INTO pendientes (sql, params) VALUES (?, ?)", (sql, json.dumps(params)))
        buffer.commit()
        return False


def sincronizar_buffer():
    with lock:
        _sincronizar()


def _sincronizar():
    filas = buffer.execute("SELECT id, sql, params FROM pendientes ORDER BY id LIMIT 200").fetchall()
    for fila_id, sql, params in filas:
        buffer.execute("DELETE FROM pendientes WHERE id = ?", (fila_id,))
        buffer.commit()
        if not _ejecutar(sql, json.loads(params)):
            break  # ejecutar() lo volvió a guardar; se reintenta después
    else:
        if filas:
            print(f"[SYNC] {len(filas)} registros pendientes enviados a la BD")


# ---------------- MQTT ----------------
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[MQTT] puente conectado con TLS")
        client.subscribe(f"iot/{DISPOSITIVO}/telemetria", qos=1)
        client.subscribe(f"iot/{DISPOSITIVO}/estado", qos=1)


def on_message(client, userdata, msg):
    datos = desempaquetar(CLAVE_HMAC, msg.payload.decode("utf-8", "replace"))
    if datos is None:
        print("[SEGURIDAD] mensaje con firma inválida: descartado")
        return
    if msg.topic.endswith("/telemetria"):
        try:
            params = [datos["dispositivo"], float(datos["temperatura"]), float(datos["humedad"]),
                      1 if datos.get("movimiento") else 0, int(datos["ts"])]
        except (KeyError, TypeError, ValueError):
            print(f"[VALIDACIÓN] lectura incompleta: {datos}")
            return
        if ejecutar(SQL_LECTURA, params):
            print(f"[BD] {params[1]} °C, {params[2]} %, movimiento={bool(params[3])}")
    else:
        ejecutar(SQL_ESTADO, [datos.get("dispositivo", DISPOSITIVO), int(bool(datos.get("led"))),
                              int(bool(datos.get("ventilador"))), int(bool(datos.get("online")))])
        print(f"[ESTADO] {datos}")


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
    print("Puente activo. Ctrl+C para salir.")
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
