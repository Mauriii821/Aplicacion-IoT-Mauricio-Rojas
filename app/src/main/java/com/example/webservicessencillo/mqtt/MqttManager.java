package com.example.webservicessencillo.mqtt;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.example.webservicessencillo.BuildConfig;
import com.example.webservicessencillo.datos.CacheLocal;
import com.example.webservicessencillo.seguridad.Firma;

import org.eclipse.paho.client.mqttv3.IMqttActionListener;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.IMqttToken;
import org.eclipse.paho.client.mqttv3.MqttAsyncClient;
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.UUID;

import javax.net.ssl.SSLSocketFactory;

/**
 * Comunicación inalámbrica App <-> dispositivo IoT por MQTT sobre TLS.
 *
 * - Conexión cifrada (ssl://...:8883) con usuario y contraseña.
 * - Reconexión automática: Paho reconecta solo si se pierde la conexión, y si el
 *   primer intento falla se reintenta con espera progresiva (2, 4, 8 ... 60 s).
 * - Mensajes firmados con HMAC-SHA256; los que llegan alterados se descartan.
 * - Sin conexión, los comandos se guardan en CacheLocal y se envían al reconectar.
 */
public class MqttManager {

    public interface Listener {
        void onConexion(boolean conectado, String detalle);
        void onLectura(JSONObject lectura);
        void onEstado(JSONObject estado);
    }

    private static final String TAG = "MqttManager";
    private static final String[] ACTUADORES_PERMITIDOS = {"led", "ventilador"};

    private final String topicTelemetria;
    private final String topicEstado;
    private final String topicComandos;
    private final CacheLocal cache;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Listener listener;

    private MqttAsyncClient cliente;
    private boolean activo = false;
    private int intentos = 0;

    public MqttManager(Context ctx, Listener listener) {
        this.listener = listener;
        this.cache = new CacheLocal(ctx);
        String id = BuildConfig.DEVICE_ID;
        topicTelemetria = "iot/" + id + "/telemetria";
        topicEstado = "iot/" + id + "/estado";
        topicComandos = "iot/" + id + "/comandos";
    }

    public boolean estaConectado() {
        return cliente != null && cliente.isConnected();
    }

    /** Llamar en onStart(). */
    public void conectar() {
        activo = true;
        try {
            if (cliente == null) {
                String clientId = "app-android-" + UUID.randomUUID().toString().substring(0, 8);
                cliente = new MqttAsyncClient(BuildConfig.MQTT_URI, clientId, new MemoryPersistence());
                cliente.setCallback(callback);
            }
            if (cliente.isConnected()) return;

            MqttConnectOptions opciones = new MqttConnectOptions();
            opciones.setUserName(BuildConfig.MQTT_USER);
            opciones.setPassword(BuildConfig.MQTT_PASS.toCharArray());
            opciones.setSocketFactory(SSLSocketFactory.getDefault()); // TLS
            opciones.setHttpsHostnameVerificationEnabled(true);       // valida el certificado del broker
            opciones.setAutomaticReconnect(true);
            opciones.setCleanSession(true);
            opciones.setConnectionTimeout(10);
            opciones.setKeepAliveInterval(60);  // 60 s: menos tráfico = menos batería

            avisar(false, "Conectando...");
            cliente.connect(opciones, null, new IMqttActionListener() {
                @Override public void onSuccess(IMqttToken token) { /* connectComplete() hace el resto */ }

                @Override public void onFailure(IMqttToken token, Throwable e) {
                    Log.w(TAG, "Fallo al conectar", e);
                    avisar(false, "Sin conexión con el broker");
                    programarReintento();
                }
            });
        } catch (MqttException e) {
            Log.w(TAG, "Error al conectar", e);
            programarReintento();
        }
    }

    /** Llamar en onStop(): con la app en segundo plano no se gasta batería. */
    public void desconectar() {
        activo = false;
        ui.removeCallbacksAndMessages(null);
        if (cliente != null && cliente.isConnected()) {
            try {
                cliente.disconnect();
            } catch (MqttException e) {
                Log.w(TAG, "Error al desconectar", e);
            }
        }
    }

    private void programarReintento() {
        if (!activo) return;
        intentos++;
        long espera = Math.min(60, (long) Math.pow(2, Math.min(intentos, 6)));
        avisar(false, "Reintentando en " + espera + " s");
        ui.postDelayed(new Runnable() {
            @Override public void run() {
                if (activo && !estaConectado()) conectar();
            }
        }, espera * 1000);
    }

    /**
     * Envía un comando al actuador. Si no hay conexión, queda pendiente.
     * @return true si se envió ahora; false si quedó en cola.
     */
    public boolean enviarComando(String actuador, boolean valor) {
        if (!esActuadorPermitido(actuador)) return false;
        if (!estaConectado()) {
            cache.encolarComando(actuador, valor);
            return false;
        }
        try {
            JSONObject cmd = new JSONObject();
            cmd.put("actuador", actuador);
            cmd.put("valor", valor);
            MqttMessage msg = new MqttMessage(
                    Firma.empaquetar(BuildConfig.HMAC_KEY, cmd).getBytes(StandardCharsets.UTF_8));
            msg.setQos(1);  // entrega garantizada al menos una vez
            cliente.publish(topicComandos, msg);
            return true;
        } catch (JSONException | MqttException e) {
            Log.w(TAG, "No se pudo enviar el comando", e);
            cache.encolarComando(actuador, valor);
            return false;
        }
    }

    private static boolean esActuadorPermitido(String a) {
        for (String p : ACTUADORES_PERMITIDOS) if (p.equals(a)) return true;
        return false;
    }

    private void enviarPendientes() {
        JSONObject pendientes = cache.sacarComandosPendientes();
        for (Iterator<String> it = pendientes.keys(); it.hasNext(); ) {
            String actuador = it.next();
            // Se firman de nuevo con la hora actual, si no el nodo los rechazaría por antiguos
            enviarComando(actuador, pendientes.optBoolean(actuador));
        }
    }

    private final MqttCallbackExtended callback = new MqttCallbackExtended() {
        @Override
        public void connectComplete(boolean reconexion, String serverURI) {
            intentos = 0;
            try {
                cliente.subscribe(new String[]{topicTelemetria, topicEstado}, new int[]{1, 1});
            } catch (MqttException e) {
                Log.w(TAG, "Error al suscribirse", e);
            }
            int pendientes = cache.contarPendientes();
            enviarPendientes();
            avisar(true, (reconexion ? "Reconectado (TLS)" : "Conectado (TLS)")
                    + (pendientes > 0 ? " · " + pendientes + " comando(s) pendientes enviados" : ""));
        }

        @Override
        public void connectionLost(Throwable causa) {
            avisar(false, "Conexión perdida, reconectando...");
        }

        @Override
        public void messageArrived(String topic, MqttMessage message) {
            final JSONObject datos = Firma.desempaquetar(BuildConfig.HMAC_KEY,
                    new String(message.getPayload(), StandardCharsets.UTF_8));
            if (datos == null) {
                Log.w(TAG, "Mensaje con firma inválida descartado en " + topic);
                return;
            }
            if (topic.equals(topicTelemetria)) {
                cache.guardarLectura(datos);
                ui.post(new Runnable() { @Override public void run() { listener.onLectura(datos); } });
            } else if (topic.equals(topicEstado)) {
                cache.guardarActuadores(datos);
                ui.post(new Runnable() { @Override public void run() { listener.onEstado(datos); } });
            }
        }

        @Override
        public void deliveryComplete(IMqttDeliveryToken token) { }
    };

    private void avisar(final boolean conectado, final String detalle) {
        ui.post(new Runnable() {
            @Override public void run() { listener.onConexion(conectado, detalle); }
        });
    }
}
