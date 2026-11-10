<?php
// Login: recibe usuario y contraseña por POST (no en la URL, así no quedan en logs)
include __DIR__ . '/cn.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['status' => 'Metodo no permitido']);
    exit;
}

$usuario = trim($_POST['usuario'] ?? '');
$password = $_POST['password'] ?? '';

if ($usuario === '' || $password === '' || strlen($usuario) > 50) {
    echo json_encode(['status' => 'Fallo']);
    exit;
}

$password_cifrada = hash('sha256', $password);

// Consulta preparada: evita inyección SQL
$stmt = mysqli_prepare($c, 'SELECT id FROM usuarios WHERE usuario = ? AND password = ? LIMIT 1');
mysqli_stmt_bind_param($stmt, 'ss', $usuario, $password_cifrada);
mysqli_stmt_execute($stmt);
mysqli_stmt_store_result($stmt);

echo json_encode(['status' => mysqli_stmt_num_rows($stmt) > 0 ? 'Exito' : 'Fallo']);
