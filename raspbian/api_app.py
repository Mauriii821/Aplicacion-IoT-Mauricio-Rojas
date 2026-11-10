"""
api_app.py - API HTTPS para la app Android
==========================================
La app "rescata" los mensajes guardados en DynamoDB y envía comandos a
los actuadores a través de esta API (que los publica en AWS IoT Core).

  POST /login    usuario, password  -> {"status": "Exito", "token": "..."}
  GET  /datos?dispositivo=raspbian01   -> última lectura, historial y actuadores
  POST /comando  actuador, valor       -> publica el comando firmado en IoT Core
  (/datos y /comando exigen la cabecera  Authorization: Bearer <token>)

Seguridad (ISO 27000):
- HTTPS con el mismo certificado del broker (firmado por nuestra CA).
- Contraseñas guardadas con hash PBKDF2 y comparadas en tiempo constante.
- Token de sesión aleatorio que vence en 12 horas; /datos lo exige.
- Bloqueo de 60 s tras 5 intentos fallidos desde la misma IP (fuerza bruta).
- Cada lectura de DynamoDB se verifica con su firma HMAC ("verificado").
- Solo se aceptan comandos para actuadores conocidos y valores booleanos.
- Validación de entradas y errores sin detalles internos.

Uso:  python3 api_app.py
"""
import json
import os
import re
import secrets
import time

from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash

import dynamo
from seguridad import empaquetar, verificar_plano

load_dotenv()

CLAVE_HMAC = os.environ["HMAC_KEY"].encode()
ACTUADORES = {"led", "ventilador"}
CAMPOS_LECTURA = ("dispositivo", "ts", "temperatura", "humedad", "movimiento")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024  # peticiones pequeñas

DURACION_TOKEN = 12 * 3600
MAX_FALLOS, BLOQUEO_S = 5, 60
tokens = {}   # token -> (usuario, vence)
fallos = {}   # ip -> (cantidad, bloqueado_hasta)
PATRON_DISPOSITIVO = re.compile(r"^[A-Za-z0-9_-]{1,30}$")
# Hash falso para que un usuario inexistente tarde lo mismo que uno real
HASH_FALSO = "pbkdf2:sha256:600000$x$" + "0" * 64


@app.after_request
def cabeceras_seguras(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    return resp


@app.post("/login")
def login():
    ip = request.remote_addr
    cantidad, hasta = fallos.get(ip, (0, 0))
    if time.time() < hasta:
        return jsonify(status="Bloqueado", espera=int(hasta - time.time())), 429

    usuario = (request.form.get("usuario") or "").strip()
    clave = request.form.get("password") or ""
    if not usuario or not clave or len(usuario) > 50 or len(clave) > 128:
        return jsonify(status="Fallo"), 400

    try:
        item = dynamo.obtener_usuario(usuario)
    except (BotoCoreError, ClientError):
        return jsonify(status="Servicio no disponible"), 503

    if check_password_hash(item["password"] if item else HASH_FALSO, clave) and item:
        fallos.pop(ip, None)
        token = secrets.token_urlsafe(32)
        tokens[token] = (usuario, time.time() + DURACION_TOKEN)
        print(f"[LOGIN] '{usuario}' inició sesión desde {ip}")
        return jsonify(status="Exito", token=token, expira_en=DURACION_TOKEN)

    cantidad += 1
    fallos[ip] = (0, time.time() + BLOQUEO_S) if cantidad >= MAX_FALLOS else (cantidad, 0)
    print(f"[LOGIN] intento fallido para '{usuario}' desde {ip} ({cantidad})")
    return jsonify(status="Fallo"), 401


def usuario_autenticado():
    cabecera = request.headers.get("Authorization", "")
    if not cabecera.startswith("Bearer "):
        return None
    sesion = tokens.get(cabecera[7:])
    if not sesion or time.time() > sesion[1]:
        tokens.pop(cabecera[7:], None)
        return None
    return sesion[0]


@app.get("/datos")
def datos():
    if not usuario_autenticado():
        return jsonify(error="No autorizado"), 401
    dispositivo = request.args.get("dispositivo", "raspbian01")
    if not PATRON_DISPOSITIVO.match(dispositivo):
        return jsonify(error="Dispositivo inválido"), 400
    try:
        historial = dynamo.ultimas_lecturas(dispositivo)
        est = dynamo.estado(dispositivo)
    except (BotoCoreError, ClientError):
        return jsonify(error="Servicio no disponible"), 503

    historial = [limpiar(item) for item in historial]
    ultima = historial[0] if historial else {}
    return jsonify(
        temperatura=ultima.get("temperatura", 0),
        humedad=ultima.get("humedad", 0),
        movimiento=ultima.get("movimiento", False),
        ts=ultima.get("ts", 0),
        historial=historial,
        actuadores={
            "led": bool(est.get("led", False)),
            "ventilador": bool(est.get("ventilador", False)),
            "online": bool(est.get("online", False)),
        },
    )


def limpiar(item):
    """
    Devuelve la lectura con los valores ORIGINALES firmados por el dispositivo
    e indica si el registro de DynamoDB está íntegro ("verificado").
    Si alguien modifica una columna en la base de datos, la firma no calza.
    """
    columnas = {k: item[k] for k in CAMPOS_LECTURA if k in item}
    if not verificar_plano(CLAVE_HMAC, item):
        print(f"[SEGURIDAD] registro sin firma válida en DynamoDB: ts={item.get('ts')}")
        return {**columnas, "verificado": False}
    firmado = json.loads(item["data"])
    original = {k: firmado[k] for k in CAMPOS_LECTURA if k in firmado}
    integro = all(columnas.get(k) == v for k, v in original.items())
    if not integro:
        print(f"[SEGURIDAD] registro alterado en DynamoDB: ts={item.get('ts')}")
    return {**original, "verificado": integro}


@app.post("/comando")
def comando():
    usuario = usuario_autenticado()
    if not usuario:
        return jsonify(error="No autorizado"), 401
    actuador = request.form.get("actuador", "")
    valor = request.form.get("valor", "")
    dispositivo = request.form.get("dispositivo", "raspbian01")
    if actuador not in ACTUADORES or valor not in ("true", "false") or not PATRON_DISPOSITIVO.match(dispositivo):
        return jsonify(error="Comando inválido"), 400
    mensaje = empaquetar(CLAVE_HMAC, {"actuador": actuador, "valor": valor == "true"})
    try:
        dynamo.publicar_iot(f"iot/{dispositivo}/comandos", mensaje)
    except (BotoCoreError, ClientError):
        return jsonify(error="Servicio no disponible"), 503
    print(f"[COMANDO] {usuario}: {actuador} -> {valor}")
    return jsonify(status="Enviado")


if __name__ == "__main__":
    cert = os.getenv("API_CERT", "certs_api/server.crt")
    llave = os.getenv("API_KEY", "certs_api/server.key")
    puerto = int(os.getenv("API_PORT", "5000"))
    print(f"API HTTPS en https://0.0.0.0:{puerto}")
    app.run(host="0.0.0.0", port=puerto, ssl_context=(cert, llave), threaded=True)
