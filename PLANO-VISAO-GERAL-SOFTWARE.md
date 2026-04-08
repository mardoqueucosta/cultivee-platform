# Plano de Visao Geral - Software Cultivee

**Data:** 2026-03-30
**Status:** Em discussao

---

## 1. Contexto do Projeto

### Titulo
Sistema inteligente de producao, distribuicao e comercializacao de hortalicas em ambientes urbanos utilizando IoT

### Descricao
Modelo integrado composto por uma fazenda vertical indoor e uma rede de expositores de pequeno porte, interligados via computacao em nuvem, para elevar a rentabilidade do produtor e entregar hortalicas mais frescas ao consumidor.

### 3 Pilares do Sistema

| Pilar | Descricao |
|-------|-----------|
| **Fazenda Vertical Indoor** | Cultivo hidroponico (microverdes, mudas, adultas) por 20-40 dias |
| **Expositores Distribuidos** | Cabines de pequeno porte em pontos urbanos, mantendo plantas vivas por 5-10 dias |
| **Software em Nuvem** | Monitoramento, controle e integracao de toda a cadeia |

### Fluxo Operacional
1. Cultivo na fazenda vertical (20-40 dias)
2. Transferencia para expositores proximos ao periodo ideal de colheita (5-10 dias)
3. Software gera alertas de reposicao, fechando o ciclo

### Hardware de Controle
- **ESP32 com WiFi** — um ESP32 fisico por modulo (cada modulo e independente)

---

## 2. Contexto Extraido das Imagens

### Diagrama Completo (Imagem 1)
- Ciclo fechado: **Produtor** (Fazenda Vertical + Estufa) → **Cloud** (Software, Computador, Smartphone) → **Expositores Distribuidos** (predios residenciais/comerciais, lojas, comercio)
- Sensores nos expositores: luminosidade/espectro, CO2, umidade, temperatura, pH, nivel de agua
- Fluxo bidirecional: **Info** sobe do produtor para a nuvem, **Dados** sobem dos expositores para a nuvem
- **Hortalicas** fluem fisicamente do produtor para os expositores

### Diagrama Simplificado (Imagem 2)
- Expositores comunicam via **WiFi** com o servidor em nuvem
- **Painel do produtor** (computador) para gestao da fazenda vertical
- **Smartphone** como interface movel
- Expositores distribuidos em **lojas e comercio**

---

## 3. Arquitetura Modular

### Principio Fundamental

Cada modulo e um **ESP32 fisico independente** com um unico firmware/produto.
Uma fazenda ou expositor e a **soma dos ESP32s pareados** no app, agrupados via Groups.
Adicionar capacidade = parear mais um ESP32. Remover = desparear.

### Catalogo de Modulos

```
┌─────────────────────────────────────────────────────────────┐
│                    MODULOS DISPONIVEIS                        │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │  HIDRO   │  │   CAM    │  │  CLIMA   │                   │
│  │ (existe) │  │ (existe) │  │  (novo)  │                   │
│  │          │  │          │  │          │                    │
│  │ Luz+Bomba│  │ OV2640   │  │ Temp     │                   │
│  │ Fases    │  │ Stream   │  │ Umidade  │                   │
│  │ Automacao│  │ Capture  │  │ CO2      │                   │
│  │          │  │ Live     │  │          │                    │
│  │ WROOM    │  │ WROVER   │  │ WROOM    │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
│                                                              │
│  ┌──────────┐  ┌──────────┐                                  │
│  │ SOLUCAO  │  │ DOSADORA │                                  │
│  │  (novo)  │  │  (novo)  │                                  │
│  │          │  │          │                                  │
│  │ pH       │  │ Bomba A  │                                  │
│  │ EC/TDS   │  │ Bomba B  │                                  │
│  │ Nivel    │  │ pH+      │                                  │
│  │          │  │ pH-      │                                  │
│  │ WROOM    │  │ WROOM    │                                  │
│  └──────────┘  └──────────┘                                  │
│                                                              │
│  Cada caixa = 1 ESP32 fisico com seu proprio firmware        │
└─────────────────────────────────────────────────────────────┘
```

#### Existentes (ja implementados)

| Modulo | Product file | Capability | Hardware | O que faz |
|--------|-------------|-----------|----------|-----------|
| **hidro** | `products/hidro.h` | Reles + fases | ESP32-WROOM, GPIO4/5 | Controle de luz e bomba, fotoperíodo, fases de cultivo |
| **cam** | `products/cam.h` | Camera OV2640 | ESP32-WROVER, PSRAM | Captura, streaming MJPEG, live mode |

#### Novos (a desenvolver)

| Modulo | Product file | Capability | Sensores/Atuadores | O que faz |
|--------|-------------|-----------|-------------------|-----------|
| **clima** | `products/clima.h` | Ambiente | DHT22/SHT30 + MH-Z19 | Monitoramento de temp, umidade, CO2 |
| **solucao** | `products/solucao.h` | Solucao nutritiva | Sensor pH + EC/TDS + boia nivel | Qualidade da hidroponia e nivel de agua |
| **dosadora** | `products/dosadora.h` | Dosagem | Bombas peristalticas (4x) | Ajuste automatico de nutrientes e pH |

### Composicao por Agrupamento (Groups)

```
FAZENDA VERTICAL "Rack 1"                EXPOSITOR "Loja Centro"
┌─────────────────────────┐              ┌─────────────────────────┐
│  Grupo no app (5 ESP32) │              │  Grupo no app (3 ESP32) │
│                         │              │                         │
│  [hidro] ← luz+bomba   │              │  [hidro] ← luz+bomba   │
│  [cam]   ← camera      │              │  [clima] ← temp+umid   │
│  [clima] ← temp+umid+co2│             │  [solucao] ← nivel     │
│  [solucao] ← pH+EC+nivel│             │                         │
│  [dosadora] ← 4 bombas │              │                         │
└─────────────────────────┘              └─────────────────────────┘

Cada [] = 1 ESP32 fisico independente pareado no grupo
```

### Flexibilidade na Pratica

O usuario monta a combinacao que precisa:

| Cenario | ESP32s pareados no grupo |
|---------|--------------------------|
| Fazenda completa | hidro + cam + clima + solucao + dosadora |
| Fazenda basica | hidro + clima + solucao |
| Expositor padrao | hidro + clima + solucao |
| Expositor com camera | hidro + clima + solucao + cam |
| Expositor minimo | hidro + solucao |
| Monitoramento avulso | clima |

Para adicionar camera no expositor → basta parear mais um ESP32 com `cam.h` no grupo.
Para remover dosadora da fazenda → basta desparear o ESP32 da dosadora.

---

## 4. Arquitetura Tecnica

### Visao Geral

```
┌───────────────────────────────────────────────────────────────┐
│                    ESP32s INDEPENDENTES                         │
│                                                                │
│  [hidro]  [cam]  [clima]  [solucao]  [dosadora]               │
│  Cada um com seu firmware, seus sensores, sua comunicacao      │
│  Cada um se registra individualmente no servidor               │
└──────────┬────────┬────────┬──────────┬──────────┬────────────┘
           │        │        │          │          │
           └────────┴────────┴────┬─────┴──────────┘
                                  │ WiFi / HTTP polling
┌─────────────────────────────────▼─────────────────────────────┐
│                    SERVIDOR (Flask unificado)                   │
│                                                                │
│  /api/modules/register  ← todos os ESP32 se registram aqui    │
│  /api/modules/poll      ← todos buscam comandos aqui          │
│  /api/ctrl/*            ← blueprint hidro                     │
│  /api/cam/*             ← blueprint cam                       │
│  /api/clima/*           ← blueprint clima (novo)              │
│  /api/solucao/*         ← blueprint solucao (novo)            │
│  /api/dosadora/*        ← blueprint dosadora (novo)           │
└─────────────────────────────────┬─────────────────────────────┘
                                  │
┌─────────────────────────────────▼─────────────────────────────┐
│                    PWA (app.cultivee.com.br)                    │
│                                                                │
│  moduleRenderers = {                                           │
│    hidro:    { renderContent: renderModule_hidro },            │
│    cam:      { renderContent: renderModule_cam },              │
│    clima:    { renderContent: renderModule_clima },    (novo)  │
│    solucao:  { renderContent: renderModule_solucao },  (novo)  │
│    dosadora: { renderContent: renderModule_dosadora }, (novo)  │
│  }                                                             │
│                                                                │
│  Groups: agrupa modulos visualmente por fazenda/expositor      │
└───────────────────────────────────────────────────────────────┘
```

### Caminho de cada Modulo (do hardware ao app)

```
  products/clima.h                firmware/mod_clima.h
  ┌──────────────┐               ┌──────────────────────┐
  │ #define MOD_  │               │ clima_setup()        │
  │ MODULE_TYPE   │──────────────▶│ clima_loop()         │
  │ PINAGEM       │  compilacao   │ clima_status_json()  │
  │ SERVER_URL    │  condicional  │ clima_dashboard_html │
  └──────────────┘               │ clima_process_cmd()  │
                                  └──────────┬───────────┘
                                             │
                                   WiFi      │  POST /api/modules/register
                                   HTTP      │  { chip_id, type:"clima",
                                   polling   │    capabilities:["clima"],
                                             │    ctrl_data:{temp,umid,co2} }
                                             │
                                  ┌──────────▼───────────┐
                                  │ server/bp_clima.py    │
                                  │                       │
                                  │ GET /status           │
                                  │ GET /history          │
                                  │ POST /thresholds      │
                                  │                       │
                                  │ Registrado em app.py: │
                                  │ /api/clima/*          │
                                  └──────────┬───────────┘
                                             │
                                  ┌──────────▼───────────┐
                                  │ PWA (app.js)          │
                                  │                       │
                                  │ moduleRenderers.clima │
                                  │ = {                   │
                                  │   label: 'Clima',     │
                                  │   renderContent: ..., │
                                  │   getStatusText: ..., │
                                  │ }                     │
                                  └──────────────────────┘
```

Esse caminho e **identico** para todos os modulos. Mudam apenas os sensores/atuadores, as rotas e o render no app.

### Padrao para cada novo modulo (ja documentado no CLAUDE.md)

| Camada | Arquivos | Trabalho |
|--------|----------|----------|
| **Firmware** | `products/modulo.h` + `firmware/mod_modulo.h` + integracao no `firmware.ino` | Sensores, atuadores, rotas locais, dashboard offline |
| **Server** | `server/bp_modulo.py` + registro no `app.py` | Blueprint com rotas, validacao de capability |
| **PWA** | Entrada no `moduleRenderers` em `app.js` | Render do conteudo, status text |
| **Infra** | DNS + label Traefik no `docker-compose.yml` | Subdominio modulo.cultivee.com.br |

---

## 5. Parametros de Cultivo de Referencia

Valores baseados em Cornell CEA Lettuce Handbook, University of Florida Extension e estudos em hidroponia. Alimentam a tabela `species` no banco e definem os limiares de alerta.

### Folhosas (Alface Crespa, Americana, Rucula)

| Parametro | Faixa Otima | Alerta Baixo | Alerta Alto | Observacao |
|-----------|-------------|-------------|-------------|------------|
| **Temperatura ar** | 18–24°C (dia), 15–18°C (noite) | < 15°C | > 25°C | Risco de pendoamento acima de 25°C |
| **Umidade relativa** | 50–70% | < 50% | > 80% | Tip burn em alta umidade |
| **CO2** | 600–1500 ppm | < 400 ppm | > 1500 ppm | Retorno decrescente acima de 1500 |
| **pH (solucao)** | 5,5–6,5 | < 5,0 | > 7,0 | Medir diariamente |
| **CE (condutividade)** | 1,2–1,8 mS/cm | < 0,8 | > 2,5 | Muda: 0,8–1,2; adulta: 1,2–1,8 |
| **DLI (luz)** | 12–17 mol/m²/dia | < 10 | > 20 | 16–18h de fotoperiodo |

### Ervas (Cebolinha, Salsinha)

| Parametro | Faixa Otima | Observacao |
|-----------|-------------|------------|
| **Temperatura ar** | 20–25°C | Ligeiramente mais alta que folhosas |
| **CE** | 1,0–1,6 mS/cm | Mais sensivel a salinidade |
| **pH** | 5,5–6,5 | Mesmo que folhosas |

### Microverdes

| Parametro | Faixa Otima | Observacao |
|-----------|-------------|------------|
| **Umidade** | 40–60% | Menor que folhosas — previne mofo |
| **CE** | 0,5–1,0 mS/cm | Solucao mais fraca |
| **Ciclo** | 7–14 dias | Mais rapido que folhosas |

### Ciclos por Especie

| Especie | Dias na Fazenda | Dias no Expositor | Total do Ciclo |
|---------|----------------|-------------------|----------------|
| Alface Crespa | 25–30 | 5–10 | ~35–40 dias |
| Alface Americana | 30–35 | 5–10 | ~35–45 dias |
| Rucula | 20–25 | 5–7 | ~25–32 dias |
| Cebolinha | 35–40 | 7–10 | ~42–50 dias |
| Salsinha | 35–40 | 7–10 | ~42–50 dias |
| Microverdes | 7–14 | 2–4 | ~9–18 dias |

> Esses valores resolvem a decisao pendente "Especies e seus tempos de ciclo" da Secao 10 e sao o input direto para a Fase 3 (Inventario e Ciclo da Planta).

---

## 7. Detalhe dos Novos Modulos

### Modulo HIDRO (products/hidro.h) — EXISTE

| Item | Detalhe |
|------|---------|
| **Board** | ESP32-WROOM-32D |
| **GPIO** | 4 (luz), 5 (bomba) |
| **Firmware** | `mod_hidro.h` (832 linhas) |
| **Blueprint** | `bp_hidro.py` → `/api/ctrl/*` |
| **ctrl_data** | `{ light, pump, mode, phase, cycle_day, phases[] }` |
| **Funcao** | Reles + fases + fotoperíodo + automacao |

### Modulo CAM (products/cam.h) — EXISTE

| Item | Detalhe |
|------|---------|
| **Board** | ESP32-WROVER-DEV (PSRAM) |
| **Sensor** | OV2640 (VGA 640x480) |
| **Firmware** | `mod_cam.h` (457 linhas) |
| **Blueprint** | `bp_cam.py` → `/api/cam/*` |
| **ctrl_data** | `{ camera_ready, live_mode }` |
| **Funcao** | Captura, streaming MJPEG, live mode |

### Modulo CLIMA (products/clima.h) — NOVO

**Objetivo:** Monitoramento ambiental (temperatura, umidade, CO2)

| Item | Detalhe |
|------|---------|
| **Board** | ESP32-WROOM-32D |
| **Sensores** | DHT22 ou SHT30 (temp+umidade), MH-Z19 (CO2) |
| **MODULE_TYPE** | "clima" |
| **Capability** | ["clima"] |
| **ctrl_data** | `{ temp: 25.3, humidity: 68.2, co2: 420 }` |
| **Intervalo leitura** | 30-60s |
| **Dashboard local** | Valores atuais + mini historico |

**Funcionalidades no app:**
- Graficos em tempo real (temp, umidade, CO2)
- Historico (ultimas 24h, 7d, 30d)
- Configuracao de faixas ideais (min/max por variavel)
- Alertas quando fora da faixa

**Rotas do blueprint (bp_clima.py):**
- `GET /<chip_id>/status` — leitura atual
- `GET /<chip_id>/history` — historico de leituras
- `POST /<chip_id>/thresholds` — salvar faixas ideais

---

### Modulo SOLUCAO (products/solucao.h) — NOVO

**Objetivo:** Monitoramento da solucao nutritiva (pH, EC/TDS, nivel)

| Item | Detalhe |
|------|---------|
| **Board** | ESP32-WROOM-32D |
| **Sensores** | Sensor pH analogico, sensor EC/TDS, boia de nivel |
| **MODULE_TYPE** | "solucao" |
| **Capability** | ["solucao"] |
| **ctrl_data** | `{ ph: 6.2, ec: 1.4, tds: 700, nivel: "ok" }` |
| **Intervalo leitura** | 60s |
| **Calibracao** | pH requer calibracao periodica (buffer 4.0 e 7.0) |

**Funcionalidades no app:**
- Valores atuais (pH, EC, nivel) com indicadores visuais (verde/amarelo/vermelho)
- Historico e tendencias
- Wizard de calibracao do pH (guiado pelo app)
- Alertas: pH fora da faixa, nivel baixo do reservatorio

**Rotas do blueprint (bp_solucao.py):**
- `GET /<chip_id>/status` — leitura atual
- `GET /<chip_id>/history` — historico
- `POST /<chip_id>/calibrate` — iniciar calibracao
- `POST /<chip_id>/thresholds` — faixas ideais

---

### Modulo DOSADORA (products/dosadora.h) — NOVO

**Objetivo:** Dosagem automatica de nutrientes e ajuste de pH

| Item | Detalhe |
|------|---------|
| **Board** | ESP32-WROOM-32D |
| **Atuadores** | 4 bombas peristalticas (Nutriente A, Nutriente B, pH+, pH-) |
| **MODULE_TYPE** | "dosadora" |
| **Capability** | ["dosadora"] |
| **ctrl_data** | `{ bomba_a: false, bomba_b: false, ph_up: false, ph_down: false, modo: "manual" }` |
| **Dependencia** | Funciona melhor em conjunto com modulo solucao (leitura de pH/EC) |

**Funcionalidades no app:**
- Controle manual de cada bomba (ligar/desligar, dosar X ml)
- Modo automatico (requer modulo solucao no mesmo grupo):
  - Se pH < min → acionar pH+
  - Se pH > max → acionar pH-
  - Se EC < min → dosar nutrientes A+B
- Historico de dosagens
- Configuracao de receitas (proporcao A:B, faixas pH/EC alvo)

**Rotas do blueprint (bp_dosadora.py):**
- `GET /<chip_id>/status` — estado das bombas
- `GET /<chip_id>/dose` — dosar manualmente (?bomba=a&ml=5)
- `POST /<chip_id>/recipe` — salvar receita
- `POST /<chip_id>/auto-config` — configurar modo automatico

---

## 8. Comunicacao entre Modulos do mesmo Grupo

Os modulos sao independentes, mas o **modo automatico da dosadora** precisa ler dados do **modulo solucao**. Isso acontece **pelo servidor**, nao entre ESP32s:

```
[solucao ESP32] ──POST ctrl_data:{ph:5.8}──▶ [SERVIDOR]
                                                  │
                                            consulta pH
                                            do grupo
                                                  │
[dosadora ESP32] ◀──comando:{dosar ph_up}─── [SERVIDOR]
```

O servidor ve todos os modulos do grupo e toma decisoes cross-module.
Nenhum ESP32 precisa saber da existencia dos outros.

---

## 9. Contextos de Uso: Fazenda vs Expositor

Mesmo catalogo de modulos, **contextos operacionais diferentes:**

| Aspecto | Fazenda Vertical | Expositor |
|---------|-----------------|-----------|
| **Localizacao** | Centralizada (1 local) | Distribuido (N locais remotos) |
| **Operador** | Presente no dia a dia | Ausente (desassistido) |
| **Objetivo** | Maximizar crescimento | Preservar frescor |
| **Modulos tipicos** | hidro + cam + clima + solucao + dosadora | hidro + clima + solucao |
| **Complexidade** | Alta (mais modulos, automacao avancada) | Baixa (poucos modulos, modo manutencao) |
| **Criticidade offline** | Media (operador por perto) | Alta (precisa funcionar sozinho) |
| **Alertas prioritarios** | Otimizacao (pH desviou, EC baixo) | Seguranca (offline, temp critica, sem agua) |
| **Fases do hidro** | Completas (Muda→Bercario→Engorda) | Simplificadas (fase unica de manutencao) |
| **Dosadora** | Sim (ajuste fino de nutrientes) | Nao (sem necessidade) |

A diferenciacao entre fazenda e expositor e feita pelo **agrupamento e configuracao no app**, nao pelo firmware.

---

## 10. Evolucao dos Groups

O sistema de groups ja existe no banco (`groups` table). Para suportar fazenda/expositor, precisamos evoluir:

### Melhorias necessarias no Group

| Funcionalidade | Descricao |
|---------------|-----------|
| **Tipo de grupo** | Campo `type` (fazenda, expositor, estufa, avulso) |
| **Dashboard agregado** | Visao consolidada de todos os modulos do grupo |
| **Alertas por grupo** | Alertas que consideram dados de multiplos modulos |
| **Localizacao** | Endereco/coordenadas do grupo (util para expositores distribuidos) |
| **Status do grupo** | Online se todos os modulos estao online, alerta se algum offline |

---

## 11. Atividades Macro para Desenvolvimento

### Premissa

A operacao inicial usa os **modulos existentes (hidro + cam)**. O sistema e modular — novos modulos de hardware (clima, solucao, dosadora) podem ser adicionados a qualquer momento sem alterar o que ja funciona. O foco agora e construir o **software de gestao** que permite ao produtor operar fazenda e expositores no dia a dia.

### Visao da Experiencia do Produtor

```
┌─────────────────────────────────────────────────────────┐
│  DASHBOARD PRINCIPAL                                     │
│                                                          │
│  ⚠ ALERTAS E ACOES                                      │
│  ┌────────────────────────────────────────────────────┐  │
│  │ ! Expositor "Cond. Flores" offline ha 2h           │  │
│  │ ! Expositor "Padaria Centro" — repor em 3 dias     │  │
│  │ ✓ Fazenda "Galpao 1" — tudo operando normal        │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  MEUS LOCAIS                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ FAZENDA       │  │ EXPOSITOR    │  │ EXPOSITOR    │   │
│  │ "Galpao 1"   │  │ "Padaria     │  │ "Cond.       │   │
│  │ ● Online     │  │  Centro"     │  │  Flores"     │   │
│  │ 5 modulos    │  │ ● Online     │  │ ⚠ Offline    │   │
│  │ 45 plantas   │  │ 3 modulos    │  │ 2 modulos    │   │
│  │              │  │ 6 alfaces    │  │ 4 ruculas    │   │
│  │              │  │ dia 7/10     │  │ dia 9/10     │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                          │
│  [+ Adicionar Local]                                     │
└─────────────────────────────────────────────────────────┘

Tocar num local → abre detalhes com modulos, plantas, historico
```

O produtor responde 3 perguntas ao abrir o app:
1. **"Ta tudo funcionando?"** — status dos locais (online/offline/alerta)
2. **"Preciso repor algum expositor?"** — alertas de reposicao no topo
3. **"O que eu faco hoje?"** — lista de acoes prioritarias

---

### Fase 1 — Locais e Dashboard do Produtor

Transformar a visao atual (lista de modulos) em visao por **locais** (fazenda/expositor).

| Item | Descricao |
|------|-----------|
| **Tipo de grupo** | Campo `type` na tabela groups (fazenda, expositor) |
| **Dashboard principal** | Cartoes por local com status resumido |
| **Tela do local** | Ao tocar, mostra modulos daquele local + status detalhado |
| **Status consolidado** | Local "online" se todos os modulos reportam; "alerta" se algum offline |
| **Localizacao** | Campo endereco/descricao no grupo (ex: "Rua X, Loja Y") |

**Resultado:** Produtor ve seus locais organizados, nao uma lista tecnica de ESP32s.

### Fase 2 — Alertas e Notificacoes

Dar visibilidade ao produtor sobre problemas sem que ele precise verificar manualmente.

#### Classificacao de Alertas (4 niveis)

| Nivel | Nome | Exemplos | Canal | Acao esperada |
|-------|------|---------|-------|---------------|
| **P0** | Critico | Expositor offline ha > 1h, temperatura fora da faixa de segurança, bomba falhou | Push imediato | Resposta em minutos |
| **P1** | Alto | pH fora do otimo, CE desviado, modulo sem comunicacao ha 30 min | Push + email | Resposta em horas |
| **P2** | Operacional | Reposicao necessaria, manutencao programada, nivel de agua baixo | Banner no dashboard | Resposta no dia |
| **P3** | Informacional | Lote pronto para transferir, resumo diario de operacao, marco de crescimento | Dashboard | Sem urgencia |

#### Mecanismos Anti-Fatigue

Evitar que o produtor ignore alertas por excesso de notificacoes:
- **Cooldown**: P0 nao re-alerta mesma condicao por 5 min; P1 por 1 hora
- **Consolidacao**: se todos os modulos de um expositor ficam offline, 1 alerta do local (nao N alertas individuais)
- **Meta**: menos de 5 alertas P0/P1 acionaveis por dia na operacao normal

#### Itens de Implementacao

| Item | Descricao |
|------|-----------|
| **Deteccao de offline** | Se ESP32 nao faz polling em 10 minutos → marcar offline (P1); 60 min → P0 |
| **Painel de alertas** | Secao no topo do dashboard com alertas ativos, agrupados por nivel |
| **Cooldown** | Registrar `last_alerted_at` por alerta para evitar repeticoes |
| **Notificacao push** | Via service worker da PWA — P0 e P1 imediatos |
| **Email** | P1 envia email como backup (se push nao for entregue) |
| **Historico** | Log de alertas com timestamp, nivel, resolucao |

**Resultado:** Produtor e notificado de problemas com contexto de urgencia. Nao recebe spam de notificacoes.

### Fase 3 — Inventario e Ciclo da Planta

Rastrear o que esta plantado, onde, e ha quanto tempo. Este e o diferencial de negocio central do projeto — o que transforma o software de monitoramento em gestao de cadeia produtiva.

#### Conceito de Receita por Especie

Cada especie tem uma "receita" que define seu comportamento ao longo do ciclo:

```
RECEITA: Alface Crespa
├── Fase 1: Semeadura (D0)
│   └── CE: 0.8–1.2 | pH: 5.5–6.5 | Luz: 12h
├── Fase 2: Bercario (D0–D10)
│   └── CE: 1.0–1.4 | pH: 5.5–6.5 | Luz: 14h
├── Fase 3: Engorda (D10–D28)
│   └── CE: 1.2–1.8 | pH: 5.5–6.5 | Luz: 16h
├── Fase 4: No Expositor (D28–D38)
│   └── CE: 1.0–1.4 | Luz: 8h (preservacao)
│   └── Alerta em D35 (5 dias restantes)
│   └── Alerta critico em D38 (remover)
```

A receita e o input para: fases do modulo hidro, limiares de alerta por fase, contagem regressiva, e alerta de reposicao.

#### Rastreabilidade Basica

Cada lote recebe um codigo unico (ex: `ALC-20260401-01`) e tem seus eventos registrados:

| Evento (CTE) | O que registrar |
|-------------|-----------------|
| **Plantio** | Especie, quantidade, data, local (fazenda), codigo do lote |
| **Transferencia** | Data de saida da fazenda, data de entrada no expositor, operador |
| **Exposicao** | Dias no expositor, condicoes ambientais (se houver modulo clima) |
| **Fim** | Data e tipo de encerramento (Vendido / Descartado / Perdido) |

Essa estrutura atende rastreabilidade basica para o produtor e estabelece a fundacao para conformidade regulatoria futura (ANVISA, tendencia FSMA 204 nos EUA para 2028).

#### Itens de Implementacao

| Item | Descricao |
|------|-----------|
| **Tabela `species`** | Especie, dias_fazenda, dias_expositor, faixas por parametro |
| **Tabela `lots`** | Codigo, especie, quantidade, status, datas de cada CTE |
| **Cadastro de lote** | Especie, quantidade, data de plantio, local (fazenda) |
| **Fases do lote** | Em cultivo → Pronto para transferir → No expositor → Encerrado |
| **Transferencia** | Registrar saida da fazenda e entrada no expositor |
| **Contagem regressiva** | Dias restantes no expositor baseado na receita da especie |
| **Alerta P2 de reposicao** | Automatico quando lote entra na janela de fim de vida |
| **Alerta P3 informacional** | "Lote pronto para transferir da fazenda para o expositor" |
| **Visao por local** | "Este expositor tem: 6 alfaces (D7/10), 4 ruculas (D3/7)" |

**Resultado:** Produtor sabe exatamente o que repor, onde e quando. Fecha o ciclo fazenda→expositor. Rastreabilidade habilitada desde o inicio para evolucao futura.

### Fase 3B — Planejamento e Previsao de Producao

Transformar a meta do produtor ("quero 1.000 plantas/mes") em numeros operacionais concretos para cada etapa do ciclo, e monitorar se o pipeline real esta no caminho certo.

#### O Conceito: Pipeline Continuo (Lei de Little)

Para ter saida constante no final, precisa de entrada constante no inicio e o numero certo de plantas em cada etapa simultaneamente:

```
Plantas na etapa = Taxa de saida diaria × Duracao da etapa (dias)
```

#### Ciclo de Referencia (Alface Crespa — exemplo simplificado)

```
DIA 0        DIA 5       DIA 15       DIA 28      DIA 30      DIA 37
  │            │            │             │            │            │
  ▼            ▼            ▼             ▼            ▼            ▼
SEMEADURA → BERCARIO  →  ENGORDA  → PRE-COLHEITA → TRANSFERE → FIM VIDA
 (5 dias)   (10 dias)   (13 dias)    (2 dias)     Expositor   (7 dias)
```

| Etapa | Duracao | O que acontece |
|-------|---------|----------------|
| Semeadura / Germinacao | 5 dias | Sementes em substrato, ambiente controlado |
| Bercario | 10 dias | Mudas no sistema hidroponico, luz moderada |
| Engorda | 13 dias | Crescimento acelerado, luz e CE maximos |
| Pre-colheita / Janela | 2 dias | Planta pronta aguardando transferencia |
| No Expositor | 7 dias | Preservacao de frescor no ponto de venda |
| **Total ciclo** | **37 dias** | Da semente ao fim da vida util |

#### Matematica do Pipeline — Meta: 1.000 plantas/mes

**Cadencia base:**
```
Plantas/dia necessarias: 1.000 / 30 = 33 plantas/dia
Plantas/semana:          33 × 7     = 231 plantas/semana

Fator de perda tipico (hidroponia controlada): ~18%
  Germinacao: 10–15% | Bercario: 3–5% | Engorda: 1–3%

Sementes necessarias/dia:    33 / 0,82 = ~41 sementes/dia
Sementes necessarias/semana: 41 × 7    = ~287 sementes/semana
```

**Pipeline ideal em estado estavel (o que deve existir simultaneamente):**

```
┌──────────────────────────────────────────────────────────────────┐
│           PIPELINE IDEAL — 1.000 PLANTAS/MES                     │
│                (Alface Crespa, ciclo 30 dias fazenda)            │
│                                                                  │
│  FAZENDA VERTICAL                                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ GERMINACAO  │  │  BERCARIO   │  │   ENGORDA   │             │
│  │  205 mudas  │  │  330 mudas  │  │ 429 plantas │             │
│  │  (5 dias)   │  │  (10 dias)  │  │  (13 dias)  │             │
│  │  41/dia ↓   │  │  33/dia ↓   │  │  33/dia ↓   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                         PRE-COLHEITA: 66 plantas (2 dias)       │
│                                                                  │
│  EXPOSITORES DISTRIBUIDOS                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  231 plantas distribuidas (7 dias)                        │   │
│  │  33 plantas/dia entram ← 33 plantas/dia saem (vendas)    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  TOTAL NA FAZENDA:  ~1.030 posicoes ocupadas                    │
│  TOTAL EXPOSITORES: ~231  posicoes ocupadas                     │
│  TOTAL NO SISTEMA:  ~1.261 plantas vivas simultaneamente        │
└──────────────────────────────────────────────────────────────────┘
```

**Tabela de referencia por meta mensal:**

| Meta/mes | Sementes/semana | Germinacao | Bercario | Engorda | Expositores | Total sistema |
|----------|----------------|-----------|---------|---------|-------------|---------------|
| 500 | ~144 | ~102 | 165 | 215 | 115 | ~597 |
| 1.000 | ~287 | ~205 | 330 | 429 | 231 | ~1.195 |
| 2.000 | ~574 | ~410 | 660 | 858 | 462 | ~2.390 |
| 5.000 | ~1.435 | ~1.020 | 1.650 | 2.145 | 1.155 | ~5.970 |

#### Cadencia Operacional Semanal (gerada pelo sistema)

Com base na meta e na especie, o software gera a agenda semanal do produtor:

| Atividade | Frequencia | Quantidade (meta 1.000/mes) |
|-----------|-----------|----------------------------|
| Semear novo lote | Semanal (ex: segunda-feira) | 287 sementes |
| Transferir germinacao → bercario | Semanal | ~235 mudas |
| Verificar pH, EC e nivel | 2–3x por semana | — |
| Transferir engorda → expositor | Semanal (ex: sexta-feira) | 231 plantas |
| Registrar encerramento de lotes | Semanal | — |

#### Monitoramento Real vs. Planejado (Dashboard)

O sistema compara o estoque real de lotes cadastrados com os numeros ideais calculados:

```
PLANEJAMENTO — Alface Crespa | Meta: 1.000 plantas/mes

ETAPA            IDEAL      REAL     STATUS
─────────────────────────────────────────────────────
Germinacao        205       198      ✓ Normal (97%)
Bercario          330       310      ✓ Normal (94%)
Engorda           429       380      ⚠ Atencao (89%)
Pre-colheita       66        72      ✓ Normal
Expositores       231       185      ⚠ Atencao (80%)
─────────────────────────────────────────────────────
Producao prevista este mes: 930 plantas  ⚠ -7% da meta
Acao sugerida: aumentar proximo lote em 50 sementes
```

#### Alertas do Planejamento

| Nivel | Condicao | Mensagem |
|-------|----------|---------|
| P1 | Etapa com < 70% do ideal | "Engorda com 70% do ideal — meta mensal em risco" |
| P1 | Sem semeadura nos ultimos 10 dias | "Pipeline sem entrada — quebra de producao prevista em 15 dias" |
| P2 | Etapa com 70–90% do ideal | "Bercario levemente abaixo — aumentar proximo lote" |
| P2 | Previsao do mes < meta em > 10% | "Previsao: 900 plantas. Meta: 1.000. Sugestao: +50 sementes" |
| P3 | Pipeline dentro da meta | "Pipeline saudavel — producao projetada: 1.020 plantas" |
| P3 | Agenda da semana disponivel | "Semear 287 sementes hoje. Transferir 231 plantas na sexta." |

#### Itens de Implementacao

| Item | Descricao |
|------|-----------|
| **Tabela `production_plans`** | Meta/mes por especie, frequencia de semeadura, fator de perda estimado |
| **Calculo do pipeline ideal** | Formula automatica: plantas_por_etapa = (meta/30) × dias_etapa / fator_perda |
| **Comparativo real vs. ideal** | Cruzar lotes cadastrados (Fase 3) com numeros calculados |
| **Previsao do mes** | "Com os lotes atuais, produzirei X plantas nos proximos 30 dias" |
| **Calendario de atividades** | Agenda semanal gerada por lote e por especie |
| **Alertas de desvio de meta** | P1/P2 automaticos quando etapa fica abaixo do ideal |
| **Ajuste dinamico** | Ao adicionar/remover expositor, recalcula meta e pipeline |
| **Sugestao de correcao** | "Aumente o proximo lote em X sementes para recuperar a meta" |

**Resultado:** Produtor nao precisa fazer a conta — o sistema diz quantas plantas plantar, quando plantar, e avisa se a meta esta em risco antes que o problema aconteca.

---

### Fase 4 — Relatorios, Metricas e Historico de Producao

Dar ao produtor visao sobre a operacao ao longo do tempo e validar o plano de producao com dados reais.

| Item | Descricao |
|------|-----------|
| **Producao realizada vs. planejada** | Mes a mes, por especie — valida se o plano esta correto |
| **Fator de perda real** | Calculado automaticamente pelo historico de lotes (sementes → plantas colhidas) |
| **Ocupacao por expositor** | % de capacidade utilizada por ponto de venda ao longo do tempo |
| **Ciclos completos** | Quantos lotes completaram o ciclo fazenda→expositor→encerramento |
| **Taxa de perda por etapa** | Onde as plantas estao sendo perdidas (germinacao? bercario?) |
| **Tempo medio por especie** | Da semeadura ao encerramento, real vs. planejado |
| **Exportacao CSV** | Todos os dados para analise externa (Excel, etc.) |

**Resultado:** Produtor ajusta o fator de perda real, calibra o plano de producao e identifica gargalos operacionais com dados do proprio historico.

---

### Futuro — Novos Modulos de Hardware

A arquitetura modular permite adicionar novos modulos a qualquer momento. Cada novo modulo segue o padrao documentado na Secao 4 (firmware + blueprint + PWA renderer) e enriquece os alertas e a automacao ja construidos.

| Modulo | O que adiciona ao sistema |
|--------|--------------------------|
| **Clima** (temp, umidade, CO2) | Alertas ambientais, historico climatico, graficos no dashboard do local |
| **Solucao** (pH, EC, nivel) | Alertas de qualidade da agua, calibracao, indicadores visuais |
| **Dosadora** (4 bombas) | Automacao de nutrientes, modo automatico com leitura cross-module |

Detalhes tecnicos de cada modulo na Secao 5. **Decisoes de hardware pendentes** — definir quando houver demanda operacional.

---

## 12. Roadmap de Evolucao Tecnologica

A stack atual (Flask + SQLite + PWA vanilla + HTTP polling) e adequada para o estagio de validacao. As migracoes abaixo so fazem sentido quando a demanda real justificar a complexidade adicional.

| Estagio | Condicao de Gatilho | Mudancas Tecnologicas |
|---------|--------------------|-----------------------|
| **Atual** (< 20 dispositivos) | — | Flask + SQLite + HTTP polling + PWA vanilla |
| **Medio prazo** (20–50 dispositivos) | Latencia de comandos vira problema operacional | Migrar SQLite → PostgreSQL; avaliar MQTT (Mosquitto) |
| **Longo prazo** (> 50 dispositivos) | Escala de rede de expositores | EMQX cluster, TimescaleDB, gestao de frota (OTA em massa) |
| **Futuro distante** | Volume de dados permite analytics | ML preditivo para anomalias, otimizacao automatica de receitas |

**Principio:** nao antecipar complexidade. Cada migracao so acontece quando o problema que ela resolve ja esta causando dor real na operacao.

### Comparativo HTTP Polling vs MQTT (referencia para decisao futura)

| Criterio | HTTP Polling (atual) | MQTT (futuro) |
|----------|---------------------|----------------|
| Header por mensagem | ~700 bytes | 2 bytes |
| Direcao | ESP32 puxa servidor | Servidor empurra ESP32 |
| Latencia de comando | ate 1x poll_interval | < 1 segundo |
| Complexidade de infra | Zero (Flask ja faz) | Broker adicional (Mosquitto/EMQX) |
| Gatilho para migrar | Comandos precisam de < 5s latencia | — |

---

## 13. Organizacao por Ambiente de Cultivo

Mesmo sistema, tres contextos operacionais distintos com necessidades diferentes de hardware, software e visualizacao.

---

### PARTE 1 — Fazenda Vertical

**Perfil:** Centralizada, operador presente, objetivo = maximizar crescimento, alta complexidade de controle.

#### Hardware necessario

| Modulo ESP32 | Sensores / Atuadores | Funcao |
|-------------|---------------------|--------|
| **HIDRO** | Rele luz (GPIO4), Rele bomba (GPIO5) | Fotoperiodo automatizado, ciclos de irrigacao por fase |
| **CAM** | Camera OV2640 | Monitoramento visual remoto, captura e streaming |
| **CLIMA** | DHT22/SHT30 (temp+umid), MH-Z19 (CO2) | Monitoramento ambiental continuo da sala de cultivo |
| **SOLUCAO** | Sensor pH, sensor EC/TDS, boia nivel | Qualidade e nivel da solucao nutritiva |
| **DOSADORA** | 4 bombas peristalticas (Nutr.A, Nutr.B, pH+, pH-) | Ajuste automatico via cross-module com SOLUCAO |

#### Parametros monitorados

| Parametro | Modulo | Faixa Otima | Tipo de dado |
|-----------|--------|------------|--------------|
| Temperatura do ar | CLIMA | 18–24°C dia / 15–18°C noite | Serie temporal + alerta |
| Umidade relativa | CLIMA | 50–70% | Serie temporal + alerta |
| CO2 | CLIMA | 600–1.500 ppm | Serie temporal + alerta |
| pH da solucao | SOLUCAO | 5,5–6,5 | Serie temporal + alerta |
| EC (condutividade) | SOLUCAO | 1,2–1,8 mS/cm | Serie temporal + alerta |
| Nivel do reservatorio | SOLUCAO | Cheio / Medio / Vazio | Estado + alerta P0 |
| Estado da luz | HIDRO | On/Off + horario | Estado + historico |
| Estado da bomba | HIDRO | On/Off + ciclo | Estado + historico |
| Estado das dosadoras | DOSADORA | 4 bombas + historico dosagens | Estado + log |
| Camera | CAM | — | Imagem / Stream |

#### Alertas da Fazenda

| Nivel | Condicao |
|-------|----------|
| P0 | Temperatura > 28°C ou < 12°C |
| P0 | Nivel do reservatorio vazio |
| P1 | pH < 5,0 ou > 7,0 |
| P1 | EC < 0,8 ou > 2,5 mS/cm |
| P1 | CO2 < 400 ppm ou > 1.500 ppm |
| P1 | Qualquer modulo offline > 30 min |
| P2 | Nivel do reservatorio baixo |
| P3 | Lote pronto para transferir ao expositor |
| P3 | Agenda da semana (semear / transferir) |

---

### PARTE 2 — Expositor de Pequeno Porte

**Perfil:** Distribuido (N locais remotos), desassistido, objetivo = preservar frescor, baixa complexidade, maxima autonomia.

#### Hardware necessario

| Modulo ESP32 | Sensores / Atuadores | Funcao |
|-------------|---------------------|--------|
| **HIDRO** | Rele luz, Rele bomba | Fotoperiodo de manutencao (fase unica simples), irrigacao leve |
| **CLIMA** | DHT22/SHT30 (temp+umid) | Monitoramento para preservar frescor das plantas |
| **SOLUCAO** | Boia nivel | Nivel da agua — critico sem operador presente |
| **CAM** | Camera OV2640 | Opcional — confirmar estado das plantas sem visita fisica |

> Sem DOSADORA (plantas chegam prontas, sem ajuste de nutrientes).
> Sem sensor CO2 obrigatorio (ambiente semi-aberto dilui relevancia).

#### Parametros monitorados

| Parametro | Modulo | Faixa Aceitavel | Observacao |
|-----------|--------|----------------|------------|
| Temperatura do ar | CLIMA | 15–25°C | Fora da faixa deteriora rapidamente |
| Umidade relativa | CLIMA | 50–75% | Alta umidade = risco de mofo |
| Nivel da agua | SOLUCAO | Cheio / Medio / Vazio | Critico — sem agua, plantas morrem em horas |
| Estado da luz | HIDRO | On/Off | Confirmacao do fotoperiodo em execucao |
| Estado da bomba | HIDRO | On/Off | Confirmacao de irrigacao |
| Conectividade | Sistema | Online / Offline | Mais critico no expositor (desassistido) |

#### Alertas do Expositor

| Nivel | Condicao | Motivo da prioridade |
|-------|----------|----------------------|
| P0 | Offline > 60 min | Desassistido — ninguem percebe presencialmente |
| P0 | Nivel da agua vazio | Plantas morrem em horas sem agua |
| P0 | Temperatura > 28°C | Deterioracao rapida e irreversivel |
| P1 | Offline > 10 min | Pode ser queda temporaria de WiFi |
| P1 | Nivel da agua baixo | Janela de acao antes de ficar vazio |
| P1 | Umidade > 80% | Risco de mofo nas plantas |
| P2 | Lote com <= 3 dias restantes | Planejar reposicao urgente |
| P2 | Lote com <= 5 dias restantes | Preparar transferencia da fazenda |

---

### PARTE 3 — Dashboard (o que cada ambiente exibe)

#### Card resumido no dashboard principal

**Fazenda:**
```
┌──────────────────────────────────┐
│ FAZENDA  "Rack 1"                │
│ ● Online   5 modulos ativos      │
│                                  │
│ 🌡 22°C  💧 65%  🌿 820 ppm      │
│ pH 6.1   EC 1.4  Nivel: OK       │
│                                  │
│ Pipeline: 1.030 plantas          │
│ ⚠ 1 lote pronto p/ transferir   │
└──────────────────────────────────┘
```

**Expositor:**
```
┌──────────────────────────────────┐
│ EXPOSITOR  "Padaria Centro"      │
│ ● Online   3 modulos ativos      │
│                                  │
│ 🌡 21°C  💧 62%  Nivel: OK       │
│                                  │
│ Alface Crespa — dia 7/10  🟡     │
│ Rucula       — dia 3/7    🟡     │
└──────────────────────────────────┘
```

#### Tela detalhada — Fazenda Vertical

| Secao | Conteudo |
|-------|---------|
| **Ambiente** | Temp + umid + CO2: gauge atual + grafico 24h/7d |
| **Solucao** | pH + EC + nivel: gauge colorido + tendencia + historico |
| **Controle** | Luz e bomba: toggles manuais + fase atual + progresso |
| **Dosadora** | Estado 4 bombas + modo auto/manual + log de dosagens |
| **Camera** | Preview + botao capturar + botao stream ao vivo |
| **Lotes em cultivo** | Lista: especie, quantidade, estagio, dia do ciclo, previsao de transferencia |
| **Planejamento** | Pipeline real vs. ideal, previsao do mes, agenda da semana |
| **Historico** | Graficos 7d/30d de todos os parametros |

#### Tela detalhada — Expositor

| Secao | Conteudo |
|-------|---------|
| **Status** | Online/Offline + ha quanto tempo + ultima comunicacao |
| **Ambiente** | Temp + umidade: gauges com faixas coloridas |
| **Agua** | Nivel: indicador visual (cheio/medio/vazio) |
| **Controle** | Luz e bomba: estado (sem toggle — sem operador presente) |
| **Inventario** | Por lote: especie, quantidade, dias restantes, indicador verde/amarelo/vermelho |
| **Acoes** | Registrar venda/descarte + registrar entrada de novo lote |

#### Mapa completo de parametros por origem

| Dado | Fazenda | Expositor |
|------|:-------:|:---------:|
| Temperatura | Sim — grafico + alerta | Sim — gauge + alerta P0 |
| Umidade | Sim — grafico + alerta | Sim — gauge + alerta P1 |
| CO2 | Sim — grafico + alerta | Nao (ambiente aberto) |
| pH | Sim — gauge + tendencia | Nao (sem dosagem) |
| EC / Condutividade | Sim — gauge + tendencia | Nao |
| Nivel da agua | Sim — reservatorio | Sim — critico (P0 se vazio) |
| Controle de luz | Sim — toggle + automatico | Sim — apenas estado |
| Controle de bomba | Sim — toggle + automatico | Sim — apenas estado |
| Dosadora (4 bombas) | Sim | Nao |
| Camera | Sim | Opcional |
| Status online/offline | Sim | Sim — P0 se > 60 min |
| Lotes em cultivo | Sim — fases e progresso | Sim — contagem regressiva |
| Pipeline vs. meta | Sim — planejamento | Nao |
| Alerta de transferencia | Sim — lote pronto | Nao |
| Alerta de reposicao | Nao | Sim — X dias restantes |
| Historico 7d/30d | Sim — todos os parametros | Sim — temp e umidade |

---

## 15. Riscos e Licoes da Industria

Analise de empresas como Freight Farms (falencia em 2025), AeroFarms (reestruturacao 2023) e Infarm revela que **o risco principal nao e tecnico — e economico**.

### Riscos do Projeto

| Risco | Probabilidade | Impacto | Mitigacao via Software |
|-------|--------------|---------|----------------------|
| **Custo de energia alto** | Alta | Alto | Monitoramento de consumo por local, otimizacao de fotoperiodo por especie |
| **Perdas pos-colheita** | Media | Alto | Contagem regressiva e alertas P0 de fim de vida no expositor |
| **Expositores desassistidos offline** | Media | Alto | Alertas P0 de offline + autonomia do ESP32 (opera sem internet) |
| **Dificuldade de reposicao** | Media | Medio | Alertas P2 antecipados (5 dias antes do fim) |
| **Complexidade tecnica prematura** | Alta | Medio | Manter stack simples, so migrar quando houver gargalo real |

### Licao do Modelo Infarm

O modelo mais proximo ao Cultivee — unidades de cultivo distribuidas em pontos de venda, gerenciadas remotamente via cloud — foi validado operacionalmente pela Infarm. O diferencial que o software deve habilitar desde o inicio:
- **Metricas de custo por lote** (energia estimada + insumos) — nao apenas monitoramento tecnico
- **Gestao remota sem visita** — expositor deve funcionar e alertar autonomamente
- **Receitas padronizadas por especie** — padronizacao e o que permite escalar sem agronomista em cada ponto

---

## 16. Decisoes Pendentes

### Software (para Fases 1-4B)

| Status | Item | Observacao |
|--------|------|------------|
| [ ] | **Estrutura da tabela `lots`** | Campos: id, code, species_id, quantity, status, group_id, planted_at, transferred_at, closed_at, closed_reason |
| [ ] | **Estrutura da tabela `production_plans`** | Campos: species_id, meta_mensal, frequencia_semeadura, fator_perda, ativo |
| [x] | **Logica de deteccao de offline** | 10 min sem polling = offline P1; 60 min = P0 critico |
| [ ] | **Canal de notificacao** | Push PWA obrigatorio; email como backup para P1+ (definir provedor) |
| [ ] | **Capacidade dos expositores** | Fixo por tipo de expositor ou configuravel no app? |
| [x] | **Especies e seus tempos de ciclo** | Resolvido na Secao 5 — tabela com 6 especies e ciclos |
| [x] | **Ciclo de referencia do pipeline** | Alface Crespa: Germinacao 5d + Bercario 10d + Engorda 13d + Pre-colheita 2d + Expositor 7d = 37d |
| [x] | **Classificacao de alertas** | Sistema P0-P3 com cooldown definido na Fase 2 |
| [ ] | **Fator de perda inicial** | Usar 18% como padrao ate historico real disponivel (Fase 4) |
| [ ] | **Frequencia padrao de semeadura** | Semanal como padrao; configuravel por produtor |

### Hardware (para Modulos Futuros)

| Status | Item | Observacao |
|--------|------|------------|
| [ ] | **Sensores para clima** | DHT22 vs SHT30; MH-Z19 vs MH-Z14 (CO2) |
| [ ] | **Sensores para solucao** | Sensor pH analogico; sensor EC/TDS |
| [ ] | **Bomba peristaltica para dosadora** | Modelo e vazao |
| [x] | **Armazenamento de historico** | Manter SQLite por enquanto; migrar para PostgreSQL quando > 20 dispositivos |
| [x] | **Frequencia de envio de leituras** | Definido pela pesquisa: medias a cada 5 min; alerta imediato se limiar violado |
| [x] | **Logica cross-module da dosadora** | Via servidor (ja definido na Secao 8) |
| [ ] | **Estrategia de OTA** | Firmware dos modulos remotos — avaliar quando expositores estiverem em campo |
