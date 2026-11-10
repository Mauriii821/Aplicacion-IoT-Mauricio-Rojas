# Aplicación IoT – Mauricio Rojas (TI3042, Unidad 3)

Prototipo IoT con una app Android que **monitorea sensores y controla actuadores** de forma inalámbrica y segura.
Sigue el flujo de la guía: **sensor → MQTT → broker → base de datos no estructurada (Amazon DynamoDB) → la app rescata los datos**.

## Arquitectura

```
                         VM Raspbian (172.20.10.2)
 ┌──────────────────────────────────────────────────────────────────────┐
 │  nodo_mqtt.py ──MQTT TLS──► Mosquitto ──MQTT TLS──► puente_mqtt_dynamo.py ──HTTPS──► Amazon DynamoDB
 │  (sensores y      ◄─comandos─  (broker   │                                                  │
 │   actuadores)                  :8883)    │                                                  │
 │                                          │          api_app.py (HTTPS :5000) ◄──────────────┘
 └──────────────────────────────────────────┼──────────────────┼───────────────────────────────┘
                                   MQTT TLS │ tiempo real      │ HTTPS: login + historial
                                            ▼                  ▼
                                         App Android (Java)
```

| Componente | Equivalente en Packet Tracer |
|---|---|
| `nodo_mqtt.py` | SBC-PT DEVICE1 (humedad/temperatura) y DEVICE2 (movimiento) |
| Mosquitto en la VM | SBC-PT BROKER |
| DynamoDB | Base de datos no estructurada (AWS DYNAMO DB del diagrama) |
| App Android | TEST1 / TEST2 |

Tópicos MQTT: `iot/raspbian01/telemetria`, `iot/raspbian01/comandos`, `iot/raspbian01/estado`.

## Cómo cumple la guía de la Unidad 3

| Requisito | Implementación |
|---|---|
| App envía instrucciones al microcontrolador | Switches LED/ventilador → `MqttManager.enviarComando()` → `nodo_mqtt.py` |
| App recibe datos de sensores | Telemetría MQTT en tiempo real (`DashboardActivity.onLectura`) |
| Reconexión automática | Paho `setAutomaticReconnect` + reintentos 2-4-8…60 s en la app; `reconnect_delay_set` en Python |
| Consumo de energía | App: desconecta MQTT y HTTPS en `onStop`, keep-alive 60 s. Nodo: intervalo configurable y solo publica si los valores cambian |
| Compatibilidad Android | minSdk 28 (Android 9) a targetSdk 36; probar en 2 emuladores con distinta API |
| Plan de contingencia | Si falla MQTT → la app consulta DynamoDB vía API cada 15 s → si falla todo, datos guardados en el teléfono. Last Will avisa si el nodo se cae |
| Almacenamiento temporal y sincronización | App: `CacheLocal`. Nodo: SQLite `buffer_offline.db`. Puente: SQLite `buffer_dynamo.db` si AWS no responde; se sincroniza solo |
| Sensor → MQTT → broker → **BD no estructurada** → app | `nodo_mqtt.py` → Mosquitto → `puente_mqtt_dynamo.py` → **DynamoDB** → `api_app.py` → app |
| Encriptación (ISO 27000) | MQTT con TLS 1.2 (solo puerto 8883), API por HTTPS, DynamoDB por HTTPS; la app solo confía en nuestra CA y bloquea todo tráfico sin cifrar |
| Integridad de datos | Firma HMAC-SHA256 en cada mensaje MQTT + comandos con más de 30 s se rechazan (anti-repetición) |
| Control de acceso | Broker sin anónimos + ACL por usuario; API con login y token que vence en 12 h; IAM con permisos solo sobre las 3 tablas |
| Protección de datos | Contraseñas con hash PBKDF2 (600.000 iteraciones), bloqueo por intentos fallidos, credenciales fuera del código (`.env`, `~/.aws/credentials`, `local.properties`), `allowBackup=false` |

## Puesta en marcha

### 1. Broker MQTT (Mosquitto en la VM Raspbian)
La red de la VM debe estar en modo **adaptador puente** (bridge). Mira su IP con `hostname -I`.
```bash
cd raspbian/broker
sudo ./instalar_broker.sh 172.20.10.2      # <- la IP de tu VM
```
Instala Mosquitto, crea la CA y el certificado TLS para esa IP, configura la ACL, pide la contraseña de los usuarios `raspbian01`, `puente` y `app_android` y copia el certificado para la API.
Deja `~/ca_mosquitto.crt`: cópialo (FileZilla) a **`app/src/main/res/raw/ca_mosquitto.crt`** en Android Studio.

> Si ya lo habías ejecutado antes, solo corre `sudo ./preparar_certs_api.sh`.

### 2. Amazon DynamoDB
**Credenciales en la VM** (nunca en el código):
```bash
sudo apt-get install -y awscli
aws configure            # Access key, Secret key, región us-east-1
```
- **Cuenta AWS personal:** IAM → Usuarios → Crear usuario `iot-raspbian` → *Adjuntar políticas directamente* → *Crear política* → pega `raspbian/aws/politica_iam.json`. Luego *Credenciales de seguridad → Crear clave de acceso*.
- **AWS Academy (Learner Lab):** inicia el lab → *AWS Details* → *AWS CLI: Show* → copia todo en `~/.aws/credentials`. Estas credenciales vencen al terminar la sesión del lab: cópialas de nuevo cada vez.

### 3. Programas de la VM
```bash
cd raspbian
sudo apt-get install -y python3-venv
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.ejemplo .env && nano .env      # contraseñas MQTT y clave HMAC
python3 -c "import secrets; print(secrets.token_hex(32))"   # clave HMAC
python3 crear_tablas.py                # una sola vez
python3 crear_usuario.py               # usuario para entrar a la app
```
Luego, en 3 terminales (cada una con `cd raspbian && source venv/bin/activate`):
```bash
python3 nodo_mqtt.py
python3 puente_mqtt_dynamo.py
python3 api_app.py
```

### 4. App Android
1. Copia `ca_mosquitto.crt` a `app/src/main/res/raw/`.
2. Agrega al final de `local.properties` (no se sube a GitHub):
```properties
api.url=https://172.20.10.2:5000/
mqtt.uri=ssl://172.20.10.2:8883
mqtt.user=app_android
mqtt.pass=clave_de_app_android
hmac.key=la_misma_clave_HMAC_del_.env
device.id=raspbian01
```
3. *Sync Gradle* y ejecutar. El celular/emulador debe estar en la misma red que la VM.

**Si la IP de la VM cambia:** ejecuta otra vez `sudo ./instalar_broker.sh <IP_NUEVA>` (la CA no cambia, no hay que copiar el certificado de nuevo), actualiza `local.properties` y `app/src/main/res/xml/network_security_config.xml`.

## Pruebas para el video demostrativo
1. Login → el panel muestra **MQTT: Conectado (TLS)** y lecturas cada 5 s.
2. Activar LED / ventilador → la terminal del nodo muestra `[ACTUADOR] ...` (con el ventilador encendido la temperatura baja).
3. Movimiento detectado → aparece en rojo en la app.
4. **DynamoDB:** en la consola de AWS → DynamoDB → Tablas → `iot_lecturas` → *Explorar elementos*: aparecen las lecturas.
5. **Reconexión del nodo:** quita la red de la VM 1 min → `[OFFLINE] lectura guardada` → vuelve la red → `[SYNC] N lecturas pendientes reenviadas`.
6. **App sin internet:** modo avión → se siguen viendo los datos guardados; activa un switch → "se enviará al reconectar" → quita modo avión → el comando llega.
7. **Contingencia:** detén `nodo_mqtt.py` → la app muestra **DESCONECTADO** (Last Will).
8. **Seguridad:**
   - Sin usuario: `mosquitto_sub -h localhost -p 8883 --cafile /etc/mosquitto/certs/ca.crt -t 'iot/#'` → *not authorised*.
   - Sin TLS: `mosquitto_sub -h localhost -p 1883 -t '#'` → *connection refused*.
   - Comando falso: `mosquitto_pub -h localhost -p 8883 --cafile /etc/mosquitto/certs/ca.crt -u app_android -P <clave> -t iot/raspbian01/comandos -m '{"data":"{}","firma":"x"}'` → el nodo muestra `[SEGURIDAD] ... descartado`.
   - 5 logins fallidos → la API bloquea 60 s.
9. Ejecuta la app en 2 emuladores con distinta versión de Android.
