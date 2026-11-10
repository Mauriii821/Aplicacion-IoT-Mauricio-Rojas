#!/usr/bin/env bash
# Instala y configura Mosquitto con TLS, usuarios y ACL en la VM Raspbian.
# Uso:   sudo ./instalar_broker.sh <IP_DE_LA_VM>
# Ej.:   sudo ./instalar_broker.sh 192.168.1.160
# La IP es la que usará la app para conectarse (ver con: hostname -I)
set -euo pipefail

IP="${1:?Uso: sudo ./instalar_broker.sh <IP_DE_LA_VM>}"
DIR="$(cd "$(dirname "$0")" && pwd)"
CERTS=/etc/mosquitto/certs

if [ "$(id -u)" -ne 0 ]; then echo "Ejecuta con sudo"; exit 1; fi

echo "==> Actualizando lista de paquetes..."
apt-get update || echo "AVISO: apt-get update tuvo errores (revisa la fecha/hora de la VM y el internet)"

echo "==> Instalando Mosquitto..."
# openssl ya viene instalado en Raspbian; solo se instala si falta
PAQUETES="mosquitto mosquitto-clients"
command -v openssl >/dev/null 2>&1 || PAQUETES="$PAQUETES openssl"
apt-get install -y --no-upgrade $PAQUETES || apt-get install -y --fix-missing --no-upgrade $PAQUETES

echo "==> Creando certificados TLS (CA propia + certificado del broker para $IP)..."
mkdir -p "$CERTS"
cd "$CERTS"
if [ ! -f ca.key ]; then
  openssl req -x509 -new -nodes -newkey rsa:2048 -sha256 -days 825 \
    -keyout ca.key -out ca.crt -subj "/CN=CA IoT TI3042" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
fi
openssl req -new -nodes -newkey rsa:2048 -keyout server.key -out server.csr -subj "/CN=$IP"
cat > server.ext <<EXT
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:$IP,IP:127.0.0.1,DNS:localhost
EXT
openssl x509 -req -sha256 -days 825 -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -extfile server.ext
rm -f server.csr server.ext
chown mosquitto:mosquitto server.key server.crt
chmod 600 server.key ca.key
chmod 644 ca.crt server.crt

echo "==> Configuración, ACL y usuarios..."
cp "$DIR/mosquitto_iot.conf" /etc/mosquitto/conf.d/iot.conf
cp "$DIR/acl" /etc/mosquitto/acl
if [ ! -f /etc/mosquitto/passwd ]; then
  touch /etc/mosquitto/passwd
fi
for usuario in raspbian01 puente app_android; do
  echo "--- Contraseña para el usuario MQTT '$usuario':"
  mosquitto_passwd /etc/mosquitto/passwd "$usuario"
done
chown mosquitto:mosquitto /etc/mosquitto/passwd /etc/mosquitto/acl
chmod 600 /etc/mosquitto/passwd /etc/mosquitto/acl

echo "==> Reiniciando broker..."
systemctl enable mosquitto >/dev/null
systemctl restart mosquitto
sleep 1
systemctl --no-pager --lines=5 status mosquitto || true

# Copia del certificado de la CA para pasarlo a la app Android
DESTINO="/home/${SUDO_USER:-pi}/ca_mosquitto.crt"
cp "$CERTS/ca.crt" "$DESTINO" && chown "${SUDO_USER:-pi}" "$DESTINO" || true

echo
echo "Broker listo en ssl://$IP:8883"
echo "Copia $DESTINO a la app: app/src/main/assets/ca_mosquitto.crt"
echo "Prueba rápida (en otra terminal):"
echo "  mosquitto_sub -h localhost -p 8883 --cafile $CERTS/ca.crt -u puente -P <clave> -t 'iot/#' -v"
