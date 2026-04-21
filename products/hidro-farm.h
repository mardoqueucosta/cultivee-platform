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
#define FIRMWARE_VERSION   "4.1.26"

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
// 6 reles concretos do hidro-farm (modulo rele 8 canais — 2 canais livres para expansao futura)
#define RELE_LAMPADA         4    // IN1 - Luz (iluminacao principal)
#define RELE_BOMBA           5    // IN2 - Bomba de irrigacao (NFT / gotejamento)
#define RELE_VENTILACAO      16   // IN3 - Ventilacao (exaustor)
#define RELE_AERACAO         17   // IN4 - Aeracao (bolhas / oxigenacao raiz)
#define RELE_VALVULA_ENTRADA 18   // IN5 - Valvula de entrada de agua no reservatorio
#define RELE_BOMBA_HOMO      19   // IN6 - Bomba de homogeneizacao (mistura nutrientes)

#define LED_ONBOARD          2    // LED azul da placa
#define RESET_BTN            0    // Botao BOOT (GPIO0) - segurar 3s = reset WiFi
#define RELE_ON              LOW    // Modulo rele ativa em LOW
#define RELE_OFF             HIGH

// ===== SENSORES DE NIVEL (boias reed-switch tipo float lateral) =====
// Boia tipo "normally open" (NO): contato ABRE quando sem agua, FECHA quando agua sobe.
// Com INPUT_PULLUP: sem agua = HIGH (pullup), com agua = LOW (contato fecha pro GND).
// level_low/level_high = true quando a boia DETECTA AGUA (GPIO LOW).
// level_low = false → sem agua no nivel da boia baixa → PRECISA ENCHER.
#define SENSOR_NIVEL_ALTO    13   // Boia alta — true quando agua atinge nivel maximo
#define SENSOR_NIVEL_BAIXO   14   // Boia baixa — true quando agua esta acima do nivel minimo
#define LEVEL_SENSOR_ACTIVE  LOW  // LOW = boia detectou agua (contato fechado)

// ===== SENSOR DHT11 (temperatura + umidade ambiente) =====
// Modulo de 3 pinos (+ / out / -). Output digital 1-wire.
// Leitura inteira (sem casa decimal). Minimo 1s entre leituras — usamos 5s.
#define DHT_PIN              25   // Pino "out" do modulo DHT11

// ===== RTC DS3231 (I2C) =====
#define RTC_SDA        21   // I2C Data (GPIO21)
#define RTC_SCL        22   // I2C Clock (GPIO22)
#define RTC_ADDRESS    0x68 // DS3231 I2C address

// TODO HIDRO-FARM EXTRA: Sensores analogicos (ADC1 — imune a WiFi)
// Todos input-only, ideais para leituras analogicas estaveis.
// #define PIN_PH           34   // ADC1_CH6, input-only
// #define PIN_EC           35   // ADC1_CH7, input-only
// #define PIN_TEMP_WATER   32   // ADC1_CH4 (DS18B20 tambem funciona em digital)
// #define PIN_CO2          33   // ADC1_CH5 (sensor de CO2 ou outro)

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
