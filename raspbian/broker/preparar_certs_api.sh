#!/usr/bin/env bash
# Copia el certificado del broker para que la API HTTPS (api_app.py) lo use.
# Uso:  sudo ./preparar_certs_api.sh
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Ejecuta con sudo"; exit 1; fi
DIR="$(cd "$(dirname "$0")/.." && pwd)/certs_api"
USUARIO="${SUDO_USER:-pi}"
mkdir -p "$DIR"
cp /etc/mosquitto/certs/server.crt /etc/mosquitto/certs/server.key "$DIR/"
chown -R "$USUARIO:$USUARIO" "$DIR"
chmod 700 "$DIR"; chmod 600 "$DIR/server.key"
echo "Certificados para la API copiados en $DIR"
