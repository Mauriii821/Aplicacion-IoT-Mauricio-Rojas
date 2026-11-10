-- Crea la base de datos completa del proyecto IoT (TI3042) en AWS RDS MySQL.
-- Uso (desde la VM Raspbian):
--   mysql -h <ENDPOINT_RDS> -u admin -p < crear_bd.sql
-- ANTES de ejecutar cambia las dos contraseñas marcadas con  <-- CAMBIAR

CREATE DATABASE IF NOT EXISTS iot_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE iot_db;

-- Usuarios de la app (contraseña guardada como hash SHA-256, nunca en texto plano)
CREATE TABLE IF NOT EXISTS usuarios (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    usuario  VARCHAR(50) NOT NULL UNIQUE,
    password CHAR(64)    NOT NULL,
    creado   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Lecturas de los sensores (las guarda puente_mqtt_db.py)
CREATE TABLE IF NOT EXISTS registros_clima (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    dispositivo VARCHAR(30)  NOT NULL DEFAULT 'raspbian01',
    temperatura DECIMAL(5,2) NOT NULL,
    humedad     DECIMAL(5,2) NOT NULL,
    movimiento  TINYINT(1)   NOT NULL DEFAULT 0,
    fecha       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_registros_disp (dispositivo, id)
);

-- Último estado conocido de los actuadores
CREATE TABLE IF NOT EXISTS estado_actuadores (
    dispositivo VARCHAR(30) PRIMARY KEY,
    led         TINYINT(1) NOT NULL DEFAULT 0,
    ventilador  TINYINT(1) NOT NULL DEFAULT 0,
    online      TINYINT(1) NOT NULL DEFAULT 0,
    actualizado TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Usuario de prueba para iniciar sesión en la app
INSERT IGNORE INTO usuarios (usuario, password)
VALUES ('admin', SHA2('ClaveApp2026', 256));                 -- <-- CAMBIAR

-- Usuario de base de datos con permisos mínimos para el PHP y el puente
-- (la cuenta "admin" de RDS solo se usa para administrar, no en el código)
CREATE USER IF NOT EXISTS 'iot_app'@'%' IDENTIFIED BY 'ClaveBD_IoT_2026';   -- <-- CAMBIAR
GRANT SELECT, INSERT, UPDATE ON iot_db.* TO 'iot_app'@'%';
FLUSH PRIVILEGES;

SELECT 'Base de datos iot_db creada correctamente' AS resultado;
