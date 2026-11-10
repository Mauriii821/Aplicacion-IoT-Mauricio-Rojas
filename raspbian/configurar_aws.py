"""
configurar_aws.py - Configura TODO lo necesario en AWS desde cero (un solo comando)
===================================================================================
1. Crea las tablas de DynamoDB (iot_lecturas, iot_estado, iot_usuarios).
2. Crea el objeto (thing) "raspbian01" en AWS IoT Core.
3. Crea el certificado X.509 + llave privada del dispositivo y los guarda en
   ~/aws-iot-certs (la llave queda con permisos 600; nunca se sube a GitHub).
4. Descarga el certificado raíz de Amazon (AmazonRootCA1.pem).
5. Crea la política de IoT con mínimo privilegio (solo su client id y sus 3 tópicos)
   y la asocia al certificado; asocia el certificado al objeto.
6. Crea las reglas de IoT Core que guardan los mensajes MQTT en DynamoDB.
7. Escribe en el .env el endpoint, las rutas de los certificados y una clave HMAC.

Se puede ejecutar varias veces sin duplicar nada.
Requisito: credenciales del Learner Lab en ~/.aws/credentials.

Uso:  python3 configurar_aws.py
"""
import json
import os
import re
import secrets
import shutil
import urllib.request

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

AQUI = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(AQUI, ".env")
if not os.path.exists(ENV):
    shutil.copy(os.path.join(AQUI, ".env.ejemplo"), ENV)
    os.chmod(ENV, 0o600)
load_dotenv(ENV)

import crear_reglas_iot  # noqa: E402  (después de cargar el .env)
import crear_tablas      # noqa: E402
from dynamo import REGION  # noqa: E402

DISPOSITIVO = os.getenv("DEVICE_ID", "raspbian01")
CLIENT_ID = os.getenv("IOT_CLIENT_ID", DISPOSITIVO)
POLITICA = f"politica_{DISPOSITIVO}"
CARPETA = os.path.expanduser("~/aws-iot-certs")
CERT = os.path.join(CARPETA, f"{DISPOSITIVO}-certificate.pem.crt")
LLAVE = os.path.join(CARPETA, f"{DISPOSITIVO}-private.pem.key")
RAIZ = os.path.join(CARPETA, "AmazonRootCA1.pem")
ARN_GUARDADO = os.path.join(CARPETA, f"{DISPOSITIVO}-certificate-arn.txt")
URL_RAIZ = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"


def paso(n, texto):
    print(f"\n=== {n}. {texto}")


def politica(cuenta):
    base = f"arn:aws:iot:{REGION}:{cuenta}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "iot:Connect", "Resource": f"{base}:client/{CLIENT_ID}"},
            {"Effect": "Allow", "Action": "iot:Publish", "Resource": [
                f"{base}:topic/iot/{DISPOSITIVO}/telemetria",
                f"{base}:topic/iot/{DISPOSITIVO}/estado"]},
            {"Effect": "Allow", "Action": "iot:Subscribe",
             "Resource": f"{base}:topicfilter/iot/{DISPOSITIVO}/comandos"},
            {"Effect": "Allow", "Action": "iot:Receive", "Resource": f"{base}:topic/iot/{DISPOSITIVO}/comandos"},
        ],
    }


def codigo(e):
    return e.response.get("Error", {}).get("Code", "")


def crear_objeto_y_certificado(iot):
    try:
        iot.create_thing(thingName=DISPOSITIVO)
        print(f"[OK] objeto '{DISPOSITIVO}' creado")
    except ClientError as e:
        if codigo(e) != "ResourceAlreadyExistsException":
            raise
        print(f"[--] objeto '{DISPOSITIVO}' ya existía")

    if os.path.exists(CERT) and os.path.exists(LLAVE) and os.path.exists(ARN_GUARDADO):
        print(f"[--] certificado ya existía en {CARPETA}")
        return open(ARN_GUARDADO).read().strip()

    os.makedirs(CARPETA, exist_ok=True)
    os.chmod(CARPETA, 0o700)
    r = iot.create_keys_and_certificate(setAsActive=True)
    with open(CERT, "w") as f:
        f.write(r["certificatePem"])
    with open(LLAVE, "w") as f:
        f.write(r["keyPair"]["PrivateKey"])
    os.chmod(LLAVE, 0o600)
    with open(ARN_GUARDADO, "w") as f:
        f.write(r["certificateArn"])
    print(f"[OK] certificado y llave privada guardados en {CARPETA}")
    return r["certificateArn"]


def descargar_raiz():
    if os.path.exists(RAIZ):
        print("[--] AmazonRootCA1.pem ya existía")
        return
    urllib.request.urlretrieve(URL_RAIZ, RAIZ)
    print("[OK] AmazonRootCA1.pem descargado")


def crear_politica(iot, cuenta, cert_arn):
    documento = json.dumps(politica(cuenta))
    try:
        iot.create_policy(policyName=POLITICA, policyDocument=documento)
        print(f"[OK] política '{POLITICA}' creada")
    except ClientError as e:
        if codigo(e) != "ResourceAlreadyExistsException":
            raise
        # Ya existe: se guarda una versión nueva (máximo 5; se borra la más antigua)
        versiones = iot.list_policy_versions(policyName=POLITICA)["policyVersions"]
        if len(versiones) >= 5:
            antigua = sorted((v for v in versiones if not v["isDefaultVersion"]),
                             key=lambda v: v["createDate"])[0]
            iot.delete_policy_version(policyName=POLITICA, policyVersionId=antigua["versionId"])
        iot.create_policy_version(policyName=POLITICA, policyDocument=documento, setAsDefault=True)
        print(f"[OK] política '{POLITICA}' actualizada")
    iot.attach_policy(policyName=POLITICA, target=cert_arn)
    iot.attach_thing_principal(thingName=DISPOSITIVO, principal=cert_arn)
    print("[OK] política asociada al certificado y certificado asociado al objeto")


def actualizar_env(valores):
    texto = open(ENV).read()
    for clave, valor in valores.items():
        linea = f"{clave}={valor}"
        if re.search(rf"^{clave}=", texto, flags=re.M):
            texto = re.sub(rf"^{clave}=.*$", lambda _m: linea, texto, flags=re.M)
        else:
            texto += f"\n{linea}\n"
    with open(ENV, "w") as f:
        f.write(texto)
    os.chmod(ENV, 0o600)


def main():
    try:
        cuenta = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    except (NoCredentialsError, ClientError) as e:
        raise SystemExit(f"No hay credenciales válidas de AWS ({e}).\n"
                         "Copia las del Learner Lab (AWS Details -> AWS CLI: Show) en ~/.aws/credentials")
    print(f"Cuenta AWS: {cuenta} · Región: {REGION}")
    iot = boto3.client("iot", region_name=REGION)

    paso(1, "Tablas de DynamoDB")
    crear_tablas.main()
    paso(2, "Objeto y certificado en AWS IoT Core")
    cert_arn = crear_objeto_y_certificado(iot)
    paso(3, "Certificado raíz de Amazon")
    descargar_raiz()
    paso(4, "Política de seguridad (mínimo privilegio)")
    crear_politica(iot, cuenta, cert_arn)
    paso(5, "Reglas IoT Core -> DynamoDB")
    endpoint = crear_reglas_iot.main(mostrar=False)

    paso(6, "Archivo .env")
    valores = {"IOT_ENDPOINT": endpoint, "IOT_ROOT_CA": RAIZ, "IOT_CERT": CERT,
               "IOT_KEY": LLAVE, "IOT_CLIENT_ID": CLIENT_ID, "DEVICE_ID": DISPOSITIVO}
    # Se lee del archivo (no de la memoria) para no cambiar nunca una clave ya creada
    encontrada = re.search(r"^HMAC_KEY=(.*)$", open(ENV).read(), flags=re.M)
    hmac_actual = encontrada.group(1).strip() if encontrada else ""
    if not hmac_actual or hmac_actual.startswith("pega_aqui"):
        valores["HMAC_KEY"] = secrets.token_hex(32)
        print("[OK] clave HMAC generada")
    actualizar_env(valores)
    print(f"[OK] {ENV} actualizado")

    print("\nTodo listo. Siguientes pasos:")
    print("  python3 crear_usuario.py")
    print("  ./crear_certs_api.sh <IP_DE_LA_RASPBERRY>")
    print("  python3 nodo_mqtt.py     y en otra terminal:   python3 api_app.py")


if __name__ == "__main__":
    main()
