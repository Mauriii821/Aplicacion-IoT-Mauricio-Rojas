package com.example.webservicessencillo;

import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.SwitchCompat;

import com.android.volley.DefaultRetryPolicy;
import com.android.volley.Request;
import com.android.volley.RequestQueue;
import com.android.volley.VolleyError;
import com.android.volley.toolbox.JsonObjectRequest;
import com.android.volley.toolbox.StringRequest;
import com.android.volley.toolbox.Volley;
import com.example.webservicessencillo.datos.CacheLocal;
import com.example.webservicessencillo.datos.Conexion;
import com.example.webservicessencillo.datos.Sesion;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Locale;
import java.util.Map;

/**
 * Panel de monitoreo y control.
 *
 * Flujo (guía Unidad 3): la Raspberry publica por MQTT en AWS IoT Core, una regla
 * guarda los mensajes en DynamoDB y la app los "rescata" a través de la API HTTPS.
 * Los comandos de la app van a la API, que los publica en IoT Core hacia la Raspberry.
 *
 * - Reconexión automática: si la API no responde, se reintenta cada 3, 6, 12... hasta 30 s.
 * - Contingencia: sin conexión se muestran los últimos datos guardados en el teléfono y
 *   los comandos quedan en cola; se envían solos al volver la conexión.
 * - Batería: solo se consulta mientras la pantalla está visible.
 */
public class DashboardActivity extends AppCompatActivity {

    private static final long INTERVALO_NORMAL_MS = 3_000;
    private static final long INTERVALO_MAXIMO_MS = 30_000;
    private static final long DATO_ANTIGUO_S = 60;          // sin lecturas nuevas en 60 s = sin señal
    private static final long IGNORAR_ESTADO_MS = 8_000;    // tras un comando, esperar a que llegue el nuevo estado

    private TextView tvConexion, tvDispositivo, tvTemp, tvHum, tvMov, tvActualizado, tvHistorial;
    private SwitchCompat swLed, swVentilador;

    private CacheLocal cache;
    private RequestQueue requestQueue;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final SimpleDateFormat formato = new SimpleDateFormat("HH:mm:ss", Locale.getDefault());

    private long intervaloMs = INTERVALO_NORMAL_MS;
    private boolean visible = false;
    private boolean actualizandoSwitches = false;
    private long ultimoComandoMs = 0;

    private final Runnable consulta = new Runnable() {
        @Override
        public void run() {
            cargarDatos();
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Sin sesión iniciada no se puede ver el panel (control de acceso)
        if (!Sesion.activa()) {
            finish();
            return;
        }
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
        requestQueue = Volley.newRequestQueue(this);

        swLed.setOnCheckedChangeListener(this::onSwitch);
        swVentilador.setOnCheckedChangeListener(this::onSwitch);
        btnSalir.setOnClickListener(v -> {
            Sesion.cerrar();
            finish();
        });

        // Mostrar de inmediato lo guardado en el teléfono (funciona sin internet)
        mostrarDesdeCache();
    }

    @Override
    protected void onStart() {
        super.onStart();
        visible = true;
        intervaloMs = INTERVALO_NORMAL_MS;
        handler.post(consulta);
    }

    @Override
    protected void onStop() {
        super.onStop();
        // Ahorro de batería: nada de red mientras la app no está en pantalla
        visible = false;
        handler.removeCallbacks(consulta);
        requestQueue.cancelAll(r -> true);
    }

    private void programarSiguiente() {
        handler.removeCallbacks(consulta);
        if (visible) handler.postDelayed(consulta, intervaloMs);
    }

    // ---------------- Monitoreo: rescatar datos de DynamoDB vía API ----------------
    private void cargarDatos() {
        String url = Conexion.URL_WEB_SERVICES + "datos?dispositivo=" + BuildConfig.DEVICE_ID;
        JsonObjectRequest req = new JsonObjectRequest(Request.Method.GET, url, null,
                response -> {
                    intervaloMs = INTERVALO_NORMAL_MS;
                    mostrarConexion(true, "Conectado a AWS (HTTPS)");

                    JSONArray historial = response.optJSONArray("historial");
                    if (historial != null && historial.length() > 0) {
                        cache.reemplazarLecturas(historial);
                        mostrarLectura(historial.optJSONObject(0));
                        mostrarHistorial(historial);
                    }
                    JSONObject act = response.optJSONObject("actuadores");
                    if (act != null) {
                        cache.guardarActuadores(act);
                        if (SystemClock.elapsedRealtime() - ultimoComandoMs > IGNORAR_ESTADO_MS) {
                            mostrarEstado(act);
                        }
                    }
                    enviarComandosPendientes();
                    programarSiguiente();
                },
                error -> {
                    if (esSesionVencida(error)) return;
                    // Reconexión automática con espera progresiva
                    intervaloMs = Math.min(intervaloMs * 2, INTERVALO_MAXIMO_MS);
                    int pendientes = cache.contarPendientes();
                    mostrarConexion(false, "Sin conexión · reintento en " + (intervaloMs / 1000) + " s"
                            + " · datos guardados en el teléfono"
                            + (pendientes > 0 ? " · " + pendientes + " comando(s) en cola" : ""));
                    programarSiguiente();
                }) {
            @Override
            public Map<String, String> getHeaders() {
                return Sesion.cabeceras();
            }
        };
        req.setRetryPolicy(new DefaultRetryPolicy(5000, 0, 1f));
        requestQueue.add(req);
    }

    // ---------------- Control: comandos a los actuadores ----------------
    private void onSwitch(CompoundButton boton, boolean encendido) {
        if (actualizandoSwitches) return;
        String actuador = boton.getId() == R.id.swLed ? "led" : "ventilador";
        ultimoComandoMs = SystemClock.elapsedRealtime();
        enviarComando(actuador, encendido, true);
    }

    private void enviarComando(final String actuador, final boolean valor, final boolean avisar) {
        String url = Conexion.URL_WEB_SERVICES + "comando";
        StringRequest req = new StringRequest(Request.Method.POST, url,
                response -> {
                    if (avisar) {
                        Toast.makeText(this, "Comando enviado: " + actuador + (valor ? " ON" : " OFF"),
                                Toast.LENGTH_SHORT).show();
                    }
                },
                error -> {
                    if (esSesionVencida(error)) return;
                    int codigo = error.networkResponse != null ? error.networkResponse.statusCode : 0;
                    if (codigo == 400) {
                        Toast.makeText(this, "Comando rechazado", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    // Sin conexión o AWS no disponible: queda en cola (solo el último valor)
                    cache.encolarComando(actuador, valor);
                    if (avisar) {
                        Toast.makeText(this, "Sin conexión: el comando se enviará al reconectar",
                                Toast.LENGTH_SHORT).show();
                    }
                }) {
            @Override
            public Map<String, String> getHeaders() {
                return Sesion.cabeceras();
            }

            @Override
            protected Map<String, String> getParams() {
                Map<String, String> p = new HashMap<>();
                p.put("actuador", actuador);
                p.put("valor", valor ? "true" : "false");
                p.put("dispositivo", BuildConfig.DEVICE_ID);
                return p;
            }
        };
        req.setRetryPolicy(new DefaultRetryPolicy(5000, 0, 1f));
        requestQueue.add(req);
    }

    private void enviarComandosPendientes() {
        JSONObject pendientes = cache.sacarComandosPendientes();
        for (Iterator<String> it = pendientes.keys(); it.hasNext(); ) {
            String actuador = it.next();
            ultimoComandoMs = SystemClock.elapsedRealtime();
            enviarComando(actuador, pendientes.optBoolean(actuador), false);
        }
        if (pendientes.length() > 0) {
            Toast.makeText(this, "Comandos pendientes enviados", Toast.LENGTH_SHORT).show();
        }
    }

    private boolean esSesionVencida(VolleyError error) {
        if (error.networkResponse != null && error.networkResponse.statusCode == 401) {
            Sesion.cerrar();
            Toast.makeText(this, "Sesión vencida, inicie sesión otra vez", Toast.LENGTH_LONG).show();
            finish();
            return true;
        }
        return false;
    }

    // ---------------- Mostrar datos ----------------
    private void mostrarConexion(boolean conectado, String detalle) {
        tvConexion.setText((conectado ? "● " : "○ ") + detalle);
        tvConexion.setBackgroundColor(conectado ? Color.parseColor("#2E7D32") : Color.parseColor("#C62828"));
    }

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
        if (ts > 0) {
            String texto = "Última lectura: " + formato.format(new Date(ts * 1000));
            if (!l.optBoolean("verificado", true)) texto += "  ⚠ firma inválida";
            tvActualizado.setText(texto);
        }
    }

    private void mostrarEstado(JSONObject e) {
        actualizandoSwitches = true;   // evita reenviar el comando al actualizar la UI
        swLed.setChecked(e.optBoolean("led"));
        swVentilador.setChecked(e.optBoolean("ventilador"));
        actualizandoSwitches = false;

        // El dispositivo está en línea si no avisó caída (Last Will) y sus datos son recientes
        JSONArray lecturas = cache.getLecturas();
        long ultimaTs = lecturas.length() > 0 && lecturas.optJSONObject(0) != null
                ? lecturas.optJSONObject(0).optLong("ts") : 0;
        boolean reciente = System.currentTimeMillis() / 1000 - ultimaTs < DATO_ANTIGUO_S;
        boolean online = e.optBoolean("online", false) && reciente;
        tvDispositivo.setText("Raspberry " + BuildConfig.DEVICE_ID + ": " + (online ? "EN LÍNEA" : "SIN SEÑAL"));
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
              .append(l.optBoolean("movimiento") ? "MOV" : "-")
              .append(l.optBoolean("verificado", true) ? "" : "  ⚠")
              .append('\n');
        }
        tvHistorial.setText(sb.length() > 0 ? sb.toString() : "Sin datos");
    }
}
