"""
seguridad.py - Funciones compartidas de integridad (ISO 27000, control A.8.24 / A.8.20)

Cada mensaje MQTT viaja así:
    {"data": "<json en texto>", "firma": "<HMAC-SHA256 de data>"}

Se firma el TEXTO exacto de "data", así Python y Java (la app) calculan
la misma firma sin depender del orden de las claves del JSON.
"""
import hashlib
import hmac
import json
import time

VENTANA_SEGUNDOS = 30  # un comando con ts más antiguo se rechaza (anti-repetición)


def _firma(clave: bytes, texto: str) -> str:
    return hmac.new(clave, texto.encode("utf-8"), hashlib.sha256).hexdigest()


def empaquetar(clave: bytes, datos: dict) -> str:
    datos = dict(datos)
    datos.setdefault("ts", int(time.time()))
    texto = json.dumps(datos, separators=(",", ":"))
    return json.dumps({"data": texto, "firma": _firma(clave, texto)})


def desempaquetar(clave: bytes, crudo, exigir_reciente: bool = False):
    """Devuelve el dict si la firma es válida, o None si no lo es."""
    try:
        sobre = json.loads(crudo)
        texto, firma = sobre["data"], sobre["firma"]
    except (ValueError, KeyError, TypeError):
        return None
    if not hmac.compare_digest(_firma(clave, texto), str(firma)):
        return None
    datos = json.loads(texto)
    if exigir_reciente and abs(time.time() - datos.get("ts", 0)) > VENTANA_SEGUNDOS:
        return None
    return datos
