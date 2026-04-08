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

// ===================== NTP =====================

void setupNTP() {
  configTime(GMT_OFFSET, DST_OFFSET, NTP_SERVER);
  struct tm t;
  if (getLocalTime(&t, 5000)) {
    ntpSynced = true;
    Serial.printf("NTP sincronizado: %02d/%02d/%04d %02d:%02d:%02d\n",
      t.tm_mday, t.tm_mon + 1, t.tm_year + 1900, t.tm_hour, t.tm_min, t.tm_sec);
  } else {
    Serial.println("NTP: falha ao sincronizar");
  }
}

bool getCurrentTime(struct tm *t) {
  return getLocalTime(t, 0);
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
