package com.example.webservicessencillo; // Revisa que este sea tu paquete exacto

import android.os.Bundle;
import android.os.Handler;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import com.android.volley.Request;
import com.android.volley.RequestQueue;
import com.android.volley.Response;
import com.android.volley.VolleyError;
import com.android.volley.toolbox.JsonObjectRequest;
import com.android.volley.toolbox.Volley;

import org.json.JSONException;
import org.json.JSONObject;

import com.example.webservicessencillo.datos.Conexion;

public class DashboardActivity extends AppCompatActivity {

    TextView tvTemp, tvHum;
    RequestQueue requestQueue;
    Handler handler = new Handler();
    Runnable runnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Conecta con tu diseño visual del dashboard
        setContentView(R.layout.activity_dashboard);

        tvTemp = findViewById(R.id.tvTemp);
        tvHum = findViewById(R.id.tvHum);
        requestQueue = Volley.newRequestQueue(this);

        // Crear un ciclo que se ejecuta cada 5 segundos (5000 milisegundos)
        runnable = new Runnable() {
            @Override
            public void run() {
                obtenerDatosSensores();
                handler.postDelayed(this, 5000);
            }
        };
        // Iniciar el ciclo
        handler.post(runnable);
    }

    private void obtenerDatosSensores() {
        String url = Conexion.URL_WEB_SERVICES + "datos.php";

        JsonObjectRequest request = new JsonObjectRequest(Request.Method.GET, url, null,
                new Response.Listener<JSONObject>() {
                    @Override
                    public void onResponse(JSONObject response) {
                        try {
                            // Extraer los datos del JSON que envía tu PHP
                            String temp = response.getString("temperatura");
                            String hum = response.getString("humedad");

                            // Actualizar los textos en la pantalla
                            tvTemp.setText("Temperatura: " + temp + " °C");
                            tvHum.setText("Humedad: " + hum + " %");
                        } catch (JSONException e) {
                            e.printStackTrace();
                        }
                    }
                }, new Response.ErrorListener() {
            @Override
            public void onErrorResponse(VolleyError error) {
                Toast.makeText(getApplicationContext(), "Buscando señal del sensor...", Toast.LENGTH_SHORT).show();
            }
        });

        requestQueue.add(request);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        // Detener las peticiones a la API si el usuario cierra la pantalla
        handler.removeCallbacks(runnable);
    }
}