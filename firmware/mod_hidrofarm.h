/*
  Cultivee Modulo - Hidro Farm (versao Premium)
  Fases, reles, automacao — clone do hidro (ponto de partida da versao Farm)
*/

#ifndef MOD_HIDROFARM_H
#define MOD_HIDROFARM_H
#ifdef MOD_HIDROFARM

// ===================== FASES =====================

#define HYDROFARM_CONFIG_VERSION 3  // Incrementar quando defaults mudarem

void loadDefaultPhasesFarm() {
  numPhases = 3;

  strcpy(phases[0].name, "Muda");
  phases[0].days = 3;
  phases[0].lightOnHour = 6; phases[0].lightOnMin = 0;
  phases[0].lightOffHour = 18; phases[0].lightOffMin = 0;
  phases[0].pumpOnDay = 15; phases[0].pumpOffDay = 15;
  phases[0].pumpOnNight = 15; phases[0].pumpOffNight = 45;
  phases[0].ventOnHour = 8; phases[0].ventOnMin = 0;
  phases[0].ventOffHour = 18; phases[0].ventOffMin = 0;
  phases[0].aerOnDay = 5; phases[0].aerOffDay = 10;
  phases[0].aerOnNight = 5; phases[0].aerOffNight = 30;

  strcpy(phases[1].name, "Bercario");
  phases[1].days = 17;
  phases[1].lightOnHour = 6; phases[1].lightOnMin = 0;
  phases[1].lightOffHour = 19; phases[1].lightOffMin = 0;
  phases[1].pumpOnDay = 15; phases[1].pumpOffDay = 15;
  phases[1].pumpOnNight = 15; phases[1].pumpOffNight = 45;
  phases[1].ventOnHour = 7; phases[1].ventOnMin = 0;
  phases[1].ventOffHour = 21; phases[1].ventOffMin = 0;
  phases[1].aerOnDay = 10; phases[1].aerOffDay = 10;
  phases[1].aerOnNight = 5; phases[1].aerOffNight = 30;

  strcpy(phases[2].name, "Engorda");
  phases[2].days = 0;  // infinito
  phases[2].lightOnHour = 6; phases[2].lightOnMin = 0;
  phases[2].lightOffHour = 20; phases[2].lightOffMin = 0;
  phases[2].pumpOnDay = 15; phases[2].pumpOffDay = 15;
  phases[2].pumpOnNight = 15; phases[2].pumpOffNight = 45;
  phases[2].ventOnHour = 6; phases[2].ventOnMin = 0;
  phases[2].ventOffHour = 22; phases[2].ventOffMin = 0;
  phases[2].aerOnDay = 10; phases[2].aerOffDay = 10;
  phases[2].aerOnNight = 10; phases[2].aerOffNight = 30;
}

void savePhasesFarm() {
  prefs.begin("hydrofarm", false);
  prefs.putInt("cfg_ver", HYDROFARM_CONFIG_VERSION);
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
    prefs.putInt((prefix + "voh").c_str(), phases[i].ventOnHour);
    prefs.putInt((prefix + "vom").c_str(), phases[i].ventOnMin);
    prefs.putInt((prefix + "vfh").c_str(), phases[i].ventOffHour);
    prefs.putInt((prefix + "vfm").c_str(), phases[i].ventOffMin);
    prefs.putInt((prefix + "aod").c_str(), phases[i].aerOnDay);
    prefs.putInt((prefix + "afd").c_str(), phases[i].aerOffDay);
    prefs.putInt((prefix + "aon").c_str(), phases[i].aerOnNight);
    prefs.putInt((prefix + "afn").c_str(), phases[i].aerOffNight);
  }
  prefs.end();
  Serial.println("Fases salvas no flash");
}

void loadPhasesFarm() {
  prefs.begin("hydrofarm", true);
  int configVersion = prefs.getInt("cfg_ver", 0);
  numPhases = prefs.getInt("num_phases", 0);
  String sd = prefs.getString("start_date", "");
  if (sd.length() > 0) strncpy(startDate, sd.c_str(), sizeof(startDate) - 1);
  // Sempre inicia em modo automatico (usuario pode trocar manualmente via app)
  modeAuto = true;

  // Se versao da config mudou ou nao tem fases, restaura defaults
  if (numPhases == 0 || configVersion < HYDROFARM_CONFIG_VERSION) {
    prefs.end();
    loadDefaultPhasesFarm();
    savePhasesFarm();
    Serial.printf("Config resetada (versao %d -> %d)\n", configVersion, HYDROFARM_CONFIG_VERSION);
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
    phases[i].ventOnHour = prefs.getInt((prefix + "voh").c_str(), 8);
    phases[i].ventOnMin = prefs.getInt((prefix + "vom").c_str(), 0);
    phases[i].ventOffHour = prefs.getInt((prefix + "vfh").c_str(), 20);
    phases[i].ventOffMin = prefs.getInt((prefix + "vfm").c_str(), 0);
    phases[i].aerOnDay = prefs.getInt((prefix + "aod").c_str(), 10);
    phases[i].aerOffDay = prefs.getInt((prefix + "afd").c_str(), 10);
    phases[i].aerOnNight = prefs.getInt((prefix + "aon").c_str(), 5);
    phases[i].aerOffNight = prefs.getInt((prefix + "afn").c_str(), 30);
  }
  prefs.end();
  Serial.printf("Fases carregadas: %d fases, inicio: %s\n", numPhases, startDate);
}

int getCycleDayFarm() {
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

int getCurrentPhaseIndexFarm() {
  int cycleDay = getCycleDayFarm();
  int dayCount = 0;
  for (int i = 0; i < numPhases; i++) {
    if (phases[i].days == 0) return i;
    dayCount += phases[i].days;
    if (cycleDay <= dayCount) return i;
  }
  return numPhases - 1;
}

// ===================== RELES E AUTOMACAO =====================

void setRelayFarm(int pin, bool on) {
  digitalWrite(pin, on ? RELE_ON : RELE_OFF);
}

bool isLightTimeFarm(Phase *p) {
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

bool isVentTimeFarm(Phase *p) {
  struct tm t;
  if (!getCurrentTime(&t)) return false;
  int nowMin = t.tm_hour * 60 + t.tm_min;
  int onMin = p->ventOnHour * 60 + p->ventOnMin;
  int offMin = p->ventOffHour * 60 + p->ventOffMin;
  if (onMin <= offMin) {
    return nowMin >= onMin && nowMin < offMin;
  } else {
    return nowMin >= onMin || nowMin < offMin;
  }
}

bool isDayTimeFarm(Phase *p) {
  return isLightTimeFarm(p);
}

// ===================== SENSOR DHT11 (inline — sem bibliotecas externas) =====================

// Le o DHT11 via protocolo 1-wire bit-banging. Bloqueante (~22ms), chamar so
// a cada >= 1s conforme spec do chip. Retorna true se leitura + checksum OK.
bool readDHT11Farm() {
  uint8_t data[5] = {0, 0, 0, 0, 0};

  // Start signal: pino LOW ~20ms, depois HIGH 40us, solta pino para leitura
  pinMode(DHT_PIN, OUTPUT);
  digitalWrite(DHT_PIN, LOW);
  delay(20);
  digitalWrite(DHT_PIN, HIGH);
  delayMicroseconds(40);
  pinMode(DHT_PIN, INPUT_PULLUP);

  // Resposta do DHT11: LOW ~80us, HIGH ~80us
  unsigned long timeout;
  timeout = micros() + 200;
  while (digitalRead(DHT_PIN) == HIGH) { if ((long)(micros() - timeout) >= 0) return false; }
  timeout = micros() + 200;
  while (digitalRead(DHT_PIN) == LOW)  { if ((long)(micros() - timeout) >= 0) return false; }
  timeout = micros() + 200;
  while (digitalRead(DHT_PIN) == HIGH) { if ((long)(micros() - timeout) >= 0) return false; }

  // 40 bits: cada bit = LOW 50us + HIGH (26us=0 / 70us=1)
  for (int i = 0; i < 40; i++) {
    timeout = micros() + 200;
    while (digitalRead(DHT_PIN) == LOW)  { if ((long)(micros() - timeout) >= 0) return false; }
    unsigned long t0 = micros();
    timeout = micros() + 200;
    while (digitalRead(DHT_PIN) == HIGH) { if ((long)(micros() - timeout) >= 0) return false; }
    unsigned long len = micros() - t0;
    if (len > 40) data[i / 8] |= (0x80 >> (i % 8));
  }

  // Checksum: byte0 + byte1 + byte2 + byte3 == byte4 (low 8 bits)
  uint8_t checksum = (data[0] + data[1] + data[2] + data[3]) & 0xFF;
  if (checksum != data[4]) return false;

  // DHT11: byte0 = umidade inteira, byte2 = temperatura inteira (byte1 e byte3 sempre 0)
  dhtHumidity    = data[0];
  dhtTemperature = data[2];
  dhtValid       = true;
  lastDhtOk      = millis();
  return true;
}

// ===================== RESERVATORIO (BOIAS + VALVULA) =====================

// Le os sensores de nivel com debounce de 2 amostras consecutivas.
// Chamada no loop principal; efetiva uma mudanca so apos 2 leituras iguais (~600ms).
void readLevelSensorsFarm() {
  unsigned long now = millis();
  if (now - lastLevelRead < 300) return;
  lastLevelRead = now;

  bool altoRaw  = (digitalRead(SENSOR_NIVEL_ALTO)  == LEVEL_SENSOR_ACTIVE);
  bool baixoRaw = (digitalRead(SENSOR_NIVEL_BAIXO) == LEVEL_SENSOR_ACTIVE);

  // Debounce: confirma mudanca so se leitura raw atual igual a anterior E diferente do estado atual
  if (altoRaw == highLevelRaw && altoRaw != highLevelState) {
    highLevelState = altoRaw;
    Serial.printf("Boia ALTA: %s\n", highLevelState ? "ATIVA" : "INATIVA");
  }
  if (baixoRaw == lowLevelRaw && baixoRaw != lowLevelState) {
    lowLevelState = baixoRaw;
    Serial.printf("Boia BAIXA: %s\n", lowLevelState ? "ATIVA" : "INATIVA");
  }

  highLevelRaw = altoRaw;
  lowLevelRaw  = baixoRaw;
}

// Retorna string com o estado logico do reservatorio (usado no JSON e dashboard).
// "full"    — ambos os sensores ativos, reservatorio cheio
// "filling" — so baixo ativo, agua entre os sensores
// "empty"   — ambos inativos, reservatorio abaixo do minimo
// "error"   — alto ativo mas baixo inativo (fisicamente impossivel — sensor defeituoso)
const char* reservoirStateStrFarm() {
  if (highLevelState && lowLevelState)  return "full";
  if (!highLevelState && lowLevelState) return "filling";
  if (!highLevelState && !lowLevelState) return "empty";
  return "error"; // alto ON + baixo OFF
}

// Maquina de estados da reposicao automatica.
// So atua se valveAuto == true. Em caso de erro de sensor, fecha valvula por seguranca.
void reservoirControlFarm() {
  if (!valveAuto) return;

  // ERRO: sensor alto ativo sem o baixo — fisicamente impossivel. Fecha por seguranca.
  if (highLevelState && !lowLevelState) {
    if (valveEntradaState) {
      valveEntradaState = false;
      setRelayFarm(RELE_VALVULA_ENTRADA, false);
      Serial.println("Auto: Valvula FECHADA (ERRO DE SENSOR — seguranca)");
    }
    return;
  }

  // CHEIO: alto ativo → fechar valvula
  if (highLevelState) {
    if (valveEntradaState) {
      valveEntradaState = false;
      setRelayFarm(RELE_VALVULA_ENTRADA, false);
      Serial.println("Auto: Valvula FECHADA (reservatorio cheio)");
    }
    return;
  }

  // VAZIO: ambos inativos → abrir valvula
  if (!highLevelState && !lowLevelState) {
    if (!valveEntradaState) {
      valveEntradaState = true;
      setRelayFarm(RELE_VALVULA_ENTRADA, true);
      Serial.println("Auto: Valvula ABERTA (reservatorio vazio)");
    }
    return;
  }

  // ENCHENDO: baixo ativo, alto inativo — manter estado atual (histerese)
}

void hidrofarm_loop() {
  // Sensores e automacao de nivel rodam SEMPRE (nao dependem do modeAuto global das fases)
  readLevelSensorsFarm();
  reservoirControlFarm();

  // DHT11: leitura a cada 5s (spec minima: 1s). Bloqueante ~22ms.
  if (millis() - lastDhtRead > 5000) {
    lastDhtRead = millis();
    if (!readDHT11Farm()) {
      dhtValid = false;  // Marca como invalido — UI mostra "--"
    }
  }

  if (!modeAuto) return;
  if (!modeAuto) return;
  struct tm testTime;
  if (!getCurrentTime(&testTime)) return;
  if (testTime.tm_year < (2024 - 1900)) return;
  if (!ntpSynced) ntpSynced = true;
  if (millis() - lastAutoCheck < 5000) return;
  lastAutoCheck = millis();

  int phaseIdx = getCurrentPhaseIndexFarm();
  Phase *p = &phases[phaseIdx];

  // Luz
  bool shouldLight = isLightTimeFarm(p);
  if (shouldLight != lightState) {
    lightState = shouldLight;
    setRelayFarm(RELE_LAMPADA, lightState);
    Serial.printf("Auto: Luz %s (fase: %s)\n", lightState ? "ON" : "OFF", p->name);
  }

  // Bomba (ciclo) — se valores invalidos (0), usa defaults seguros
  bool isDay = isDayTimeFarm(p);
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
      setRelayFarm(RELE_BOMBA, pumpState);
      Serial.printf("Auto: Bomba %s (%s, %lumin/%lumin)\n",
        pumpState ? "ON" : "OFF", isDay ? "dia" : "noite", pumpOn, pumpOff);
    }
  }

  // Ventilacao (horario — como luz)
  bool shouldVent = isVentTimeFarm(p);
  if (shouldVent != ventilationState) {
    ventilationState = shouldVent;
    setRelayFarm(RELE_VENTILACAO, ventilationState);
    Serial.printf("Auto: Ventilacao %s (fase: %s)\n", ventilationState ? "ON" : "OFF", p->name);
  }

  // Aeracao (ciclo — como bomba)
  unsigned long aerOn = isDay ? p->aerOnDay : p->aerOnNight;
  unsigned long aerOff = isDay ? p->aerOffDay : p->aerOffNight;
  if (aerOn == 0) aerOn = 5;
  if (aerOff == 0) aerOff = 10;
  if (getCurrentTime(&ct)) {
    unsigned long secsMid = ct.tm_hour * 3600UL + ct.tm_min * 60UL + ct.tm_sec;
    unsigned long aerCycleSec = (aerOn + aerOff) * 60UL;
    unsigned long aerPos = (secsMid % aerCycleSec) * 1000UL;
    unsigned long aerOnTime = aerOn * 60UL * 1000UL;
    bool shouldAer = aerPos < aerOnTime;
    if (shouldAer != aerationState) {
      aerationState = shouldAer;
      setRelayFarm(RELE_AERACAO, aerationState);
      Serial.printf("Auto: Aeracao %s (%s, %lumin/%lumin)\n",
        aerationState ? "ON" : "OFF", isDay ? "dia" : "noite", aerOn, aerOff);
    }
  }
}

// ===================== LED STATUS =====================

void updateStatusLedFarm() {
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

String hidrofarm_status_json() {
  struct tm t;
  bool hasTime = getCurrentTime(&t);
  int cycleDay = getCycleDayFarm();
  int phaseIdx = getCurrentPhaseIndexFarm();
  Phase *p = &phases[phaseIdx];

  String json = "";
  json += "\"mode\":\"" + String(modeAuto ? "auto" : "manual") + "\",";
  json += "\"light\":" + String(lightState ? "true" : "false") + ",";
  json += "\"pump\":" + String(pumpState ? "true" : "false") + ",";
  json += "\"ventilation\":" + String(ventilationState ? "true" : "false") + ",";
  json += "\"aeration\":" + String(aerationState ? "true" : "false") + ",";
  json += "\"valve_entrada\":" + String(valveEntradaState ? "true" : "false") + ",";
  json += "\"bomba_homo\":" + String(bombaHomoState ? "true" : "false") + ",";
  json += "\"valve_auto\":" + String(valveAuto ? "true" : "false") + ",";
  json += "\"level_high\":" + String(highLevelState ? "true" : "false") + ",";
  json += "\"level_low\":" + String(lowLevelState ? "true" : "false") + ",";
  json += "\"reservoir_state\":\"" + String(reservoirStateStrFarm()) + "\",";
  json += "\"temperature\":" + String(dhtTemperature) + ",";
  json += "\"humidity\":" + String(dhtHumidity) + ",";
  json += "\"dht_valid\":" + String(dhtValid ? "true" : "false") + ",";
  json += "\"cycle_day\":" + String(cycleDay) + ",";
  json += "\"phase\":\"" + String(p->name) + "\",";
  json += "\"phase_index\":" + String(phaseIdx) + ",";
  json += "\"num_phases\":" + String(numPhases) + ",";
  json += "\"start_date\":\"" + String(startDate) + "\",";
  json += "\"ntp_synced\":" + String(ntpSynced ? "true" : "false") + ",";
  json += "\"rtc_available\":" + String(rtcAvailable ? "true" : "false") + ",";
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
    json += ",\"ventOnHour\":" + String(phases[i].ventOnHour);
    json += ",\"ventOnMin\":" + String(phases[i].ventOnMin);
    json += ",\"ventOffHour\":" + String(phases[i].ventOffHour);
    json += ",\"ventOffMin\":" + String(phases[i].ventOffMin);
    json += ",\"aerOnDay\":" + String(phases[i].aerOnDay);
    json += ",\"aerOffDay\":" + String(phases[i].aerOffDay);
    json += ",\"aerOnNight\":" + String(phases[i].aerOnNight);
    json += ",\"aerOffNight\":" + String(phases[i].aerOffNight);
    json += "}";
  }
  json += "]";

  return json;
}

// JSON para registerOnServer (ctrl_data)
String hidrofarm_register_json() {
  struct tm t;
  bool hasTime = getCurrentTime(&t);
  int cycleDay = getCycleDayFarm();
  int phaseIdx = getCurrentPhaseIndexFarm();
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
    phasesJson += ",\"ventOnHour\":" + String(phases[i].ventOnHour);
    phasesJson += ",\"ventOnMin\":" + String(phases[i].ventOnMin);
    phasesJson += ",\"ventOffHour\":" + String(phases[i].ventOffHour);
    phasesJson += ",\"ventOffMin\":" + String(phases[i].ventOffMin);
    phasesJson += ",\"aerOnDay\":" + String(phases[i].aerOnDay);
    phasesJson += ",\"aerOffDay\":" + String(phases[i].aerOffDay);
    phasesJson += ",\"aerOnNight\":" + String(phases[i].aerOnNight);
    phasesJson += ",\"aerOffNight\":" + String(phases[i].aerOffNight);
    phasesJson += "}";
  }
  phasesJson += "]";

  String json = "";
  json += "\"light\":" + String(lightState ? "true" : "false") + ",";
  json += "\"pump\":" + String(pumpState ? "true" : "false") + ",";
  json += "\"ventilation\":" + String(ventilationState ? "true" : "false") + ",";
  json += "\"aeration\":" + String(aerationState ? "true" : "false") + ",";
  json += "\"valve_entrada\":" + String(valveEntradaState ? "true" : "false") + ",";
  json += "\"bomba_homo\":" + String(bombaHomoState ? "true" : "false") + ",";
  json += "\"valve_auto\":" + String(valveAuto ? "true" : "false") + ",";
  json += "\"level_high\":" + String(highLevelState ? "true" : "false") + ",";
  json += "\"level_low\":" + String(lowLevelState ? "true" : "false") + ",";
  json += "\"reservoir_state\":\"" + String(reservoirStateStrFarm()) + "\",";
  json += "\"temperature\":" + String(dhtTemperature) + ",";
  json += "\"humidity\":" + String(dhtHumidity) + ",";
  json += "\"dht_valid\":" + String(dhtValid ? "true" : "false") + ",";
  json += "\"mode\":\"" + String(modeAuto ? "auto" : "manual") + "\",";
  json += "\"phase\":\"" + String(p->name) + "\",";
  json += "\"phase_index\":" + String(phaseIdx) + ",";
  json += "\"cycle_day\":" + String(cycleDay) + ",";
  json += "\"num_phases\":" + String(numPhases) + ",";
  json += "\"start_date\":\"" + String(startDate) + "\",";
  json += "\"ntp_synced\":" + String(ntpSynced ? "true" : "false") + ",";
  json += "\"rtc_available\":" + String(rtcAvailable ? "true" : "false") + ",";
  json += "\"time\":\"" + String(timeStr) + "\",";
  json += "\"phases\":" + phasesJson;

  return json;
}

// ===================== ROUTE HANDLERS =====================

void handleGpioFarm() {
  String name = server.arg("name");
  String action = server.arg("action");

  if (name == "light") {
    if (!modeAuto || action == "toggle") {
      lightState = !lightState;
      setRelayFarm(RELE_LAMPADA, lightState);
      if (modeAuto) { modeAuto = false; }
      Serial.printf("GPIO: Luz %s\n", lightState ? "ON" : "OFF");
    }
  } else if (name == "pump") {
    if (!modeAuto || action == "toggle") {
      pumpState = !pumpState;
      setRelayFarm(RELE_BOMBA, pumpState);
      if (modeAuto) { modeAuto = false; }
      Serial.printf("GPIO: Bomba %s\n", pumpState ? "ON" : "OFF");
    }
  } else if (name == "ventilation") {
    if (!modeAuto || action == "toggle") {
      ventilationState = !ventilationState;
      setRelayFarm(RELE_VENTILACAO, ventilationState);
      if (modeAuto) { modeAuto = false; }
      Serial.printf("GPIO: Ventilacao %s\n", ventilationState ? "ON" : "OFF");
    }
  } else if (name == "aeration") {
    if (!modeAuto || action == "toggle") {
      aerationState = !aerationState;
      setRelayFarm(RELE_AERACAO, aerationState);
      if (modeAuto) { modeAuto = false; }
      Serial.printf("GPIO: Aeracao %s\n", aerationState ? "ON" : "OFF");
    }
  } else if (name == "valve_entrada") {
    // Toggle manual da valvula — so tem efeito se valveAuto=false (senao a automacao sobrepoe)
    valveEntradaState = !valveEntradaState;
    setRelayFarm(RELE_VALVULA_ENTRADA, valveEntradaState);
    Serial.printf("GPIO: Valvula Entrada %s\n", valveEntradaState ? "ON" : "OFF");
  } else if (name == "valve_auto") {
    // Toggle do modo da valvula — persiste no NVS
    valveAuto = !valveAuto;
    prefs.begin("hydrofarm", false);
    prefs.putBool("valve_auto", valveAuto);
    prefs.end();
    Serial.printf("GPIO: Valvula modo %s\n", valveAuto ? "AUTO (boias)" : "MANUAL");
  } else if (name == "bomba_homo") {
    // Rele sempre manual — NAO interage com modeAuto
    bombaHomoState = !bombaHomoState;
    setRelayFarm(RELE_BOMBA_HOMO, bombaHomoState);
    Serial.printf("GPIO: Bomba Homogeneizacao %s\n", bombaHomoState ? "ON" : "OFF");
  } else if (name == "mode") {
    modeAuto = !modeAuto;
    if (!modeAuto) {
      manualLight = lightState;
      manualPump = pumpState;
    }
    prefs.begin("hydrofarm", false);
    prefs.putBool("mode_auto", modeAuto);
    prefs.end();
    Serial.printf("GPIO: Modo %s\n", modeAuto ? "Auto" : "Manual");
  }

  sendCORS();
  server.send(200, "application/json", buildStatusJSON());
}

void handleRelayFarm() {
  String device = server.arg("device");
  String action = server.arg("action");

  if (device == "mode") {
    modeAuto = !modeAuto;
    if (!modeAuto) {
      manualLight = lightState;
      manualPump = pumpState;
    }
    prefs.begin("hydrofarm", false);
    prefs.putBool("mode_auto", modeAuto);
    prefs.end();
    Serial.printf("Modo: %s\n", modeAuto ? "Automatico" : "Manual");
  } else if (device == "light") {
    if (!modeAuto || action == "toggle") {
      lightState = !lightState;
      setRelayFarm(RELE_LAMPADA, lightState);
      if (!modeAuto) modeAuto = false;
      Serial.printf("Manual: Luz %s\n", lightState ? "ON" : "OFF");
    }
  } else if (device == "pump") {
    if (!modeAuto || action == "toggle") {
      pumpState = !pumpState;
      setRelayFarm(RELE_BOMBA, pumpState);
      if (!modeAuto) modeAuto = false;
      Serial.printf("Manual: Bomba %s\n", pumpState ? "ON" : "OFF");
    }
  } else if (device == "ventilation") {
    if (!modeAuto || action == "toggle") {
      ventilationState = !ventilationState;
      setRelayFarm(RELE_VENTILACAO, ventilationState);
      if (!modeAuto) modeAuto = false;
      Serial.printf("Manual: Ventilacao %s\n", ventilationState ? "ON" : "OFF");
    }
  } else if (device == "aeration") {
    if (!modeAuto || action == "toggle") {
      aerationState = !aerationState;
      setRelayFarm(RELE_AERACAO, aerationState);
      if (!modeAuto) modeAuto = false;
      Serial.printf("Manual: Aeracao %s\n", aerationState ? "ON" : "OFF");
    }
  } else if (device == "valve_entrada") {
    // Toggle manual da valvula — so tem efeito se valveAuto=false
    valveEntradaState = !valveEntradaState;
    setRelayFarm(RELE_VALVULA_ENTRADA, valveEntradaState);
    Serial.printf("Manual: Valvula Entrada %s\n", valveEntradaState ? "ON" : "OFF");
  } else if (device == "valve_auto") {
    // Toggle do modo da valvula — persiste no NVS
    valveAuto = !valveAuto;
    prefs.begin("hydrofarm", false);
    prefs.putBool("valve_auto", valveAuto);
    prefs.end();
    Serial.printf("Manual: Valvula modo %s\n", valveAuto ? "AUTO (boias)" : "MANUAL");
  } else if (device == "bomba_homo") {
    // Rele sempre manual — NAO interage com modeAuto
    bombaHomoState = !bombaHomoState;
    setRelayFarm(RELE_BOMBA_HOMO, bombaHomoState);
    Serial.printf("Manual: Bomba Homogeneizacao %s\n", bombaHomoState ? "ON" : "OFF");
  }

  sendCORS();
  server.send(200, "application/json", buildStatusJSON());
}

void handleStatusFarm() {
  sendCORS();
  server.send(200, "application/json", buildStatusJSON());
}

void handleAddPhaseFarm() {
  if (numPhases < MAX_PHASES) {
    strcpy(phases[numPhases].name, "Nova Fase");
    phases[numPhases].days = 7;
    phases[numPhases].lightOnHour = 6; phases[numPhases].lightOnMin = 0;
    phases[numPhases].lightOffHour = 18; phases[numPhases].lightOffMin = 0;
    phases[numPhases].pumpOnDay = 15; phases[numPhases].pumpOffDay = 15;
    phases[numPhases].pumpOnNight = 15; phases[numPhases].pumpOffNight = 45;
    phases[numPhases].ventOnHour = 8; phases[numPhases].ventOnMin = 0;
    phases[numPhases].ventOffHour = 20; phases[numPhases].ventOffMin = 0;
    phases[numPhases].aerOnDay = 5; phases[numPhases].aerOffDay = 10;
    phases[numPhases].aerOnNight = 5; phases[numPhases].aerOffNight = 30;
    numPhases++;
    savePhasesFarm();
  }
  server.sendHeader("Location", "/config");
  server.send(302);
}

void handleRemovePhaseFarm() {
  int idx = server.arg("idx").toInt();
  if (idx >= 0 && idx < numPhases && numPhases > 1) {
    for (int i = idx; i < numPhases - 1; i++) phases[i] = phases[i + 1];
    numPhases--;
    savePhasesFarm();
  }
  server.sendHeader("Location", "/config");
  server.send(302);
}

void handleResetPhasesFarm() {
  loadDefaultPhasesFarm();
  savePhasesFarm();
  server.sendHeader("Location", "/config");
  server.send(302);
}

void handleSaveConfigFarm() {
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

    String von = server.arg("von" + String(i));
    if (von.length() >= 5) {
      phases[i].ventOnHour = von.substring(0, 2).toInt();
      phases[i].ventOnMin = von.substring(3, 5).toInt();
    }
    String voff = server.arg("voff" + String(i));
    if (voff.length() >= 5) {
      phases[i].ventOffHour = voff.substring(0, 2).toInt();
      phases[i].ventOffMin = voff.substring(3, 5).toInt();
    }
    int aod = server.arg("aod" + String(i)).toInt();
    int afd = server.arg("afd" + String(i)).toInt();
    int aon = server.arg("aon" + String(i)).toInt();
    int afn = server.arg("afn" + String(i)).toInt();
    phases[i].aerOnDay = aod > 0 ? aod : 5;
    phases[i].aerOffDay = afd > 0 ? afd : 10;
    phases[i].aerOnNight = aon > 0 ? aon : 5;
    phases[i].aerOffNight = afn > 0 ? afn : 30;
  }
  numPhases = np;
  savePhasesFarm();

  server.sendHeader("Location", "/");
  server.send(302, "text/plain", "Salvo!");
}

// ===================== CONFIG PAGE HTML =====================

void handleConfigFarm() {
  String phaseForms = "";
  for (int i = 0; i < numPhases; i++) {
    Phase *p = &phases[i];
    String lonVal = (p->lightOnHour < 10 ? "0" : "") + String(p->lightOnHour) + ":" + (p->lightOnMin < 10 ? "0" : "") + String(p->lightOnMin);
    String loffVal = (p->lightOffHour < 10 ? "0" : "") + String(p->lightOffHour) + ":" + (p->lightOffMin < 10 ? "0" : "") + String(p->lightOffMin);
    String vonVal = (p->ventOnHour < 10 ? "0" : "") + String(p->ventOnHour) + ":" + (p->ventOnMin < 10 ? "0" : "") + String(p->ventOnMin);
    String voffVal = (p->ventOffHour < 10 ? "0" : "") + String(p->ventOffHour) + ":" + (p->ventOffMin < 10 ? "0" : "") + String(p->ventOffMin);

    phaseForms += "<div class='ph'>";
    phaseForms += "<div class='ph-hdr'><span class='ph-t'>Fase " + String(i + 1) + "</span>";
    if (numPhases > 1) phaseForms += "<button type='button' onclick=\"removePhase(" + String(i) + ")\" class='ph-rm'>&#10005;</button>";
    phaseForms += "</div>";

    phaseForms += "<div class='gr'><div class='fd'><label>Nome</label><input name='n" + String(i) + "' value='" + String(p->name) + "'></div>";
    phaseForms += "<div class='fd'><label>Dias</label><input type='number' name='d" + String(i) + "' value='" + String(p->days) + "' min='0' placeholder='0=infinito'></div></div>";

    phaseForms += "<div class='sl sl-l'>&#128161; Ilumina&ccedil;&atilde;o</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>Liga</label><input type='time' name='lon" + String(i) + "' value='" + lonVal + "'></div>";
    phaseForms += "<div class='fd'><label>Desliga</label><input type='time' name='loff" + String(i) + "' value='" + loffVal + "'></div></div>";

    phaseForms += "<div class='sl sl-p'>&#128167; Irriga&ccedil;&atilde;o Dia</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>ON (min)</label><input type='number' name='pod" + String(i) + "' value='" + String(p->pumpOnDay) + "' min='1'></div>";
    phaseForms += "<div class='fd'><label>OFF (min)</label><input type='number' name='pfd" + String(i) + "' value='" + String(p->pumpOffDay) + "' min='1'></div></div>";

    phaseForms += "<div class='sl sl-p'>&#127769; Irriga&ccedil;&atilde;o Noite</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>ON (min)</label><input type='number' name='pon" + String(i) + "' value='" + String(p->pumpOnNight) + "' min='1'></div>";
    phaseForms += "<div class='fd'><label>OFF (min)</label><input type='number' name='pfn" + String(i) + "' value='" + String(p->pumpOffNight) + "' min='1'></div></div>";

    phaseForms += "<div class='sl sl-v'>&#127744; Ventila&ccedil;&atilde;o</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>Liga</label><input type='time' name='von" + String(i) + "' value='" + vonVal + "'></div>";
    phaseForms += "<div class='fd'><label>Desliga</label><input type='time' name='voff" + String(i) + "' value='" + voffVal + "'></div></div>";

    phaseForms += "<div class='sl sl-a'>&#129707; Aera&ccedil;&atilde;o Dia</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>ON (min)</label><input type='number' name='aod" + String(i) + "' value='" + String(p->aerOnDay) + "' min='1'></div>";
    phaseForms += "<div class='fd'><label>OFF (min)</label><input type='number' name='afd" + String(i) + "' value='" + String(p->aerOffDay) + "' min='1'></div></div>";

    phaseForms += "<div class='sl sl-a'>&#127769; Aera&ccedil;&atilde;o Noite</div>";
    phaseForms += "<div class='gr'><div class='fd'><label>ON (min)</label><input type='number' name='aon" + String(i) + "' value='" + String(p->aerOnNight) + "' min='1'></div>";
    phaseForms += "<div class='fd'><label>OFF (min)</label><input type='number' name='afn" + String(i) + "' value='" + String(p->aerOffNight) + "' min='1'></div></div>";
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
.sl{font-size:0.8rem;font-weight:700;margin:0.75rem 0 0.35rem;padding:0.3rem 0.6rem;border-radius:0.5rem;display:inline-block}
.sl-l{color:hsl(142,71%,45%);background:hsla(142,71%,45%,0.12)}
.sl-p{color:hsl(210,80%,55%);background:hsla(210,80%,55%,0.12)}
.sl-v{color:#2ecc71;background:rgba(46,204,113,0.12)}
.sl-a{color:#00bcd4;background:rgba(0,188,212,0.12)}
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

String hidrofarm_dashboard_html() {
  int cycleDay = getCycleDayFarm();
  int phaseIdx = getCurrentPhaseIndexFarm();
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
  String ventIndicator = ventilationState ? "<span id='iv' style='color:#2ecc71'>&#9679; Vent Ligada</span>" : "<span id='iv' style='color:#666'>&#9679; Vent Desligada</span>";
  String aerIndicator = aerationState ? "<span id='ia' style='color:#00bcd4'>&#9679; Aera Ligada</span>" : "<span id='ia' style='color:#666'>&#9679; Aera Desligada</span>";

  String manualBtns = "";
  if (!modeAuto) {
    // Grid 2 colunas: LUZ/BOMBA, VENT/AERA (4 botoes da automacao de fase)
    // HOMOG foi movido para o card "Controles Extras" (sempre visivel, fora do modeAuto)
    manualBtns = "<div id='mb' style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px'>"
      "<button id='bl' onclick=\"cmd('light','toggle')\" style='padding:12px;border-radius:10px;border:none;font-weight:700;font-size:0.9rem;cursor:pointer;"
      + String(lightState ? "background:#27ae60;color:#fff'" : "background:#2a2d35;color:#aaa;border:1px solid #3a3d45'") + ">LUZ " + (lightState ? "ON" : "OFF") + "</button>"
      "<button id='bp' onclick=\"cmd('pump','toggle')\" style='padding:12px;border-radius:10px;border:none;font-weight:700;font-size:0.9rem;cursor:pointer;"
      + String(pumpState ? "background:#3498db;color:#fff'" : "background:#2a2d35;color:#aaa;border:1px solid #3a3d45'") + ">BOMBA " + (pumpState ? "ON" : "OFF") + "</button>"
      "<button id='bv' onclick=\"cmd('ventilation','toggle')\" style='padding:12px;border-radius:10px;border:none;font-weight:700;font-size:0.9rem;cursor:pointer;"
      + String(ventilationState ? "background:#2ecc71;color:#fff'" : "background:#2a2d35;color:#aaa;border:1px solid #3a3d45'") + ">VENT " + (ventilationState ? "ON" : "OFF") + "</button>"
      "<button id='ba' onclick=\"cmd('aeration','toggle')\" style='padding:12px;border-radius:10px;border:none;font-weight:700;font-size:0.9rem;cursor:pointer;"
      + String(aerationState ? "background:#00bcd4;color:#fff'" : "background:#2a2d35;color:#aaa;border:1px solid #3a3d45'") + ">AERA " + (aerationState ? "ON" : "OFF") + "</button></div>";
  }

  // Card "Controles Extras" — sempre visivel, independente do modeAuto
  // Contem o HOMOG (bomba de homogeneizacao) que nao faz parte da automacao por fase
  String extrasCard = "";
  extrasCard += "<div class='card'>";
  extrasCard += "<h3 style='font-size:0.9rem;margin-bottom:10px'>Controles Extras</h3>";
  extrasCard += "<button id='bbh' onclick=\"cmd('bomba_homo','toggle')\" style='width:100%;padding:12px;border-radius:10px;border:none;font-weight:700;font-size:0.85rem;cursor:pointer;"
    + String(bombaHomoState ? "background:#9b59b6;color:#fff'" : "background:#2a2d35;color:#aaa;border:1px solid #3a3d45'")
    + ">&#128260; HOMOG " + (bombaHomoState ? "ON" : "OFF") + "</button>";
  extrasCard += "</div>";

  // Card "Ambiente" — temperatura + umidade do DHT11
  String ambientCard = "";
  ambientCard += "<div class='card'>";
  ambientCard += "<h3 style='font-size:0.9rem;margin-bottom:10px'>&#127777; Ambiente</h3>";
  ambientCard += "<div class='grid'>";
  ambientCard += "<div class='stat'><div class='lb'>&#127777; Temperatura</div>";
  ambientCard += "<div id='atv' class='vl' style='color:#e67e22'>" + String(dhtValid ? String(dhtTemperature) + " &deg;C" : "--") + "</div></div>";
  ambientCard += "<div class='stat'><div class='lb'>&#128167; Umidade</div>";
  ambientCard += "<div id='ahv' class='vl' style='color:#4ba3ff'>" + String(dhtValid ? String(dhtHumidity) + " %" : "--") + "</div></div>";
  ambientCard += "</div>";
  if (dhtValid && lastDhtOk > 0) {
    unsigned long ago = (millis() - lastDhtOk) / 1000;
    ambientCard += "<div id='adu' style='text-align:center;font-size:0.7rem;color:#666;margin-top:6px'>atualizado ha " + String(ago) + "s</div>";
  } else {
    ambientCard += "<div id='adu' style='text-align:center;font-size:0.7rem;color:#e74c3c;margin-top:6px'>sensor offline</div>";
  }
  ambientCard += "</div>";

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
    phasesHtml += "<span style='color:#888;font-size:0.85rem'>" + diasStr + "</span></div>";
    phasesHtml += "<div style='color:#888;font-size:0.85rem;margin-top:4px'>";
    phasesHtml += "&#128161; " + String(ph->lightOnHour) + ":" + (ph->lightOnMin < 10 ? "0" : "") + String(ph->lightOnMin);
    phasesHtml += " - " + String(ph->lightOffHour) + ":" + (ph->lightOffMin < 10 ? "0" : "") + String(ph->lightOffMin) + "<br>";
    phasesHtml += "&#128167; Dia: " + String(ph->pumpOnDay) + "/" + String(ph->pumpOffDay) + "min";
    phasesHtml += " | Noite: " + String(ph->pumpOnNight) + "/" + String(ph->pumpOffNight) + "min<br>";
    phasesHtml += "&#127744; " + String(ph->ventOnHour) + ":" + (ph->ventOnMin < 10 ? "0" : "") + String(ph->ventOnMin);
    phasesHtml += " - " + String(ph->ventOffHour) + ":" + (ph->ventOffMin < 10 ? "0" : "") + String(ph->ventOffMin) + "<br>";
    phasesHtml += "&#129707; Dia: " + String(ph->aerOnDay) + "/" + String(ph->aerOffDay) + "min";
    phasesHtml += " | Noite: " + String(ph->aerOnNight) + "/" + String(ph->aerOffNight) + "min";
    phasesHtml += "</div></div>";
  }

  // Card "Reservatorio" — sempre visivel, com tanque visual, indicadores e controles
  const char* reservoirState = reservoirStateStrFarm();
  String stateLabel, stateColor, waterHeight, waterTop;
  if (strcmp(reservoirState, "full") == 0) {
    stateLabel = "CHEIO"; stateColor = "#27ae60";
    waterHeight = "92%"; waterTop = "8%";
  } else if (strcmp(reservoirState, "filling") == 0) {
    stateLabel = "ENCHENDO"; stateColor = "#3498db";
    waterHeight = "55%"; waterTop = "45%";
  } else if (strcmp(reservoirState, "empty") == 0) {
    stateLabel = "VAZIO"; stateColor = "#e67e22";
    waterHeight = "8%"; waterTop = "92%";
  } else {
    stateLabel = "ERRO"; stateColor = "#e74c3c";
    waterHeight = "50%"; waterTop = "50%";
  }

  String reservoirCard = "";
  reservoirCard += "<div class='card'>";
  reservoirCard += "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px'>";
  reservoirCard += "<h3 style='font-size:0.9rem'>&#128167; Reservatorio</h3>";
  reservoirCard += "<button id='bva' onclick=\"cmd('valve_auto','toggle')\" style='padding:4px 10px;border-radius:6px;font-size:0.7rem;font-weight:700;cursor:pointer;border:1px solid "
    + String(valveAuto ? "#27ae60;background:rgba(39,174,96,0.15);color:#27ae60'" : "#e67e22;background:rgba(230,126,34,0.15);color:#e67e22'")
    + ">Modo: " + String(valveAuto ? "AUTO" : "MANUAL") + "</button>";
  reservoirCard += "</div>";

  // Corpo: tanque a esquerda, indicadores/botoes a direita
  reservoirCard += "<div style='display:flex;gap:14px;align-items:center'>";

  // Tanque (60x160px)
  reservoirCard += "<div id='tank' style='position:relative;width:60px;height:160px;flex-shrink:0'>";
  reservoirCard += "<div style='width:100%;height:100%;border:2px solid #3a3d45;border-radius:6px;background:#1a1d23;position:relative;overflow:hidden'>";
  reservoirCard += "<div id='tankWater' style='position:absolute;left:0;right:0;top:" + waterTop + ";height:" + waterHeight
    + ";background:linear-gradient(to top,#2980b9,#4ba3ff);transition:all 0.5s ease'></div>";
  // Linha do sensor ALTO em ~13% do topo
  reservoirCard += "<div style='position:absolute;left:-4px;right:-4px;top:13%;border-top:1px dashed #888;pointer-events:none'></div>";
  // Linha do sensor BAIXO em ~70% do topo
  reservoirCard += "<div style='position:absolute;left:-4px;right:-4px;top:70%;border-top:1px dashed #888;pointer-events:none'></div>";
  reservoirCard += "</div></div>";

  // Coluna da direita
  reservoirCard += "<div style='flex:1;display:flex;flex-direction:column;gap:8px'>";
  // Indicadores dos sensores
  reservoirCard += "<div id='ilh' style='font-size:0.8rem;color:" + String(highLevelState ? "#27ae60" : "#666") + "'>&#9679; Alto: " + String(highLevelState ? "ATIVO" : "inativo") + "</div>";
  reservoirCard += "<div id='ill' style='font-size:0.8rem;color:" + String(lowLevelState ? "#27ae60" : "#666") + "'>&#9679; Baixo: " + String(lowLevelState ? "ATIVO" : "inativo") + "</div>";
  // Estado + valvula
  reservoirCard += "<div id='irs' style='font-size:0.85rem;margin-top:4px'><b>Estado:</b> <span style='color:" + stateColor + "'>" + stateLabel + "</span></div>";
  reservoirCard += "<div id='irv' style='font-size:0.85rem'><b>Valvula:</b> <span style='color:" + String(valveEntradaState ? "#4ba3ff" : "#888") + "'>" + String(valveEntradaState ? "ABERTA" : "FECHADA") + "</span></div>";
  reservoirCard += "</div></div>";

  // Botao unico de toggle (so aparece em modo MANUAL da valvula)
  if (!valveAuto) {
    reservoirCard += "<div id='vmb' style='margin-top:12px'>";
    reservoirCard += "<button id='bvt' onclick=\"cmd('valve_entrada','toggle')\" style='width:100%;padding:12px;border-radius:10px;border:none;font-weight:700;font-size:0.9rem;cursor:pointer;"
      + String(valveEntradaState ? "background:#e74c3c;color:#fff'" : "background:#4ba3ff;color:#fff'")
      + ">" + String(valveEntradaState ? "&#9940; FECHAR VALVULA" : "&#128167; ABRIR VALVULA") + "</button>";
    reservoirCard += "</div>";
  }
  reservoirCard += "</div>";

  String html = "";
  html += "<div class='card'>";
  html += "<div class='grid'>";
  html += "<div class='stat'><div class='lb'>Ciclo</div><div class='vl'>Dia " + String(cycleDay) + "</div></div>";
  html += "<div class='stat'><div class='lb'>Fase</div><div class='vl' style='font-size:1rem'>" + String(p->name) + "</div></div>";
  html += "<div class='stat'><div class='lb'>Inicio</div><div class='vl' style='font-size:0.9rem'>" + String(startDateFmt) + "</div></div>";
  html += "<div class='stat'><div class='lb'>Hoje</div><div class='vl' style='font-size:0.9rem'>" + String(todayStr) + "</div></div>";
  html += "</div>";
  html += "<div class='ind'>" + lightIndicator + pumpIndicator + "</div><div class='ind'>" + ventIndicator + aerIndicator + "</div>";
  html += modeBtn + manualBtns;
  html += "</div>";

  html += extrasCard;
  html += ambientCard;
  html += reservoirCard;

  html += "<div class='card'><h3 style='font-size:0.9rem;margin-bottom:8px'>Fases Configuradas";
  html += "<a href='/config' style='float:right;color:#27ae60;font-size:0.8rem;text-decoration:none'>&#9881; Configurar</a></h3>";
  html += phasesHtml + "</div>";

  return html;
}

String hidrofarm_dashboard_js() {
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
var iv=document.getElementById('iv'),ia=document.getElementById('ia'),
bv=document.getElementById('bv'),ba=document.getElementById('ba');
if(iv){iv.style.color=s.ventilation?'#2ecc71':'#666';iv.innerHTML=s.ventilation?'&#9679; Vent Ligada':'&#9679; Vent Desligada'}
if(ia){ia.style.color=s.aeration?'#00bcd4':'#666';ia.innerHTML=s.aeration?'&#9679; Aera Ligada':'&#9679; Aera Desligada'}
if(bv){bv.style.background=s.ventilation?'#2ecc71':'#2a2d35';bv.style.color=s.ventilation?'#fff':'#aaa';bv.textContent='VENT '+(s.ventilation?'ON':'OFF')}
if(ba){ba.style.background=s.aeration?'#00bcd4':'#2a2d35';ba.style.color=s.aeration?'#fff':'#aaa';ba.textContent='AERA '+(s.aeration?'ON':'OFF')}
var bbh=document.getElementById('bbh');
if(bbh){bbh.style.background=s.bomba_homo?'#9b59b6':'#2a2d35';bbh.style.color=s.bomba_homo?'#fff':'#aaa';bbh.innerHTML='&#128260; HOMOG '+(s.bomba_homo?'ON':'OFF')}
// Reservatorio
var ilh=document.getElementById('ilh'),ill=document.getElementById('ill'),irs=document.getElementById('irs'),irv=document.getElementById('irv'),tw=document.getElementById('tankWater'),bva=document.getElementById('bva'),bvt=document.getElementById('bvt'),vmb=document.getElementById('vmb');
if(ilh){ilh.style.color=s.level_high?'#27ae60':'#666';ilh.innerHTML='&#9679; Alto: '+(s.level_high?'ATIVO':'inativo')}
if(ill){ill.style.color=s.level_low?'#27ae60':'#666';ill.innerHTML='&#9679; Baixo: '+(s.level_low?'ATIVO':'inativo')}
if(irs){var lbl='',col='#888';if(s.reservoir_state==='full'){lbl='CHEIO';col='#27ae60'}else if(s.reservoir_state==='filling'){lbl='ENCHENDO';col='#3498db'}else if(s.reservoir_state==='empty'){lbl='VAZIO';col='#e67e22'}else if(s.reservoir_state==='error'){lbl='ERRO';col='#e74c3c'}irs.innerHTML='<b>Estado:</b> <span style="color:'+col+'">'+lbl+'</span>'}
if(irv){irv.innerHTML='<b>Valvula:</b> <span style="color:'+(s.valve_entrada?'#4ba3ff':'#888')+'">'+(s.valve_entrada?'ABERTA':'FECHADA')+'</span>'}
if(tw){var h='50%',t='50%';if(s.reservoir_state==='full'){h='92%';t='8%'}else if(s.reservoir_state==='filling'){h='55%';t='45%'}else if(s.reservoir_state==='empty'){h='8%';t='92%'}tw.style.height=h;tw.style.top=t}
if(bva){var va=s.valve_auto;bva.style.borderColor=va?'#27ae60':'#e67e22';bva.style.background=va?'rgba(39,174,96,0.15)':'rgba(230,126,34,0.15)';bva.style.color=va?'#27ae60':'#e67e22';bva.textContent='Modo: '+(va?'AUTO':'MANUAL');if(va&&vmb){vmb.remove()}else if(!va&&!vmb){location.reload()}}
if(bvt){bvt.style.background=s.valve_entrada?'#e74c3c':'#4ba3ff';bvt.innerHTML=s.valve_entrada?'&#9940; FECHAR VALVULA':'&#128167; ABRIR VALVULA'}
// Ambiente (DHT11)
var atv=document.getElementById('atv'),ahv=document.getElementById('ahv'),adu=document.getElementById('adu');
if(atv){atv.innerHTML=s.dht_valid?(s.temperature+' &deg;C'):'--'}
if(ahv){ahv.innerHTML=s.dht_valid?(s.humidity+' %'):'--'}
if(adu){if(s.dht_valid){adu.style.color='#666';adu.textContent='atualizado agora'}else{adu.style.color='#e74c3c';adu.textContent='sensor offline'}}
var isAuto=s.mode==='auto';
if(bm){bm.style.borderColor=isAuto?'#27ae60':'#e67e22';bm.style.background=isAuto?'rgba(39,174,96,0.1)':'rgba(230,126,34,0.1)';bm.style.color=isAuto?'#27ae60':'#e67e22';bm.innerHTML=isAuto?'&#9881; Modo Automatico':'&#9995; Modo Manual'}
if(isAuto&&mb){mb.remove()}
if(!isAuto&&!mb){location.reload()}
}
setInterval(()=>fetch('/status').then(r=>r.json()).then(s=>upd(s)).catch(()=>{}),10000);
)rawliteral";
}

// ===================== COMMAND HANDLER =====================

bool hidrofarm_process_command(String cmd, String obj) {
  if (cmd == "relay") {
    String device = jsonVal(obj, "device");
    if (device == "mode") {
      modeAuto = !modeAuto;
      Serial.printf("Remoto: Modo %s\n", modeAuto ? "Auto" : "Manual");
    } else if (device == "light") {
      lightState = !lightState;
      setRelayFarm(RELE_LAMPADA, lightState);
      if (modeAuto) modeAuto = false;
      Serial.printf("Remoto: Luz %s\n", lightState ? "ON" : "OFF");
    } else if (device == "pump") {
      pumpState = !pumpState;
      setRelayFarm(RELE_BOMBA, pumpState);
      if (modeAuto) modeAuto = false;
      Serial.printf("Remoto: Bomba %s\n", pumpState ? "ON" : "OFF");
    } else if (device == "ventilation") {
      ventilationState = !ventilationState;
      setRelayFarm(RELE_VENTILACAO, ventilationState);
      if (modeAuto) modeAuto = false;
      Serial.printf("Remoto: Ventilacao %s\n", ventilationState ? "ON" : "OFF");
    } else if (device == "aeration") {
      aerationState = !aerationState;
      setRelayFarm(RELE_AERACAO, aerationState);
      if (modeAuto) modeAuto = false;
      Serial.printf("Remoto: Aeracao %s\n", aerationState ? "ON" : "OFF");
    } else if (device == "valve_entrada") {
      // Toggle manual da valvula — so tem efeito se valveAuto=false
      valveEntradaState = !valveEntradaState;
      setRelayFarm(RELE_VALVULA_ENTRADA, valveEntradaState);
      Serial.printf("Remoto: Valvula Entrada %s\n", valveEntradaState ? "ON" : "OFF");
    } else if (device == "valve_auto") {
      valveAuto = !valveAuto;
      prefs.begin("hydrofarm", false);
      prefs.putBool("valve_auto", valveAuto);
      prefs.end();
      Serial.printf("Remoto: Valvula modo %s\n", valveAuto ? "AUTO (boias)" : "MANUAL");
    } else if (device == "bomba_homo") {
      // Rele sempre manual — NAO interage com modeAuto
      bombaHomoState = !bombaHomoState;
      setRelayFarm(RELE_BOMBA_HOMO, bombaHomoState);
      Serial.printf("Remoto: Bomba Homogeneizacao %s\n", bombaHomoState ? "ON" : "OFF");
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
      phases[numPhases].ventOnHour = 8; phases[numPhases].ventOnMin = 0;
      phases[numPhases].ventOffHour = 20; phases[numPhases].ventOffMin = 0;
      phases[numPhases].aerOnDay = 5; phases[numPhases].aerOffDay = 10;
      phases[numPhases].aerOnNight = 5; phases[numPhases].aerOffNight = 30;
      numPhases++;
      savePhasesFarm();
      Serial.println("Remoto: Fase adicionada");
    }
    return true;
  } else if (cmd == "reset-phases") {
    loadDefaultPhasesFarm();
    savePhasesFarm();
    Serial.println("Remoto: Fases restauradas");
    return true;
  } else if (cmd == "remove-phase") {
    int idx = jsonInt(obj, "idx");
    if (idx >= 0 && idx < numPhases && numPhases > 1) {
      for (int i = idx; i < numPhases - 1; i++) phases[i] = phases[i + 1];
      numPhases--;
      savePhasesFarm();
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

        String von = jsonVal(obj, "von" + String(i));
        if (von.length() >= 5) {
          phases[i].ventOnHour = von.substring(0, 2).toInt();
          phases[i].ventOnMin = von.substring(3, 5).toInt();
        }
        String voff = jsonVal(obj, "voff" + String(i));
        if (voff.length() >= 5) {
          phases[i].ventOffHour = voff.substring(0, 2).toInt();
          phases[i].ventOffMin = voff.substring(3, 5).toInt();
        }
        int aod = jsonInt(obj, "aod" + String(i));
        int afd = jsonInt(obj, "afd" + String(i));
        int aon = jsonInt(obj, "aon" + String(i));
        int afn = jsonInt(obj, "afn" + String(i));
        phases[i].aerOnDay = aod > 0 ? aod : 5;
        phases[i].aerOffDay = afd > 0 ? afd : 10;
        phases[i].aerOnNight = aon > 0 ? aon : 5;
        phases[i].aerOffNight = afn > 0 ? afn : 30;
      }
      numPhases = np;
    }
    savePhasesFarm();
    Serial.println("Remoto: Config salva");
    return true;
  }
  return false;
}

// ===================== SETUP & ROUTES =====================

void hidrofarm_setup() {
  rtcInit();
  if (rtcAvailable) rtcSeedFromCompileTime();

  // Reles automatizados (controlados pelas fases/automacao)
  pinMode(RELE_LAMPADA, OUTPUT);
  pinMode(RELE_BOMBA, OUTPUT);
  pinMode(RELE_VENTILACAO, OUTPUT);
  pinMode(RELE_AERACAO, OUTPUT);
  setRelayFarm(RELE_LAMPADA, false);
  setRelayFarm(RELE_BOMBA, false);
  setRelayFarm(RELE_VENTILACAO, false);
  setRelayFarm(RELE_AERACAO, false);

  // Reles extras do hidro-farm
  pinMode(RELE_VALVULA_ENTRADA, OUTPUT);
  pinMode(RELE_BOMBA_HOMO, OUTPUT);
  setRelayFarm(RELE_VALVULA_ENTRADA, false);
  setRelayFarm(RELE_BOMBA_HOMO, false);

  // Sensores de nivel (boias) — INPUT_PULLUP (fail-safe: sem cabo = inativo)
  pinMode(SENSOR_NIVEL_ALTO, INPUT_PULLUP);
  pinMode(SENSOR_NIVEL_BAIXO, INPUT_PULLUP);

  // DHT11: pino em INPUT_PULLUP por default — a funcao de leitura alterna pra OUTPUT temporariamente
  pinMode(DHT_PIN, INPUT_PULLUP);

  // Carrega preferencia do modo da valvula (default: auto)
  prefs.begin("hydrofarm", true);
  valveAuto = prefs.getBool("valve_auto", true);
  prefs.end();
  Serial.printf("Valvula: modo %s (NVS)\n", valveAuto ? "AUTO (boias)" : "MANUAL");

  loadPhasesFarm();
}

void hidrofarm_register_routes() {
  server.on("/config", handleConfigFarm);
  server.on("/save-config", HTTP_POST, handleSaveConfigFarm);
  server.on("/relay", handleRelayFarm);
  server.on("/gpio", handleGpioFarm);
  server.on("/status", handleStatusFarm);
  server.on("/add-phase", handleAddPhaseFarm);
  server.on("/remove-phase", handleRemovePhaseFarm);
  server.on("/reset-phases", handleResetPhasesFarm);
}

void hidrofarm_serial_command(String cmd) {
  if (cmd == "L1") {
    lightState = true; setRelayFarm(RELE_LAMPADA, true); modeAuto = false;
    Serial.println("OK:L1");
  } else if (cmd == "L0") {
    lightState = false; setRelayFarm(RELE_LAMPADA, false); modeAuto = false;
    Serial.println("OK:L0");
  } else if (cmd == "P1") {
    pumpState = true; setRelayFarm(RELE_BOMBA, true); modeAuto = false;
    Serial.println("OK:P1");
  } else if (cmd == "P0") {
    pumpState = false; setRelayFarm(RELE_BOMBA, false); modeAuto = false;
    Serial.println("OK:P0");
  } else if (cmd == "V1") {
    ventilationState = true; setRelayFarm(RELE_VENTILACAO, true); modeAuto = false;
    Serial.println("OK:V1");
  } else if (cmd == "V0") {
    ventilationState = false; setRelayFarm(RELE_VENTILACAO, false); modeAuto = false;
    Serial.println("OK:V0");
  } else if (cmd == "A1") {
    aerationState = true; setRelayFarm(RELE_AERACAO, true); modeAuto = false;
    Serial.println("OK:A1");
  } else if (cmd == "A0") {
    aerationState = false; setRelayFarm(RELE_AERACAO, false); modeAuto = false;
    Serial.println("OK:A0");
  } else if (cmd == "VE1") {
    valveEntradaState = true; setRelayFarm(RELE_VALVULA_ENTRADA, true);
    Serial.println("OK:VE1");
  } else if (cmd == "VE0") {
    valveEntradaState = false; setRelayFarm(RELE_VALVULA_ENTRADA, false);
    Serial.println("OK:VE0");
  } else if (cmd == "BH1") {
    bombaHomoState = true; setRelayFarm(RELE_BOMBA_HOMO, true);
    Serial.println("OK:BH1");
  } else if (cmd == "BH0") {
    bombaHomoState = false; setRelayFarm(RELE_BOMBA_HOMO, false);
    Serial.println("OK:BH0");
  } else if (cmd == "VA1") {
    valveAuto = true;
    prefs.begin("hydrofarm", false); prefs.putBool("valve_auto", true); prefs.end();
    Serial.println("OK:VA1 (valvula AUTO)");
  } else if (cmd == "VA0") {
    valveAuto = false;
    prefs.begin("hydrofarm", false); prefs.putBool("valve_auto", false); prefs.end();
    Serial.println("OK:VA0 (valvula MANUAL)");
  } else if (cmd == "LEVEL") {
    Serial.printf("Nivel ALTO:%d BAIXO:%d Estado:%s Valvula:%s Modo:%s\n",
      highLevelState, lowLevelState, reservoirStateStrFarm(),
      valveEntradaState ? "ABERTA" : "FECHADA",
      valveAuto ? "auto" : "manual");
  } else if (cmd == "AUTO") {
    modeAuto = true;
    Serial.println("OK:AUTO");
  } else if (cmd == "STATUS") {
    Serial.printf("L:%d P:%d V:%d A:%d VE:%d BH:%d VA:%d LH:%d LL:%d M:%s\n",
      lightState, pumpState, ventilationState, aerationState,
      valveEntradaState, bombaHomoState, valveAuto, highLevelState, lowLevelState,
      modeAuto ? "auto" : "manual");
  }
}

#endif // MOD_HIDROFARM
#endif // MOD_HIDROFARM_H
