/*
  Cultivee - Produto: Camera Standalone
  ESP32-WROVER-DEV + Camera OV2640 (sem controle de reles)
  Monitoramento visual — composto com modulo ctrl via grupos no servidor
*/

#ifndef PRODUCT_CAM_H
#define PRODUCT_CAM_H

// ===== MODULOS ATIVOS =====
#define MOD_CAM
// SEM MOD_HIDRO — sem reles, sem fases

// ===== IDENTIDADE =====
#define MODULE_TYPE        "cam"
#define PRODUCT_NAME       "Cultivee Cam"
#define MDNS_NAME          "cultivee-cam"
#define AP_SSID            "Cultivee-Cam"

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

// ===== HARDWARE (ESP32-WROVER-DEV) =====
#define LED_ONBOARD   2    // LED azul da placa
#define RESET_BTN     0    // Botao BOOT (GPIO0) - segurar 3s = reset WiFi

// ===== PINOS CAMERA (ESP32-WROVER-DEV OV2640) =====
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     21
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       19
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM        5
#define Y2_GPIO_NUM        4
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ===== NTP =====
#define NTP_SERVER     "pool.ntp.org"
#define GMT_OFFSET     -3 * 3600
#define DST_OFFSET     0

// ===== BOARD =====
// Compilar com: esp32:esp32:esp32wroverkit
// Porta: COM9

#endif
