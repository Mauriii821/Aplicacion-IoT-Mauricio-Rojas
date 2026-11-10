"""
crear_tablas.py - Crea las 3 tablas de DynamoDB del proyecto.
Normalmente lo ejecuta configurar_aws.py. Uso directo:  python3 crear_tablas.py
"""
from botocore.exceptions import ClientError

from dynamo import T_ESTADO, T_LECTURAS, T_USUARIOS, recurso

TABLAS = [
    (T_LECTURAS, [("dispositivo", "S", "HASH"), ("ts", "N", "RANGE")]),
    (T_ESTADO, [("dispositivo", "S", "HASH")]),
    (T_USUARIOS, [("usuario", "S", "HASH")]),
]


def main():
    db = recurso()
    for nombre, claves in TABLAS:
        try:
            t = db.create_table(
                TableName=nombre,
                KeySchema=[{"AttributeName": n, "KeyType": k} for n, _, k in claves],
                AttributeDefinitions=[{"AttributeName": n, "AttributeType": t} for n, t, _ in claves],
                BillingMode="PAY_PER_REQUEST",  # bajo demanda: sin costo fijo
            )
            t.wait_until_exists()
            print(f"[OK] tabla {nombre} creada")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                print(f"[--] tabla {nombre} ya existía")
            else:
                raise


if __name__ == "__main__":
    main()
