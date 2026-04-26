"""
Cultivee — Sistema de Alertas (Push PWA + Email)
Monitora condicoes dos modulos e notifica o usuario.

Chamado a cada register do ESP32 (a cada 10s). Verifica thresholds
e envia notificacao se condicao persistir alem do tempo configurado.

Alertas implementados:
- reservoir_empty: reservatorio vazio por 10+ minutos

Extensivel: adicionar metodos _check_* para novos tipos de alerta
(temperatura, modulo offline, bomba travada, etc.).
"""

import os
import json
import time
import logging
import smtplib
import uuid
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

log = logging.getLogger(__name__)

# Timer em memoria: {chip_id: {alert_type: first_seen_timestamp}}
# Reseta quando a condicao desaparece. Nao persiste entre reboots do servidor.
_alert_timers = {}


# =====================================================================
# v4.1.52 — Catalogo de alertas POR MODULO (universal + por produto)
# =====================================================================
# Refator do catalogo global anterior (v4.1.40 ALERT_CATALOG). Motivacao:
# os modulos foram pensados pra serem totalmente independentes — interface
# e router/storage, nao "decisor". O catalogo unificado contradizia isso:
# user com so Camera via alertas de "level_low" que jamais disparariam.
#
# Solucao: cada modulo carrega o seu catalogo proprio = UNIVERSAIS (todo
# modulo tem) + ESPECIFICOS DO PRODUTO (declarados aqui por module_type).
# Adicionar produto novo = adicionar entry em PRODUCT_ALERTS, sem mexer
# em endpoint, UI, ou banco.
#
# Severidades:
#   P0 — emergencia (acao imediata): vazamento, modulo critico offline >24h
#   P1 — alta (acao no dia): reservatorio vazio, modulo offline 60min-24h
#   P2 — media (acao na semana): leitura anormal, instabilidade WiFi
#   P3 — info (registro): recovery, atualizacao aplicada
# =====================================================================

# Alertas que TODO modulo tem — derivados de campos universais (offline
# detection no servidor, min_free_heap/wifi_disconnect_count reportados
# por todo firmware desde v4.1.8/v4.1.26).
UNIVERSAL_ALERTS = {
    "module_offline": {
        "name": "Modulo offline",
        "severity_default": "P1",
        "cooldown_sec": 4 * 3600,    # offline_watcher escala P0=12h se >24h
    },
    "module_recovered": {
        "name": "Modulo voltou online",
        "severity_default": "P3",    # info, nao urgente
        "cooldown_sec": 3600,
    },
    "low_heap_warning": {
        "name": "Memoria baixa no modulo",
        "severity_default": "P2",
        "cooldown_sec": 24 * 3600,   # alerta no maximo 1x/dia
    },
    "wifi_disconnect_burst": {
        "name": "WiFi instavel (varias quedas)",
        "severity_default": "P2",
        "cooldown_sec": 6 * 3600,
    },
}

# Alertas especificos por module_type. Adicionar produto novo aqui +
# implementar a deteccao em AlertManager (se nao for o servidor que detecta).
# Nome do alerta DEVE ser unico globalmente — mesmo que aplicavel a varios
# produtos (ex: sensor_invalid existe em hidro e hidro-farm).
PRODUCT_ALERTS = {
    "hidro": {
        # Hidro tem RTC + 4 reles. RTC desync e um sinal valido — adia
        # ate o firmware reportar `rtc_offline` ou similar.
    },
    "hidro-farm": {
        "level_low": {
            "name": "Reservatorio vazio",
            "severity_default": "P1",
            "cooldown_sec": 3600,
        },
        "sensor_invalid": {
            "name": "Sensor DHT11 com leitura invalida",
            "severity_default": "P2",
            "cooldown_sec": 12 * 3600,
        },
        # v4.1.58: 4 alertas novos (server-only, zero firmware change)
        "dht_temperature_high": {
            "name": "Temperatura alta no ambiente",
            "severity_default": "P2",
            "cooldown_sec": 6 * 3600,
        },
        "dht_temperature_low": {
            "name": "Temperatura baixa no ambiente",
            "severity_default": "P2",
            "cooldown_sec": 6 * 3600,
        },
        "dht_humidity_extreme": {
            "name": "Umidade fora da faixa segura",
            "severity_default": "P3",
            "cooldown_sec": 12 * 3600,
        },
        "reservoir_fill_stuck": {
            "name": "Reservatorio nao enche (valvula aberta sem agua)",
            "severity_default": "P1",
            "cooldown_sec": 4 * 3600,
        },
    },
    "cam": {
        # v4.1.58: 1 alerta server-only (baseado em last_capture_at)
        "cam_capture_failed": {
            "name": "Falha de captura na camera",
            "severity_default": "P2",
            "cooldown_sec": 12 * 3600,
        },
        # v4.1.59: 2 alertas que requerem firmware Cam >= v4.1.59
        # (reporta cam_init_error_code) + instrumentacao no upload pra
        # rolling window de tamanhos (recent_capture_sizes).
        "cam_init_failed": {
            "name": "Falha ao inicializar a camera",
            "severity_default": "P1",
            "cooldown_sec": 24 * 3600,   # 1x/dia max — bug de hardware nao se resolve sozinho
        },
        "cam_dark_frame": {
            "name": "Capturas com frame anormal (escuro/uniforme)",
            "severity_default": "P3",
            "cooldown_sec": 24 * 3600,   # info — nao urgente
        },
    },
}


def get_alerts_for_module(module_type):
    """
    Retorna catalogo aplicavel a UM modulo: universais + especificos do
    produto. Funcao pura — sem knowledge cruzado entre modulos.
    """
    return {**UNIVERSAL_ALERTS, **PRODUCT_ALERTS.get(module_type, {})}


def get_alert_meta(alert_type, module_type=None):
    """
    Retorna metadata do alerta. Se module_type for passado, busca primeiro
    no catalogo do modulo (precedencia: produto > universal). Fallback
    defensivo se desconhecido.

    Mantida assinatura compativel — module_type e opcional. Sem ele, busca
    nos universais e em todos os produtos (primeiro match vence — ok porque
    nomes sao unicos globalmente por design).
    """
    if module_type:
        catalog = get_alerts_for_module(module_type)
        if alert_type in catalog:
            return catalog[alert_type]
    # Fallback: procura globalmente (universal + todos produtos)
    if alert_type in UNIVERSAL_ALERTS:
        return UNIVERSAL_ALERTS[alert_type]
    for product_catalog in PRODUCT_ALERTS.values():
        if alert_type in product_catalog:
            return product_catalog[alert_type]
    return {
        "name": alert_type,
        "severity_default": "P2",
        "cooldown_sec": 3600,
    }


def _user_wants_channel(user_id, chip_id, alert_type, channel):
    """
    v4.1.52: prefs agora per-modulo. Se nao ha pref pra esse (chip, type),
    default ON. channel: 'push' ou 'email'.
    """
    import models as _m
    prefs = _m.get_module_alert_prefs(user_id, chip_id)
    p = prefs.get(alert_type)
    if not p:
        return True  # nenhuma pref = default ON
    if channel == "push":
        return p.get("enabled_push", True)
    if channel == "email":
        return p.get("enabled_email", True)
    return True


def _is_in_silent_hours(user_id, severity):
    """
    v4.1.41: True se estamos na janela de silencio do user E severidade != P0.
    P0 e emergencia — sempre passa, ate de madrugada.
    Janela suporta atravessar meia-noite (ex: 22:00 → 07:00).
    """
    if severity == "P0":
        return False  # emergencia ignora silencio
    import models as _m
    start_str, end_str = _m.get_user_silent_hours(user_id)
    if not start_str or not end_str:
        return False  # nao configurado
    try:
        from datetime import datetime
        # Compara so HH:MM do horario local atual
        now = datetime.now().strftime("%H:%M")
        # Janela normal (start < end, mesmo dia): 09:00 → 18:00
        if start_str < end_str:
            return start_str <= now < end_str
        # Janela cruzando meia-noite: 22:00 → 07:00
        return now >= start_str or now < end_str
    except Exception:
        return False


class AlertManager:
    """Verifica condicoes de alerta e envia notificacoes."""

    def check(self, chip_id, ctrl_data, module):
        """Chamado a cada register do ESP32. ctrl_data e dict (raw do ESP32), module e row do DB."""
        user_id = module.get("user_id")
        if not user_id:
            return  # Modulo nao pareado — sem usuario pra notificar

        # Merge: dados do ESP32 + dados do banco (low_since, alert_threshold_min, etc.)
        # O ESP32 nao manda campos gerenciados pelo servidor — precisa ler do banco.
        import json as _json
        try:
            db_data = _json.loads(module.get("ctrl_data", "{}"))
        except (ValueError, TypeError):
            db_data = {}
        merged = {**db_data, **ctrl_data}  # ESP32 sobrescreve dados do banco, mas campos ausentes ficam

        # Alerta: reservatorio vazio por 10+ minutos
        self._check_reservoir(chip_id, merged, user_id, module)

        # v4.1.40: 3 checks novos (zero impacto no firmware — usam dados ja
        # reportados via register desde v4.1.8/v4.1.26)
        try:
            self._check_low_heap(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_low_heap falhou pra {chip_id}: {e}")
        try:
            self._check_sensor_invalid(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_sensor_invalid falhou pra {chip_id}: {e}")
        try:
            self._check_wifi_disconnect_burst(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_wifi_burst falhou pra {chip_id}: {e}")

        # v4.1.58: 5 alertas novos (server-only). Filtra por module_type
        # internamente — alerta de DHT so faz sentido pra hidro-farm,
        # capture_failed so pra cam, etc.
        module_type = module.get("type") if module else None
        try:
            if module_type == "hidro-farm":
                self._check_dht_temperature(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_dht_temperature falhou pra {chip_id}: {e}")
        try:
            if module_type == "hidro-farm":
                self._check_dht_humidity(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_dht_humidity falhou pra {chip_id}: {e}")
        try:
            if module_type == "hidro-farm":
                self._check_reservoir_fill_stuck(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_fill_stuck falhou pra {chip_id}: {e}")
        try:
            if module_type == "cam":
                self._check_cam_capture_failed(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_cam_capture_failed falhou pra {chip_id}: {e}")
        # v4.1.59: 2 checks novos da Cam (requerem firmware >= v4.1.59)
        try:
            if module_type == "cam":
                self._check_cam_init_failed(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_cam_init_failed falhou pra {chip_id}: {e}")
        try:
            if module_type == "cam":
                self._check_cam_dark_frame(chip_id, merged, user_id, module)
        except Exception as e:
            log.warning(f"check_cam_dark_frame falhou pra {chip_id}: {e}")

        # Futuros: firmware_update_failed (precisa firmware reportar
        # ota_rollback_count — adia ate proxima rev de firmware)

    def _check_reservoir(self, chip_id, ctrl_data, user_id, module=None):
        """Timer baseado na BOIA DE NIVEL BAIXO (level_low).
        level_low = true  → boia detectou agua (nivel OK, acima da boia)
        level_low = false → boia NAO detectou agua (nivel BAIXO, precisa encher)

        Timer inicia quando level_low = FALSE (sem agua na boia baixa).
        Timer para quando level_low = TRUE (agua voltou).
        Se level_low fica false por 10+ min → envia alerta."""
        level_low = ctrl_data.get("level_low", True)  # default true = OK
        timer_key = f"{chip_id}:level_low"

        if level_low:
            # Boia baixa detectou agua — nivel OK, limpa timer
            if timer_key in _alert_timers:
                _alert_timers.pop(timer_key, None)
                import models as _m
                _m.update_ctrl_data(chip_id, {"low_since": None})
            return

        # Boia baixa SEM AGUA (level_low = false) — inicia ou verifica timer
        now = time.time()
        if timer_key not in _alert_timers:
            # Verifica se ja tinha low_since no banco (timer sobrevive restart do container)
            existing_since = ctrl_data.get("low_since")
            if existing_since:
                try:
                    from datetime import datetime, timezone
                    since_dt = datetime.fromisoformat(existing_since)
                    _alert_timers[timer_key] = since_dt.timestamp()
                    log.info(f"Reservatorio {chip_id}: timer restaurado do banco (low_since={existing_since})")
                except (ValueError, TypeError):
                    _alert_timers[timer_key] = now
            else:
                _alert_timers[timer_key] = now
                # Salva timestamp UTC no banco pra o PWA mostrar o contador
                from datetime import datetime, timezone
                import models as _m
                _m.update_ctrl_data(chip_id, {"low_since": datetime.now(timezone.utc).isoformat()})
                log.info(f"Reservatorio {chip_id}: boia baixa sem agua — timer iniciado")
                return  # Comecou agora — espera

        elapsed = now - _alert_timers[timer_key]
        threshold_min = ctrl_data.get("alert_threshold_min", 10)
        threshold_sec = threshold_min * 60
        if elapsed < threshold_sec:
            return  # Menos que o threshold configurado — espera

        # Threshold atingido — verifica cooldown
        import models
        if not models.should_send_alert(user_id, chip_id, "level_low"):
            return  # Ja notificou na ultima hora

        # Monta payload e envia
        module_name = (module.get("name") if module else None) or "Modulo"
        payload = {
            "title": "Nivel baixo no reservatorio",
            "body": f"{module_name}: boia de nivel minimo ativa ha {int(elapsed/60)} min. Verificar abastecimento de agua.",
            "tag": f"reservoir-{chip_id}",
            "url": "/"
        }

        self._send_alert(user_id, chip_id, "level_low", payload)

    # =========================================================
    # v4.1.40 — Checks novos (sensor + memoria + WiFi instavel)
    # =========================================================

    # Threshold 10kB pra free_heap baixo. ESP32-WROOM tem 320kB — 10kB
    # eh sintoma claro de fragmentacao/vazamento, ainda da pra reagir.
    LOW_HEAP_THRESHOLD_BYTES = 10 * 1024

    # Sensor invalido: alerta apos N leituras consecutivas invalidas.
    SENSOR_INVALID_STREAK_THRESHOLD = 3

    # WiFi instavel: alerta se contador subiu N+ desde snapshot baseline
    # de ate 1h atras. Threshold conservador (10) pra evitar fadiga em
    # redes ruins por natureza (parceiro com WiFi 4G/grama).
    WIFI_DISCONNECT_BURST_THRESHOLD = 10
    WIFI_DISCONNECT_BURST_WINDOW_SEC = 3600

    def _check_low_heap(self, chip_id, ctrl_data, user_id, module):
        """min_free_heap < 10kB sugere vazamento. P2, cooldown 24h."""
        min_heap = ctrl_data.get("min_free_heap")
        if min_heap is None:
            return  # firmware antigo (<v4.1.26) nao reporta
        try:
            min_heap = int(min_heap)
        except (TypeError, ValueError):
            return
        if min_heap >= self.LOW_HEAP_THRESHOLD_BYTES:
            return

        import models
        if not models.should_send_alert(user_id, chip_id, "low_heap_warning",
                                        cooldown_seconds=24 * 3600):
            return

        name = (module.get("name") if module else None) or "Modulo"
        payload = {
            "title": "[P2] Memoria baixa no modulo",
            "body": (f"{name}: heap minimo observado caiu pra {min_heap} bytes "
                     f"(<10kB). Pode indicar vazamento de memoria. Avalie "
                     f"reiniciar o ESP32."),
            "tag": f"low-heap-{chip_id}",
            "url": "/"
        }
        self._send_alert(user_id, chip_id, "low_heap_warning", payload)

    def _check_sensor_invalid(self, chip_id, ctrl_data, user_id, module):
        """
        DHT11 reporta `dht_valid` (true/false) — usado por Hidro-Farm.
        Conta streak consecutivo. Apos 3 leituras invalidas, alerta P2.
        Reseta o streak quando volta.
        """
        dht_valid = ctrl_data.get("dht_valid")
        if dht_valid is None:
            return  # produto sem DHT11 (Hidro/Cam) — pula

        import models as _m
        current_streak = int(ctrl_data.get("sensor_invalid_streak") or 0)

        if dht_valid:
            # Voltou — reseta streak silenciosamente
            if current_streak > 0:
                _m.update_ctrl_data(chip_id, {"sensor_invalid_streak": 0})
            return

        new_streak = current_streak + 1
        _m.update_ctrl_data(chip_id, {"sensor_invalid_streak": new_streak})
        if new_streak < self.SENSOR_INVALID_STREAK_THRESHOLD:
            return  # ainda sem alerta — espera mais leituras invalidas

        if not _m.should_send_alert(user_id, chip_id, "sensor_invalid",
                                     cooldown_seconds=12 * 3600):
            return

        name = (module.get("name") if module else None) or "Modulo"
        payload = {
            "title": "[P2] Sensor com leitura invalida",
            "body": (f"{name}: sensor de temperatura/umidade (DHT11) reporta "
                     f"leitura invalida ha {new_streak} medicoes. Verifique "
                     f"conexao do sensor."),
            "tag": f"sensor-{chip_id}",
            "url": "/"
        }
        self._send_alert(user_id, chip_id, "sensor_invalid", payload)

    def _check_wifi_disconnect_burst(self, chip_id, ctrl_data, user_id, module):
        """
        Compara `wifi_disconnect_count` atual com snapshot baseline.
        Se subiu >=10 em 1h, alerta P2 (WiFi instavel — sintoma de roteador
        ruim, sinal fraco, interferencia).

        Snapshot baseline e atualizado quando:
          - Nao existe ainda
          - Janela atual ja passou (ressetar pra proximo periodo de 1h)
        """
        cur_count = ctrl_data.get("wifi_disconnect_count")
        if cur_count is None:
            return  # firmware antigo (<v4.1.8)
        try:
            cur_count = int(cur_count)
        except (TypeError, ValueError):
            return

        import models as _m
        from datetime import datetime, timedelta

        baseline = ctrl_data.get("wifi_disconnect_baseline")
        baseline_at = ctrl_data.get("wifi_disconnect_baseline_at")
        now_ts = time.time()

        # Inicializa baseline se ausente ou janela expirada (>=1h)
        baseline_age_sec = None
        if baseline_at:
            try:
                baseline_age_sec = (datetime.now() - datetime.fromisoformat(baseline_at)).total_seconds()
            except (ValueError, TypeError):
                baseline_age_sec = None

        if baseline is None or baseline_age_sec is None or \
           baseline_age_sec >= self.WIFI_DISCONNECT_BURST_WINDOW_SEC:
            # Inicia/reseta janela
            _m.update_ctrl_data(chip_id, {
                "wifi_disconnect_baseline": cur_count,
                "wifi_disconnect_baseline_at": datetime.now().isoformat(),
            })
            return

        # Diferenca dentro da janela
        try:
            baseline = int(baseline)
        except (TypeError, ValueError):
            return
        diff = cur_count - baseline
        if diff < self.WIFI_DISCONNECT_BURST_THRESHOLD:
            return

        if not _m.should_send_alert(user_id, chip_id, "wifi_disconnect_burst",
                                     cooldown_seconds=6 * 3600):
            return

        name = (module.get("name") if module else None) or "Modulo"
        win_min = int(self.WIFI_DISCONNECT_BURST_WINDOW_SEC / 60)
        payload = {
            "title": "[P2] WiFi instavel",
            "body": (f"{name}: {diff} quedas de WiFi em {win_min}min "
                     f"(threshold {self.WIFI_DISCONNECT_BURST_THRESHOLD}). "
                     f"Verifique sinal/roteador."),
            "tag": f"wifi-burst-{chip_id}",
            "url": "/"
        }
        self._send_alert(user_id, chip_id, "wifi_disconnect_burst", payload)
        # Reseta baseline pra evitar alertar de novo no mesmo burst
        _m.update_ctrl_data(chip_id, {
            "wifi_disconnect_baseline": cur_count,
            "wifi_disconnect_baseline_at": datetime.now().isoformat(),
        })

    # =========================================================
    # v4.1.58 — Alertas especificos Hidro-Farm (DHT + reservatorio)
    # =========================================================
    # Todos server-only, zero impacto no firmware. Campos `temperature`,
    # `humidity`, `dht_valid`, `valve_entrada`, `level_high` ja sao
    # reportados pelo mod_hidrofarm.h via register a cada poll.

    DHT_TEMP_HIGH_C = 35              # >= 35°C por 30min = alerta
    DHT_TEMP_LOW_C = 10               # <= 10°C por 30min = alerta
    DHT_TEMP_DURATION_SEC = 30 * 60
    DHT_HUMIDITY_LOW = 20             # < 20% UR
    DHT_HUMIDITY_HIGH = 95            # > 95% UR
    DHT_HUMIDITY_DURATION_SEC = 60 * 60   # 1h

    # Reservoir fill stuck: valvula aberta ha 30min+ sem boia alta ativar.
    # Causas: agua na entrada esgotou, valvula entupida, boia alta defeituosa.
    VALVE_FILL_TIMEOUT_SEC = 30 * 60

    def _check_dht_temperature(self, chip_id, ctrl_data, user_id, module):
        """Temperatura DHT11 fora da faixa segura (10-35°C) por 30min+.
        Pattern de timer igual _check_reservoir: persiste timestamp em
        ctrl_data pra sobreviver a restart do container."""
        if not ctrl_data.get("dht_valid"):
            return  # leitura invalida — _check_sensor_invalid cuida disso
        temp = ctrl_data.get("temperature")
        if temp is None:
            return
        try:
            temp = int(temp)
        except (TypeError, ValueError):
            return

        # HIGH: >= 35°C
        self._dht_threshold_check(
            chip_id, ctrl_data, user_id, module,
            value=temp,
            condition=(temp >= self.DHT_TEMP_HIGH_C),
            timer_field="dht_temp_high_since",
            duration_sec=self.DHT_TEMP_DURATION_SEC,
            alert_type="dht_temperature_high",
            title="[P2] Temperatura alta no ambiente",
            body_template=(
                "{name}: temperatura ambiente em {value}°C ha {min}min "
                "(limite >= {thr}°C). Verifique ventilacao."
            ),
            threshold=self.DHT_TEMP_HIGH_C,
            cooldown_sec=6 * 3600,
        )
        # LOW: <= 10°C
        self._dht_threshold_check(
            chip_id, ctrl_data, user_id, module,
            value=temp,
            condition=(temp <= self.DHT_TEMP_LOW_C),
            timer_field="dht_temp_low_since",
            duration_sec=self.DHT_TEMP_DURATION_SEC,
            alert_type="dht_temperature_low",
            title="[P2] Temperatura baixa no ambiente",
            body_template=(
                "{name}: temperatura ambiente em {value}°C ha {min}min "
                "(limite <= {thr}°C). Pode prejudicar germinacao."
            ),
            threshold=self.DHT_TEMP_LOW_C,
            cooldown_sec=6 * 3600,
        )

    def _check_dht_humidity(self, chip_id, ctrl_data, user_id, module):
        """Umidade DHT11 fora da faixa 20-95% por 1h+. Severidade P3 (info)."""
        if not ctrl_data.get("dht_valid"):
            return
        hum = ctrl_data.get("humidity")
        if hum is None:
            return
        try:
            hum = int(hum)
        except (TypeError, ValueError):
            return

        # Fora da faixa: < 20% OU > 95%
        out_of_range = (hum < self.DHT_HUMIDITY_LOW or hum > self.DHT_HUMIDITY_HIGH)
        side = "alta" if hum > self.DHT_HUMIDITY_HIGH else "baixa"
        self._dht_threshold_check(
            chip_id, ctrl_data, user_id, module,
            value=hum,
            condition=out_of_range,
            timer_field="dht_humidity_since",
            duration_sec=self.DHT_HUMIDITY_DURATION_SEC,
            alert_type="dht_humidity_extreme",
            title="[P3] Umidade fora da faixa segura",
            body_template=(
                "{name}: umidade " + side + " em {value}% ha {min}min "
                "(faixa segura: " + str(self.DHT_HUMIDITY_LOW) + "-"
                + str(self.DHT_HUMIDITY_HIGH) + "%)."
            ),
            threshold=hum,  # nao usado no template, evita KeyError
            cooldown_sec=12 * 3600,
        )

    def _dht_threshold_check(self, chip_id, ctrl_data, user_id, module,
                             value, condition, timer_field, duration_sec,
                             alert_type, title, body_template, threshold,
                             cooldown_sec):
        """Helper generico de timer pra alertas baseados em sensor fora de
        faixa. Mesma logica do _check_reservoir — persiste timestamp pra
        sobreviver a restart, dispara apos N segundos de condicao continua,
        limpa quando volta ao normal."""
        import models as _m
        timer_key = f"{chip_id}:{alert_type}"

        if not condition:
            # Voltou ao normal — limpa timer (memoria + banco)
            if timer_key in _alert_timers:
                _alert_timers.pop(timer_key, None)
                _m.update_ctrl_data(chip_id, {timer_field: None})
            return

        now = time.time()
        if timer_key not in _alert_timers:
            existing_since = ctrl_data.get(timer_field)
            if existing_since:
                try:
                    from datetime import datetime
                    since_dt = datetime.fromisoformat(existing_since)
                    _alert_timers[timer_key] = since_dt.timestamp()
                except (ValueError, TypeError):
                    _alert_timers[timer_key] = now
            else:
                _alert_timers[timer_key] = now
                from datetime import datetime, timezone
                _m.update_ctrl_data(chip_id, {
                    timer_field: datetime.now(timezone.utc).isoformat()
                })
                return  # acabou de iniciar — espera

        elapsed = now - _alert_timers[timer_key]
        if elapsed < duration_sec:
            return  # ainda dentro do tempo de tolerancia

        if not _m.should_send_alert(user_id, chip_id, alert_type,
                                     cooldown_seconds=cooldown_sec):
            return

        name = (module.get("name") if module else None) or "Modulo"
        body = body_template.format(
            name=name, value=value,
            min=int(elapsed / 60), thr=threshold
        )
        payload = {
            "title": title,
            "body": body,
            "tag": f"{alert_type}-{chip_id}",
            "url": "/"
        }
        self._send_alert(user_id, chip_id, alert_type, payload)

    def _check_reservoir_fill_stuck(self, chip_id, ctrl_data, user_id, module):
        """Valvula de entrada aberta ha 30min+ sem a boia alta ativar.
        Sintoma de: (a) agua na entrada esgotou, (b) valvula entupida,
        (c) boia alta defeituosa, (d) vazamento maior que a vazao.
        P1 — acao no dia. So checa quando valveAuto=true (modo manual
        e responsabilidade do usuario)."""
        valve_auto = ctrl_data.get("valve_auto", True)
        if not valve_auto:
            return  # modo manual — usuario sabe o que ta fazendo

        valve = ctrl_data.get("valve_entrada")
        if not valve:
            # Valvula fechada — limpa timer
            timer_key = f"{chip_id}:fill_stuck"
            if timer_key in _alert_timers:
                _alert_timers.pop(timer_key, None)
                import models as _m
                _m.update_ctrl_data(chip_id, {"valve_open_since": None})
            return

        # Valvula aberta — checar boia alta
        high = ctrl_data.get("level_high")
        if high:
            # Boia alta ativou — encheu, OK, valvula deve fechar logo
            timer_key = f"{chip_id}:fill_stuck"
            if timer_key in _alert_timers:
                _alert_timers.pop(timer_key, None)
                import models as _m
                _m.update_ctrl_data(chip_id, {"valve_open_since": None})
            return

        # Valvula aberta + boia alta NAO ativou — timer
        import models as _m
        timer_key = f"{chip_id}:fill_stuck"
        now = time.time()
        if timer_key not in _alert_timers:
            existing_since = ctrl_data.get("valve_open_since")
            if existing_since:
                try:
                    from datetime import datetime
                    since_dt = datetime.fromisoformat(existing_since)
                    _alert_timers[timer_key] = since_dt.timestamp()
                except (ValueError, TypeError):
                    _alert_timers[timer_key] = now
            else:
                _alert_timers[timer_key] = now
                from datetime import datetime, timezone
                _m.update_ctrl_data(chip_id, {
                    "valve_open_since": datetime.now(timezone.utc).isoformat()
                })
                return

        elapsed = now - _alert_timers[timer_key]
        if elapsed < self.VALVE_FILL_TIMEOUT_SEC:
            return

        if not _m.should_send_alert(user_id, chip_id, "reservoir_fill_stuck",
                                     cooldown_seconds=4 * 3600):
            return

        name = (module.get("name") if module else None) or "Modulo"
        payload = {
            "title": "[P1] Reservatorio nao enche",
            "body": (f"{name}: valvula aberta ha {int(elapsed/60)}min mas "
                     f"a boia alta nao ativou. Verifique: agua na entrada, "
                     f"valvula entupida, ou boia defeituosa."),
            "tag": f"fill-stuck-{chip_id}",
            "url": "/"
        }
        self._send_alert(user_id, chip_id, "reservoir_fill_stuck", payload)

    # =========================================================
    # v4.1.58 — Alerta Cam: capture_failed (server-only)
    # =========================================================

    # Margem de tolerancia: alerta se passou 2x o capture_interval sem
    # upload, com floor de 30min (intervalos curtos como 5min nao alertariam
    # em 10min — pouco tempo, pode ser glitch transiente).
    CAM_CAPTURE_FAIL_FLOOR_SEC = 30 * 60

    def _check_cam_capture_failed(self, chip_id, ctrl_data, user_id, module):
        """Cam configurada pra gravar mas nao envia foto ha mais de
        max(2*capture_interval, 30min). Sintoma de: erro na camera, falha
        de upload, storage cheio no servidor, ou ESP32 trastornado."""
        if not ctrl_data.get("recording"):
            return  # Cam nao esta capturando — nada a alertar

        try:
            interval = int(ctrl_data.get("capture_interval", 600))
        except (TypeError, ValueError):
            interval = 600

        last_at = ctrl_data.get("last_capture_at")
        if not last_at:
            # Nunca capturou — pode ser 1a vez (acabou de ligar recording).
            # Espera 1 ciclo antes de alertar — proximo poll vai ter
            # last_capture_at se a Cam funcionar.
            return

        from datetime import datetime
        try:
            last_dt = datetime.fromisoformat(last_at)
        except (ValueError, TypeError):
            return

        elapsed = (datetime.now() - last_dt).total_seconds()
        threshold = max(2 * interval, self.CAM_CAPTURE_FAIL_FLOOR_SEC)
        if elapsed < threshold:
            return

        import models
        if not models.should_send_alert(user_id, chip_id, "cam_capture_failed",
                                         cooldown_seconds=12 * 3600):
            return

        name = (module.get("name") if module else None) or "Camera"
        payload = {
            "title": "[P2] Falha de captura na camera",
            "body": (f"{name}: ultima captura ha {int(elapsed/60)}min "
                     f"(intervalo configurado: {int(interval/60)}min). "
                     f"Verifique modulo da camera ou storage do servidor."),
            "tag": f"cam-fail-{chip_id}",
            "url": "/"
        }
        self._send_alert(user_id, chip_id, "cam_capture_failed", payload)

    # =========================================================
    # v4.1.59 — Cam: init_failed + dark_frame (requer firmware >= v4.1.59)
    # =========================================================

    # Threshold pra cam_dark_frame: precisa N capturas pra estabelecer baseline
    # E ultimas K consecutivas precisam estar abaixo de FRACTION % da mediana.
    DARK_FRAME_BASELINE_MIN = 10        # mediana de quantas amostras
    DARK_FRAME_TRAILING_LOW = 5         # ultimas N consecutivas baixas
    DARK_FRAME_THRESHOLD_FRACTION = 0.30  # < 30% da mediana = anormal
    DARK_FRAME_BASELINE_FLOOR = 5000    # bytes — abaixo disso ja e suspeito (cap mediana)

    def _check_cam_init_failed(self, chip_id, ctrl_data, user_id, module):
        """v4.1.59: firmware da Cam reporta cam_init_error_code = esp_err_t.
        0 = OK; != 0 = erro de hardware/sensor (cabo solto, OV2640 com defeito,
        PSRAM corrompida). Sintoma: dashboard offline mostra 'Camera nao
        inicializada'. Cooldown 24h — bug de hardware nao se resolve sozinho."""
        code = ctrl_data.get("cam_init_error_code")
        if code is None:
            return  # firmware antigo (<v4.1.59) nao reporta
        try:
            code = int(code)
        except (TypeError, ValueError):
            return
        if code == 0:
            return  # OK

        import models
        if not models.should_send_alert(user_id, chip_id, "cam_init_failed",
                                         cooldown_seconds=24 * 3600):
            return

        name = (module.get("name") if module else None) or "Camera"
        payload = {
            "title": "[P1] Camera nao inicializou",
            "body": (f"{name}: esp_camera_init falhou com codigo 0x{code:x}. "
                     f"Provavel: cabo solto, sensor OV2640 com defeito, ou "
                     f"PSRAM corrompida. Reset fisico do ESP32 pode ajudar; "
                     f"se persistir, trocar modulo."),
            "tag": f"cam-init-{chip_id}",
            "url": "/"
        }
        self._send_alert(user_id, chip_id, "cam_init_failed", payload)

    def _check_cam_dark_frame(self, chip_id, ctrl_data, user_id, module):
        """v4.1.59: deteccao de anomalia visual via tamanho do JPEG (proxy de
        complexidade). Lente tampada ou escuridao total -> JPEG MUITO menor
        que o baseline (poucos detalhes pra comprimir). Frames muito grandes
        tambem podem ser suspeitos (ruido extremo) mas fica pra outra release.

        Baseline: mediana das ultimas DARK_FRAME_BASELINE_MIN+ capturas
        (ou DARK_FRAME_BASELINE_FLOOR se historico e curto). Alerta se
        ultimas DARK_FRAME_TRAILING_LOW estao todas abaixo de
        DARK_FRAME_THRESHOLD_FRACTION x baseline.

        recent_capture_sizes vem de upload_capture (instrumentado em v4.1.59),
        rolling window de 10 sizes em ctrl_data."""
        sizes = ctrl_data.get("recent_capture_sizes")
        if not isinstance(sizes, list) or len(sizes) < self.DARK_FRAME_BASELINE_MIN:
            return  # historico insuficiente — espera juntar amostras

        # Baseline: mediana das primeiras (mais antigas) — assumindo que cenario
        # "normal" estabilizou la atras. Sortear pra mediana real:
        sorted_sizes = sorted(sizes)
        n = len(sorted_sizes)
        median = sorted_sizes[n // 2]
        baseline = max(median, self.DARK_FRAME_BASELINE_FLOOR)

        # Ultimas K sao as ULTIMAS posicoes da lista (mais recentes)
        trailing = sizes[-self.DARK_FRAME_TRAILING_LOW:]
        if len(trailing) < self.DARK_FRAME_TRAILING_LOW:
            return
        threshold = baseline * self.DARK_FRAME_THRESHOLD_FRACTION
        if not all(s < threshold for s in trailing):
            return  # nem todas as ultimas estao baixas — pode ser glitch isolado

        import models
        if not models.should_send_alert(user_id, chip_id, "cam_dark_frame",
                                         cooldown_seconds=24 * 3600):
            return

        avg_trailing = sum(trailing) / len(trailing)
        name = (module.get("name") if module else None) or "Camera"
        payload = {
            "title": "[P3] Capturas com frame anormal",
            "body": (f"{name}: ultimas {self.DARK_FRAME_TRAILING_LOW} fotos "
                     f"tem media de {avg_trailing/1024:.1f} KB (baseline "
                     f"~{baseline/1024:.1f} KB). Pode indicar: lente tampada, "
                     f"escuridao total, ou falha do sensor."),
            "tag": f"cam-dark-{chip_id}",
            "url": "/"
        }
        self._send_alert(user_id, chip_id, "cam_dark_frame", payload)

    def _send_alert(self, user_id, chip_id, alert_type, payload, severity=None):
        """
        Envia notificacao respeitando prefs do user:
        - Silent hours: bloqueia tudo (exceto P0) — GLOBAL por user
        - Pref por canal (push/email): per-modulo desde v4.1.52
        - Cooldown: ja checado pelo caller via should_send_alert antes de chamar
        - Sempre loga em alert_log mesmo quando canal e bloqueado (timeline)

        v4.1.52: prefs migraram de (user, type) pra (user, chip, type).
        v4.1.40: severity opcional. Se None, usa default do catalogo do modulo.
        """
        import models

        # Resolve severity. Tenta usar module_type pra contextualizar (precedencia
        # PRODUCT_ALERTS > UNIVERSAL_ALERTS — relevante caso um produto futuro
        # sobrescreva severidade default de um alerta universal).
        mod = models.get_module_by_chip_id(chip_id)
        module_type = mod["type"] if mod else None
        meta = get_alert_meta(alert_type, module_type=module_type)
        sev = severity or meta.get("severity_default", "P1")

        # Silent hours continua GLOBAL (propriedade do user, nao do modulo)
        silent = _is_in_silent_hours(user_id, sev)

        # 1. Push PWA — respeita pref per-modulo + silent hours
        push_sent = 0
        if not silent and _user_wants_channel(user_id, chip_id, alert_type, "push"):
            subscriptions = models.get_push_subscriptions(user_id)
            for sub in subscriptions:
                try:
                    _send_web_push(sub, payload)
                    push_sent += 1
                except Exception as e:
                    log.warning(f"Push falhou ({sub['endpoint'][:50]}...): {e}")
                    # Subscription expirada ou invalida — remove
                    models.delete_push_subscription_by_endpoint(sub["endpoint"])

        # 2. Email (usa notification_email se existir, senao email de login)
        email_sent = False
        if not silent and _user_wants_channel(user_id, chip_id, alert_type, "email"):
            user = models.get_user_by_id(user_id)
            to_email = None
            if user:
                try:
                    to_email = user["notification_email"] or user["email"]
                except (IndexError, KeyError):
                    to_email = user["email"]
            if to_email:
                try:
                    # v4.1.60: passa contexto pro subject identificar o modulo.
                    # `mod` ja foi resolvido la em cima (get_module_by_chip_id).
                    module_name = mod.get("name") if mod else None
                    _send_email_alert(
                        to_email, payload,
                        chip_id=chip_id,
                        module_name=module_name,
                        severity=sev,
                        alert_type=alert_type,
                    )
                    email_sent = True
                except Exception as e:
                    log.warning(f"Email falhou ({to_email}): {e}")

        # Loga sempre — mesmo quando bloqueado por silent_hours/pref. User ainda
        # ve no historico que o alerta DISPAROU (so nao foi entregue por canal).
        models.log_alert(user_id, chip_id, alert_type, severity=sev)
        suffix = " [SILENCIADO]" if silent else ""
        log.info(f"ALERTA [{sev}] [{alert_type}] chip={chip_id}: "
                 f"push={push_sent} email={email_sent}{suffix}")


def _send_web_push(subscription, payload):
    """Envia push notification via Web Push (VAPID)."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("pywebpush nao instalado — push desabilitado")
        return

    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY", "")
    vapid_claim_email = os.environ.get("VAPID_CLAIM_EMAIL", "")
    if not vapid_private_key:
        log.warning("VAPID_PRIVATE_KEY nao configurada — push desabilitado")
        return

    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {
                    "p256dh": subscription["p256dh"],
                    "auth": subscription["auth"]
                }
            },
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims={"sub": vapid_claim_email},
            timeout=10
        )
    except WebPushException as e:
        # 410 Gone = subscription expirada
        if "410" in str(e) or "404" in str(e):
            raise  # Propaga pra AlertManager remover a subscription
        log.error(f"WebPush error: {e}")


def send_email(to_email, subject, body):
    """
    Envia email generico via SMTP (reutilizado por alertas, auth, onboarding, etc.)

    Retorna True se enviou, False se SMTP nao esta configurado.
    Lanca excecao em caso de erro SMTP — chamador decide se ignora ou re-lanca.
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        log.warning("SMTP nao configurado — email ignorado")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "contato@cultivee.com.br")
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain="cultivee.com.br")
    msg["Date"] = formatdate(localtime=True)

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    passwd = os.environ.get("SMTP_PASS", "")

    if port == 465:
        # SSL direto (HostGator, Gmail com SSL)
        with smtplib.SMTP_SSL(smtp_host, port) as s:
            s.login(user, passwd)
            s.send_message(msg)
    else:
        # STARTTLS (porta 587)
        with smtplib.SMTP(smtp_host, port) as s:
            s.starttls()
            s.login(user, passwd)
            s.send_message(msg)
    return True


def _send_email_alert(to_email, payload, chip_id=None, module_name=None,
                      severity=None, alert_type=None):
    """Envia email de alerta com subject + body contextualizados (v4.1.60).

    Antes (v4.1.0+): subject era 'Cultivee Alerta - [P2] WiFi instavel' —
    mesma string pra TODOS os modulos do user, impossivel saber QUAL deu
    o problema sem abrir o email. Nome do modulo so aparecia embutido na
    1a frase do body, sem destaque.

    Agora: subject inclui nome do modulo + tipo do alerta + severidade.
    Body comeca com bloco de metadados estruturado (Modulo/Severidade/Hora)
    pra scan rapido. Body original do payload vem logo depois.

    Parametros novos (todos opcionais, backward-compat):
      chip_id, module_name, severity, alert_type
    """
    import re
    title = payload.get("title", "Alerta")
    body_text = payload.get("body", "")

    # Nome amigavel: nome cadastrado pelo user, fallback chip_id curto
    name = module_name or (f"chip {chip_id[:6]}" if chip_id else "modulo")

    # Subject: limpa prefixo "[P#] " do title (vai pro fim como suffix)
    clean_title = re.sub(r'^\[P\d\]\s*', '', title)
    sev_suffix = f" [{severity}]" if severity else ""
    subject = f"Cultivee · {name} · {clean_title}{sev_suffix}"

    # Body: bloco de metadados + corpo + CTA + instrucoes de ajuste
    from datetime import datetime
    when = datetime.now().strftime("%d/%m/%Y %H:%M")
    full_body = f"""Modulo:     {name}
Severidade: {severity or '?'}
Hora:       {when}

{body_text}

---
Acesse o app: https://app.cultivee.com.br

Para ajustar canais (push/email) deste tipo de alerta NESTE modulo, abra
o card do modulo no app > Notificacoes > Tipos de alerta.

Para silenciar TODOS os alertas em uma faixa de horario (ex: madrugada),
use o menu do usuario > Janela de silencio. Alertas P0 (emergencia)
sempre passam mesmo na janela de silencio.
"""
    try:
        send_email(to_email, subject, full_body)
    except Exception as e:
        log.error(f"SMTP error (alerta): {e}")
        raise


# =====================================================================
# 2FA Email OTP — template (v4.1.29)
# =====================================================================

def send_email_2fa_code(user, code, context="login"):
    """
    Envia codigo OTP por email pra 2FA.
    context = 'login' (a cada tentativa de login) ou 'setup' (ativacao inicial).
    Usa notification_email se setado, senao email de login.
    """
    destination = None
    try:
        destination = user["notification_email"]
    except (KeyError, IndexError, TypeError):
        pass
    if not destination:
        destination = user["email"]
    name = user["name"] if user["name"] else "Usuario"

    if context == "setup":
        subject = "Cultivee - Confirme sua autenticacao por email"
        body = f"""Ola, {name}!

Voce solicitou ativar a autenticacao em duas etapas (2FA) por email.

Seu codigo de confirmacao:

    {code}

Digite esse codigo no app pra concluir a ativacao. O codigo e valido por
10 minutos. Se nao foi voce que solicitou, ignore este email.

--
Equipe Cultivee
contato@cultivee.com.br
"""
    else:
        subject = "Cultivee - Codigo de login"
        body = f"""Ola, {name}!

Alguem (provavelmente voce) tentou entrar na sua conta Cultivee. Use o
codigo abaixo pra concluir o login:

    {code}

O codigo e valido por 10 minutos e so pode ser usado uma vez.

Se nao foi voce, alguem pode ter sua senha. Recomendamos:
  1. Trocar a senha imediatamente
  2. Manter a 2FA ativa

--
Equipe Cultivee
contato@cultivee.com.br
"""
    send_email(destination, subject, body)


# Instancia global — usada por app.py
alert_manager = AlertManager()
