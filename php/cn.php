<?php
// Conexión a la base de datos (AWS RDS MySQL)
// Las credenciales se leen desde config.php, que NO está en el repositorio.
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

$cfg = require __DIR__ . '/config.php';

try {
    $c = mysqli_init();
    $flags = 0;
    if (!empty($cfg['db_ssl_ca']) && file_exists($cfg['db_ssl_ca'])) {
        mysqli_ssl_set($c, null, null, $cfg['db_ssl_ca'], null, null);
        $flags = MYSQLI_CLIENT_SSL;   // conexión cifrada con TLS
    }
    mysqli_real_connect($c, $cfg['db_host'], $cfg['db_user'], $cfg['db_pass'], $cfg['db_name'], 3306, null, $flags);
    mysqli_set_charset($c, 'utf8mb4');
} catch (mysqli_sql_exception $e) {
    // No se muestran detalles internos al cliente (ISO 27002 8.28)
    error_log('Error BD: ' . $e->getMessage());
    http_response_code(503);
    echo json_encode(['error' => 'Servicio no disponible']);
    exit;
}
