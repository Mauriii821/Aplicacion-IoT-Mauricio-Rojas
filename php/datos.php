<?php
include("cn.php");
$q = mysqli_query($c, "SELECT temperatura, humedad FROM registros_clima ORDER BY id DESC LIMIT 1");

if ($fila = mysqli_fetch_array($q)) {
    echo json_encode(array("temperatura" => $fila['temperatura'], "humedad" => $fila['humedad']));
} else {
    echo json_encode(array("temperatura" => 0, "humedad" => 0));
}
?>