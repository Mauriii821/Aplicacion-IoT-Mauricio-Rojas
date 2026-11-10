package com.example.webservicessencillo.seguridad;

import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * Integridad de los mensajes MQTT (ISO 27000).
 * Formato de cada mensaje: {"data": "<json en texto>", "firma": "<HMAC-SHA256 de data>"}
 * Es el mismo formato que usa raspbian/seguridad.py, así ambos lados verifican al otro.
 */
public final class Firma {

    private Firma() { }

    public static String hmacSha256(String clave, String texto) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(clave.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] bytes = mac.doFinal(texto.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : bytes) hex.append(String.format("%02x", b));
            return hex.toString();
        } catch (Exception e) {
            throw new IllegalStateException("No se pudo calcular HMAC", e);
        }
    }

    /** Agrega la marca de tiempo, firma y devuelve el mensaje listo para publicar. */
    public static String empaquetar(String clave, JSONObject datos) throws JSONException {
        datos.put("ts", System.currentTimeMillis() / 1000);
        String texto = datos.toString();
        JSONObject sobre = new JSONObject();
        sobre.put("data", texto);
        sobre.put("firma", hmacSha256(clave, texto));
        return sobre.toString();
    }

    /** Devuelve los datos si la firma es válida; null si el mensaje fue alterado. */
    public static JSONObject desempaquetar(String clave, String crudo) {
        try {
            JSONObject sobre = new JSONObject(crudo);
            String texto = sobre.getString("data");
            String firma = sobre.getString("firma");
            String esperada = hmacSha256(clave, texto);
            // Comparación en tiempo constante
            if (!MessageDigest.isEqual(esperada.getBytes(StandardCharsets.UTF_8),
                    firma.getBytes(StandardCharsets.UTF_8))) {
                return null;
            }
            return new JSONObject(texto);
        } catch (JSONException e) {
            return null;
        }
    }
}
