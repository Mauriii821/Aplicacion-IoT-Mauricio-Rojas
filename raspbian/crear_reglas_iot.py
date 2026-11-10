"""
crear_reglas_iot.py - Crea las reglas de AWS IoT Core que guardan los mensajes
MQTT en DynamoDB (la "BD no estructurada" de la guía).
Normalmente lo ejecuta configurar_aws.py.

  iot/<dispositivo>/telemetria  ->  tabla iot_lecturas
  iot/<dispositivo>/estado      ->  tabla iot_estado

En AWS Academy (Learner Lab) las reglas usan el rol "LabRole".
Al final muestra el endpoint de IoT Core para ponerlo en el .env (IOT_ENDPOINT).

Uso:  python3 crear_reglas_iot.py
"""
import os

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from dynamo import REGION, T_ESTADO, T_LECTURAS

load_dotenv()
DISPOSITIVO = os.getenv("DEVICE_ID", "raspbian01")


def main(mostrar=True):
    cuenta = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    rol = os.getenv("IOT_RULE_ROLE_ARN") or f"arn:aws:iam::{cuenta}:role/LabRole"
    iot = boto3.client("iot", region_name=REGION)

    REGLAS = [
        (f"guardar_lecturas_{DISPOSITIVO}", f"iot/{DISPOSITIVO}/telemetria", T_LECTURAS),
        (f"guardar_estado_{DISPOSITIVO}", f"iot/{DISPOSITIVO}/estado", T_ESTADO),
    ]

    for nombre, topico, tabla in REGLAS:
        regla = {
            "sql": f"SELECT * FROM '{topico}'",
            "awsIotSqlVersion": "2016-03-23",
            "ruleDisabled": False,
            "description": f"Guarda los mensajes de {topico} en DynamoDB ({tabla})",
            "actions": [{"dynamoDBv2": {"roleArn": rol, "putItem": {"tableName": tabla}}}],
        }
        try:
            iot.create_topic_rule(ruleName=nombre, topicRulePayload=regla)
            print(f"[OK] regla {nombre}: {topico} -> {tabla}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
                iot.replace_topic_rule(ruleName=nombre, topicRulePayload=regla)
                print(f"[OK] regla {nombre} actualizada")
            else:
                raise

    endpoint = iot.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
    print(f"[OK] rol usado por las reglas: {rol}")
    if mostrar:
        print(f"Pon esto en tu .env:\nIOT_ENDPOINT={endpoint}")
    return endpoint


if __name__ == "__main__":
    main()
