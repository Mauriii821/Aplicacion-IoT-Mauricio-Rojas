package com.example.webservicessencillo;

import android.content.Intent;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.android.volley.DefaultRetryPolicy;
import com.android.volley.Request;
import com.android.volley.RequestQueue;
import com.android.volley.toolbox.StringRequest;
import com.android.volley.toolbox.Volley;
import com.example.webservicessencillo.datos.Conexion;

import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

public class MainActivity extends AppCompatActivity {

    private static final int MAX_INTENTOS = 3;
    private static final long BLOQUEO_MS = 30_000;

    EditText editTextUser, editTextPass;
    Button btnLogin;
    RequestQueue servicio;
    int intentosFallidos = 0;
    long bloqueadoHasta = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        editTextUser = findViewById(R.id.etUser);
        editTextPass = findViewById(R.id.etPass);
        btnLogin = findViewById(R.id.btnLogin);
        servicio = Volley.newRequestQueue(this);
    }

    public void validarLogin(View v) {
        final String user = editTextUser.getText().toString().trim();
        final String pass = editTextPass.getText().toString();

        // Validación de entrada
        if (user.isEmpty() || pass.isEmpty()) {
            Toast.makeText(this, "Ingrese usuario y contraseña", Toast.LENGTH_SHORT).show();
            return;
        }
        // Bloqueo temporal tras varios intentos fallidos (evita fuerza bruta)
        long ahora = SystemClock.elapsedRealtime();
        if (ahora < bloqueadoHasta) {
            long seg = (bloqueadoHasta - ahora) / 1000 + 1;
            Toast.makeText(this, "Demasiados intentos. Espere " + seg + " s", Toast.LENGTH_SHORT).show();
            return;
        }

        btnLogin.setEnabled(false);
        String url = Conexion.URL_WEB_SERVICES + "login.php";

        // POST: las credenciales viajan en el cuerpo, no en la URL
        StringRequest peticion = new StringRequest(Request.Method.POST, url,
                response -> {
                    btnLogin.setEnabled(true);
                    if (esExito(response)) {
                        intentosFallidos = 0;
                        editTextPass.setText("");
                        startActivity(new Intent(getApplicationContext(), DashboardActivity.class));
                    } else {
                        intentosFallidos++;
                        if (intentosFallidos >= MAX_INTENTOS) {
                            bloqueadoHasta = SystemClock.elapsedRealtime() + BLOQUEO_MS;
                            intentosFallidos = 0;
                        }
                        Toast.makeText(getApplicationContext(), "Credenciales incorrectas", Toast.LENGTH_SHORT).show();
                    }
                },
                error -> {
                    btnLogin.setEnabled(true);
                    Toast.makeText(getApplicationContext(), "Error de comunicación con el servidor", Toast.LENGTH_SHORT).show();
                }) {
            @Override
            protected Map<String, String> getParams() {
                Map<String, String> p = new HashMap<>();
                p.put("usuario", user);
                p.put("password", pass);
                return p;
            }
        };
        peticion.setRetryPolicy(new DefaultRetryPolicy(8000, 1, 1f));
        servicio.add(peticion);
    }

    private static boolean esExito(String response) {
        String r = response.trim();
        if (r.equals("Exito")) return true;  // formato antiguo
        try {
            return "Exito".equals(new JSONObject(r).optString("status"));
        } catch (Exception e) {
            return false;
        }
    }
}
