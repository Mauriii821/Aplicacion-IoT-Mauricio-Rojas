"""
crear_usuario.py - Crea (o cambia la contraseña de) un usuario de la app.
La contraseña se guarda con hash PBKDF2-SHA256 con sal, nunca en texto plano.
Uso:  python3 crear_usuario.py
"""
import getpass

from werkzeug.security import generate_password_hash

from dynamo import T_USUARIOS, tabla

usuario = input("Usuario: ").strip()
if not usuario or len(usuario) > 50:
    raise SystemExit("Usuario inválido")
clave = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
if len(clave) < 8 or clave != getpass.getpass("Repite la contraseña: "):
    raise SystemExit("La contraseña es muy corta o no coincide")

tabla(T_USUARIOS).put_item(Item={
    "usuario": usuario,
    "password": generate_password_hash(clave, method="pbkdf2:sha256:600000"),
})
print(f"[OK] usuario '{usuario}' guardado en DynamoDB")
