/*
  Cultivee Core - Registro no servidor, polling e despacho de comandos
*/

#ifndef CORE_REGISTER_H
#define CORE_REGISTER_H

#include "mbedtls/sha256.h"  // v4.1.26: valida SHA-256 do firmware OTA
#include "esp_ota_ops.h"     // v4.1.26: esp_ota_mark_app_valid_cancel_rollback

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
#ifdef MOD_HIDROFARM
bool hidrofarm_process_command(String cmd, String obj);
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
    #ifdef MOD_HIDROFARM
    if (!handled) handled = hidrofarm_process_command(cmd, obj);
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

// ===================== OTA REMOTO (via servidor) =====================
// O ESP32 recebe "firmware_url" na resposta do register. Se presente,
// baixa o .bin via HTTP e se auto-atualiza. So tenta 1x por boot
// (flag em RAM) para evitar loop infinito se o OTA falhar.

bool otaRemoteAttempted = false;  // Reseta no reboot (RAM, nao NVS)

// v4.1.26: converte 32 bytes binarios pra hex lowercase (64 chars + \0)
static void sha256BytesToHex(const unsigned char *bytes, char *out) {
  static const char hex[] = "0123456789abcdef";
  for (int i = 0; i < 32; i++) {
    out[i * 2]     = hex[(bytes[i] >> 4) & 0xF];
    out[i * 2 + 1] = hex[bytes[i] & 0xF];
  }
  out[64] = '\0';
}

// v4.1.26: OTA remoto com validacao de SHA-256 + abort sem gravar na particao ativa.
// `expectedSha` em hex lowercase ou "" se o servidor nao enviou hash (legado).
// Se o hash nao bater: Update.end(false) (nao aplica), firmware atual continua ativo.
void performRemoteOTA(String url, String expectedSha) {
  if (otaRemoteAttempted) return;  // Ja tentou neste boot — espera proximo reboot
  otaRemoteAttempted = true;

  Serial.println("=== OTA REMOTO ===");
  Serial.println("Baixando: " + url);
  if (expectedSha.length() == 64) {
    Serial.println("Hash esperado: " + expectedSha);
  } else {
    Serial.println("AVISO: servidor nao enviou hash SHA-256 — validacao de integridade desabilitada");
  }

  HTTPClient http;
  http.begin(url);
  http.setTimeout(30000);  // 30s timeout — arquivo grande (~1.2 MB)
  int httpCode = http.GET();

  if (httpCode != 200) {
    Serial.printf("OTA remoto: HTTP %d — abortando\n", httpCode);
    http.end();
    return;
  }

  int contentLength = http.getSize();
  if (contentLength <= 0) {
    Serial.println("OTA remoto: tamanho invalido — abortando");
    http.end();
    return;
  }

  Serial.printf("OTA remoto: %d bytes. Gravando na particao OTA...\n", contentLength);

  if (!Update.begin(contentLength)) {
    Serial.printf("OTA remoto: sem espaco ou particao OTA ausente: %s\n", Update.errorString());
    http.end();
    return;
  }

  // v4.1.26: calcula SHA-256 incrementalmente durante o download.
  // Buffer de 1024B: equilibrio entre overhead HTTP e alocacao RAM.
  mbedtls_sha256_context shaCtx;
  mbedtls_sha256_init(&shaCtx);
  mbedtls_sha256_starts(&shaCtx, 0);  // 0 = SHA-256 (vs SHA-224)

  WiFiClient *stream = http.getStreamPtr();
  uint8_t buf[1024];
  size_t written = 0;
  unsigned long lastData = millis();
  const unsigned long STREAM_TIMEOUT = 15000;  // 15s sem bytes = abort

  while (written < (size_t)contentLength) {
    size_t avail = stream->available();
    if (avail == 0) {
      if (millis() - lastData > STREAM_TIMEOUT) {
        Serial.println("OTA remoto: stream stalled — abortando");
        Update.end(false);
        mbedtls_sha256_free(&shaCtx);
        http.end();
        return;
      }
      delay(10);
      continue;
    }
    size_t toRead = avail > sizeof(buf) ? sizeof(buf) : avail;
    int n = stream->readBytes(buf, toRead);
    if (n <= 0) { delay(10); continue; }
    lastData = millis();
    mbedtls_sha256_update(&shaCtx, buf, n);
    size_t w = Update.write(buf, n);
    if (w != (size_t)n) {
      Serial.printf("OTA remoto: Update.write falhou (%u/%d): %s\n", (unsigned)w, n, Update.errorString());
      Update.end(false);
      mbedtls_sha256_free(&shaCtx);
      http.end();
      return;
    }
    written += n;
  }

  unsigned char digest[32];
  mbedtls_sha256_finish(&shaCtx, digest);
  mbedtls_sha256_free(&shaCtx);

  char hexDigest[65];
  sha256BytesToHex(digest, hexDigest);
  Serial.printf("Hash calculado: %s\n", hexDigest);

  // Se o servidor mandou hash, DEVE bater — senao, aborta sem marcar particao como valida.
  if (expectedSha.length() == 64 && !expectedSha.equalsIgnoreCase(String(hexDigest))) {
    Serial.println("OTA remoto: HASH MISMATCH — firmware nao aplicado (firmware atual preservado).");
    Update.end(false);
    http.end();
    return;
  }

  if (written == (size_t)contentLength && Update.end(true)) {
    Serial.printf("OTA remoto: SUCESSO! %u bytes gravados%s. Reiniciando em 2s...\n",
      (unsigned)written,
      (expectedSha.length() == 64) ? " (SHA-256 OK)" : "");
    http.end();
    delay(2000);
    ESP.restart();
  } else {
    Serial.printf("OTA remoto: ERRO — escreveu %u/%d bytes: %s\n", (unsigned)written, contentLength, Update.errorString());
    Update.end(false);
  }

  http.end();
}

// ===================== REGISTRO =====================

// Forward declarations — cada modulo contribui com seu JSON
#ifdef MOD_HIDRO
String hidro_register_json();
#endif
#ifdef MOD_HIDROFARM
String hidrofarm_register_json();
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
  #ifdef MOD_HIDROFARM
  if (!firstCap) json += ",";
  json += "\"hidro-farm\"";
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
  #ifdef MOD_HIDROFARM
  if (!firstModule) json += ",";
  json += hidrofarm_register_json();
  firstModule = false;
  #endif
  #ifdef MOD_CAM
  if (!firstModule) json += ",";
  json += cam_register_json();
  firstModule = false;
  #endif

  // v4.1.8: telemetria de conectividade WiFi (cross-produto, sempre presente)
  // Usado pra dashboard/suporte entender por que o modulo caiu
  if (!firstModule) json += ",";
  json += "\"wifi_last_error\":\"" + wifiLastError + "\"";
  json += ",\"wifi_last_connected_ms\":" + String(wifiLastConnectedMs);
  json += ",\"wifi_disconnect_count\":" + String(wifiDisconnectCount);

  // v4.1.26: min_free_heap — menor heap observado desde o boot.
  // Permite suporte detectar fragmentacao antes do crash (free_heap atual
  // pode parecer OK mas o piso ja estar perto do limite).
  extern size_t minFreeHeap;
  json += ",\"min_free_heap\":" + String((unsigned long)minFreeHeap);

  json += "}}";

  int code = http.POST(json);
  if (code == 200) {
    String response = http.getString();

    // v4.1.26: primeiro register bem-sucedido = self-test OTA passou.
    // Marca a versao atual como "good" no NVS para que um rollback so
    // aconteca se nem isto conseguir (WiFi + HTTP 200 do servidor real).
    extern bool otaSelfTestPassed;
    if (!otaSelfTestPassed) {
      otaSelfTestPassed = true;
      prefs.begin("ota_guard", false);
      prefs.putString("last_good", String(FIRMWARE_VERSION));
      prefs.putInt("attempts", 0);
      prefs.end();
      // API oficial do ESP-IDF — no-op se bootloader rollback nao esta ativado,
      // mas nao custa nada: limpa flag ESP_OTA_IMG_PENDING_VERIFY quando presente
      esp_ota_mark_app_valid_cancel_rollback();
      Serial.printf("OTA guard: self-test OK — versao %s marcada como boa\n", FIRMWARE_VERSION);
    }

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

    // OTA remoto: se o servidor retornou firmware_url, baixa e aplica.
    // v4.1.26: tambem extrai firmware_sha256 (opcional) pra validar integridade.
    int fwKey = response.indexOf("\"firmware_url\":\"");
    if (fwKey >= 0) {
      int fwStart = fwKey + 16;  // pula ate apos o segundo "
      int fwEnd = response.indexOf("\"", fwStart);
      if (fwEnd > fwStart) {
        String fwUrl = response.substring(fwStart, fwEnd);
        String fwSha = jsonVal(response, "firmware_sha256");
        http.end();  // Libera a conexao HTTP antes de iniciar o download OTA
        performRemoteOTA(fwUrl, fwSha);
        // Se chegar aqui, OTA falhou (nao reiniciou). Continua normalmente.
        return;  // Sai do register — proximo ciclo tenta de novo (se nao tentou ainda)
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
