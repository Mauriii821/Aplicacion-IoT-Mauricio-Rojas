<?php
include("cn.php");

// Recibe los datos en formato JSON que enviará el script de Python
$datos = json_decode(file_get_contents('php://input'), true);

if (isset($datos['temperatura']) && isset($datos['humedad'])) {
    $temperatura = $datos['temperatura'];
    $humedad = $datos['humedad'];

    // Inserta los datos en la tabla de AWS RDS
    $query = "INSERT INTO registros_clima (temperatura, humedad) VALUES ('$temperatura', '$humedad')";
    $resultado = mysqli_query($c, $query);

    if ($resultado) {
        echo json_encode(["status" => "Exito"]);
    } else {
        echo json_encode(["status" => "Error"]);
    }
} else {
    echo json_encode(["status" => "Faltan datos"]);
}
?>