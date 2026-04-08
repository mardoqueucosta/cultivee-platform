/*
  Cultivee Modulo - Hidroponia
  Fases de cultivo, controle de reles (luz/bomba), automacao por horario
*/

#ifndef MOD_HIDRO_H
#define MOD_HIDRO_H
#ifdef MOD_HIDRO

// ===================== FASES =====================

#define HYDRO_CONFIG_VERSION 2  // Incrementar quando defaults mudarem

void loadDefaultPhases() {
  numPhases = 3;

  strcpy(phases[0].name, "Muda");
  phases[0].days = 3;
  phases[0].lightOnHour = 6; phases[0].lightOnMin = 0;
  phases[0].lightOffHour = 18; phases[0].lightOffMin = 0;
  phases[0].pumpOnDay = 15; phases[0].pumpOffDay = 15;
  phases[0].pumpOnNight = 15; phases[0].pumpOffNight = 45;

  strcpy(phases[1].name, "Bercario");
  phases[1].days = 17;
  phases[1].lightOnHour = 6; phases[1].lightOnMin = 0;
  phases[1].lightOffHour = 19; phases[1].lightOffMin = 0;
  phases[1].pumpOnDay = 15; phases[1].pumpOffDay = 15;
  phases[1].pumpOnNight = 15; phases[1].pumpOffNight = 45;

  strcpy(phases[2].name, "Engorda");
  phases[2].days = 0;  // infinito
  phases[2].lightOnHour = 6; phases[2].lightOnMin = 0;
  phases[2].lightOffHour = 20; phases[2].lightOffMin = 0;
  phases[2].pumpOnDay = 15; phases[2].pumpOffDay = 15;
  phases[2].pumpOnNight = 15; phases[2].pumpOffNight = 45;
}

void savePhases() {
  prefs.begin("hydro", false);
  prefs.putInt("cfg_ver", HYDRO_CONFIG_VERSION);
  prefs.putString("start_date", startDate);
  prefs.putInt("num_phases", numPhases);
  prefs.putBool("mode_auto", modeAuto);

  for (int i = 0; i < numPhases; i++) {
    String prefix = "p" + String(i) + "_";
    prefs.putString((prefix + "name").c_str(), phases[i].name);
    prefs.putInt((prefix + "days").c_str(), phases[i].days);
    prefs.putInt((prefix + "loh").c_str(), phases[i].lightOnHour);
    prefs.putInt((prefix + "lom").c_str(), phases[i].lightOnMin);
    prefs.putInt((prefix + "lfh").c_str(), phases[i].lightOffHour);
    prefs.putInt((prefix + "lfm").c_str(), phases[i].lightOffMin);
    prefs.putInt((prefix + "pod").c_str(), phases[i].pumpOnDay);
    prefs.putInt((prefix + "pfd").c_str(), phases[i].pumpOffDay);
    prefs.putInt((prefix + "pon").c_str(), phases[i].pumpOnNight);
    prefs.putInt((prefix + "pfn").c_str(), phases[i].pumpOffNight);
  }
  prefs.end();
  Serial.println("Fases salvas no flash");
}

void loadPhases() {
  prefs.begin("hydro", true);
  int configVersion = prefs.getInt("cfg_ver", 0);
  numPhases = prefs.getInt("num_phases", 0);
  String sd = prefs.getString("start_date", "");
  if (sd.length() > 0) strncpy(startDate, sd.c_str(), sizeof(startDate) - 1);
  // Sempre inicia em modo automatico (usuario pode trocar manualmente via app)
  modeAuto = true;

  // Se versao da config mudou ou nao tem fases, restaura defaults
  if (numPhases == 0 || configVersion < HYDRO_CONFIG_VERSION) {
    prefs.end();
    loadDefaultPhases();
    savePhases();
    Serial.printf("Config resetada (versao %d -> %d)\n", configVersion, HYDRO_CONFIG_VERSION);
    return;
  }

  for (int i = 0; i < numPhases && i < MAX_PHASES; i++) {
    String prefix = "p" + String(i) + "_";
    String n = prefs.getString((prefix + "name").c_str(), "Fase");
    strncpy(phases[i].name, n.c_str(), sizeof(phases[i].name) - 1);
    phases[i].days = prefs.getInt((prefix + "days").c_str(), 7);
    phases[i].lightOnHour = prefs.getInt((prefix + "loh").c_str(), 6);
    phases[i].lightOnMin = prefs.getInt((prefix + "lom").c_str(), 0);
    phases[i].lightOffHour = prefs.getInt((prefix + "lfh").c_str(), 18);
    phases[i].lightOffMin = prefs.getInt((prefix + "lfm").c_str(), 0);
    phases[i].pumpOnDay = prefs.getInt((prefix + "pod").c_str(), 15);
    phases[i].pumpOffDay = prefs.getInt((prefix + "pfd").c_str(), 15);
    phases[i].pumpOnNight = prefs.getInt((prefix + "pon").c_str(), 15);
    phases[i].pumpOffNight = prefs.getInt((prefix + "pfn").c_str(), 45);
  }
  prefs.end();
  Serial.printf("Fases carregadas: %d fases, inicio: %s\n", numPhases, startDate);
}

int getCycleDay() {
  struct tm t;
  if (!getCurrentTime(&t)) return 0;

  int sy, sm, sd;
  sscanf(startDate, "%d-%d-%d", &sy, &sm, &sd);

  struct tm startTm = {0};
  startTm.tm_year = sy - 1900;
  startTm.tm_mon = sm - 1;
  startTm.tm_mday = sd;
  time_t startTime = mktime(&startTm);
  time_t now = mktime(&t);

  int days = (int)((now - startTime) / 86400) + 1;
  return days > 0 ? days : 1;
}

int getCurrentPhaseIndex() {
  int cycleDay = getCycleDay();
  int dayCount = 0;
  for (int i = 0; i < numPhases; i++) {
    if (phases[i].days == 0) return i;
    dayCount += phases[i].days;
    if (cycleDay <= dayCount) return i;
  }
  return numPhases - 1;
}

// ===================== RELES E AUTOMACAO =====================

void setRelay(int pin, bool on) {
  digitalWrite(pin, on ? RELE_ON : RELE_OFF);
}

bool isLightTime(Phase *p) {
  struct tm t;
  if (!getCurrentTime(&t)) return false;

  int nowMin = t.tm_hour * 60 + t.tm_min;
  int onMin = p->lightOnHour * 60 + p->lightOnMin;
  int offMin = p->lightOffHour * 60 + p->lightOffMin;

  if (onMin <= offMin) {
    return nowMin >= onMin && nowMin < offMin;
  } else {
    return nowMin >= onMin || nowMin < offMin;
  }
}

bool isDayTime(Phase *p) {
  return isLightTime(p);
}

void hidro_loop() {
  if (!modeAuto) return;
  struct tm testTime;
  if (!getCurrentTime(&testTime)) return;
  if (testTime.tm_year < (2024 - 1900)) return;
  if (!ntpSynced) ntpSynced = true;
  if (millis() - lastAutoCheck < 5000) return;
  lastAutoCheck = millis();

  int phaseIdx = getCurrentPhaseIndex();
  Phase *p = &phases[phaseIdx];

  // Luz
  bool shouldLight = isLightTime(p);
  if (shouldLight != lightState) {
    lightState = shouldLight;
    setRelay(RELE_LAMPADA, lightState);
    Serial.printf("Auto: Luz %s (fase: %s)\n", lightState ? "ON" : "OFF", p->name);
  }

  // Bomba (ciclo) — se valores invalidos (0), usa defaults seguros
  bool isDay = isDayTime(p);
  unsigned long pumpOn = isDay ? p->pumpOnDay : p->pumpOnNight;
  unsigned long pumpOff = isDay ? p->pumpOffDay : p->pumpOffNight;
  if (pumpOn == 0) pumpOn = 15;   // default: 15min ligada
  if (pumpOff == 0) pumpOff = 15;  // default: 15min desligada
  unsigned long cycleTotal = (pumpOn + pumpOff) * 60UL * 1000UL;
  unsigned long onTime = pumpOn * 60UL * 1000UL;

  struct tm ct;
  if (getCurrentTime(&ct)) {
    unsigned long secsSinceMidnight = ct.tm_hour * 3600UL + ct.tm_min * 60UL + ct.tm_sec;
    unsigned long cycleTotalSec = (pumpOn + pumpOff) * 60UL;
    unsigned long posInCycle = (secsSinceMidnight % cycleTotalSec) * 1000UL;
    bool shouldPump = posInCycle < onTime;
    if (shouldPump != pumpState) {
      pumpState = shouldPump;
      setRelay(RELE_BOMBA, pumpState);
      Serial.printf("Auto: Bomba %s (%s, %lumin/%lumin)\n",
        pumpState ? "ON" : "OFF", isDay ? "dia" : "noite", pumpOn, pumpOff);
    }
  }
}

// ===================== LED STATUS =====================

void updateStatusLed() {
  unsigned long now = millis();
  if (now - lastLedUpdate < 100) return;
  lastLedUpdate = now;

  switch (currentMode) {
    case MODE_SETUP:
      digitalWrite(LED_ONBOARD, (now / 250) % 2);
      break;
    case MODE_CONNECTED:
      digitalWrite(LED_ONBOARD, (now / 3000) % 2 == 0 && (now % 3000) < 100);
      break;
    case MODE_OFFLINE:
      {
        int pos = (now / 200) % 10;
        digitalWrite(LED_ONBOARD, pos < 6 && pos % 2 == 0);
      }
      break;
  }
}

// checkResetButton() movido para core_server.h (compartilhado entre modulos)

// ===================== STATUS JSON =====================

String hidro_status_json() {
  struct tm t;
  bool hasTime = getCurrentTime(&t);
  int cycleDay = getCycleDay();
  int phaseIdx = getCurrentPhaseIndex();
  Phase *p = &phases[phaseIdx];

  String json = "";
  json += "\"mode\":\"" + String(modeAuto ? "auto" : "manual") + "\",";
  json += "\"light\":" + String(lightState ? "true" : "false") + ",";
  json += "\"pump\":" + String(pumpState ? "true" : "false") + ",";
  json += "\"cycle_day\":" + String(cycleDay) + ",";
  json += "\"phase\":\"" + String(p->name) + "\",";
  json += "\"phase_index\":" + String(phaseIdx) + ",";
  json += "\"num_phases\":" + String(numPhases) + ",";
  json += "\"start_date\":\"" + String(startDate) + "\",";
  json += "\"ntp_synced\":" + String(ntpSynced ? "true" : "false") + ",";
  if (hasTime) {
    char timeStr[9];
    snprintf(timeStr, sizeof(timeStr), "%02d:%02d:%02d", t.tm_hour, t.tm_min, t.tm_sec);
    json += "\"time\":\"" + String(timeStr) + "\",";
  }

  // Fases completas
  json += "\"phases\":[";
  for (int i = 0; i < numPhases; i++) {
    if (i > 0) json += ",";
    json += "{\"name\":\"" + String(phases[i].name) + "\"";
    json += ",\"days\":" + String(phases[i].days);
    json += ",\"lightOnHour\":" + String(phases[i].lightOnHour);
    json += ",\"lightOnMin\":" + String(phases[i].lightOnMin);
    json += ",\"lightOffHour\":" + String(phases[i].lightOffHour);
    json += ",\"lightOffMin\":" + String(phases[i].lightOffMin);
    json += ",\"pumpOnDay\":" + String(phases[i].pumpOnDay);
    json += ",\"pumpOffDay\":" + String(phases[i].pumpOffDay);
    json += ",\"pumpOnNight\":" + String(phases[i].pumpOnNight);
    json += ",\"pumpOffNight\":" + String(phases[i].pumpOffNight);
    json += "}";
  }
  json += "]";

  return json;
}

// JSON para registerOnServer (ctrl_data)
String hidro_register_json() {
  struct tm t;
  bool hasTime = getCurrentTime(&t);
  int cycleDay = getCycleDay();
  int phaseIdx = getCurrentPhaseIndex();
  Phase *p = &phases[phaseIdx];

  char timeStr[9] = "--:--:--";
  if (hasTime) snprintf(timeStr, sizeof(timeStr), "%02d:%02d:%02d", t.tm_hour, t.tm_min, t.tm_sec);

  String phasesJson = "[";
  for (int i = 0; i < numPhases; i++) {
    if (i > 0) phasesJson += ",";
    phasesJson += "{\"name\":\"" + String(phases[i].name) + "\"";
    phasesJson += ",\"days\":" + String(phases[i].days);
    phasesJson += ",\"lightOnHour\":" + String(phases[i].lightOnHour);
    phasesJson += ",\"lightOnMin\":" + String(phases[i].lightOnMin);
    phasesJson += ",\"lightOffHour\":" + String(phases[i].lightOffHour);
    phasesJson += ",\"lightOffMin\":" + String(phases[i].lightOffMin);
    phasesJson += ",\"pumpOnDay\":" + String(phases[i].pumpOnDay);
    phasesJson += ",\"pumpOffDay\":" + String(phases[i].pumpOffDay);
    phasesJson += ",\"pumpOnNight\":" + String(phases[i].pumpOnNight);
    phasesJson += ",\"pumpOffNight\":" + String(phases[i].pumpOffNight);
    phasesJson += "}";
  }
  phasesJson += "]";

  String json = "";
  json += "\"light\":" + String(lightState ? "true" : "false") + ",";
  json += "\"pump\":" + String(pumpState ? "true" : "false") + ",";
  json += "\"mode\":\"" + String(modeAuto ? "auto" : "manual") + "\",";
  json += "\"phase\":\"" + String(p->name) + "\",";
  json += "\"phase_index\":" + String(phaseIdx) + ",";
  json += "\"cycle_day\":" + String(cycleDay) + ",";
  json += "\"num_phases\":" + String(numPhases) + ",";
  json += "\"start_date\":\"" + String(startDate) + "\",";
  json += "\"ntp_synced\":" + String(ntpSynced ? "true" : "false") + ",";
  json += "\"time\":\"" + String(timeStr) + "\",";
  json += "\"phases\":" + phasesJson;

  return json;
}

// ===================== ROUTE HANDLERS =====================

void handleGpio() {
  String name = server.arg("name");
  String action = server.arg("action");

  if (name == "light") {
    if (!modeAuto || action == "toggle") {
      lightState = !lightState;
      setRelay(RELE_LAMPADA, lightState);
      if (modeAuto) { modeAuto = false; }
      Serial.printf("GPIO: Luz %s\n", lightState ? "ON" : "OFF");
    }
  } else if (name == "pump") {
    if (!modeAuto || action == "toggle") {
      pumpState = !pumpState;
      setRelay(RELE_BOMBA, pumpState);
      if (modeAuto) { modeAuto = false; }
      Serial.printf("GPIO: Bomba %s\n", pumpState ? "ON" : "OFF");
    }
  } else if (name == "mode") {
    modeAuto = !modeAuto;
    if (!modeAuto) {
      manualLight = lightState;
      manualPump = pumpState;
    }
    prefs.begin("hydro", false);
    prefs.putBool("mode_auto", modeAuto);
    prefs.end();
    Serial.printf("GPIO: Modo %s\n", modeAuto ? "Auto" : "Manual");
  }

  sendCORS();
  server.send(200, "application/json", buildStatusJSON());
}

void handleRelay() {
  String device = server.arg("device");
  String action = server.arg("action");

  if (device == "mode") {
    modeAuto = !modeAuto;
    if (!modeAuto) {
      manualLight = lightState;
      manualPump = pumpState;
    }
    prefs.begin("hydro", false);
    prefs.putBool("mode_auto", modeAuto);
    prefs.end();
    Serial.printf("Modo: %s\n", modeAuto ? "Automatico" : "Manual");
  } else if (device == "light") {
    if (!modeAuto || action == "toggle") {
      lightState = !lightState;
      setRelay(RELE_LAMPADA, lightState);
      if (!modeAuto) modeAuto = false;
      Serial.printf("Manual: Luz %s\n", lightState ? "ON" : "OFF");
    }
  } else if (device == "pump") {
    if (!modeAuto || action == "toggle") {
      pumpState = !pumpState;
      setRelay(RELE_BOMBA, pumpState);
      if (!modeAuto) modeAuto = false;
      Serial.printf("Manual: Bomba %s\n", pumpState ? "ON" : "OFF");
    }
  }

  sendCORS();
  server.send(200, "application/json", buildStatusJSON());
}

void handleStatus() {
  sendCORS();
  server.send(200, "application/json", buildStatusJSON());
}

void handleAddPhase() {
  if (numPhases < MAX_PHASES) {
    strcpy(phases[numPhases].name, "Nova Fase");
    phases[numPhases].days = 7;
    phases[numPhases].lightOnHour = 6; phases[numPhases].lightOnMin = 0;
    phases[numPhases].lightOffHour = 18; phases[numPhases].lightOffMin = 0;
    phases[numPhases].pumpOnDay = 15; phases[numPhases].pumpOffDay = 15;
    phases[numPhases].pumpOnNight = 15; phases[numPhases].pumpOffNight = 45;
    numPhases++;
    savePhases();
  }
  server.sendHeader("Location", "/config");
  server.send(302);
}

void handleRemovePhase() {
  int idx = server.arg("idx").toInt();
  if (idx >= 0 && idx < numPhases && numPhases > 1) {
    for (int i = idx; i < numPhases - 1; i++) phases[i] = phases[i + 1];
    numPhases--;
    savePhases();
  }
  server.sendHeader("Location", "/config");
  server.send(302);
}

void handleResetPhases() {
  loadDefaultPhases();
  savePhases();
  server.sendHeader("Location", "/config");
  server.send(302);
}

void handleSaveConfig() {
  String sd = server.arg("start_date");
  if (sd.length() > 0) strncpy(startDate, sd.c_str(), sizeof(startDate) - 1);

  int np = server.arg("num_phases").toInt();
  if (np > MAX_PHASES) np = MAX_PHASES;

  for (int i = 0; i < np; i++) {
    String n = server.arg("n" + String(i));
    if (n.length() > 0) strncpy(phases[i].name, n.c_str(), sizeof(phases[i].name) - 1);
    phases[i].days = server.arg("d" + String(i)).toInt();

    String lon = server.arg("lon" + String(i));
    if (lon.length() >= 5) {
      phases[i].lightOnHour = lon.substring(0, 2).toInt();
      phases[i].lightOnMin = lon.substring(3, 5).toInt();
    }
    String loff = server.arg("loff" + String(i));
    if (loff.length() >= 5) {
      phases[i].lightOffHour = loff.substring(0, 2).toInt();
      phases[i].lightOffMin = loff.substring(3, 5).toInt();
    }

    int pod = server.arg("pod" + String(i)).toInt();
    int pfd = server.arg("pfd" + String(i)).toInt();
    int pon = server.arg("pon" + String(i)).toInt();
    int pfn = server.arg("pfn" + String(i)).toInt();
    phases[i].pumpOnDay = pod > 0 ? pod : 15;
    phases[i].pumpOffDay = pfd > 0 ? pfd : 15;
    phases[i].pumpOnNight = pon > 0 ? pon : 15;
    phases[i].pumpOffNight = pfn > 0 ? pfn : 45;
  }
  numPhases = np;
  savePhases();

  server.sendHeader("Location", "/");
  server.send(302, "text/plain", "Salvo!");
}

// ===================== CONFIG PAGE HTML =====================

void handleConfig() {
  String phaseForms = "";
  for (int i = 0; i < numPhases; i++) {
    Phase *p = &phases[i];
    String lonVal = (p->lightOnHour < 10 ? "0" : "") + String(p->lightOnHour) + ":" + (p->lightOnMin < 10 ? "0" : "") + String(p->lightOnMin);
    String loffVal = (p->lightOffHour < 10 ? "0" : "") + String(p->lightOffHour) + ":" + (p->lightOffMin < 10 ? "0" : "") + String(p->lightOffMin);

    phaseForms += "<div class='ph'>";
    phaseForms += "<div class='ph-hdr'><span class='ph-t'>Fase " + String(i + 1) + "</span>";
    if (numPhases > 1) phaseForms += "<button type='button' onclick=\"removePhase(" + String(i) + ")\" class='ph-rm'>&#10005;</button>";
    phaseForms += "</div>";

    phaseForms += "<div class='gr'><div class='fd'><label>Nome</label><input name='n" + String(i) + "' value='" + String(p->name) + "'></div>";
    phaseForms += "<div class='fd'><label>Dias</label><input type='number' name='d" + String(i) + "' value='" + String(p->days) + "' min='0' placeholder='0=infinito'></div></div>";

    phaseForms += "<div class='sl'>&#128161; Ilumina&ccedil;&atilde;o</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>Liga</label><input type='time' name='lon" + String(i) + "' value='" + lonVal + "'></div>";
    phaseForms += "<div class='fd'><label>Desliga</label><input type='time' name='loff" + String(i) + "' value='" + loffVal + "'></div></div>";

    phaseForms += "<div class='sl'>&#128167; Irriga&ccedil;&atilde;o Dia</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>ON (min)</label><input type='number' name='pod" + String(i) + "' value='" + String(p->pumpOnDay) + "' min='1'></div>";
    phaseForms += "<div class='fd'><label>OFF (min)</label><input type='number' name='pfd" + String(i) + "' value='" + String(p->pumpOffDay) + "' min='1'></div></div>";

    phaseForms += "<div class='sl'>&#127769; Irriga&ccedil;&atilde;o Noite</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>ON (min)</label><input type='number' name='pon" + String(i) + "' value='" + String(p->pumpOnNight) + "' min='1'></div>";
    phaseForms += "<div class='fd'><label>OFF (min)</label><input type='number' name='pfn" + String(i) + "' value='" + String(p->pumpOffNight) + "' min='1'></div></div>";
    phaseForms += "</div>";
  }

  String html = R"rawliteral(<!DOCTYPE html><html><head>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<meta charset='UTF-8'>
<title>Configuracao - Cultivee</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:hsl(210,20%,8%);color:hsl(210,20%,90%);max-width:480px;margin:0 auto}
.top{background:hsl(210,18%,12%);padding:1.5rem;text-align:center;border-bottom:1px solid hsl(210,15%,20%)}
.top-icon{width:56px;height:56px;background:hsla(142,71%,45%,0.15);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 0.75rem;color:hsl(142,71%,45%)}
.top-icon svg{width:32px;height:32px}
.top h1{font-size:1.1rem;font-weight:700;color:hsl(210,20%,90%)}
.top p{font-size:0.85rem;color:hsl(210,15%,55%);margin-top:0.25rem}
.wrap{padding:1rem}
.fd label{display:block;font-size:0.7rem;color:hsl(210,15%,40%);margin-bottom:0.25rem;font-weight:500}
.fd input{width:100%;padding:0.5rem 0.75rem;border:1px solid hsl(210,15%,20%);border-radius:0.75rem;font-size:0.85rem;background:hsl(210,18%,12%);color:hsl(210,20%,90%);font-family:inherit}
.fd input:focus{outline:none;border-color:hsl(142,71%,45%);box-shadow:0 0 0 3px hsla(142,71%,45%,0.15)}
.gr{display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:0.5rem}
.ph{background:hsl(210,18%,14%);border:1px solid hsl(210,15%,20%);border-radius:0.75rem;padding:1rem;margin-bottom:0.75rem}
.ph-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:1px solid hsl(210,15%,20%)}
.ph-t{font-weight:700;font-size:0.9rem}
.ph-rm{background:none;border:1px solid hsl(210,15%,20%);color:hsl(210,15%,40%);width:24px;height:24px;border-radius:50%;cursor:pointer;font-size:0.7rem;display:flex;align-items:center;justify-content:center}
.sl{font-size:0.75rem;font-weight:600;color:hsl(210,15%,55%);margin:0.5rem 0 0.25rem}
.acts{display:flex;gap:0.5rem;margin-top:0.5rem}
.btn-p{flex:1;padding:0.75rem 1.5rem;border-radius:0.75rem;font-weight:600;font-size:0.9rem;border:none;cursor:pointer;background:hsl(142,71%,45%);color:#fff}
.btn-s{flex:1;padding:0.65rem 1rem;border-radius:0.75rem;font-weight:600;font-size:0.8rem;border:1px solid hsl(210,15%,20%);cursor:pointer;background:transparent;color:hsl(210,15%,55%);text-align:center;text-decoration:none}
.btn-d{flex:1;padding:0.65rem 1rem;border-radius:0.75rem;font-weight:600;font-size:0.8rem;border:1px solid hsl(210,15%,20%);cursor:pointer;background:transparent;color:hsl(0,72%,51%);text-align:center;text-decoration:none}
</style></head><body>
<div class='top'>
<div class='top-icon'><svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='3'/><path d='M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z'/></svg></div>
<h1>Configura&ccedil;&atilde;o</h1>
<p>Edite as fases do cultivo</p>
</div>

<form method='POST' action='/save-config' class='wrap'>
<div class='fd' style='margin-bottom:1rem'><label>Data de In&iacute;cio do Cultivo</label>
<input type='date' name='start_date' value=')rawliteral" + String(startDate) + R"rawliteral('>
</div>

<div id='phases'>)rawliteral" + phaseForms + R"rawliteral(</div>
<input type='hidden' name='num_phases' id='num_phases' value=')rawliteral" + String(numPhases) + R"rawliteral('>

<div class='acts'>
<button type='submit' class='btn-p'>Salvar</button>
</div>
<div class='acts'>
<button type='button' onclick='addPhase()' class='btn-s'>+ Adicionar Fase</button>
<a href='/reset-phases' class='btn-d' onclick="return confirm('Restaurar fases padrao?')">Restaurar Padr&atilde;o</a>
</div>
</form>

<script>
function removePhase(idx) {
  if(!confirm('Remover esta fase?')) return;
  fetch('/remove-phase?idx='+idx).then(()=>location.reload());
}
function addPhase() {
  fetch('/add-phase').then(()=>location.reload());
}
</script>
</body></html>)rawliteral";

  server.send(200, "text/html", html);
}

// ===================== DASHBOARD HTML =====================

String hidro_dashboard_html() {
  int cycleDay = getCycleDay();
  int phaseIdx = getCurrentPhaseIndex();
  Phase *p = &phases[phaseIdx];
  struct tm t;
  bool hasTime = getCurrentTime(&t);

  char todayStr[11] = "--/--/----";
  if (hasTime) snprintf(todayStr, sizeof(todayStr), "%02d/%02d/%04d", t.tm_mday, t.tm_mon + 1, t.tm_year + 1900);

  char startDateFmt[11] = "--/--/----";
  int sy2, sm2, sd2;
  if (sscanf(startDate, "%d-%d-%d", &sy2, &sm2, &sd2) == 3) {
    snprintf(startDateFmt, sizeof(startDateFmt), "%02d/%02d/%04d", sd2, sm2, sy2);
  }

  String lightIndicator = lightState ? "<span id='il' style='color:#27ae60'>&#9679; Luz Ligada</span>" : "<span id='il' style='color:#666'>&#9679; Luz Desligada</span>";
  String pumpIndicator = pumpState ? "<span id='ip' style='color:#3498db'>&#9679; Bomba Ligada</span>" : "<span id='ip' style='color:#666'>&#9679; Bomba Desligada</span>";

  String manualBtns = "";
  if (!modeAuto) {
    manualBtns = "<div id='mb' style='display:flex;gap:8px;margin-top:10px'>"
      "<button id='bl' onclick=\"cmd('light','toggle')\" style='flex:1;padding:12px;border-radius:10px;border:none;font-weight:700;font-size:0.9rem;cursor:pointer;"
      + String(lightState ? "background:#27ae60;color:#fff'" : "background:#2a2d35;color:#aaa;border:1px solid #3a3d45'") + ">LUZ " + (lightState ? "ON" : "OFF") + "</button>"
      "<button id='bp' onclick=\"cmd('pump','toggle')\" style='flex:1;padding:12px;border-radius:10px;border:none;font-weight:700;font-size:0.9rem;cursor:pointer;"
      + String(pumpState ? "background:#3498db;color:#fff'" : "background:#2a2d35;color:#aaa;border:1px solid #3a3d45'") + ">BOMBA " + (pumpState ? "ON" : "OFF") + "</button></div>";
  }

  String modeBtn = modeAuto
    ? "<button id='bm' onclick=\"cmd('mode','toggle')\" style='width:100%;padding:12px;border-radius:10px;border:1px solid #27ae60;background:rgba(39,174,96,0.1);color:#27ae60;font-weight:700;cursor:pointer'>&#9881; Modo Automatico</button>"
    : "<button id='bm' onclick=\"cmd('mode','toggle')\" style='width:100%;padding:12px;border-radius:10px;border:1px solid #e67e22;background:rgba(230,126,34,0.1);color:#e67e22;font-weight:700;cursor:pointer'>&#9995; Modo Manual</button>";

  // Fases detalhadas
  String phasesHtml = "";
  int daysAccum = 0;
  for (int i = 0; i < numPhases; i++) {
    Phase *ph = &phases[i];
    bool isActive = (i == phaseIdx);
    String border = isActive ? "border-left:4px solid #27ae60;background:rgba(39,174,96,0.08)" : "border-left:4px solid #3a3d45";
    String badge = isActive ? " <span style='background:#27ae60;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.65rem'>ATIVA</span>" : "";

    String diasStr;
    if (ph->days > 0) {
      if (isActive) {
        int daysInPhase = cycleDay - daysAccum;
        if (daysInPhase < 0) daysInPhase = 0;
        diasStr = String(daysInPhase) + " de " + String(ph->days) + " dias";
      } else if (i < phaseIdx) {
        diasStr = String(ph->days) + "/" + String(ph->days) + " dias &#10003;";
      } else {
        diasStr = String(ph->days) + " dias";
      }
      daysAccum += ph->days;
    } else {
      diasStr = "&#8734;";
      daysAccum += 30;
    }

    phasesHtml += "<div style='border-radius:10px;padding:10px;margin-bottom:6px;" + border + "'>";
    phasesHtml += "<div style='display:flex;justify-content:space-between;align-items:center'>";
    phasesHtml += "<b>" + String(ph->name) + "</b>" + badge;
    phasesHtml += "<span style='color:#888;font-size:0.8rem'>" + diasStr + "</span></div>";
    phasesHtml += "<div style='color:#888;font-size:0.75rem;margin-top:4px'>";
    phasesHtml += "&#128161; " + String(ph->lightOnHour) + ":" + (ph->lightOnMin < 10 ? "0" : "") + String(ph->lightOnMin);
    phasesHtml += " - " + String(ph->lightOffHour) + ":" + (ph->lightOffMin < 10 ? "0" : "") + String(ph->lightOffMin) + "<br>";
    phasesHtml += "&#128167; Dia: " + String(ph->pumpOnDay) + "/" + String(ph->pumpOffDay) + "min";
    phasesHtml += " | Noite: " + String(ph->pumpOnNight) + "/" + String(ph->pumpOffNight) + "min";
    phasesHtml += "</div></div>";
  }

  String html = "";
  html += "<div class='card'>";
  html += "<div class='grid'>";
  html += "<div class='stat'><div class='lb'>Ciclo</div><div class='vl'>Dia " + String(cycleDay) + "</div></div>";
  html += "<div class='stat'><div class='lb'>Fase</div><div class='vl' style='font-size:1rem'>" + String(p->name) + "</div></div>";
  html += "<div class='stat'><div class='lb'>Inicio</div><div class='vl' style='font-size:0.9rem'>" + String(startDateFmt) + "</div></div>";
  html += "<div class='stat'><div class='lb'>Hoje</div><div class='vl' style='font-size:0.9rem'>" + String(todayStr) + "</div></div>";
  html += "</div>";
  html += "<div class='ind'>" + lightIndicator + pumpIndicator + "</div>";
  html += modeBtn + manualBtns;
  html += "</div>";

  html += "<div class='card'><h3 style='font-size:0.9rem;margin-bottom:8px'>Fases Configuradas";
  html += "<a href='/config' style='float:right;color:#27ae60;font-size:0.8rem;text-decoration:none'>&#9881; Configurar</a></h3>";
  html += phasesHtml + "</div>";

  return html;
}

String hidro_dashboard_js() {
  return R"rawliteral(
function cmd(d,a){fetch('/relay?device='+d+'&action='+a).then(r=>r.json()).then(s=>upd(s)).catch(()=>{})}
function upd(s){
var il=document.getElementById('il'),ip=document.getElementById('ip'),
bl=document.getElementById('bl'),bp=document.getElementById('bp'),bm=document.getElementById('bm'),
mb=document.getElementById('mb');
if(il){il.style.color=s.light?'#27ae60':'#666';il.innerHTML=s.light?'&#9679; Luz Ligada':'&#9679; Luz Desligada'}
if(ip){ip.style.color=s.pump?'#3498db':'#666';ip.innerHTML=s.pump?'&#9679; Bomba Ligada':'&#9679; Bomba Desligada'}
if(bl){bl.style.background=s.light?'#27ae60':'#2a2d35';bl.style.color=s.light?'#fff':'#aaa';bl.textContent='LUZ '+(s.light?'ON':'OFF')}
if(bp){bp.style.background=s.pump?'#3498db':'#2a2d35';bp.style.color=s.pump?'#fff':'#aaa';bp.textContent='BOMBA '+(s.pump?'ON':'OFF')}
var isAuto=s.mode==='auto';
if(bm){bm.style.borderColor=isAuto?'#27ae60':'#e67e22';bm.style.background=isAuto?'rgba(39,174,96,0.1)':'rgba(230,126,34,0.1)';bm.style.color=isAuto?'#27ae60':'#e67e22';bm.innerHTML=isAuto?'&#9881; Modo Automatico':'&#9995; Modo Manual'}
if(isAuto&&mb){mb.remove()}
if(!isAuto&&!mb){location.reload()}
}
setInterval(()=>fetch('/status').then(r=>r.json()).then(s=>upd(s)).catch(()=>{}),10000);
)rawliteral";
}

// ===================== COMMAND HANDLER =====================

bool hidro_process_command(String cmd, String obj) {
  if (cmd == "relay") {
    String device = jsonVal(obj, "device");
    if (device == "mode") {
      modeAuto = !modeAuto;
      Serial.printf("Remoto: Modo %s\n", modeAuto ? "Auto" : "Manual");
    } else if (device == "light") {
      lightState = !lightState;
      setRelay(RELE_LAMPADA, lightState);
      if (modeAuto) modeAuto = false;
      Serial.printf("Remoto: Luz %s\n", lightState ? "ON" : "OFF");
    } else if (device == "pump") {
      pumpState = !pumpState;
      setRelay(RELE_BOMBA, pumpState);
      if (modeAuto) modeAuto = false;
      Serial.printf("Remoto: Bomba %s\n", pumpState ? "ON" : "OFF");
    }
    return true;
  } else if (cmd == "add-phase") {
    if (numPhases < MAX_PHASES) {
      strcpy(phases[numPhases].name, "Nova Fase");
      phases[numPhases].days = 7;
      phases[numPhases].lightOnHour = 6; phases[numPhases].lightOnMin = 0;
      phases[numPhases].lightOffHour = 18; phases[numPhases].lightOffMin = 0;
      phases[numPhases].pumpOnDay = 15; phases[numPhases].pumpOffDay = 15;
      phases[numPhases].pumpOnNight = 15; phases[numPhases].pumpOffNight = 45;
      numPhases++;
      savePhases();
      Serial.println("Remoto: Fase adicionada");
    }
    return true;
  } else if (cmd == "reset-phases") {
    loadDefaultPhases();
    savePhases();
    Serial.println("Remoto: Fases restauradas");
    return true;
  } else if (cmd == "remove-phase") {
    int idx = jsonInt(obj, "idx");
    if (idx >= 0 && idx < numPhases && numPhases > 1) {
      for (int i = idx; i < numPhases - 1; i++) phases[i] = phases[i + 1];
      numPhases--;
      savePhases();
      Serial.printf("Remoto: Fase %d removida\n", idx);
    }
    return true;
  } else if (cmd == "save-config") {
    String sd = jsonVal(obj, "start_date");
    if (sd.length() > 0) strncpy(startDate, sd.c_str(), sizeof(startDate) - 1);

    int np = jsonInt(obj, "num_phases");
    if (np > 0 && np <= MAX_PHASES) {
      for (int i = 0; i < np; i++) {
        String n = jsonVal(obj, "n" + String(i));
        if (n.length() > 0) strncpy(phases[i].name, n.c_str(), sizeof(phases[i].name) - 1);
        phases[i].days = jsonInt(obj, "d" + String(i));

        String lon = jsonVal(obj, "lon" + String(i));
        if (lon.length() >= 5) {
          phases[i].lightOnHour = lon.substring(0, 2).toInt();
          phases[i].lightOnMin = lon.substring(3, 5).toInt();
        }
        String loff = jsonVal(obj, "loff" + String(i));
        if (loff.length() >= 5) {
          phases[i].lightOffHour = loff.substring(0, 2).toInt();
          phases[i].lightOffMin = loff.substring(3, 5).toInt();
        }

        int pod = jsonInt(obj, "pod" + String(i));
        int pfd = jsonInt(obj, "pfd" + String(i));
        int pon = jsonInt(obj, "pon" + String(i));
        int pfn = jsonInt(obj, "pfn" + String(i));
        phases[i].pumpOnDay = pod > 0 ? pod : 15;
        phases[i].pumpOffDay = pfd > 0 ? pfd : 15;
        phases[i].pumpOnNight = pon > 0 ? pon : 15;
        phases[i].pumpOffNight = pfn > 0 ? pfn : 45;
      }
      numPhases = np;
    }
    savePhases();
    Serial.println("Remoto: Config salva");
    return true;
  }
  return false;
}

// ===================== SETUP & ROUTES =====================

void hidro_setup() {
  pinMode(RELE_LAMPADA, OUTPUT);
  pinMode(RELE_BOMBA, OUTPUT);
  setRelay(RELE_LAMPADA, false);
  setRelay(RELE_BOMBA, false);

  loadPhases();
}

void hidro_register_routes() {
  server.on("/config", handleConfig);
  server.on("/save-config", HTTP_POST, handleSaveConfig);
  server.on("/relay", handleRelay);
  server.on("/gpio", handleGpio);
  server.on("/status", handleStatus);
  server.on("/add-phase", handleAddPhase);
  server.on("/remove-phase", handleRemovePhase);
  server.on("/reset-phases", handleResetPhases);
}

void hidro_serial_command(String cmd) {
  if (cmd == "L1") {
    lightState = true; setRelay(RELE_LAMPADA, true); modeAuto = false;
    Serial.println("OK:L1");
  } else if (cmd == "L0") {
    lightState = false; setRelay(RELE_LAMPADA, false); modeAuto = false;
    Serial.println("OK:L0");
  } else if (cmd == "P1") {
    pumpState = true; setRelay(RELE_BOMBA, true); modeAuto = false;
    Serial.println("OK:P1");
  } else if (cmd == "P0") {
    pumpState = false; setRelay(RELE_BOMBA, false); modeAuto = false;
    Serial.println("OK:P0");
  } else if (cmd == "AUTO") {
    modeAuto = true;
    Serial.println("OK:AUTO");
  } else if (cmd == "STATUS") {
    Serial.printf("L:%d P:%d M:%s\n", lightState, pumpState, modeAuto ? "auto" : "manual");
  }
}

#endif // MOD_HIDRO
#endif // MOD_HIDRO_H
