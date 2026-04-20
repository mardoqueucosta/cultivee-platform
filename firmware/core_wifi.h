/*
  Cultivee Core - WiFi Manager, AP, NTP
  Gerencia credenciais WiFi, modo AP hibrido, NTP e reconexao
*/

#ifndef CORE_WIFI_H
#define CORE_WIFI_H

// ===================== TELEMETRIA WIFI (v4.1.8) =====================
// Expostas via register.ctrl_data para dashboard/debug/suporte
String wifiLastError      = "";  // "OK","NO_SSID","WRONG_PASS","BEACON_LOST","AUTH_EXPIRE","DISCONNECTED","TIMEOUT","IDLE","UNKNOWN"
unsigned long wifiLastConnectedMs = 0;  // millis() da ultima vez que STA ficou up (GOT_IP)
int wifiDisconnectCount   = 0;   // quantas quedas desde o boot
bool wifiAutoReconnectSet = false;  // guard pra so chamar setAutoReconnect 1x

// Traduz status do driver em rotulo de erro legivel
String wifiStatusToError(wl_status_t s) {
  switch (s) {
    case WL_CONNECTED:       return "OK";
    case WL_NO_SSID_AVAIL:   return "NO_SSID";
    case WL_CONNECT_FAILED:  return "WRONG_PASS";
    case WL_CONNECTION_LOST: return "LOST";
    case WL_DISCONNECTED:    return "DISCONNECTED";
    case WL_IDLE_STATUS:     return "IDLE";
    case WL_NO_SHIELD:       return "NO_SHIELD";
    case WL_SCAN_COMPLETED:  return "SCAN";
    default:                 return "UNKNOWN";
  }
}

// Callback de eventos WiFi — detecta queda/reconexao em ~1s (vs 60s do poll antigo)
// Roda num task FreeRTOS dedicado; so atualiza flags (leve) — transicoes de MODE
// continuam sendo feitas em tryReconnectWiFi/checkWiFiConnection no main loop.
void onWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      Serial.printf("[WiFi evt] GOT_IP %s | RSSI %d dBm\n",
        WiFi.localIP().toString().c_str(), WiFi.RSSI());
      wifiLastError = "OK";
      wifiLastConnectedMs = millis();
      break;
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED: {
      uint8_t reason = info.wifi_sta_disconnected.reason;
      // Mapeamento dos codigos mais comuns (esp_wifi_types.h)
      if (reason == 201)      wifiLastError = "NO_SSID";        // NO_AP_FOUND
      else if (reason == 202 || reason == 15) wifiLastError = "WRONG_PASS"; // AUTH_FAIL / 4WAY_TIMEOUT
      else if (reason == 200) wifiLastError = "BEACON_LOST";    // BEACON_TIMEOUT
      else if (reason == 2)   wifiLastError = "AUTH_EXPIRE";
      else if (reason == 8)   wifiLastError = "ASSOC_LEAVE";
      else                    wifiLastError = "DISCONNECTED";
      Serial.printf("[WiFi evt] DISCONNECTED reason=%u err=%s\n", reason, wifiLastError.c_str());
      if (currentMode == MODE_CONNECTED) {
        wifiDisconnectCount++;
        // A transicao MODE_CONNECTED -> MODE_OFFLINE eh feita em checkWiFiConnection
      }
      break;
    }
    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
      Serial.println("[WiFi evt] STA_CONNECTED (aguardando IP)");
      break;
    default:
      break;
  }
}

// ===================== WIFI MANAGER =====================

void loadWiFiCredentials() {
  prefs.begin("wifi", true);
  savedSSID = prefs.getString("ssid", "");
  savedPass = prefs.getString("pass", "");
  prefs.end();
}

void saveWiFiCredentials(String ssid, String pass) {
  prefs.begin("wifi", false);
  prefs.putString("ssid", ssid);
  prefs.putString("pass", pass);
  prefs.end();
}

void clearWiFiCredentials() {
  prefs.begin("wifi", false);
  prefs.remove("ssid");
  prefs.remove("pass");
  prefs.end();
  savedSSID = "";
  savedPass = "";
}

void startAP() {
  WiFi.softAP(AP_SSID, NULL, 6, 0, 4);  // Canal 6, sem senha, max 4 clientes
  delay(100);
  esp_wifi_set_ps(WIFI_PS_NONE);  // Desabilita power saving — melhora latencia
  #ifdef MOD_CAM
  WiFi.setTxPower(WIFI_POWER_8_5dBm);  // WROVER: TX mais baixo = AP mais estavel
  #endif
  dnsServer.start(53, "*", WiFi.softAPIP());
  Serial.printf("AP ativo: %s IP: %s\n", AP_SSID, WiFi.softAPIP().toString().c_str());
}

bool connectWiFi() {
  if (savedSSID.length() == 0) return false;
  Serial.printf("Conectando em '%s'...\n", savedSSID.c_str());
  WiFi.mode(WIFI_AP_STA);
  // setAutoReconnect: stack ESP32 reconecta sozinho em C — complementa tryReconnectWiFi
  if (!wifiAutoReconnectSet) {
    WiFi.setAutoReconnect(true);
    wifiAutoReconnectSet = true;
  }
  startAP();
  WiFi.begin(savedSSID.c_str(), savedPass.c_str());
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  wl_status_t finalStatus = WiFi.status();
  if (finalStatus == WL_CONNECTED) {
    Serial.printf("Conectado! IP STA: %s | IP AP: %s\n",
      WiFi.localIP().toString().c_str(), WiFi.softAPIP().toString().c_str());
    wifiLastError = "OK";
    wifiLastConnectedMs = millis();
    return true;
  }
  // Timeout bloqueante de 15s terminou sem conectar — classifica erro
  // (onWiFiEvent normalmente ja populou wifiLastError; so sobrescreve se ficou vazio)
  if (finalStatus == WL_IDLE_STATUS || finalStatus == WL_DISCONNECTED) {
    if (wifiLastError.length() == 0 || wifiLastError == "OK") wifiLastError = "TIMEOUT";
  } else {
    wifiLastError = wifiStatusToError(finalStatus);
  }
  Serial.printf("Falha ao conectar WiFi (%s) — AP continua ativo\n", wifiLastError.c_str());
  return false;
}

void startSetupMode() {
  WiFi.mode(WIFI_AP_STA);  // AP+STA para permitir scan de redes
  startAP();
  currentMode = MODE_SETUP;
  Serial.println("Modo SETUP — sem credenciais WiFi");
}

// ===================== RTC DS3231 =====================
// Compartilhado entre hidro e hidro-farm (mesma pinagem I2C, mesmo chip)

#if defined(MOD_HIDRO) || defined(MOD_HIDROFARM)
bool rtcAvailable = false;

uint8_t bcd2dec(uint8_t val) { return (val >> 4) * 10 + (val & 0x0F); }
uint8_t dec2bcd(uint8_t val) { return ((val / 10) << 4) + (val % 10); }

void rtcInit() {
  Wire.begin(RTC_SDA, RTC_SCL);
  Wire.beginTransmission(RTC_ADDRESS);
  if (Wire.endTransmission() == 0) {
    rtcAvailable = true;
    Serial.println("RTC DS3231 detectado");
  } else {
    Serial.println("RTC DS3231 nao encontrado");
  }
}

// Forward declaration — chamado após rtcInit() no hidro_setup()
void rtcSeedFromCompileTime();

bool rtcRead(struct tm *t) {
  Wire.beginTransmission(RTC_ADDRESS);
  Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;
  Wire.requestFrom((uint8_t)RTC_ADDRESS, (uint8_t)7);
  if (Wire.available() < 7) return false;

  t->tm_sec  = bcd2dec(Wire.read() & 0x7F);
  t->tm_min  = bcd2dec(Wire.read());
  t->tm_hour = bcd2dec(Wire.read() & 0x3F);
  Wire.read(); // dia da semana (ignorado)
  t->tm_mday = bcd2dec(Wire.read());
  t->tm_mon  = bcd2dec(Wire.read() & 0x1F) - 1; // tm_mon: 0-11
  t->tm_year = bcd2dec(Wire.read()) + 100;        // tm_year: anos desde 1900
  t->tm_isdst = 0;
  mktime(t); // normaliza (calcula tm_wday, tm_yday)
  return true;
}

void rtcWrite(struct tm *t) {
  Wire.beginTransmission(RTC_ADDRESS);
  Wire.write(0x00);
  Wire.write(dec2bcd(t->tm_sec));
  Wire.write(dec2bcd(t->tm_min));
  Wire.write(dec2bcd(t->tm_hour));
  Wire.write(dec2bcd(t->tm_wday + 1)); // DS3231: 1-7
  Wire.write(dec2bcd(t->tm_mday));
  Wire.write(dec2bcd(t->tm_mon + 1));  // DS3231: 1-12
  Wire.write(dec2bcd(t->tm_year - 100)); // DS3231: 00-99
  Wire.endTransmission();
  Serial.printf("RTC atualizado: %02d/%02d/%04d %02d:%02d:%02d\n",
    t->tm_mday, t->tm_mon + 1, t->tm_year + 1900, t->tm_hour, t->tm_min, t->tm_sec);
}

void rtcSeedFromCompileTime() {
  const char *months = "JanFebMarAprMayJunJulAugSepOctNovDec";
  char mon[4]; int day, year, hour, minute, sec;
  sscanf(__DATE__, "%s %d %d", mon, &day, &year);
  sscanf(__TIME__, "%d:%d:%d", &hour, &minute, &sec);
  int monthIdx = 0;
  for (int i = 0; i < 12; i++) {
    if (strncmp(mon, months + i * 3, 3) == 0) { monthIdx = i; break; }
  }
  struct tm t = {0};
  t.tm_year = year - 1900; t.tm_mon = monthIdx; t.tm_mday = day;
  t.tm_hour = hour; t.tm_min = minute; t.tm_sec = sec;
  mktime(&t);
  Serial.printf("RTC seed: %02d/%02d/%04d %02d:%02d:%02d (compilacao)\n",
    day, monthIdx + 1, year, hour, minute, sec);
  rtcWrite(&t);
}
#endif // RTC DS3231

// ===================== NTP =====================

void setupNTP() {
  configTime(GMT_OFFSET, DST_OFFSET, NTP_SERVER);
  struct tm t;
  if (getLocalTime(&t, 5000)) {
    ntpSynced = true;
    Serial.printf("NTP sincronizado: %02d/%02d/%04d %02d:%02d:%02d\n",
      t.tm_mday, t.tm_mon + 1, t.tm_year + 1900, t.tm_hour, t.tm_min, t.tm_sec);
    #if defined(MOD_HIDRO) || defined(MOD_HIDROFARM)
    if (rtcAvailable) rtcWrite(&t);
    #endif
  } else {
    Serial.println("NTP: falha ao sincronizar");
  }
}

bool getCurrentTime(struct tm *t) {
  // NTP primeiro (mais preciso)
  if (getLocalTime(t, 0)) return true;
  // Fallback: RTC DS3231 (só aceita se ano >= 2024)
  #if defined(MOD_HIDRO) || defined(MOD_HIDROFARM)
  if (rtcAvailable && rtcRead(t) && t->tm_year >= (2024 - 1900)) return true;
  #endif
  return false;
}

// ===================== RECONEXAO =====================

void tryReconnectWiFi() {
  if (currentMode != MODE_OFFLINE) return;
  if (savedSSID.length() == 0) return;
  #ifdef MOD_CAM
  if (localStreamActive) return;
  #endif

  // Verifica se ja reconectou (setAutoReconnect + WiFi.begin de ciclo anterior)
  if (WiFi.status() == WL_CONNECTED) {
    currentMode = MODE_CONNECTED;
    wifiLastError = "OK";
    wifiLastConnectedMs = millis();
    Serial.printf("Reconectado! IP: %s\n", WiFi.localIP().toString().c_str());
    if (!ntpSynced) setupNTP();
    if (MDNS.begin(MDNS_NAME)) {
      MDNS.addService("http", "tcp", 80);
    }
    return;
  }

  // Dispara tentativa a cada 60s (nao-bloqueante)
  if (millis() - lastWiFiRetry < 60000) return;
  lastWiFiRetry = millis();
  Serial.printf("Reconexao WiFi (background, last_err=%s)...\n", wifiLastError.c_str());
  WiFi.begin(savedSSID.c_str(), savedPass.c_str());
}

void checkWiFiConnection() {
  if (currentMode == MODE_CONNECTED && WiFi.status() != WL_CONNECTED) {
    currentMode = MODE_OFFLINE;
    if (wifiLastError == "OK" || wifiLastError.length() == 0) {
      wifiLastError = wifiStatusToError(WiFi.status());
    }
    Serial.printf("WiFi desconectado (%s)! Modo OFFLINE — automacao continua\n",
      wifiLastError.c_str());
  }
}

#endif
