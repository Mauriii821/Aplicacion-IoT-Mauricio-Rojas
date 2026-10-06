<?php
$c = mysqli_connect("database-2.cxg3us5o1f5f.us-east-1.rds.amazonaws.com", "pi", "12345678", "iot_db");
if (!$c) {
    die("Error de conexión: " . mysqli_connect_error());
}
?>