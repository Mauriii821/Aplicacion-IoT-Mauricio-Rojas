import time
import random
import requests

API_URL = "http://127.0.0.1/iot_app/guardar.php" 

while True:
    temp = round(random.uniform(15.0, 30.0), 1)
    hum = round(random.uniform(40.0, 60.0), 1)
    
    payload = {"temperatura": temp, "humedad": hum}
    
    try:
        respuesta = requests.post(API_URL, json=payload)
        print(f"Enviado: Temp {temp}°C, Hum {hum}% - Respuesta: {respuesta.text}")
    except Exception as e:
        print(f"Error de conexión: {e}")
        
    time.sleep(5)