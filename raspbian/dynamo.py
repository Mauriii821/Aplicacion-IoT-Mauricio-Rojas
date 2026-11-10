"""
dynamo.py - Acceso a Amazon DynamoDB (base de datos NoSQL / no estructurada)

Tablas (modo bajo demanda, se crean con crear_tablas.py):
  iot_lecturas  clave: dispositivo (texto) + ts (número)  -> historial de sensores
  iot_estado    clave: dispositivo                        -> último estado de actuadores
  iot_usuarios  clave: usuario                            -> usuarios de la app (hash de contraseña)

Las credenciales de AWS NO van en el código: boto3 las lee de ~/.aws/credentials
(se crean con "aws configure" o copiando las del AWS Academy Learner Lab).
"""
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
T_LECTURAS = os.getenv("DYNAMO_LECTURAS", "iot_lecturas")
T_ESTADO = os.getenv("DYNAMO_ESTADO", "iot_estado")
T_USUARIOS = os.getenv("DYNAMO_USUARIOS", "iot_usuarios")

_recurso = None


def recurso():
    global _recurso
    if _recurso is None:
        # Todas las llamadas a AWS van por HTTPS (cifrado en tránsito)
        _recurso = boto3.resource("dynamodb", region_name=REGION)
    return _recurso


def tabla(nombre):
    return recurso().Table(nombre)


def a_decimal(valor):
    """DynamoDB no acepta float: se guarda como Decimal."""
    return Decimal(str(round(float(valor), 2)))


def a_json(item):
    """Convierte Decimal de DynamoDB a tipos normales para responder JSON."""
    salida = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            salida[k] = int(v) if v == v.to_integral_value() else float(v)
        else:
            salida[k] = v
    return salida


def guardar_lectura(datos):
    tabla(T_LECTURAS).put_item(Item={
        "dispositivo": str(datos["dispositivo"]),
        "ts": int(datos["ts"]),
        "temperatura": a_decimal(datos["temperatura"]),
        "humedad": a_decimal(datos["humedad"]),
        "movimiento": bool(datos.get("movimiento", False)),
    })


def guardar_estado(datos):
    tabla(T_ESTADO).put_item(Item={
        "dispositivo": str(datos.get("dispositivo", "raspbian01")),
        "led": bool(datos.get("led", False)),
        "ventilador": bool(datos.get("ventilador", False)),
        "online": bool(datos.get("online", False)),
        "ts": int(datos.get("ts", 0)),
    })


def ultimas_lecturas(dispositivo, cantidad=20):
    resp = tabla(T_LECTURAS).query(
        KeyConditionExpression=Key("dispositivo").eq(dispositivo),
        ScanIndexForward=False,  # de la más nueva a la más antigua
        Limit=cantidad,
    )
    return [a_json(i) for i in resp.get("Items", [])]


def estado(dispositivo):
    item = tabla(T_ESTADO).get_item(Key={"dispositivo": dispositivo}).get("Item")
    return a_json(item) if item else {}


def obtener_usuario(usuario):
    return tabla(T_USUARIOS).get_item(Key={"usuario": usuario}).get("Item")
