"""
seguridad.py - Integridad de los mensajes (ISO 27000)

Dos formatos firmados con HMAC-SHA256:

1) Telemetría y estado (van a DynamoDB mediante una regla de AWS IoT Core):
   {"dispositivo": ..., "ts": ..., "temperatura": ..., ..., "data": "<json firmado>", "firma": "<hmac>"}
   Los campos sueltos permiten que la regla los guarde como columnas;
   "data" es el texto exacto que se firmó, para poder verificarlo después.

2) Comandos para los actuadores:
   {"data": "<json firmado>", "firma": "<hmac>"}
   Además se rechazan si tienen más de 30 s (anti-repetición).
"""
import hashlib
import hmac
import json
import time

VENTANA_SEGUNDOS = 30


def _firma(clave: bytes, texto: str) -> str:
    return hmac.new(clave, texto.encode("utf-8"), hashlib.sha256).hexdigest()


def _texto(datos: dict) -> str:
    return json.dumps(datos, sort_keys=True, separators=(",", ":"))


def firmar_plano(clave: bytes, datos: dict) -> str:
    """Formato 1: campos sueltos + data + firma (para la regla de IoT Core)."""
    datos = dict(datos)
    datos.setdefault("ts", int(time.time()))
    texto = _texto(datos)
    return json.dumps({**datos, "data": texto, "firma": _firma(clave, texto)})


def verificar_plano(clave: bytes, item: dict) -> bool:
    """True si el registro (leído de DynamoDB) no fue alterado."""
    texto, firma = item.get("data"), item.get("firma")
    if not isinstance(texto, str) or not isinstance(firma, str):
        return False
    return hmac.compare_digest(_firma(clave, texto), firma)


def empaquetar(clave: bytes, datos: dict) -> str:
    """Formato 2: comandos."""
    datos = dict(datos)
    datos.setdefault("ts", int(time.time()))
    texto = _texto(datos)
    return json.dumps({"data": texto, "firma": _firma(clave, texto)})


def desempaquetar(clave: bytes, crudo, exigir_reciente: bool = False):
    """Devuelve el dict si la firma es válida, o None si no lo es."""
    try:
        sobre = json.loads(crudo)
        texto, firma = sobre["data"], sobre["firma"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(texto, str) or not hmac.compare_digest(_firma(clave, texto), str(firma)):
        return None
    datos = json.loads(texto)
    if exigir_reciente and abs(time.time() - datos.get("ts", 0)) > VENTANA_SEGUNDOS:
        return None
    return datos
