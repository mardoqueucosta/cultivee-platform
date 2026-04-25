/*
  Cultivee - Firmware Modular
  Plataforma IoT para cultivo inteligente

  Produto ativo definido em config.h (troca de produto = 1 linha)
  Modulos ativos definidos no product header (products/*.h)
*/

// ===== BIBLIOTECAS =====
#include <WiFi.h>
#include <esp_wifi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <DNSServer.h>
#include <HTTPClient.h>
#include <ESPmDNS.h>
#include <time.h>
#include <Wire.h>
#include <Update.h>
#include "esp_system.h"       // v4.1.26: brownout detector (esp_brownout_*)
#include "esp_ota_ops.h"      // v4.1.26: rollback manual A/B (esp_ota_set_boot_partition)
#include "soc/rtc_cntl_reg.h" // v4.1.26: RTC_CNTL_BROWN_OUT_REG
#include "soc/soc.h"
#include "config.h"

#ifdef MOD_CAM
#include "esp_camera.h"
#endif

// Exclusao mutua: so um produto hidroponico por vez
#if defined(MOD_HIDRO) && defined(MOD_HIDROFARM)
  #error "Escolha apenas um: MOD_HIDRO ou MOD_HIDROFARM em products/*.h"
#endif

// ===== TIPOS (definidos por modulos) =====
// Phase e compartilhada entre hidro e hidro-farm (mesma estrutura de fases)
#if defined(MOD_HIDRO) || defined(MOD_HIDROFARM)
struct Phase {
  char name[20];
  int days;
  int lightOnHour;
  int lightOnMin;
  int lightOffHour;
  int lightOffMin;
  int pumpOnDay;
  int pumpOffDay;
  int pumpOnNight;
  int pumpOffNight;
  int ventOnHour;
  int ventOnMin;
  int ventOffHour;
  int ventOffMin;
  int aerOnDay;
  int aerOffDay;
  int aerOnNight;
  int aerOffNight;
};
#endif

// ===== VARIAVEIS GLOBAIS CORE =====
enum Mode { MODE_SETUP, MODE_CONNECTED, MODE_OFFLINE };
Mode currentMode = MODE_SETUP;
Preferences prefs;
WebServer server(80);
DNSServer dnsServer;
String chipId;
String shortId;
bool ntpSynced = false;

// WiFi
String savedSSID = "";
String savedPass = "";

// Timers
unsigned long lastRegister = 0;
unsigned long lastLedUpdate = 0;
unsigned long lastWiFiRetry = 0;
#define WIFI_RETRY_INTERVAL 30000

// Polling adaptativo
unsigned long currentPollInterval = REGISTER_INTERVAL;
unsigned long lastPollCheck = 0;
#define POLL_FAST_INTERVAL 1000

// v4.1.26: timeout de provisionamento — depois de 30min em MODE_SETUP sem
// configurar WiFi, cai pra MODE_OFFLINE. Evita AP aberto indefinidamente
// (consumo + risco de outro cliente achar). Reset vira o botao BOOT (3s).
unsigned long setupStartMs = 0;
#define SETUP_MODE_TIMEOUT_MS (30UL * 60UL * 1000UL)  // 30 minutos

// v4.1.26: telemetria + protecao de heap.
// `min_free_heap` = menor heap ja observado desde o boot (detecta fragmentacao).
// Se o heap cair abaixo de HEAP_MIN_BYTES, reinicia preventivamente — melhor
// downtime curto e controlado do que crash aleatorio com NVS corrompido.
size_t minFreeHeap = 0xFFFFFFFF;
#define HEAP_MIN_BYTES 5000
unsigned long lastHeapCheck = 0;
#define HEAP_CHECK_INTERVAL 10000  // 10s entre checagens

// v4.1.26: OTA A/B rollback manual (sem precisar rebuildar o bootloader).
// Estrategia:
//   - NVS guarda "last_good_ver" (versao que ja passou no self-test) e
//     "boot_attempts" (boots consecutivos SEM chegar a self-test).
//   - Self-test = 1 register bem-sucedido no servidor (WiFi OK + HTTP 200).
//   - Se FIRMWARE_VERSION != last_good_ver: incrementa boot_attempts.
//     Apos self-test OK: last_good_ver=FIRMWARE_VERSION, boot_attempts=0.
//   - Se boot_attempts >= MAX_BOOT_ATTEMPTS no inicio do setup(), troca pra
//     outra particao OTA via esp_ota_set_boot_partition() + restart.
//   Fail safe sem dependencia do bootloader.
bool otaSelfTestPassed = false;
int  otaBootAttempts   = 0;
String otaLastGoodVersion = "";
#define OTA_MAX_BOOT_ATTEMPTS 3

// ===== VARIAVEIS GLOBAIS HIDRO / HIDRO-FARM =====
// Compartilhadas — so um dos dois modulos esta ativo por vez (exclusao mutua acima)
#if defined(MOD_HIDRO) || defined(MOD_HIDROFARM)
Phase phases[MAX_PHASES];
int numPhases = 0;
char startDate[12] = "2026-03-23";
bool modeAuto = true;
bool manualLight = false;
bool manualPump = false;
bool lightState = false;
bool pumpState = false;
bool ventilationState = false;
bool aerationState = false;
unsigned long lastAutoCheck = 0;
#endif

// ===== VARIAVEIS GLOBAIS HIDRO-FARM EXTRA =====
// Reles extras do hidro-farm — NAO participam da automacao por fase nem do modeAuto global
#ifdef MOD_HIDROFARM
// Rele da valvula de entrada — controlado pela automacao de nivel (se valveAuto=true) ou manual
bool valveEntradaState = false;
// Rele da bomba de homogeneizacao — sempre manual puro
bool bombaHomoState    = false;

// Sistema de reposicao automatica do reservatorio
bool valveAuto         = true;    // true = automacao por boias controla a valvula; false = manual puro
bool highLevelState    = false;   // Estado confirmado (pos-debounce) da boia ALTA
bool lowLevelState     = false;   // Estado confirmado (pos-debounce) da boia BAIXA
bool highLevelRaw      = false;   // Ultima leitura raw (para debounce de 2 amostras)
bool lowLevelRaw       = false;
unsigned long lastLevelRead = 0;  // Timestamp da ultima leitura (debounce + throttle)

// Sensor DHT11 (temperatura + umidade)
int dhtTemperature       = 0;     // Temperatura em graus Celsius (inteiro)
int dhtHumidity          = 0;     // Umidade relativa em % (inteiro)
bool dhtValid            = false; // true se a ultima leitura foi bem-sucedida
unsigned long lastDhtRead = 0;    // Timestamp da ultima tentativa de leitura
unsigned long lastDhtOk   = 0;    // Timestamp da ultima leitura bem-sucedida (para "atualizado ha Xs")
#endif

// ===== VARIAVEIS GLOBAIS CAMERA =====
#ifdef MOD_CAM
bool cameraReady = false;
bool camLiveMode = false;
bool localStreamActive = false;  // true durante /stream local — suspende registro
unsigned long lastLiveFrame = 0;
#define LIVE_FRAME_INTERVAL 800
#define LIVE_MAX_DURATION 600000  // v4.1.10: 10 min (antes 2 min — muito curto para observacao de transplante/poda)
unsigned long liveStartTime = 0;
framesize_t captureFrameSize = FRAMESIZE_SVGA;  // SVGA 800x600 — melhor relacao qualidade/tamanho para processamento
int captureQuality = 5;                          // q5 — maxima nitidez para deteccao em plantas
#endif

// ===== FORWARD DECLARATIONS (funcoes compostas usadas pelos modulos) =====
String buildStatusJSON();
#ifdef MOD_HIDRO
void hidro_loop();
#endif
#ifdef MOD_HIDROFARM
void hidrofarm_loop();
#endif

// ===== INCLUDES DOS MODULOS (apos globals — funcoes referenciam as variaveis) =====
#include "core_wifi.h"
#include "core_server.h"
#include "core_ota.h"
#include "core_register.h"

#ifdef MOD_HIDRO
#include "mod_hidro.h"
#endif
#ifdef MOD_HIDROFARM
#include "mod_hidrofarm.h"
#endif
#ifdef MOD_CAM
#include "mod_cam.h"
#endif

// ===== FUNCOES COMPOSTAS =====

// Status JSON completo (usado por /status e /relay)
String buildStatusJSON() {
  String json = "{";
  json += "\"chip_id\":\"" + chipId + "\",";
  json += "\"short_id\":\"" + shortId + "\",";
  json += "\"uptime\":" + String(millis() / 1000) + ",";
  json += "\"free_heap\":" + String(ESP.getFreeHeap()) + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"ssid\":\"" + WiFi.SSID() + "\",";
  json += "\"rssi\":" + String(WiFi.RSSI());

  #ifdef MOD_HIDRO
  json += "," + hidro_status_json();
  #endif
  #ifdef MOD_HIDROFARM
  json += "," + hidrofarm_status_json();
  #endif
  #ifdef MOD_CAM
  json += cam_status_json();
  #endif

  json += "}";
  return json;
}

// Dashboard HTML completo (composicao modular)
void handleDashboard() {
  String html = R"rawliteral(<!DOCTYPE html><html><head>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<meta charset='UTF-8'>
<title>)rawliteral" + String(PRODUCT_NAME) + R"rawliteral(</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#1a1d23;color:#e0e0e0;max-width:480px;margin:0 auto}
.top{background:#22252d;padding:16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #2a2d35}
.logo{width:36px;height:36px;background:#27ae60;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:1.1rem}
.top h1{color:#27ae60;font-size:1.1rem;margin:0}.top p{color:#888;font-size:0.75rem;margin:0}
.card{background:#22252d;border-radius:12px;margin:10px;padding:14px;border:1px solid #2a2d35}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.stat{background:#1a1d23;border-radius:8px;padding:10px;text-align:center}
.stat .lb{font-size:0.65rem;color:#888;text-transform:uppercase;font-weight:600}
.stat .vl{font-size:1.3rem;font-weight:700;color:#27ae60}
.ind{display:flex;justify-content:center;gap:12px;padding:8px 0;font-size:0.85rem}
.footer{text-align:center;padding:12px;font-size:0.7rem;color:#555}
.footer a{color:#27ae60;text-decoration:none}
@keyframes spin{to{transform:rotate(360deg)}}
</style></head><body>
<div class='top'><div class='logo'>C</div><div><h1>CULTIVEE</h1><p>)rawliteral" + String(PRODUCT_NAME) + R"rawliteral(</p></div></div>
)rawliteral";

  // Modulos contribuem com seus cards
  #ifdef MOD_CAM
  html += cam_dashboard_html();
  #endif
  #ifdef MOD_HIDRO
  html += hidro_dashboard_html();
  #endif
  #ifdef MOD_HIDROFARM
  html += hidrofarm_dashboard_html();
  #endif

  // WiFi telemetry (v4.1.8+) — cross-produto, antes do footer
  {
    String errColor = (wifiLastError == "OK" || wifiLastError == "") ? "#27ae60" : "#e74c3c";
    String errText  = (wifiLastError == "") ? "OK" : wifiLastError;
    String dropColor = (wifiDisconnectCount > 0) ? "#e74c3c" : "#666";
    html += "<div style='text-align:center;font-size:0.7rem;color:#666;padding:8px 10px;margin:8px 10px 0;border-top:1px dashed #333'>";
    html += "&#128246; <span style='color:" + errColor + ";font-weight:600'>" + errText + "</span>";
    html += " &middot; " + String(WiFi.RSSI()) + " dBm";
    html += " &middot; <span style='color:" + dropColor + "'>" + String(wifiDisconnectCount) + " quedas</span>";
    if (wifiLastConnectedMs > 0 && millis() > wifiLastConnectedMs) {
      unsigned long onlineSec = (millis() - wifiLastConnectedMs) / 1000;
      unsigned long oh = onlineSec / 3600, om = (onlineSec % 3600) / 60;
      String onlineStr = (oh > 0) ? (String(oh) + "h " + String(om) + "min")
                                   : (om > 0 ? (String(om) + "min") : (String(onlineSec) + "s"));
      html += " &middot; online ha " + onlineStr;
    }
    html += "</div>";
  }

  html += "<div class='footer'>";
  html += "<a href='/setup-wifi'>&#9881; WiFi</a> &nbsp;|&nbsp; <a href='/update'>&#8679; Firmware</a> &nbsp;|&nbsp; " + String(PRODUCT_NAME) + " v" + String(FIRMWARE_VERSION);
  html += "</div>";

  // JavaScript dos modulos
  html += "<script>";
  #ifdef MOD_HIDRO
  html += hidro_dashboard_js();
  #endif
  #ifdef MOD_HIDROFARM
  html += hidrofarm_dashboard_js();
  #endif
  #ifdef MOD_CAM
  html += cam_dashboard_js();
  #endif
  html += "</script></body></html>";

  server.send(200, "text/html", html);
}

// ===== SERIAL COMMANDS =====

void handleSerialCommands() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  #ifdef MOD_HIDRO
  hidro_serial_command(cmd);
  #endif
  #ifdef MOD_HIDROFARM
  hidrofarm_serial_command(cmd);
  #endif
}

// ===== SETUP =====

void setup() {
  Serial.begin(115200);
  delay(1000);

  // v4.1.26: A/B rollback check — ANTES de qualquer outra coisa, decide
  // se a imagem atual e confiavel. Se nao e, troca de particao e reinicia.
  {
    prefs.begin("ota_guard", false);
    otaLastGoodVersion = prefs.getString("last_good", "");
    otaBootAttempts    = prefs.getInt("attempts", 0);
    String current     = String(FIRMWARE_VERSION);
    if (current == otaLastGoodVersion) {
      // Firmware atual ja foi confirmado antes — trata como valido, zera contador
      otaBootAttempts = 0;
      otaSelfTestPassed = true;
      prefs.putInt("attempts", 0);
    } else {
      // Imagem nova (ou ainda nao validada) — conta esta tentativa.
      otaBootAttempts += 1;
      prefs.putInt("attempts", otaBootAttempts);
      Serial.printf("OTA guard: boot #%d da versao %s (last_good=%s)\n",
        otaBootAttempts, current.c_str(), otaLastGoodVersion.c_str());
      if (otaBootAttempts > OTA_MAX_BOOT_ATTEMPTS) {
        const esp_partition_t *cur  = esp_ota_get_running_partition();
        const esp_partition_t *next = esp_ota_get_next_update_partition(NULL);
        // "next" aqui eh a OUTRA particao OTA (a anterior, quando rodando na nova)
        if (next && next != cur) {
          Serial.printf("OTA guard: %d boots sem self-test — ROLLBACK pra %s\n",
            otaBootAttempts, next->label);
          prefs.putInt("attempts", 0);  // zera antes de rebootar na outra
          prefs.end();
          esp_ota_set_boot_partition(next);
          delay(500);
          ESP.restart();
        } else {
          Serial.println("OTA guard: sem particao alternativa (single-slot) — seguindo em modo degradado");
        }
      }
    }
    prefs.end();
  }

  // v4.1.26: brownout detector — reset forcado se VDD cair abaixo do limiar.
  // Sem isso, oscilacoes de rede eletrica (comum no BR) podem corromper NVS
  // durante escrita. O detector vem habilitado por default no SDK, mas setamos
  // explicitamente o nivel pra garantir (0=2.43V default, 4=2.70V agressivo).
  // Nivel 4 evita escrita com tensao marginal — escolha recomendada pra campo.
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG,
    (1 << 31)        // RTC_CNTL_BROWN_OUT_ENA — habilita
    | (1 << 30)      // RTC_CNTL_BROWN_OUT_RST_ENA — reset no trigger
    | (4 << 22)      // RTC_CNTL_DBROWN_OUT_THRES — nivel 4 (~2.70V)
    | (0x3FF << 8)   // RTC_CNTL_BROWN_OUT_RST_WAIT — espera antes do reset
  );

  // Hardware comum
  pinMode(RESET_BTN, INPUT_PULLUP);
  pinMode(LED_ONBOARD, OUTPUT);

  // Modulos: setup hardware (cam depois do WiFi — câmera afeta rádio)
  #ifdef MOD_HIDRO
  hidro_setup();
  #endif
  #ifdef MOD_HIDROFARM
  hidrofarm_setup();
  #endif

  // Chip ID
  uint64_t mac = ESP.getEfuseMac();
  char macStr[13];
  snprintf(macStr, sizeof(macStr), "%04X%08X", (uint16_t)(mac >> 32), (uint32_t)mac);
  chipId = String(macStr);
  shortId = chipId.substring(chipId.length() - 4);

  // v4.1.34: identidade unica do AP/mDNS — sufixo de 6 hex chars do MAC.
  // Evita colisao quando 2 modulos do mesmo produto estao na mesma rede
  // (ex: 2 HIDROs em casa pra bench test). Vivem em core_wifi.h.
  String macSuffix = chipId.substring(chipId.length() - 6);    // ex: "A7DBCC"
  String macSuffixLower = macSuffix;
  macSuffixLower.toLowerCase();
  dynamicApSsid   = String(AP_SSID)   + "-" + macSuffix;       // "Cultivee-Hidro-A7DBCC"
  dynamicMdnsName = String(MDNS_NAME) + "-" + macSuffixLower;  // "cultivee-hidro-a7dbcc"

  Serial.println("\n=== " + String(PRODUCT_NAME) + " ===");
  Serial.printf("Chip ID: %s (%s)\n", chipId.c_str(), shortId.c_str());
  Serial.printf("AP SSID: %s | mDNS: %s.local\n",
    dynamicApSsid.c_str(), dynamicMdnsName.c_str());

  // WiFi — registra callback de eventos ANTES de begin() pra capturar GOT_IP/DISCONNECTED
  // (v4.1.8: detecta queda em ~1s em vez de esperar 60s do retry)
  WiFi.onEvent(onWiFiEvent);

  loadWiFiCredentials();
  if (savedSSID.length() > 0) {
    if (connectWiFi()) {
      currentMode = MODE_CONNECTED;
      setupNTP();
      if (MDNS.begin(dynamicMdnsName.c_str())) {
        Serial.printf("mDNS: %s.local\n", dynamicMdnsName.c_str());
        MDNS.addService("http", "tcp", 80);
      }
    } else {
      currentMode = MODE_OFFLINE;
      Serial.println("WiFi falhou, modo OFFLINE — AP ativo, automacao continua");
    }
  } else {
    startSetupMode();
  }

  // Camera: inicializar apos WiFi (DMA/PSRAM da camera afeta radio)
  #ifdef MOD_CAM
  cam_setup();
  #endif

  // Rotas: rota raiz dinamica
  server.on("/", []() {
    if (currentMode == MODE_SETUP) {
      handleSetupPage();
    } else {
      handleDashboard();
    }
  });

  // Rotas: modulos
  #ifdef MOD_HIDRO
  hidro_register_routes();
  #endif
  #ifdef MOD_HIDROFARM
  hidrofarm_register_routes();
  #endif
  #ifdef MOD_CAM
  cam_register_routes();
  #endif

  // Rotas: core (WiFi setup, captive portal)
  core_register_routes();

  // Rotas: OTA (atualizar firmware via navegador)
  ota_register_routes();

  server.begin();
  Serial.println("Web server iniciado");
}

// ===== LOOP =====

// v4.1.26: vigilancia de heap — atualiza minFreeHeap e reinicia se cair
// abaixo do threshold. Evita travas silenciosas de uptime alto (~30d+) por
// fragmentacao acumulada nas construcoes de JSON via `String +=`.
void checkHeapHealth() {
  if (millis() - lastHeapCheck < HEAP_CHECK_INTERVAL) return;
  lastHeapCheck = millis();
  size_t free = ESP.getFreeHeap();
  if (free < minFreeHeap) minFreeHeap = free;
  if (free < HEAP_MIN_BYTES) {
    Serial.printf("!!! Heap critico (%u bytes). Reiniciando para recuperar !!!\n", (unsigned)free);
    delay(500);
    ESP.restart();
  }
}

// v4.1.26: se ficamos 30min em MODE_SETUP sem configurar WiFi, cai pra OFFLINE.
// AP continua ativo (permite controle local), mas encerra o captive portal
// agressivo. Reset via botao BOOT (3s) volta pro SETUP quando o usuario quiser.
void checkSetupTimeout() {
  if (currentMode != MODE_SETUP) { setupStartMs = 0; return; }
  if (setupStartMs == 0) { setupStartMs = millis(); return; }
  if (millis() - setupStartMs < SETUP_MODE_TIMEOUT_MS) return;
  Serial.println("SETUP timeout 30min — caindo pra MODE_OFFLINE (AP ativo, controle local)");
  currentMode = MODE_OFFLINE;
  setupStartMs = 0;
}

void loop() {
  checkResetButton();
  checkHeapHealth();
  checkSetupTimeout();

  handleSerialCommands();
  dnsServer.processNextRequest();
  server.handleClient();

  #ifdef MOD_HIDRO
  updateStatusLed();
  #endif
  #ifdef MOD_HIDROFARM
  updateStatusLedFarm();
  #endif

  // Automacao (connected ou offline)
  if (currentMode != MODE_SETUP) {
    #ifdef MOD_HIDRO
    hidro_loop();
    #endif
    #ifdef MOD_HIDROFARM
    hidrofarm_loop();
    #endif
  }

  // Camera live mode (push frames para servidor)
  #ifdef MOD_CAM
  if (currentMode == MODE_CONNECTED) {
    cam_loop();
  }
  #endif

  // Funcoes que precisam de WiFi (suspensas durante stream local)
  if (currentMode == MODE_CONNECTED) {
    #ifdef MOD_CAM
    if (!localStreamActive) {
    #endif
      pollCommands();
      registerOnServer();
      checkWiFiConnection();
    #ifdef MOD_CAM
    }
    #endif
  }

  // Reconexao em background
  if (currentMode == MODE_OFFLINE) {
    tryReconnectWiFi();
  }
}
