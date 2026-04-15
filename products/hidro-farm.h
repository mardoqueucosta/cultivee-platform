/*
  Cultivee - Produto: Hidro Farm (versao Premium)
  ESP32-WROOM-32D + Modulo Rele 4 canais (expansivel ate 8)
  Controle hidroponico avancado: luz, bomba, ventilacao, aeracao
  (+ slots preparados para reles extras e sensores analogicos)

  NOTA: Este produto comeca como copia funcional do hidro. Os slots de
  expansao estao marcados com "TODO HIDRO-FARM EXTRA" e devem ser ativados
  conforme a necessidade (mais reles, sensores pH/EC/temp/nivel).
*/

#ifndef PRODUCT_HIDRO_FARM_H
#define PRODUCT_HIDRO_FARM_H

// ===== VERSAO =====
#define FIRMWARE_VERSION   "4.0.0"

// ===== MODULOS ATIVOS =====
#define MOD_HIDROFARM

// ===== IDENTIDADE =====
#define MODULE_TYPE        "hidro-farm"
#define PRODUCT_NAME       "Cultivee Hidro Farm"
#define MDNS_NAME          "cultivee-hidro-farm"
#define AP_SSID            "Cultivee-HidroFarm"

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
// Reles principais (iguais ao hidro — mantidos por compatibilidade)
#define RELE_LAMPADA     4    // IN1 do modulo rele (GPIO4)
#define RELE_BOMBA       5    // IN2 do modulo rele (GPIO5)
#define RELE_VENTILACAO  18   // IN3 do modulo rele (GPIO18)
#define RELE_AERACAO     19   // IN4 do modulo rele (GPIO19)
#define LED_ONBOARD      2    // LED azul da placa
#define RESET_BTN        0    // Botao BOOT (GPIO0) - segurar 3s = reset WiFi
#define RELE_ON          LOW    // Modulo rele ativa em LOW
#define RELE_OFF         HIGH

// TODO HIDRO-FARM EXTRA: Reles adicionais (modulo de 8 canais)
// Descomente e ative em mod_hidrofarm.h quando for usar.
// #define RELE_EXTRA_1    13   // IN5 - ex: luz secundaria / UV
// #define RELE_EXTRA_2    14   // IN6 - ex: bomba dreno
// #define RELE_EXTRA_3    25   // IN7 - ex: resistencia aquecedor
// #define RELE_EXTRA_4    26   // IN8 - ex: cooler / nebulizador

// ===== RTC DS3231 (I2C) =====
#define RTC_SDA        21   // I2C Data (GPIO21)
#define RTC_SCL        22   // I2C Clock (GPIO22)
#define RTC_ADDRESS    0x68 // DS3231 I2C address

// TODO HIDRO-FARM EXTRA: Sensores analogicos (ADC1 — imune a WiFi)
// Todos input-only, ideais para leituras analogicas estaveis.
// #define PIN_PH           34   // ADC1_CH6, input-only
// #define PIN_EC           35   // ADC1_CH7, input-only
// #define PIN_TEMP_WATER   32   // ADC1_CH4 (DS18B20 tambem funciona em digital)
// #define PIN_LEVEL        33   // ADC1_CH5 (sensor de nivel d'agua)

// ===== NTP =====
#define NTP_SERVER     "pool.ntp.org"
#define GMT_OFFSET     -3 * 3600
#define DST_OFFSET     0

// ===== FASES =====
#define MAX_PHASES     10

// ===== BOARD =====
// Compilar com: esp32:esp32:esp32doit-devkit-v1:PartitionScheme=min_spiffs
// Porta USB: a definir (quando for gravar, atualizar compile.sh)
// Particao: min_spiffs (1.9MB app0 + 1.9MB app1 OTA)

#endif
