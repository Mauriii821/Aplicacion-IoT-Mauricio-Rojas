"""
api_app.py - API HTTPS para la app Android (reemplaza a los archivos PHP)
=======================================================================
La app "rescata" los datos guardados en DynamoDB a través de esta API.

  POST /login   usuario, password  -> {"status": "Exito", "token": "..."}
  GET  /datos?dispositivo=raspbian01  (cabecera Authorization: Bearer <token>)
       -> última lectura, historial (20) y estado de los actuadores

Seguridad (ISO 27000):
- HTTPS con el mismo certificado del broker (firmado por nuestra CA).
- Contraseñas guardadas con hash PBKDF2 y comparadas en tiempo constante.
- Token de sesión aleatorio que vence en 12 horas; /datos lo exige.
- Bloqueo de 60 s tras 5 intentos fallidos desde la misma IP (fuerza bruta).
- Validación de entradas y errores sin detalles internos.

Uso:  python3 api_app.py
"""
import os
import re
import secrets
import time

from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash

import dynamo

load_dotenv()

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


if __name__ == "__main__":
    cert = os.getenv("API_CERT", "certs_api/server.crt")
    llave = os.getenv("API_KEY", "certs_api/server.key")
    puerto = int(os.getenv("API_PORT", "5000"))
    print(f"API HTTPS en https://0.0.0.0:{puerto}")
    app.run(host="0.0.0.0", port=puerto, ssl_context=(cert, llave), threaded=True)
