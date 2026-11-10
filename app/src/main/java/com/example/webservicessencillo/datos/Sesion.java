package com.example.webservicessencillo.datos;

import java.util.HashMap;
import java.util.Map;

/**
 * Token de sesión entregado por la API al iniciar sesión.
 * Se guarda solo en memoria (no en disco): al cerrar la app hay que volver a entrar.
 */
public final class Sesion {

    private static String token;

    private Sesion() { }

    public static void iniciar(String nuevoToken) { token = nuevoToken; }

    public static void cerrar() { token = null; }

    public static boolean activa() { return token != null; }

    /** Cabeceras para las peticiones autenticadas a la API. */
    public static Map<String, String> cabeceras() {
        Map<String, String> h = new HashMap<>();
        if (token != null) h.put("Authorization", "Bearer " + token);
        return h;
    }
}
