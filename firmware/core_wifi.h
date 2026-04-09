/*
  Cultivee Core - WiFi Manager, AP, NTP
  Gerencia credenciais WiFi, modo AP hibrido, NTP e reconexao
*/

#ifndef CORE_WIFI_H
#define CORE_WIFI_H

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
  dnsServer.start(53, "*", WiFi.softAPIP());
  Serial.printf("AP ativo: %s IP: %s\n", AP_SSID, WiFi.softAPIP().toString().c_str());
}

bool connectWiFi() {
  if (savedSSID.length() == 0) return false;
  Serial.printf("Conectando em '%s'...\n", savedSSID.c_str());
  WiFi.mode(WIFI_AP_STA);
  startAP();
  WiFi.begin(savedSSID.c_str(), savedPass.c_str());
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Conectado! IP STA: %s | IP AP: %s\n",
      WiFi.localIP().toString().c_str(), WiFi.softAPIP().toString().c_str());
    return true;
  }
  Serial.println("Falha ao conectar WiFi (AP continua ativo)");
  return false;
}

void startSetupMode() {
  WiFi.mode(WIFI_AP);
  startAP();
  currentMode = MODE_SETUP;
  Serial.println("Modo SETUP — sem credenciais WiFi");
}

// ===================== RTC DS3231 =====================

#ifdef MOD_HIDRO
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
#endif

// ===================== NTP =====================

void setupNTP() {
  configTime(GMT_OFFSET, DST_OFFSET, NTP_SERVER);
  struct tm t;
  if (getLocalTime(&t, 5000)) {
    ntpSynced = true;
    Serial.printf("NTP sincronizado: %02d/%02d/%04d %02d:%02d:%02d\n",
      t.tm_mday, t.tm_mon + 1, t.tm_year + 1900, t.tm_hour, t.tm_min, t.tm_sec);
    #ifdef MOD_HIDRO
    if (rtcAvailable) rtcWrite(&t);
    #endif
  } else {
    Serial.println("NTP: falha ao sincronizar");
  }
}

bool getCurrentTime(struct tm *t) {
  // NTP primeiro (mais preciso)
  if (getLocalTime(t, 0)) return true;
  // Fallback: RTC DS3231
  #ifdef MOD_HIDRO
  if (rtcAvailable && rtcRead(t)) return true;
  #endif
  return false;
}

// ===================== RECONEXAO =====================

void tryReconnectWiFi() {
  if (currentMode != MODE_OFFLINE) return;
  if (savedSSID.length() == 0) return;
  #ifdef MOD_CAM
  if (localStreamActive) return;  // Nao reconectar durante stream local
  #endif
  if (millis() - lastWiFiRetry < WIFI_RETRY_INTERVAL) return;
  lastWiFiRetry = millis();

  Serial.println("Tentando reconectar WiFi...");
  WiFi.begin(savedSSID.c_str(), savedPass.c_str());

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 5000) {
    delay(100);
    #ifdef MOD_HIDRO
    hidro_loop();  // continua automacao durante tentativa
    #endif
  }

  if (WiFi.status() == WL_CONNECTED) {
    currentMode = MODE_CONNECTED;
    Serial.printf("Reconectado! IP: %s\n", WiFi.localIP().toString().c_str());
    if (!ntpSynced) setupNTP();
    if (MDNS.begin(MDNS_NAME)) {
      MDNS.addService("http", "tcp", 80);
    }
  } else {
    Serial.println("Reconexao falhou, tentando novamente em 30s...");
  }
}

void checkWiFiConnection() {
  if (currentMode == MODE_CONNECTED && WiFi.status() != WL_CONNECTED) {
    currentMode = MODE_OFFLINE;
    Serial.println("WiFi desconectado! Modo OFFLINE — automacao continua");
  }
}

#endif
