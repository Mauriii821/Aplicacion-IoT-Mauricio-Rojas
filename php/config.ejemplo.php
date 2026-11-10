<?php
// Copia este archivo como "config.php" y completa los datos.
// config.php está en .gitignore: las credenciales NO se suben a GitHub.
// Mejor aún: deja config.php FUERA de la carpeta pública del servidor web
// (ej. /var/www/config_iot.php) y ajusta la ruta en cn.php.
return [
    'db_host' => 'database-2.xxxxxxxx.us-east-1.rds.amazonaws.com',
    'db_user' => 'pi',
    'db_pass' => 'nueva_clave_segura',
    'db_name' => 'iot_db',
    // Certificado de AWS RDS para cifrar la conexión (opcional, recomendado)
    'db_ssl_ca' => '/home/pi/global-bundle.pem',
];
