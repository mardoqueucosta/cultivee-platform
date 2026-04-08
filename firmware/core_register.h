/*
  Cultivee Core - Registro no servidor, polling e despacho de comandos
*/

#ifndef CORE_REGISTER_H
#define CORE_REGISTER_H

// ===================== JSON HELPERS =====================

String jsonVal(String json, String key) {
  String search = "\"" + key + "\":\"";
  int start = json.indexOf(search);
  if (start < 0) return "";
  start += search.length();
  int end = json.indexOf("\"", start);
  return (end > start) ? json.substring(start, end) : "";
}

int jsonInt(String json, String key) {
  String search = "\"" + key + "\":";
  int start = json.indexOf(search);
  if (start < 0) return -1;
  String rest = json.substring(start + search.length());
  // Suporta valores com ou sem aspas: "key":1 ou "key":"1"
  if (rest.startsWith("\"")) rest = rest.substring(1);
  return rest.toInt();
}

// ===================== COMMAND DISPATCH =====================

// Forward declarations — cada modulo implementa sua funcao de processar comandos
#ifdef MOD_HIDRO
bool hidro_process_command(String cmd, String obj);
#endif
#ifdef MOD_CAM
bool cam_process_command(String cmd, String obj);
#endif

void processPendingCommands(String response) {
  int cmdsStart = response.indexOf("\"commands\":[");
  if (cmdsStart < 0) return;

  int arrStart = response.indexOf("[", cmdsStart);
  int arrEnd = response.lastIndexOf("]");
  if (arrStart < 0 || arrEnd < 0 || arrEnd <= arrStart + 1) return;

  String cmdsStr = response.substring(arrStart + 1, arrEnd);
  Serial.printf("Cmds pendentes: %s\n", cmdsStr.c_str());

  int pos = 0;
  while (pos < (int)cmdsStr.length()) {
    int objStart = cmdsStr.indexOf("{", pos);
    if (objStart < 0) break;
    int objEnd = cmdsStr.indexOf("}", objStart);
    if (objEnd < 0) break;

    String obj = cmdsStr.substring(objStart, objEnd + 1);
    pos = objEnd + 1;

    String cmd = jsonVal(obj, "cmd");
    Serial.printf("Exec: %s\n", cmd.c_str());

    bool handled = false;

    #ifdef MOD_HIDRO
    if (!handled) handled = hidro_process_command(cmd, obj);
    #endif
    #ifdef MOD_CAM
    if (!handled) handled = cam_process_command(cmd, obj);
    #endif

    if (!handled) {
      Serial.printf("Comando desconhecido: %s\n", cmd.c_str());
    }
  }
}

// ===================== POLL RAPIDO =====================

void pollCommands() {
  if (currentMode != MODE_CONNECTED) return;
  if (currentPollInterval >= 10000) return;
  if (millis() - lastPollCheck < POLL_FAST_INTERVAL) return;
  if (millis() - lastRegister >= currentPollInterval - 500) return;
  lastPollCheck = millis();

  HTTPClient http;
  String url = String(SERVER_URL) + "/api/modules/poll?chip_id=" + chipId;
  http.begin(url);
  http.setTimeout(3000);

  int code = http.GET();
  if (code == 200) {
    String response = http.getString();

    int piKey = response.indexOf("\"poll_interval\":");
    if (piKey >= 0) {
      unsigned long newInterval = response.substring(piKey + 16).toInt();
      if (newInterval >= 1000 && newInterval <= 60000) {
        currentPollInterval = newInterval;
      }
    }

    int cmdsStart = response.indexOf("\"commands\":[");
    if (cmdsStart >= 0) {
      int arrStart = response.indexOf("[", cmdsStart);
      int arrEnd = response.indexOf("]", arrStart);
      if (arrStart >= 0 && arrEnd > arrStart + 1) {
        processPendingCommands(response);
      }
    }
  }
  http.end();
}

// ===================== REGISTRO =====================

// Forward declarations — cada modulo contribui com seu JSON
#ifdef MOD_HIDRO
String hidro_register_json();
#endif
#ifdef MOD_CAM
String cam_register_json();
#endif

void registerOnServer() {
  if (currentMode != MODE_CONNECTED) return;
  if (millis() - lastRegister < currentPollInterval) return;
  lastRegister = millis();

  HTTPClient http;
  String url = String(SERVER_URL) + "/api/modules/register";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);

  String json = "{";
  json += "\"chip_id\":\"" + chipId + "\",";
  json += "\"short_id\":\"" + shortId + "\",";
  json += "\"type\":\"" + String(MODULE_TYPE) + "\",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"ssid\":\"" + WiFi.SSID() + "\",";
  json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"uptime\":" + String(millis() / 1000) + ",";
  json += "\"free_heap\":" + String(ESP.getFreeHeap()) + ",";

  // Capabilities — lista de modulos ativos (permite server/PWA adaptar UI)
  json += "\"capabilities\":[";
  bool firstCap = true;
  #ifdef MOD_HIDRO
  json += "\"hidro\"";
  firstCap = false;
  #endif
  #ifdef MOD_CAM
  if (!firstCap) json += ",";
  json += "\"cam\"";
  #endif
  json += "],";

  json += "\"ctrl_data\":{";

  // Cada modulo contribui com seus campos
  bool firstModule = true;
  #ifdef MOD_HIDRO
  json += hidro_register_json();
  firstModule = false;
  #endif
  #ifdef MOD_CAM
  if (!firstModule) json += ",";
  json += cam_register_json();
  #endif

  json += "}}";

  int code = http.POST(json);
  if (code == 200) {
    String response = http.getString();

    int piKey = response.indexOf("\"poll_interval\":");
    if (piKey >= 0) {
      unsigned long newInterval = response.substring(piKey + 16).toInt();
      if (newInterval >= 1000 && newInterval <= 60000) {
        if (newInterval != currentPollInterval) {
          Serial.printf("Poll interval: %lu -> %lu ms\n", currentPollInterval, newInterval);
        }
        currentPollInterval = newInterval;
      }
    }

    // Sincroniza config da camera do servidor (persiste entre reboots do ESP)
    #ifdef MOD_CAM
    int resKey = response.indexOf("\"cam_resolution\":\"");
    if (resKey >= 0) {
      int resStart = resKey + 18;
      int resEnd = response.indexOf("\"", resStart);
      if (resEnd > resStart) {
        String res = response.substring(resStart, resEnd);
        framesize_t newSize = FRAMESIZE_SVGA;
        if (res == "UXGA") newSize = FRAMESIZE_UXGA;
        else if (res == "VGA") newSize = FRAMESIZE_VGA;
        if (newSize != captureFrameSize) {
          captureFrameSize = newSize;
          Serial.printf("Sync config: resolucao=%s\n", res.c_str());
        }
      }
    }
    int qualKey = response.indexOf("\"cam_quality\":");
    if (qualKey >= 0) {
      int newQual = response.substring(qualKey + 14).toInt();
      if (newQual > 0 && newQual <= 63 && newQual != captureQuality) {
        captureQuality = newQual;
        Serial.printf("Sync config: qualidade=%d\n", newQual);
      }
    }
    #endif

    Serial.printf("Registrado OK (poll=%lums)\n", currentPollInterval);
    processPendingCommands(response);
  } else {
    Serial.printf("Erro registro servidor: %d\n", code);
  }
  http.end();
}

#endif
