# Aplicación IoT – Mauricio Rojas (TI3042, Unidad 3)

Prototipo IoT con una app Android que **monitorea sensores y controla actuadores** de forma inalámbrica y segura, siguiendo el flujo de la guía:

**SENSOR RECIBE LECTURAS → ENVÍA MENSAJES POR MQTT → RECIBE BROKER PÚBLICO (AWS IoT Core) → GUARDA EN DB NO ESTRUCTURADA (DynamoDB) → RESCATA MENSAJES LA APP**

## Arquitectura

```
 Raspberry Pi (física o VM Raspbian)                         AWS (Learner Lab)
 ┌──────────────────────────────┐   MQTT + TLS mutuo   ┌───────────────────┐  regla IoT  ┌──────────────┐
 │ nodo_mqtt.py                 │──── telemetría ─────►│                   │────────────►│   DynamoDB   │
 │  sensores: temp, humedad,    │──── estado ─────────►│   AWS IoT Core    │────────────►│ iot_lecturas │
 │            movimiento        │◄─── comandos ────────│  (broker público) │             │ iot_estado   │
 │  actuadores: LED, ventilador │  (certificados X.509)│                   │             │ iot_usuarios │
 │                              │                      └─────────▲─────────┘             └──────┬───────┘
 │ api_app.py (HTTPS :5000) ────┼──── publica comandos ──────────┘                              │
 │        ▲            ◄────────┼──── lee mensajes guardados ─────────────────────────────────────┘
 └────────┼─────────────────────┘
          │ HTTPS (login con token, datos, comandos)
     App Android (Java)
```

| Componente | En el taller / Packet Tracer |
|---|---|
| `nodo_mqtt.py` | SBC-PT DEVICE1 (humedad) y DEVICE2 (movimiento) |
| AWS IoT Core | Broker público que recibe y lee los mensajes MQTT (cliente de prueba MQTT en la consola) |
| DynamoDB | Base de datos no estructurada que guarda los mensajes MQTT |
| App Android | TEST1 / TEST2 (emuladores o celulares) |

Tópicos MQTT: `iot/raspbian01/telemetria`, `iot/raspbian01/estado`, `iot/raspbian01/comandos`.

## Cómo cumple la guía de la Unidad 3

| Requisito | Implementación |
|---|---|
| App envía instrucciones al microcontrolador | Switches LED/ventilador → API → AWS IoT Core → `nodo_mqtt.py` |
| App recibe datos de sensores | La app rescata de DynamoDB (vía API) las lecturas que la regla de IoT Core guardó |
| Reconexión automática | Nodo: reconexión MQTT 1…60 s. App: reintentos 3, 6, 12… hasta 30 s |
| Consumo de energía | Nodo: intervalo configurable y solo publica si los valores cambian. App: solo consulta con la pantalla visible |
| Compatibilidad Android | minSdk 28 (Android 9) a targetSdk 36; probar en 2 emuladores con distinta API |
| Plan de contingencia | Last Will: si la Raspberry se cae, IoT Core publica `online: false`. App sin red: muestra datos guardados y deja los comandos en cola |
| Almacenamiento temporal y sincronización | Nodo: SQLite `buffer_offline.db`; al volver la conexión reenvía todo a IoT Core → DynamoDB. App: `CacheLocal` |
| Encriptación (ISO 27000) | MQTT con TLS mutuo (certificados X.509 de AWS IoT), API por HTTPS con CA propia, DynamoDB por HTTPS; la app bloquea todo tráfico sin cifrar |
| Integridad de datos | Cada mensaje firmado con HMAC-SHA256; la API marca como `verificado: false` cualquier registro alterado en DynamoDB; comandos con más de 30 s se rechazan |
| Control de acceso | Política de IoT: el certificado solo puede conectarse como `raspbian01` y usar sus 3 tópicos. API con login y token de 12 h |
| Protección de datos | Contraseñas con hash PBKDF2, bloqueo tras 5 intentos fallidos, credenciales fuera del código (`.env`, `~/.aws/credentials`, `local.properties`) |

## Puesta en marcha

### 0. Conexión a la Raspberry
```bash
ping 172.20.10.2               # prueba de conectividad
ssh -l pi 172.20.10.2          # conexión remota segura
```
Archivos: FileZilla con `sftp://IP`, usuario `pi`, puerto 22.

### 1. Credenciales del Learner Lab (cada vez que inicies el lab)
*Start Lab* → *AWS Details* → *AWS CLI: Show* → copia el bloque en la Raspberry:
```bash
mkdir -p ~/.aws && nano ~/.aws/credentials
printf "[default]\nregion = us-east-1\n" > ~/.aws/config      # solo la primera vez
```

### 2. Configurar AWS desde cero (un solo comando)
```bash
cd ~/Aplicacion-IoT-Mauricio-Rojas/raspbian
sudo apt-get install -y python3-venv
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 configurar_aws.py
```
`configurar_aws.py` crea las tablas de DynamoDB, el objeto `raspbian01` en IoT Core, su certificado y llave privada (en `~/aws-iot-certs`), descarga `AmazonRootCA1.pem`, crea y asocia la política de mínimo privilegio (`aws/politica_iot_core.json` es la versión de referencia), crea las reglas IoT Core → DynamoDB y completa el `.env` (endpoint, rutas y clave HMAC). Se puede ejecutar varias veces sin duplicar nada.

### 3. Usuario de la app y certificado HTTPS
```bash
python3 crear_usuario.py
./crear_certs_api.sh 172.20.10.2      # la IP de tu Raspberry
```

### 4. Ejecutar (2 terminales, cada una con `cd raspbian && source venv/bin/activate`)
```bash
python3 nodo_mqtt.py
python3 api_app.py
```

### 5. App Android
1. Copia `~/ca_api.crt` de la Raspberry (FileZilla) a **`app/src/main/res/raw/ca_api.crt`**.
2. Agrega al final de `local.properties`:
```properties
api.url=https://172.20.10.2:5000/
device.id=raspbian01
```
3. *Sync Gradle* y ejecutar. El celular/emulador debe estar en la misma red que la Raspberry.

**Si la IP de la Raspberry cambia:** `./crear_certs_api.sh <IP_NUEVA>` y actualiza `api.url`. La CA no cambia, así que no hay que copiar el certificado de nuevo.

## Pruebas para el video demostrativo
1. `ping` y `ssh` a la Raspberry.
2. **AWS IoT → Cliente de prueba MQTT** → suscribirse a `iot/#` → se ven llegar las lecturas en JSON.
3. **DynamoDB → Tablas → `iot_lecturas` → Explorar elementos**: aparecen los mensajes guardados.
4. App: login → lecturas cada 3 s → activar LED / ventilador → la terminal del nodo muestra `[ACTUADOR] ...`.
5. **Almacenamiento temporal:** quita la red de la Raspberry 1 min → `[OFFLINE] lectura guardada` → vuelve la red → `[SYNC] N lecturas pendientes reenviadas` → aparecen en DynamoDB.
6. **Contingencia:** detén `nodo_mqtt.py` con el cable/red desconectado → la app muestra **SIN SEÑAL**.
7. **App sin red:** modo avión → se siguen viendo los datos guardados; activa un switch → "se enviará al reconectar" → quita modo avión → el comando llega.
8. **Seguridad:**
   - Publica desde el cliente de prueba MQTT en `iot/raspbian01/comandos` un mensaje falso → el nodo muestra `[SEGURIDAD] ... descartado`.
   - Edita una temperatura en DynamoDB → la app muestra **⚠ firma inválida** y la API lo registra.
   - 5 logins fallidos → la API bloquea 60 s.
9. Ejecuta la app en 2 emuladores con distinta versión de Android.
