<?php
include("cn.php");

$usuario = mysqli_real_escape_string($c, $_GET["usuario"]);
$password_plana = $_GET["password"];

$password_cifrada = hash('sha256', $password_plana);

//Consultar base de datos
$query = "SELECT * FROM usuarios WHERE usuario = '$usuario' AND password = '$password_cifrada'";
$q = mysqli_query($c, $query);

if(mysqli_num_rows($q) > 0){
    echo "Exito";
} else {
    echo "Fallo";
}
?>