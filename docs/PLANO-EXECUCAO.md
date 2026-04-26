# Plano de Execucao Cultivee — 5 Meses (Abril → Agosto 2026)

> **Documento de referencia.** Atualizar status conforme entregas.
> Marcar `[x]` quando concluido, anotar versao + observacao.
> Itens parciais ficam `[~]` com nota explicando o que falta.

**Ultima atualizacao**: 2026-04-26
**Status global**: 7/20 itens (35%) — ver detalhe por mes abaixo

---

## Resumo executivo

| Mes | Tema | Itens | Status |
|---|---|---|---|
| **Abril** | Fundacao e Controle | 4/4 | ✅ Concluido |
| **Maio** | Rede Distribuida e Vigilancia | 2/4 | 🟡 Parcial (2 presenciais pendentes) |
| **Junho** | Rastreabilidade e Ciclo de Producao | 0/4 | ⏳ Nao iniciado |
| **Julho** | Instrumentacao Ambiental | 0/4 (1 parcial) | ⏳ Nao iniciado |
| **Agosto** | Planejamento e Inteligencia Operacional | 0/4 | ⏳ Nao iniciado |

---

## Mes 1 — Abril (Fundacao e Controle) — ✅ CONCLUIDO

- [x] **Instalacao e validacao do modulo HIDRO em campo: ciclos de luz e bomba por 72h continuas**
  - Status: ✅ Concluido. 2 chips Hidro rodando em campo desde inicio do mes (`50B525077000` em bench / `E04730A7DBCC` no parceiro). Sistema de fases ja roda os ciclos via RTC DS3231 (offline-first).
  - Versoes relevantes: firmware base (pre-v4.0.x) ja tinha; refinamentos continuaram ate v4.1.60.

- [x] **Automacao do reservatorio de solucao nutritiva: sensor de nivel (float switch) com corte automatico da bomba**
  - Status: ✅ Concluido no produto **HIDRO-FARM** (que tem 2 boias reed-switch + valvula de entrada com automacao via `valveAuto=true`). Maquina de estados em `mod_hidrofarm.h:reservoirControlFarm()`.
  - Observacao: o HIDRO base nao tem boias (so o FARM tem). O plano original previa apenas no Hidro, foi cumprido com o produto Premium.
  - Versoes relevantes: firmware base do hidro-farm; alerta `level_low` (P1) em v4.1.0; alerta `reservoir_fill_stuck` (P1) em v4.1.58.

- [x] **Configuracao do dashboard IoT com locais, modulos pareados e controle remoto de atuadores**
  - Status: ✅ Concluido desde v4.0.x. PWA `app.cultivee.com.br` com:
    - Pareamento via short_id (4 chars) — wizard
    - Lista per-user com checkbox/setas de ordem (`module_prefs`)
    - Controle remoto de reles via `/api/hidro|hidro-farm|cam/<chip>/relay`
    - Proxy direto ao IP local + fallback `pending_commands` na fila
  - Versoes relevantes: arquitetura 3-camadas v4.1.17, registry pattern frontend, blueprints por capability.

- [x] **Implementacao de alertas P0/P1 de nivel do reservatorio com push notification via PWA**
  - Status: ✅ Concluido em v4.1.0. `level_low` alert P1 com cooldown 1h, push (VAPID/pywebpush) + email (SMTP HostGator). Timer visual `low_since` no card. Threshold configuravel (1-120 min).
  - Versoes relevantes: v4.1.0 (sistema base), v4.1.7 (threshold configuravel), v4.1.40 (catalogo P0-P3 formal).

---

## Mes 2 — Maio (Rede Distribuida e Vigilancia) — 🟡 2/4 (2 presenciais pendentes)

- [ ] **Instalacao e pareamento do segundo modulo HIDRO no expositor de pequeno porte**
  - Status: 🔴 Pendente — exige **visita presencial** ao parceiro.
  - Pre-requisitos tecnicos: prontos. Firmware v4.1.60 ja em outro chip de bench (`50B525077000`), pronto pra ser regravado pro expositor quando agendar.
  - Acao: agendar visita.

- [ ] **Validacao da operacao do modulo em rede WiFi externa (ambiente do parceiro/expositor)**
  - Status: 🔴 Pendente — depende do item anterior. Validar sinal RSSI, estabilidade (`wifi_disconnect_count`), conectividade ao app, captive portal funcionando.
  - Pre-requisitos tecnicos: telemetria WiFi ja existe (v4.1.8) — `wifi_last_error`, `wifi_last_connected_ms`, `wifi_disconnect_count`. Alert `wifi_disconnect_burst` (P2) ja monitora estabilidade.

- [x] **Implementacao do sistema de alertas P0-P3 com push notification, email e cooldown anti-fadiga**
  - Status: ✅ Concluido + EVOLUIDO alem do escopo.
  - Versao base: v4.1.40 (catalogo P0-P3 formal, 6 tipos com cooldown variavel).
  - Refator: v4.1.52 (per-module — alertas viraram propriedade do modulo, nao do user).
  - Hoje: 9 alertas no catalogo total (4 universais + 6 hidro-farm + 3 cam):
    - Universais: `module_offline`, `module_recovered`, `low_heap_warning`, `wifi_disconnect_burst`
    - Hidro-Farm: `level_low`, `sensor_invalid`, `dht_temperature_high/low`, `dht_humidity_extreme`, `reservoir_fill_stuck`
    - Cam: `cam_capture_failed`, `cam_init_failed`, `cam_dark_frame`
  - Anti-fadiga: cooldowns variaveis (1h-24h por tipo) + janela de silencio global do user (P0 sempre passa) + prefs per-modulo (push/email opt-in).
  - Email contextualizado em v4.1.60 (subject identifica modulo).

- [x] **Configuracao de deteccao automatica de offline para todos os locais cadastrados no dashboard**
  - Status: ✅ Concluido em v4.1.38. `server/jobs/offline_watcher.py` thread daemon (a cada 60s) detecta modulos com `last_seen > threshold` e dispara alerta P1 (push + email). Lock distribuido via `offline_watcher_state` singleton (1 worker do Gunicorn executa).
  - v4.1.39: threshold configuravel **per-modulo** (1-1440 min, default 15min) + toggle ON/OFF no card de notificacoes.
  - Cooldowns: P1 4h, P0 12h (>24h offline), recovery 1h.

---

## Mes 3 — Junho (Rastreabilidade e Ciclo de Producao) — ⏳ NAO INICIADO

- [ ] **Cadastro do catalogo de especies cultivadas com parametros agronomicos e duracao de ciclo por estagio**
  - Status: ⏳ Nao iniciado.
  - Escopo provavel:
    - Schema novo `species (id, nome, parametros_agronomicos JSON, ciclo_estagios JSON)`
    - Cada estagio tem duracao + thresholds de temp/hum/CE/pH ideais
    - UI: pagina `/especies` no app pra cadastrar/editar
    - Endpoint admin pra catalogo "padrao da casa" (alface, manjericao, etc.)

- [ ] **Implementacao do registro e progressao automatica de lotes na fazenda vertical (Germinacao → Bercario → Engorda → Pre-colheita)**
  - Status: ⏳ Nao iniciado.
  - Observacao: ja existe conceito de **fases** no Hidro/Hidro-Farm (`struct Phase` com luz/bomba/vent/aer + duracao em dias), mas e **por modulo**, nao por **lote** com identidade propria.
  - Escopo provavel:
    - Schema novo `lots (id, species_id, modulo_id, estagio_atual, planted_at, harvested_at)`
    - State machine de progressao automatica (data-based ou trigger manual)
    - Historico por lote pra rastreabilidade

- [ ] **Desenvolvimento do fluxo de transferencia de lotes da fazenda vertical para o expositor com rastreamento completo**
  - Status: ⏳ Nao iniciado.
  - Pre-requisito: itens 1 e 2 acima (catalogo + lotes).
  - Escopo provavel:
    - UI: tela "Mover lote" — escolher lote + destino (expositor)
    - Trigger automatico quando estagio == "pre-colheita"
    - Transacao atomica: lot.modulo_id atualizado + log de transferencia

- [ ] **Contagem regressiva de dias no expositor e alertas automaticos de reposicao (P2 a 3 dias do fim do ciclo)**
  - Status: ⏳ Nao iniciado.
  - Pre-requisito: item 3 acima.
  - Escopo provavel:
    - Novo alerta `lot_near_harvest` (P2, cooldown 24h) — dispara quando `dias_no_expositor + dias_restantes_ciclo <= 3`
    - Card visual no dashboard com countdown
    - Integra com sistema de alertas per-module (v4.1.52)

---

## Mes 4 — Julho (Instrumentacao Ambiental) — ⏳ NAO INICIADO

- [ ] **Instalacao do modulo CLIMA na fazenda vertical: sensores de temperatura, umidade relativa (DHT22) e CO2 (MH-Z19)**
  - Status: ⏳ Nao iniciado (modulo dedicado).
  - Observacao: o **HIDRO-FARM** ja tem DHT11 (temp+umidade ambiente), mas e modulo de irrigacao com sensor "tag along". O plano preve modulo CLIMA dedicado com:
    - DHT22 (mais preciso que DHT11, casa decimal)
    - MH-Z19 (CO2 NDIR — sensor novo nao existente no projeto)
  - Escopo provavel:
    - Novo produto `products/clima.h` + `firmware/mod_clima.h`
    - Capability "clima" + blueprint `server/hardware/clima.py`
    - Frontend: novo `renderModule_clima` no registry pattern

- [ ] **Instalacao do modulo SOLUCAO: sondas de pH e condutividade eletrica (CE) com calibracao inicial (solucoes pH 4.0 e 7.0)**
  - Status: ⏳ Nao iniciado.
  - Escopo provavel:
    - Novo produto `products/solucao.h` + `firmware/mod_solucao.h`
    - Sensor pH (DFRobot ou similar) + sensor CE (TDS/EC)
    - Procedimento de calibracao 2 pontos (pH 4.0 + 7.0) — UI no app pra registrar
    - Persistir offsets de calibracao no NVS do ESP32
    - Reportar `ph` + `ec` no register a cada poll

- [ ] **Implementacao de historico de leituras sensoriais com graficos de tendencia das ultimas 24h por parametro**
  - Status: 🟡 PARCIAL — infra de eventos temporais existe (`module_status_events` v4.1.31, retencao 90 dias) mas e SO uptime (online/offline), nao leituras sensoriais.
  - Falta: tabela nova tipo `sensor_readings (chip_id, timestamp, parametro, valor)` com aggregation por hora pra historico de 24h.
  - UI: componente de chart (sparkline ou line chart) — Chart.js ja foi cogitado no backlog.

- [ ] **Configuracao de alertas sensoriais automaticos (P1) por desvio de faixa configurada por especie**
  - Status: 🟡 PARCIAL — alertas DHT temp/hum existem (v4.1.58) mas com **thresholds globais hardcoded** (35°C / 10°C / 20%-95%), nao por especie.
  - Falta:
    - Thresholds vir do catalogo de especies (Mes 3 item 1)
    - Logica per-modulo cruzar lote ativo (Mes 3 item 2) com especie pra resolver thresholds
    - Severidade aumentar pra P1 quando alerta sensorial cruza com lote em estagio critico

---

## Mes 5 — Agosto (Planejamento e Inteligencia Operacional) — ⏳ NAO INICIADO

- [ ] **Implementacao do motor de planejamento de producao com calculo de pipeline ideal por especie (Lei de Little)**
  - Status: ⏳ Nao iniciado. Pre-requisito: catalogo de especies (Mes 3) + lotes (Mes 3).
  - Conceito: **Lei de Little** (`L = λ × W`) — em estado estavel, lotes em pipeline = throughput × tempo de ciclo. Permite calcular quantos lotes deveriam estar em cada estagio pra atingir meta mensal.
  - Escopo provavel: pagina `/planejamento` com calculadora + dashboard do estado atual vs ideal.

- [ ] **Agenda semanal automatica de semeadura e transferencias com base na meta mensal configurada**
  - Status: ⏳ Nao iniciado. Pre-requisito: motor de planejamento (item 1 acima).
  - Escopo provavel: cron interno gera tarefas (semear lote X, transferir lote Y) baseado em meta + ciclo das especies. Card "agenda da semana" no dashboard.

- [ ] **Relatorios de producao real vs. planejado por especie com calculo de fator de perda real**
  - Status: ⏳ Nao iniciado.
  - Escopo provavel:
    - Pagina `/relatorios` com filtros (especie, periodo)
    - Calcular fator de perda = `1 - (colhidos / plantados)` por especie
    - Comparar planejado (meta × ciclo) vs real (lotes finalizados)

- [ ] **Alertas automaticos de pipeline (P2) por estagio de cultivo abaixo de 70% do volume ideal**
  - Status: ⏳ Nao iniciado. Pre-requisito: motor de planejamento (item 1).
  - Conceito: novo alerta `pipeline_underflow` (P2) por estagio + especie. Dispara quando `volume_atual < 0.7 × volume_ideal_calculado`.
  - Escopo provavel: novo `_check_pipeline` em AlertManager (server-only). Adicionar em `PRODUCT_ALERTS` ou cria categoria nova de alertas "operacionais" (nao per-module).

---

## Como atualizar este documento

Quando entregar um item:
1. Marca `[x]` (ou `[~]` pra parcial).
2. Adiciona linha "Status: ✅ Concluido em vX.Y.Z" + observacao breve.
3. Atualiza o "Resumo executivo" no topo (contadores).
4. Atualiza "Ultima atualizacao" no topo.
5. Commit junto com a release que entregou o item.

Se o escopo MUDAR (item ganhou novo requisito ou foi descartado):
- Adicionar nota inline "**Reescopo (DD/MM)**: ..." mantendo o texto original visivel.
- NAO apaga o item original — preserva historico.

---

## Visao por capacidade tecnica (cross-mes)

Util pra estimar quanto falta de cada area:

| Capacidade | Meses afetados | Status |
|---|---|---|
| **Hardware base (HIDRO/FARM/CAM)** | Mes 1 | ✅ |
| **Alertas P0-P3** | Mes 1 (P0/P1) + Mes 2 (P0-P3 + cooldown) | ✅ + evoluido |
| **Monitoring de operacao** | Mes 2 (offline) | ✅ |
| **Catalogo de especies** | Mes 3 → Mes 4 (alertas por especie) → Mes 5 (planejamento) | 0% |
| **Lotes / rastreabilidade** | Mes 3 + Mes 4 (alertas por lote) | 0% |
| **Modulos de sensor (CLIMA, SOLUCAO)** | Mes 4 | 0% |
| **Historico sensorial + graficos** | Mes 4 | 10% (infra existe pra uptime, falta pra sensores) |
| **Planejamento / Inteligencia operacional** | Mes 5 | 0% |
| **Comercializacao (LGPD, billing, manual)** | Cross-mes (paralelo) | Parcial — ver `docs/license-gate.md`, `docs/lgpd-aipd.md`, `docs/manual-usuario.md` (drafts) |

---

## Proximos passos imediatos (ordem sugerida)

1. **Agendar visita ao parceiro** — fecha 2 itens do Mes 2 (presenciais).
2. **Iniciar Mes 3 — catalogo de especies**: schema + UI basica + 3-5 especies "padrao da casa". Habilita Mes 4 (alertas por especie) e Mes 5 (planejamento).
3. **Mes 3 — lotes**: schema + state machine. Sequencial ao item 2.
4. **Mes 4 — modulo CLIMA primeiro** (DHT22 + MH-Z19). E o "produto novo" mais simples — segue o template do hidro-farm. Habilita historico sensorial.
5. **Mes 4 — modulo SOLUCAO**: pH + CE. Mais complexo (calibracao 2 pontos).
6. **Mes 5**: motor de planejamento, agenda automatica, relatorios. Sequencia logica apos meses 3 e 4.

Em paralelo (nao bloqueia roadmap tecnico):
- Decidir modelo de monetizacao (`docs/license-gate.md`)
- DPO + AIPD + Termos (compliance)
- Manual consumidor PDF + video 3min
