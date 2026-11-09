package com.example.webservicessencillo;

import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.SwitchCompat;

import com.android.volley.Request;
import com.android.volley.RequestQueue;
import com.android.volley.toolbox.JsonObjectRequest;
import com.android.volley.toolbox.Volley;
import com.example.webservicessencillo.datos.CacheLocal;
import com.example.webservicessencillo.datos.Conexion;
import com.example.webservicessencillo.mqtt.MqttManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Pantalla principal: monitorea los sensores y controla los actuadores.
 *
 * Canal principal: MQTT sobre TLS (tiempo real).
 * Plan de contingencia: si MQTT no está disponible, se consulta la base de datos
 * por HTTP (datos.php) cada 15 s, y siempre se muestra lo último guardado en el teléfono.
 */
public class DashboardActivity extends AppCompatActivity implements MqttManager.Listener {

    private static final long RESPALDO_HTTP_MS = 15_000;

    private TextView tvConexion, tvDispositivo, tvTemp, tvHum, tvMov, tvActualizado, tvHistorial;
    private SwitchCompat swLed, swVentilador;

    private MqttManager mqtt;
    private CacheLocal cache;
    private RequestQueue requestQueue;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean actualizandoSwitches = false;
    private final SimpleDateFormat formato = new SimpleDateFormat("HH:mm:ss", Locale.getDefault());

    private final Runnable respaldoHttp = new Runnable() {
        @Override
        public void run() {
            if (!mqtt.estaConectado()) cargarDesdeServidor();
            handler.postDelayed(this, RESPALDO_HTTP_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_dashboard);

        tvConexion = findViewById(R.id.tvConexion);
        tvDispositivo = findViewById(R.id.tvDispositivo);
        tvTemp = findViewById(R.id.tvTemp);
        tvHum = findViewById(R.id.tvHum);
        tvMov = findViewById(R.id.tvMovimiento);
        tvActualizado = findViewById(R.id.tvActualizado);
        tvHistorial = findViewById(R.id.tvHistorial);
        swLed = findViewById(R.id.swLed);
        swVentilador = findViewById(R.id.swVentilador);
        Button btnSalir = findViewById(R.id.btnSalir);

        cache = new CacheLocal(this);
        mqtt = new MqttManager(this, this);
        requestQueue = Volley.newRequestQueue(this);

        swLed.setOnCheckedChangeListener(this::onSwitch);
        swVentilador.setOnCheckedChangeListener(this::onSwitch);
        btnSalir.setOnClickListener(v -> finish());

        // Mostrar de inmediato lo guardado en el teléfono (funciona sin internet)
        mostrarDesdeCache();
    }

    @Override
    protected void onStart() {
        super.onStart();
        mqtt.conectar();
        cargarDesdeServidor();               // trae el historial de la BD
        handler.postDelayed(respaldoHttp, RESPALDO_HTTP_MS);
    }

    @Override
    protected void onStop() {
        super.onStop();
        // Ahorro de batería: nada de red mientras la app no está en pantalla
        handler.removeCallbacks(respaldoHttp);
        mqtt.desconectar();
        requestQueue.cancelAll(r -> true);
    }

    // ---------------- Actuadores ----------------
    private void onSwitch(CompoundButton boton, boolean encendido) {
        if (actualizandoSwitches) return;
        String actuador = boton.getId() == R.id.swLed ? "led" : "ventilador";
        if (!mqtt.enviarComando(actuador, encendido)) {
            Toast.makeText(this, "Sin conexión: el comando se enviará al reconectar",
                    Toast.LENGTH_SHORT).show();
        }
    }

    // ---------------- Callbacks MQTT ----------------
    @Override
    public void onConexion(boolean conectado, String detalle) {
        tvConexion.setText((conectado ? "● MQTT: " : "○ MQTT: ") + detalle);
        tvConexion.setBackgroundColor(conectado ? Color.parseColor("#2E7D32") : Color.parseColor("#C62828"));
    }

    @Override
    public void onLectura(JSONObject lectura) {
        mostrarLectura(lectura);
        mostrarHistorial(cache.getLecturas());
    }

    @Override
    public void onEstado(JSONObject estado) {
        mostrarEstado(estado);
    }

    // ---------------- Respaldo HTTP (base de datos) ----------------
    private void cargarDesdeServidor() {
        String url = Conexion.URL_WEB_SERVICES + "datos.php?dispositivo=" + BuildConfig.DEVICE_ID;
        JsonObjectRequest req = new JsonObjectRequest(Request.Method.GET, url, null,
                response -> {
                    JSONArray historial = response.optJSONArray("historial");
                    if (historial != null && historial.length() > 0) {
                        cache.reemplazarLecturas(historial);
                        mostrarLectura(historial.optJSONObject(0));
                        mostrarHistorial(historial);
                    }
                    JSONObject act = response.optJSONObject("actuadores");
                    if (act != null && !mqtt.estaConectado()) {
                        cache.guardarActuadores(act);
                        mostrarEstado(act);
                    }
                },
                error -> {
                    if (!mqtt.estaConectado()) {
                        tvConexion.setText("○ Sin conexión: mostrando datos guardados en el teléfono");
                        tvConexion.setBackgroundColor(Color.parseColor("#EF6C00"));
                    }
                });
        requestQueue.add(req);
    }

    // ---------------- Mostrar datos ----------------
    private void mostrarDesdeCache() {
        JSONArray lecturas = cache.getLecturas();
        if (lecturas.length() > 0) {
            mostrarLectura(lecturas.optJSONObject(0));
            mostrarHistorial(lecturas);
        }
        JSONObject act = cache.getActuadores();
        if (act.length() > 0) mostrarEstado(act);
    }

    private void mostrarLectura(JSONObject l) {
        if (l == null) return;
        tvTemp.setText("Temperatura: " + l.optDouble("temperatura") + " °C");
        tvHum.setText("Humedad: " + l.optDouble("humedad") + " %");
        boolean mov = l.optBoolean("movimiento");
        tvMov.setText(mov ? "¡MOVIMIENTO DETECTADO!" : "Sin movimiento");
        tvMov.setTextColor(mov ? Color.parseColor("#C62828") : Color.parseColor("#2E7D32"));
        long ts = l.optLong("ts");
        if (ts > 0) tvActualizado.setText("Última lectura: " + formato.format(new Date(ts * 1000)));
    }

    private void mostrarEstado(JSONObject e) {
        actualizandoSwitches = true;   // evita reenviar el comando al actualizar la UI
        swLed.setChecked(e.optBoolean("led"));
        swVentilador.setChecked(e.optBoolean("ventilador"));
        actualizandoSwitches = false;
        boolean online = e.optBoolean("online", true);
        tvDispositivo.setText("Dispositivo " + BuildConfig.DEVICE_ID + ": " + (online ? "EN LÍNEA" : "DESCONECTADO"));
        tvDispositivo.setTextColor(online ? Color.parseColor("#2E7D32") : Color.parseColor("#C62828"));
    }

    private void mostrarHistorial(JSONArray lecturas) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < Math.min(10, lecturas.length()); i++) {
            JSONObject l = lecturas.optJSONObject(i);
            if (l == null) continue;
            sb.append(formato.format(new Date(l.optLong("ts") * 1000)))
              .append("  ").append(l.optDouble("temperatura")).append("°C  ")
              .append(l.optDouble("humedad")).append("%  ")
              .append(l.optBoolean("movimiento") ? "MOV" : "-").append('\n');
        }
        tvHistorial.setText(sb.length() > 0 ? sb.toString() : "Sin datos");
    }
}
