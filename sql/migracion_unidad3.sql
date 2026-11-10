-- Cambios a la base de datos iot_db (AWS RDS MySQL) para la Unidad 3.
-- Ejecútalo una vez (MySQL Workbench o: mysql -h HOST -u pi -p iot_db < migracion_unidad3.sql)
-- Si alguna columna ya existe, MySQL dará error en esa línea: bórrala y vuelve a ejecutar.

ALTER TABLE registros_clima
    ADD COLUMN dispositivo VARCHAR(30) NOT NULL DEFAULT 'raspbian01',
    ADD COLUMN movimiento  TINYINT(1)  NOT NULL DEFAULT 0,
    ADD COLUMN fecha       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE INDEX idx_registros_disp ON registros_clima (dispositivo, id);

CREATE TABLE IF NOT EXISTS estado_actuadores (
    dispositivo VARCHAR(30) PRIMARY KEY,
    led         TINYINT(1) NOT NULL DEFAULT 0,
    ventilador  TINYINT(1) NOT NULL DEFAULT 0,
    online      TINYINT(1) NOT NULL DEFAULT 0,
    actualizado TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Usuario con permisos mínimos para la app y el puente (principio de mínimo privilegio).
-- Cambia la contraseña antes de ejecutar.
-- CREATE USER 'iot_app'@'%' IDENTIFIED BY 'cambia_esta_clave';
-- GRANT SELECT, INSERT, UPDATE ON iot_db.* TO 'iot_app'@'%';
