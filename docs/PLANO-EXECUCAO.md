# Plano de Execucao Cultivee — 5 Meses (Abril → Agosto 2026)

> **Cronologia preservada** (Mes 1..5) com **colunas por natureza de trabalho** —
> permite ver de relance se um item e puro software, exige hardware novo, ou
> precisa de visita presencial.

**Ultima atualizacao**: 2026-04-26
**Status global**: 7/20 itens (35%)

---

## Legenda

**Categorias de trabalho** (o que precisa ser feito pra entregar):

| Tag | Significado | Caracteristica |
|---|---|---|
| **HW** | Hardware fisico | Comprar, montar, validar — leadtime de semanas |
| **FW** | Firmware ESP32 | Compilar, OTA — risco de brick, exige USB ou OTA estavel |
| **BE** | Backend Flask | Schema, endpoints, jobs — deploy automatico via push |
| **FE** | Frontend PWA | UI, dashboard, fluxos — deploy junto com backend |
| **OPS** | Operacional / presencial | Visita, instalacao fisica, configuracao no local |
| **DATA** | Dados / conteudo | Cadastro de catalogo, calibracao com solucoes reais |

**Status:**
- ✅ Concluido
- 🟡 Parcial (infra existe, falta integracao ou dados)
- 🔴 Pendente bloqueado (depende de algo externo, ex: presencial)
- ⏳ Nao iniciado (sem bloqueio aparente)

---

## Tabela mestre — todos os 20 itens (cronologica)

| # | Mes | Item | HW | FW | BE | FE | OPS | DATA | Versao / Ref | Status |
|---|---|---|:-:|:-:|:-:|:-:|:-:|:-:|---|:-:|
| **1.1** | Abril | Instalacao HIDRO em campo (ciclos 72h) | • | • | | | • | | pre-v4.0 | ✅ |
| **1.2** | Abril | Automacao reservatorio (boias + valvula auto) | • | • | • | • | | | hidro-farm | ✅ |
| **1.3** | Abril | Dashboard IoT (locais + modulos + controle) | | | • | • | | | v4.0.x → v4.1.17 | ✅ |
| **1.4** | Abril | Alertas P0/P1 nivel reservatorio + push PWA | | | • | • | | | v4.1.0 | ✅ |
| **2.1** | Maio | Instalacao 2º HIDRO no expositor parceiro | | | | | • | | — | 🔴 |
| **2.2** | Maio | Validacao operacao em WiFi externa parceiro | | | | | • | | — | 🔴 |
| **2.3** | Maio | Sistema P0-P3 push + email + cooldown | | | • | • | | | v4.1.40 → v4.1.52 | ✅ |
| **2.4** | Maio | Deteccao offline automatica (todos modulos) | | | • | | | | v4.1.38 → v4.1.39 | ✅ |
| **3.1** | Junho | Catalogo de especies (parametros agronomicos) | | | • | • | | • | — | ⏳ |
| **3.2** | Junho | Lotes + progressao (Germ→Berc→Engorda→Pre-col) | | | • | • | | | — | ⏳ |
| **3.3** | Junho | Transferencia fazenda → expositor | | | • | • | • | | — | ⏳ |
| **3.4** | Junho | Contagem regressiva + alerta P2 reposicao | | | • | • | | | — | ⏳ |
| **4.1** | Julho | **Modulo CLIMA** (DHT22 + MH-Z19 CO2) | • | • | • | • | • | | — | ⏳ |
| **4.2** | Julho | **Modulo SOLUCAO** (sondas pH + CE) | • | • | • | • | • | • | — | ⏳ |
| **4.3** | Julho | Historico sensorial + graficos 24h | | | • | • | | | — | 🟡 |
| **4.4** | Julho | Alertas sensoriais P1 por especie | | | • | | | | — | 🟡 |
| **5.1** | Agosto | Motor planejamento producao (Lei de Little) | | | • | | | | — | ⏳ |
| **5.2** | Agosto | Agenda automatica semeadura/transferencia | | | • | • | | | — | ⏳ |
| **5.3** | Agosto | Relatorios real vs planejado + fator perda | | | • | • | | | — | ⏳ |
| **5.4** | Agosto | Alertas pipeline P2 (estagio < 70% volume ideal) | | | • | | | | — | ⏳ |

---

## Estatisticas por categoria (visao complementar)

| Categoria | Total de itens que tocam | Concluidos | Pendentes |
|---|:-:|:-:|:-:|
| **HW** (hardware fisico) | 4 | 2 (1.1, 1.2) | 2 (4.1, 4.2) |
| **FW** (firmware) | 4 | 2 (1.1, 1.2) | 2 (4.1, 4.2) |
| **BE** (backend) | 18 | 6 | 12 |
| **FE** (frontend) | 14 | 5 | 9 |
| **OPS** (presencial) | 6 | 1 (1.1) | 5 (2.1, 2.2, 3.3, 4.1, 4.2) |
| **DATA** (cadastro/calibracao) | 3 | 0 | 3 (3.1, 4.2 calibracao, especies novas) |

**Insight chave**: 65% do plano (13 itens) e **PURO software** (so BE+FE) — pode rodar em paralelo enquanto hardware/presencial estao em andamento.

---

## Dependencias entre itens (cross-mes)

Algumas entregas precisam de outras prontas antes:

```
3.1 catalogo de especies ──┬──→ 4.4 alertas sensoriais por especie
                            ├──→ 5.1 motor de planejamento
                            └──→ 5.3 relatorios

3.2 lotes ─────────────────┬──→ 3.3 transferencia
                            ├──→ 3.4 contagem regressiva
                            ├──→ 5.1 motor de planejamento
                            ├──→ 5.2 agenda automatica
                            └──→ 5.3 relatorios

4.1 modulo CLIMA ──────────┬──→ 4.3 historico sensorial (precisa dos dados)
                            └──→ 4.4 alertas sensoriais (precisa dos sensores)

4.2 modulo SOLUCAO ────────┬──→ 4.3 historico sensorial
                            └──→ 4.4 alertas sensoriais

5.1 motor planejamento ────┬──→ 5.2 agenda automatica
                            └──→ 5.4 alertas pipeline
```

**Caminho critico**: `3.1 + 3.2 → 5.1 → 5.2/5.4`. Sem catalogo + lotes (Junho), nada do Mes 5 anda.

---

## Filtros uteis pra planejamento

### Itens que podem rodar EM PARALELO ao hardware sendo comprado/instalado

(Software puro, sem dependencia de HW novo na mesma rodada)

- **3.1, 3.2, 3.4** (Junho) — catalogo + lotes + contagem regressiva
- **5.1, 5.2, 5.3, 5.4** (Agosto) — depois de Junho pronto

Total: **7 itens** que voce pode comecar enquanto hardware do Mes 4 esta em compra/montagem.

### Itens bloqueados por presencial

- **2.1, 2.2** — exigem visita ao parceiro (instalacao 2º HIDRO + validacao WiFi)
- **3.3** — gestao de transferencia (acompanhamento, nao instalacao)
- **4.1, 4.2** — instalacao fisica dos modulos novos (depois HW pronto)

Total: **5 itens** bloqueados por algum presencial.

### Itens que dependem de hardware NOVO (CLIMA + SOLUCAO)

- **4.1, 4.2** — os proprios modulos
- **4.3, 4.4** — consomem dados deles

Total: **4 itens** atrelados ao Mes 4. Comprar componentes assim que decidir prosseguir.

---

## Detalhe expandido por mes

### Mes 1 — Abril (Fundacao e Controle) — ✅ CONCLUIDO

**1.1 Instalacao HIDRO em campo (ciclos 72h)** — `[HW][FW][OPS]` ✅
- 2 chips Hidro rodando: `50B525077000` (bench) + `E04730A7DBCC` (parceiro)
- Sistema de fases roda offline-first via RTC DS3231
- Refinamentos continuaram ate v4.1.60

**1.2 Automacao reservatorio (boias + valvula auto)** — `[HW][FW][BE][FE]` ✅
- Implementado no produto **HIDRO-FARM** (boias reed-switch + maquina de estados em `mod_hidrofarm.h:reservoirControlFarm()`)
- Alerta `level_low` (P1) v4.1.0; alerta `reservoir_fill_stuck` (P1) v4.1.58

**1.3 Dashboard IoT (locais + modulos + controle remoto)** — `[BE][FE]` ✅
- PWA `app.cultivee.com.br` desde v4.0.x
- Pareamento via short_id, lista per-user, controle remoto via blueprints por capability
- Arquitetura 3-camadas v4.1.17, registry pattern frontend

**1.4 Alertas P0/P1 nivel + push PWA** — `[BE][FE]` ✅
- v4.1.0 (sistema base) + v4.1.7 (threshold configuravel) + v4.1.40 (catalogo P0-P3)

---

### Mes 2 — Maio (Rede Distribuida e Vigilancia) — 🟡 2/4

**2.1 Instalacao 2º HIDRO no expositor parceiro** — `[OPS]` 🔴
- Pre-requisitos tecnicos: prontos. Firmware v4.1.60 ja em outro chip de bench, pronto pra ser regravado.
- **Acao pendente**: agendar visita ao parceiro.

**2.2 Validacao operacao em WiFi externa parceiro** — `[OPS]` 🔴
- Depende de 2.1.
- Telemetria WiFi ja existe (v4.1.8): `wifi_last_error`, `wifi_last_connected_ms`, `wifi_disconnect_count`. Alert `wifi_disconnect_burst` (P2) ja monitora.

**2.3 Sistema P0-P3 push + email + cooldown anti-fadiga** — `[BE][FE]` ✅ + EVOLUIDO
- v4.1.40 (catalogo formal) → v4.1.52 (refator per-module).
- Hoje: 9 alertas no catalogo (4 universais + 6 hidro-farm + 3 cam).
- Cooldowns variaveis (1h-24h por tipo) + janela de silencio global do user (P0 sempre passa) + prefs per-modulo.

**2.4 Deteccao offline automatica** — `[BE]` ✅
- v4.1.38 (`server/jobs/offline_watcher.py` thread daemon) + v4.1.39 (threshold per-modulo configuravel, default 15min).
- Cooldowns: P1 4h, P0 12h (>24h offline), recovery 1h.

---

### Mes 3 — Junho (Rastreabilidade e Ciclo de Producao) — ⏳ 0/4

**3.1 Catalogo de especies** — `[BE][FE][DATA]`
- Schema novo `species (id, nome, parametros_agronomicos JSON, ciclo_estagios JSON)`
- Cada estagio: duracao + thresholds ideais (temp/hum/CE/pH)
- UI: pagina `/especies` no app pra cadastrar/editar
- Dados: 3-5 especies "padrao da casa" (alface, manjericao, etc.)
- **Habilita**: 4.4, 5.1, 5.3

**3.2 Lotes com progressao automatica** — `[BE][FE]`
- Schema novo `lots (id, species_id, modulo_id, estagio_atual, planted_at, harvested_at)`
- State machine: Germinacao → Bercario → Engorda → Pre-colheita
- Progressao data-based ou trigger manual
- Historico por lote pra rastreabilidade
- **Habilita**: 3.3, 3.4, 5.1, 5.2, 5.3
- **Observacao**: o Hidro/Hidro-Farm ja tem `struct Phase` por modulo, mas e diferente — phases controlam atuadores, lots controlam ciclo do PRODUTO

**3.3 Transferencia fazenda → expositor** — `[BE][FE][OPS]`
- UI: tela "Mover lote" — escolher lote + destino (expositor)
- Trigger automatico quando estagio == "pre-colheita" (config opcional)
- Transacao atomica: `lot.modulo_id` atualizado + log de transferencia
- Pre-requisito: 3.1 + 3.2

**3.4 Contagem regressiva + alerta P2 reposicao** — `[BE][FE]`
- Novo alerta `lot_near_harvest` (P2, cooldown 24h) — dispara quando `dias_no_expositor + dias_restantes_ciclo <= 3`
- Card visual no dashboard com countdown
- Integra com sistema de alertas per-module (v4.1.52) — adicionar em `PRODUCT_ALERTS["hidro-farm"]` e/ou criar categoria "operacional"

---

### Mes 4 — Julho (Instrumentacao Ambiental) — ⏳ 0/4 (2 parciais)

**4.1 Modulo CLIMA (DHT22 + MH-Z19 CO2)** — `[HW][FW][BE][FE][OPS]`
- HW: comprar DHT22 (mais preciso que DHT11, casa decimal) + MH-Z19 NDIR + ESP32-WROOM
- FW: novo `firmware/mod_clima.h` + `products/clima.h` (segue template do hidro-farm)
- BE: novo blueprint `server/hardware/clima.py` + capability `"clima"`
- FE: novo `renderModule_clima` no `moduleRenderers` (registry pattern)
- OPS: instalar fisicamente na fazenda vertical
- **Habilita**: 4.3, 4.4

**4.2 Modulo SOLUCAO (sondas pH + CE)** — `[HW][FW][BE][FE][OPS][DATA]`
- HW: sonda pH (DFRobot ou similar) + sensor CE/TDS + ESP32
- FW: novo `firmware/mod_solucao.h` + `products/solucao.h`
- BE: blueprint `server/hardware/solucao.py` + capability `"solucao"`
- FE: `renderModule_solucao` + UI de calibracao 2 pontos
- OPS: instalacao fisica
- DATA: **calibracao inicial** com solucoes pH 4.0 + 7.0 (procedimento documentado)
- Persistir offsets de calibracao no NVS do ESP32
- **Habilita**: 4.3, 4.4

**4.3 Historico sensorial + graficos 24h** — `[BE][FE]` 🟡 PARCIAL
- Infra de eventos temporais existe (`module_status_events` v4.1.31, retencao 90 dias) mas e SO uptime — nao leituras sensoriais.
- Falta: tabela `sensor_readings (chip_id, timestamp, parametro, valor)` com aggregation por hora
- UI: chart component (Chart.js cogitado no backlog)
- **Pre-requisito**: 4.1 + 4.2 (pra ter dados pra plotar)

**4.4 Alertas sensoriais P1 por especie** — `[BE]` 🟡 PARCIAL
- Alertas DHT temp/hum existem (v4.1.58) com **thresholds globais hardcoded** (35°C / 10°C / 20%-95%)
- Falta:
  - Thresholds vir do catalogo de especies (3.1)
  - Logica per-modulo cruzar lote ativo (3.2) com especie pra resolver thresholds
  - Severidade subir pra P1 quando alerta sensorial cruza com lote em estagio critico
- **Pre-requisito**: 3.1 + 3.2 + (4.1 ou 4.2 — ja teria com hidro-farm DHT11 mas com baixa precisao)

---

### Mes 5 — Agosto (Planejamento e Inteligencia Operacional) — ⏳ 0/4

**5.1 Motor de planejamento (Lei de Little)** — `[BE]`
- Conceito: `L = λ × W` — lotes em pipeline = throughput × tempo de ciclo
- Permite calcular quantos lotes deveriam estar em cada estagio pra atingir meta mensal
- UI minima nesta release: API `GET /api/planning/ideal-pipeline?species=X&meta=N`
- **Pre-requisito**: 3.1 + 3.2

**5.2 Agenda automatica semeadura/transferencia** — `[BE][FE]`
- Cron interno gera tarefas (semear lote X, transferir lote Y) baseado em meta + ciclo
- Card "agenda da semana" no dashboard
- **Pre-requisito**: 5.1

**5.3 Relatorios real vs planejado + fator perda** — `[BE][FE]`
- Pagina `/relatorios` com filtros (especie, periodo)
- Calcular fator de perda = `1 - (colhidos / plantados)` por especie
- Comparar planejado (meta × ciclo) vs real (lotes finalizados)
- **Pre-requisito**: 3.1 + 3.2 (pra ter dados de plantados/colhidos)

**5.4 Alertas pipeline P2 (estagio < 70% volume ideal)** — `[BE]`
- Novo alerta `pipeline_underflow` (P2)
- Dispara quando `volume_atual_no_estagio < 0.7 × volume_ideal_calculado`
- Possivelmente categoria nova de alertas "operacionais" (nao per-module — e cross-fazenda)
- **Pre-requisito**: 5.1

---

## Como atualizar este documento

Quando entregar um item:

1. Mudar status na **tabela mestre** (coluna Status: ✅ ou 🟡)
2. Adicionar versao na coluna **Versao / Ref** (ex: `v4.1.60`)
3. Atualizar contadores no **Resumo executivo** (35% no topo)
4. Atualizar **Estatisticas por categoria** (concluidos)
5. Atualizar **Ultima atualizacao** no topo
6. No **detalhe expandido** do mes, marcar item com ✅ + observacao breve
7. Commit junto com a release que entregou o item

Se o **escopo MUDAR** (item ganhou novo requisito ou foi descartado):
- Adicionar nota inline `**Reescopo (DD/MM/YYYY)**: ...` mantendo o texto original visivel
- NAO apaga o item original — preserva historico

---

## Proximos passos imediatos (ordem sugerida)

### Curto prazo (~2 semanas)
1. **Agendar visita ao parceiro** — fecha 2.1 + 2.2 (presenciais).
2. **Iniciar 3.1 (catalogo de especies)** — software puro, habilita Mes 5 inteiro + 4.4.
3. **Decidir compras do Mes 4** (DHT22 + MH-Z19 + sondas pH/CE) — leadtime longo, comecar antes.

### Medio prazo (~1 mes)
4. **3.2 (lotes + state machine)** — sequencial a 3.1.
5. **3.3 + 3.4** — completam o Mes 3.

### Sequencia natural daqui
6. **4.1 modulo CLIMA primeiro** (mais simples que SOLUCAO).
7. **4.2 modulo SOLUCAO** (calibracao 2 pontos exige cuidado extra).
8. **4.3 + 4.4** — depois de 4.1 + 4.2 + 3.1 + 3.2.
9. **Mes 5 inteiro** — depende de 3.1 + 3.2.

### Em paralelo (nao bloqueia roadmap tecnico)
- Decidir modelo de monetizacao (`docs/license-gate.md`)
- DPO + AIPD + Termos (compliance)
- Manual consumidor PDF + video 3min (`docs/manual-usuario.md`)
