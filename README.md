# Aplicación IoT – Mauricio Rojas (TI3042, Unidad 3)

Prototipo IoT con una app Android que **monitorea sensores y controla actuadores** de forma inalámbrica y segura, mediante **MQTT sobre TLS**, con respaldo en **AWS RDS (MySQL)**. El broker MQTT es **Mosquitto en la propia VM Raspbian** (equivale al SBC-PT BROKER del taller de Packet Tracer).

## Arquitectura

```
 VM Raspbian (microcontrolador virtual)         VM Raspbian (Mosquitto)      VM Raspbian
 ┌──────────────────────────────┐   MQTT TLS    ┌──────────────┐  MQTT TLS  ┌────────────────────┐
 │ nodo_mqtt.py                 │──telemetría──►│              │───────────►│ puente_mqtt_db.py  │
 │  sensores: temp, humedad,    │               │    BROKER    │            │  verifica firma y  │
 │            movimiento        │◄──comandos────│   (8883)     │            │  guarda en la BD   │
 │  actuadores: LED, ventilador │───estado─────►│              │            └─────────┬──────────┘
 └──────────────────────────────┘               └──────┬───────┘                      │
                                                       │ MQTT TLS                     ▼
                                                ┌──────┴───────┐   HTTP (respaldo) ┌──────────────┐
                                                │  App Android │◄──────────────────│ PHP + AWS RDS│
                                                │  (Java)      │   historial       │   MySQL      │
                                                └──────────────┘                   └──────────────┘
```

Tópicos MQTT: `iot/raspbian01/telemetria`, `iot/raspbian01/comandos`, `iot/raspbian01/estado`.

## Cómo cumple la guía de la Unidad 3

| Requisito | Implementación |
|---|---|
| App envía instrucciones al microcontrolador | Switches LED/ventilador → `MqttManager.enviarComando()` → `nodo_mqtt.py` |
| App recibe datos de sensores | Telemetría MQTT en tiempo real (`DashboardActivity.onLectura`) |
| Reconexión automática | Paho `setAutomaticReconnect` + reintentos 2-4-8…60 s en la app; `reconnect_delay_set` en Python |
| Consumo de energía | App: desconecta MQTT y HTTP en `onStop`, keep-alive 60 s. Nodo: intervalo configurable y solo publica si los valores cambian |
| Compatibilidad Android | minSdk 28 (Android 9) a targetSdk 36; probar en 2 emuladores con distinta API |
| Plan de contingencia | Si falla MQTT → respaldo HTTP a la BD cada 15 s → si falla todo, datos guardados en el teléfono. Last Will avisa si el nodo se cae |
| Almacenamiento temporal y sincronización | App: `CacheLocal` (lecturas y comandos pendientes). Nodo: SQLite `buffer_offline.db`. Puente: SQLite si RDS no responde |
| Flujo sensor → MQTT → broker → BD → app | `nodo_mqtt.py` → Mosquitto → `puente_mqtt_db.py` → RDS → `datos.php` → app |
| Encriptación (ISO 27000) | Mosquitto solo acepta MQTT con TLS 1.2 (puerto 8883, sin 1883 abierto) con certificado de una CA propia que la app valida, conexión TLS a RDS, `network_security_config` bloquea HTTP salvo el servidor local |
| Integridad de datos | Firma HMAC-SHA256 en cada mensaje + comandos con más de 30 s se rechazan (anti-repetición) |
| Control de acceso al broker | Sin usuarios anónimos; 3 usuarios (nodo, puente, app) y ACL: cada uno solo lee/publica sus tópicos (mínimo privilegio) |
| Protección de datos | Login por POST, consultas preparadas (sin inyección SQL), bloqueo tras 3 intentos, credenciales fuera del código (`.env`, `config.php`, `local.properties`), `allowBackup=false`, ofuscación en release |

## Puesta en marcha

### 1. Broker MQTT (Mosquitto en la VM Raspbian)
La red de la VM debe estar en modo **adaptador puente** (bridge) para que el celular/emulador la alcance. Mira su IP con `hostname -I`.
```bash
cd raspbian/broker
sudo ./instalar_broker.sh 192.168.1.160      # <- la IP de tu VM
```
El script instala Mosquitto, crea la CA y el certificado TLS para esa IP, configura la ACL y te pide la contraseña de los usuarios `raspbian01`, `puente` y `app_android`.
Al final deja `~/ca_mosquitto.crt`: cópialo a `app/src/main/assets/ca_mosquitto.crt` en Android Studio.

Prueba del broker:
```bash
mosquitto_sub -h localhost -p 8883 --cafile /etc/mosquitto/certs/ca.crt -u puente -P <clave> -t 'iot/#' -v
```

### 2. Base de datos (AWS RDS)
Ejecuta `sql/migracion_unidad3.sql` sobre `iot_db`.

### 3. Servidor PHP
```bash
cd php
cp config.ejemplo.php config.php   # y completa los datos
```
Copia los `.php` a `/var/www/html/iot_app/` (ya no se usa `guardar.php`).

### 4. VM Raspbian
```bash
cd raspbian
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.ejemplo .env               # y completa los datos
python3 -c "import secrets; print(secrets.token_hex(32))"   # clave HMAC para .env y la app
python3 nodo_mqtt.py               # terminal 1
python3 puente_mqtt_db.py          # terminal 2
```

### 5. App Android
Agrega al final de `local.properties` (este archivo no se sube a GitHub):
```properties
api.url=http://192.168.1.157/iot_app/
mqtt.uri=ssl://192.168.1.160:8883
mqtt.user=app_android
mqtt.pass=clave_de_app_android
hmac.key=la_misma_clave_HMAC_del_.env
device.id=raspbian01
```
Si la IP de la VM cambia, vuelve a ejecutar `instalar_broker.sh` con la nueva IP (el certificado va ligado a la IP) y actualiza `mqtt.uri`.
Si cambias la IP del servidor PHP, actualízala también en `app/src/main/res/xml/network_security_config.xml`.
Luego *Sync Gradle* y ejecuta.

## Pruebas para el video demostrativo
1. Login → el dashboard muestra **MQTT: Conectado (TLS)** y lecturas cada 5 s.
2. Activar LED / ventilador → la terminal del nodo muestra `[ACTUADOR] ...` (con el ventilador encendido la temperatura baja).
3. Movimiento detectado → aparece en rojo en la app.
4. **Reconexión:** quita la red de la VM 1 min → `[OFFLINE] lectura guardada` → vuelve la red → `[SYNC] N lecturas pendientes reenviadas`.
5. **App sin internet:** modo avión → se siguen viendo los datos guardados; activa un switch → "se enviará al reconectar" → quita modo avión → el comando llega.
6. **Contingencia:** detén `nodo_mqtt.py` → la app muestra **DESCONECTADO** (Last Will).
7. **Seguridad:**
   - Sin usuario: `mosquitto_sub -h localhost -p 8883 --cafile /etc/mosquitto/certs/ca.crt -t 'iot/#'` → *not authorised*.
   - Sin TLS: `mosquitto_sub -h localhost -p 1883 -t '#'` → *connection refused*.
   - Comando falso: `mosquitto_pub ... -u app_android -P <clave> -t iot/raspbian01/comandos -m '{"data":"{}","firma":"x"}'` → el nodo muestra `[SEGURIDAD] ... descartado`.
8. Ejecuta la app en 2 emuladores con distinta versión de Android.
