/*
  Cultivee - Produto: Hidro
  ESP32-WROOM-32D + Modulo Rele 2 canais
  Apenas controle hidroponico (sem camera)
*/

#ifndef PRODUCT_HIDRO_H
#define PRODUCT_HIDRO_H

// ===== MODULOS ATIVOS =====
#define MOD_HIDRO

// ===== IDENTIDADE =====
#define MODULE_TYPE        "ctrl"
#define PRODUCT_NAME       "Cultivee Hidro"
#define MDNS_NAME          "cultivee-ctrl"
#define AP_SSID            "Cultivee-Hidro"

// ===== SERVIDOR =====
#define LOCAL_SERVER_IP    "192.168.7.233"
#define LOCAL_SERVER_PORT  "5002"
#define REGISTER_INTERVAL  10000
#define WIFI_TIMEOUT       15000

#ifdef ENV_LOCAL
  #define SERVER_URL       "http://" LOCAL_SERVER_IP ":" LOCAL_SERVER_PORT
  #define APP_URL          "http://" LOCAL_SERVER_IP ":" LOCAL_SERVER_PORT
#endif
#ifdef ENV_PRODUCTION
  #define SERVER_URL       "http://app.cultivee.com.br"
  #define APP_URL          "https://app.cultivee.com.br"
#endif

// ===== HARDWARE (ESP32-WROOM-32D) =====
#define RELE_LAMPADA  4    // IN1 do modulo rele (GPIO4)
#define RELE_BOMBA    5    // IN2 do modulo rele (GPIO5)
#define LED_ONBOARD   2    // LED azul da placa
#define RESET_BTN     0    // Botao BOOT (GPIO0) - segurar 3s = reset WiFi
#define RELE_ON       LOW    // Modulo rele ativa em LOW
#define RELE_OFF      HIGH

// ===== NTP =====
#define NTP_SERVER     "pool.ntp.org"
#define GMT_OFFSET     -3 * 3600
#define DST_OFFSET     0

// ===== FASES =====
#define MAX_PHASES     10

// ===== BOARD =====
// Compilar com: esp32:esp32:esp32doit-devkit-v1
// Porta: COM7

#endif
