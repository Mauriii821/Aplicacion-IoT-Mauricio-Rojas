package com.example.webservicessencillo.datos;

import com.example.webservicessencillo.BuildConfig;

// La URL ahora se configura en local.properties (api.url) y no queda fija en el código.
public class Conexion {
    public static final String URL_WEB_SERVICES = BuildConfig.URL_WEB_SERVICES;
}
