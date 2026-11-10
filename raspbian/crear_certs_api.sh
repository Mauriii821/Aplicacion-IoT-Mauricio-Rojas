#!/usr/bin/env bash
# Crea el certificado HTTPS de la API (api_app.py), firmado por una CA propia.
# Uso:   ./crear_certs_api.sh <IP_DE_LA_RASPBERRY>
# Ej.:   ./crear_certs_api.sh 172.20.10.2
# Si la IP cambia, vuelve a ejecutarlo: la CA se mantiene, así que la app no cambia.
set -euo pipefail
IP="${1:?Uso: ./crear_certs_api.sh <IP_DE_LA_RASPBERRY>}"
DIR="$(cd "$(dirname "$0")" && pwd)/certs_api"
mkdir -p "$DIR" && chmod 700 "$DIR" && cd "$DIR"

if [ ! -f ca.key ]; then
  openssl req -x509 -new -nodes -newkey rsa:2048 -sha256 -days 825 \
    -keyout ca.key -out ca.crt -subj "/CN=CA IoT TI3042" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  echo "CA creada"
fi
openssl req -new -nodes -newkey rsa:2048 -keyout server.key -out server.csr -subj "/CN=$IP" 2>/dev/null
cat > server.ext <<EXT
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:$IP,IP:127.0.0.1,DNS:localhost
EXT
openssl x509 -req -sha256 -days 825 -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -extfile server.ext 2>/dev/null
rm -f server.csr server.ext
chmod 600 ca.key server.key
cp ca.crt "$HOME/ca_api.crt"

echo "Certificado HTTPS creado para $IP"
echo "Copia ~/ca_api.crt a la app:  app/src/main/res/raw/ca_api.crt"
