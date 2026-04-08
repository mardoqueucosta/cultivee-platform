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
#include "config.h"

#ifdef MOD_CAM
#include "esp_camera.h"
#endif

// ===== TIPOS (definidos por modulos) =====
#ifdef MOD_HIDRO
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

// ===== VARIAVEIS GLOBAIS HIDRO =====
#ifdef MOD_HIDRO
Phase phases[MAX_PHASES];
int numPhases = 0;
char startDate[12] = "2026-03-23";
bool modeAuto = true;
bool manualLight = false;
bool manualPump = false;
bool lightState = false;
bool pumpState = false;
unsigned long lastAutoCheck = 0;
#endif

// ===== VARIAVEIS GLOBAIS CAMERA =====
#ifdef MOD_CAM
bool cameraReady = false;
bool camLiveMode = false;
bool localStreamActive = false;  // true durante /stream local — suspende registro
unsigned long lastLiveFrame = 0;
#define LIVE_FRAME_INTERVAL 800
#define LIVE_MAX_DURATION 120000
unsigned long liveStartTime = 0;
framesize_t captureFrameSize = FRAMESIZE_SVGA;  // SVGA 800x600 — melhor relacao qualidade/tamanho para processamento
int captureQuality = 5;                          // q5 — maxima nitidez para deteccao em plantas
#endif

// ===== FORWARD DECLARATIONS (funcoes compostas usadas pelos modulos) =====
String buildStatusJSON();
#ifdef MOD_HIDRO
void hidro_loop();
#endif

// ===== INCLUDES DOS MODULOS (apos globals — funcoes referenciam as variaveis) =====
#include "core_wifi.h"
#include "core_server.h"
#include "core_register.h"

#ifdef MOD_HIDRO
#include "mod_hidro.h"
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

  html += "<div class='footer'>";
  html += "<a href='/setup-wifi'>&#9881; Configurar WiFi</a> &nbsp;|&nbsp; " + String(PRODUCT_NAME) + " v1.0.1";
  html += "</div>";

  // JavaScript dos modulos
  html += "<script>";
  #ifdef MOD_HIDRO
  html += hidro_dashboard_js();
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
}

// ===== SETUP =====

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Hardware comum
  pinMode(RESET_BTN, INPUT_PULLUP);
  pinMode(LED_ONBOARD, OUTPUT);

  // Modulos: setup hardware
  #ifdef MOD_CAM
  cam_setup();
  #endif
  #ifdef MOD_HIDRO
  hidro_setup();
  #endif

  // Chip ID
  uint64_t mac = ESP.getEfuseMac();
  char macStr[13];
  snprintf(macStr, sizeof(macStr), "%04X%08X", (uint16_t)(mac >> 32), (uint32_t)mac);
  chipId = String(macStr);
  shortId = chipId.substring(chipId.length() - 4);

  Serial.println("\n=== " + String(PRODUCT_NAME) + " ===");
  Serial.printf("Chip ID: %s (%s)\n", chipId.c_str(), shortId.c_str());

  // WiFi
  loadWiFiCredentials();
  if (savedSSID.length() > 0) {
    if (connectWiFi()) {
      currentMode = MODE_CONNECTED;
      setupNTP();
      if (MDNS.begin(MDNS_NAME)) {
        Serial.printf("mDNS: %s.local\n", MDNS_NAME);
        MDNS.addService("http", "tcp", 80);
      }
    } else {
      currentMode = MODE_OFFLINE;
      Serial.println("WiFi falhou, modo OFFLINE — AP ativo, automacao continua");
    }
  } else {
    startSetupMode();
  }

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
  #ifdef MOD_CAM
  cam_register_routes();
  #endif

  // Rotas: core (WiFi setup, captive portal)
  core_register_routes();

  server.begin();
  Serial.println("Web server iniciado");
}

// ===== LOOP =====

void loop() {
  checkResetButton();

  handleSerialCommands();
  dnsServer.processNextRequest();
  server.handleClient();

  #ifdef MOD_HIDRO
  updateStatusLed();
  #endif

  // Automacao (connected ou offline)
  if (currentMode != MODE_SETUP) {
    #ifdef MOD_HIDRO
    hidro_loop();
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
