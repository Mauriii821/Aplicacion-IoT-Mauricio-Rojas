package com.example.webservicessencillo; // Revisa que este sea tu paquete

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.EditText;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import com.android.volley.Request;
import com.android.volley.RequestQueue;
import com.android.volley.Response;
import com.android.volley.VolleyError;
import com.android.volley.toolbox.StringRequest;
import com.android.volley.toolbox.Volley;

// Asegúrate de importar la clase Conexion que creaste
import com.example.webservicessencillo.datos.Conexion;

public class MainActivity extends AppCompatActivity {

    // 1. Declarar las variables de los campos de texto
    EditText editTextUser, editTextPass;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Conecta este código con el diseño visual del Login
        setContentView(R.layout.activity_main);

        // 2. Relacionar las variables con los IDs del XML que pegaste antes
        editTextUser = findViewById(R.id.etUser);
        editTextPass = findViewById(R.id.etPass);
    }

    // 3. AQUÍ VA EL CÓDIGO DE TU IMAGEN
    public void validarLogin(View v){
        final String user = editTextUser.getText().toString();
        final String pass = editTextPass.getText().toString();

        String url = Conexion.URL_WEB_SERVICES + "login.php?usuario=" + user + "&password=" + pass;
        RequestQueue servicio = Volley.newRequestQueue(this);

        StringRequest respuesta = new StringRequest(Request.Method.GET, url, new Response.Listener<String>() {
            @Override
            public void onResponse(String response) {
                if(response.trim().equals("Exito")){
                    // Cambiar de pantalla al Dashboard
                    Intent i = new Intent(getApplicationContext(), DashboardActivity.class);
                    startActivity(i);
                } else {
                    Toast.makeText(getApplicationContext(), "Credenciales incorrectas", Toast.LENGTH_SHORT).show();
                }
            }
        }, new Response.ErrorListener() {
            @Override
            public void onErrorResponse(VolleyError error) {
                Toast.makeText(getApplicationContext(), "Error comunicación", Toast.LENGTH_SHORT).show();
            }
        });
        servicio.add(respuesta);
    }
}