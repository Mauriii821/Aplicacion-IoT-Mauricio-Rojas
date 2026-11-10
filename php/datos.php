<?php
// Devuelve la última lectura, el historial y el estado de los actuadores.
// La app lo usa como respaldo cuando no hay conexión MQTT y para el historial.
include __DIR__ . '/cn.php';

$dispositivo = $_GET['dispositivo'] ?? 'raspbian01';
if (!preg_match('/^[A-Za-z0-9_-]{1,30}$/', $dispositivo)) {
    http_response_code(400);
    echo json_encode(['error' => 'Dispositivo inválido']);
    exit;
}

$stmt = mysqli_prepare($c,
    'SELECT temperatura, humedad, movimiento, UNIX_TIMESTAMP(fecha) AS ts
       FROM registros_clima WHERE dispositivo = ? ORDER BY id DESC LIMIT 20');
mysqli_stmt_bind_param($stmt, 's', $dispositivo);
mysqli_stmt_execute($stmt);
$res = mysqli_stmt_get_result($stmt);

$historial = [];
while ($f = mysqli_fetch_assoc($res)) {
    $historial[] = [
        'temperatura' => (float)$f['temperatura'],
        'humedad'     => (float)$f['humedad'],
        'movimiento'  => (bool)$f['movimiento'],
        'ts'          => (int)$f['ts'],
    ];
}

$stmt = mysqli_prepare($c, 'SELECT led, ventilador, online FROM estado_actuadores WHERE dispositivo = ?');
mysqli_stmt_bind_param($stmt, 's', $dispositivo);
mysqli_stmt_execute($stmt);
$est = mysqli_fetch_assoc(mysqli_stmt_get_result($stmt));

echo json_encode([
    // Compatibilidad con la versión anterior de la app
    'temperatura' => $historial[0]['temperatura'] ?? 0,
    'humedad'     => $historial[0]['humedad'] ?? 0,
    'movimiento'  => $historial[0]['movimiento'] ?? false,
    'ts'          => $historial[0]['ts'] ?? 0,
    'historial'   => $historial,
    'actuadores'  => [
        'led'        => (bool)($est['led'] ?? false),
        'ventilador' => (bool)($est['ventilador'] ?? false),
        'online'     => (bool)($est['online'] ?? false),
    ],
]);
