package com.example.webservicessencillo.datos;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.Iterator;

/**
 * Almacenamiento temporal en el teléfono.
 * - Guarda las últimas lecturas para mostrarlas aunque no haya conexión.
 * - Guarda los comandos que el usuario envía sin conexión; se envían
 *   automáticamente al reconectar (solo el último valor de cada actuador,
 *   para no ejecutar órdenes viejas en cadena).
 */
public class CacheLocal {

    private static final String PREFS = "cache_iot";
    private static final String K_LECTURAS = "lecturas";
    private static final String K_PENDIENTES = "comandos_pendientes";
    private static final String K_ACTUADORES = "actuadores";
    private static final int MAX_LECTURAS = 20;

    private final SharedPreferences prefs;

    public CacheLocal(Context ctx) {
        prefs = ctx.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    // ---------- Lecturas ----------
    public synchronized void guardarLectura(JSONObject lectura) {
        try {
            JSONArray actual = getLecturas();
            JSONArray nuevo = new JSONArray();
            nuevo.put(lectura);
            for (int i = 0; i < actual.length() && nuevo.length() < MAX_LECTURAS; i++) {
                nuevo.put(actual.get(i));
            }
            prefs.edit().putString(K_LECTURAS, nuevo.toString()).apply();
        } catch (JSONException ignored) { }
    }

    public synchronized void reemplazarLecturas(JSONArray historial) {
        prefs.edit().putString(K_LECTURAS, historial.toString()).apply();
    }

    public synchronized JSONArray getLecturas() {
        try {
            return new JSONArray(prefs.getString(K_LECTURAS, "[]"));
        } catch (JSONException e) {
            return new JSONArray();
        }
    }

    // ---------- Estado de actuadores ----------
    public synchronized void guardarActuadores(JSONObject estado) {
        prefs.edit().putString(K_ACTUADORES, estado.toString()).apply();
    }

    public synchronized JSONObject getActuadores() {
        try {
            return new JSONObject(prefs.getString(K_ACTUADORES, "{}"));
        } catch (JSONException e) {
            return new JSONObject();
        }
    }

    // ---------- Comandos pendientes ----------
    public synchronized void encolarComando(String actuador, boolean valor) {
        try {
            JSONObject pendientes = new JSONObject(prefs.getString(K_PENDIENTES, "{}"));
            pendientes.put(actuador, valor);   // reemplaza el anterior del mismo actuador
            prefs.edit().putString(K_PENDIENTES, pendientes.toString()).apply();
        } catch (JSONException ignored) { }
    }

    /** Devuelve y borra los comandos pendientes: {"led": true, ...} */
    public synchronized JSONObject sacarComandosPendientes() {
        JSONObject pendientes;
        try {
            pendientes = new JSONObject(prefs.getString(K_PENDIENTES, "{}"));
        } catch (JSONException e) {
            pendientes = new JSONObject();
        }
        prefs.edit().remove(K_PENDIENTES).apply();
        return pendientes;
    }

    public synchronized int contarPendientes() {
        try {
            JSONObject p = new JSONObject(prefs.getString(K_PENDIENTES, "{}"));
            int n = 0;
            for (Iterator<String> it = p.keys(); it.hasNext(); it.next()) n++;
            return n;
        } catch (JSONException e) {
            return 0;
        }
    }
}
