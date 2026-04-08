# PRD — Cultivee
## Product Requirements Document

**Versão:** 1.0
**Data:** 2026-03-31
**Status:** Em revisão
**Autor:** Mardoqueu Costa

---

## Índice

1. [Visão do Produto](#1-visão-do-produto)
2. [Problema e Oportunidade](#2-problema-e-oportunidade)
3. [Usuários — Personas](#3-usuários--personas)
4. [Objetivos e Métricas de Sucesso](#4-objetivos-e-métricas-de-sucesso)
5. [Escopo do Produto](#5-escopo-do-produto)
6. [User Stories](#6-user-stories)
7. [Requisitos Funcionais](#7-requisitos-funcionais)
8. [Requisitos Não-Funcionais](#8-requisitos-não-funcionais)
9. [Modelo de Dados](#9-modelo-de-dados)
10. [Fluxos de Navegação](#10-fluxos-de-navegação)
11. [Priorização MoSCoW](#11-priorização-moscow)
12. [Roadmap de Entregas](#12-roadmap-de-entregas)
13. [Critérios de Aceite](#13-critérios-de-aceite)
14. [Fora do Escopo](#14-fora-do-escopo)
15. [Riscos e Mitigações](#15-riscos-e-mitigações)
16. [Restrições técnicas](#16-restrições-técnicas)
17. [Referências](#17-referências)

---

## 1. Visão do Produto

### Declaração de Visão

> Cultivee é uma plataforma IoT em nuvem que conecta a produção de hortaliças em fazendas verticais indoor a uma rede de expositores de pequeno porte distribuídos em pontos urbanos, permitindo ao produtor gerenciar toda a cadeia — do plantio à venda — por um único aplicativo.

### O que é o Cultivee

Sistema composto por três pilares físico-digitais integrados:

| Pilar | Descrição |
|-------|-----------|
| **Fazenda Vertical Indoor** | Cultivo hidropônico centralizado. Hortaliças crescem de 20 a 40 dias em ambiente controlado (temperatura, umidade, CO2, pH, EC, iluminação, irrigação). |
| **Expositores Distribuídos** | Cabines de pequeno porte instaladas em prédios, lojas e comércios. Recebem as plantas próximas ao ponto ideal de colheita e as mantêm vivas por 5 a 10 dias no ponto de venda. |
| **Software em Nuvem (Cultivee)** | Plataforma web responsiva (PWA) que monitora, controla e integra fazenda e expositores via ESP32 com WiFi. Centraliza alertas, gestão de lotes, planejamento de produção e relatórios. |

### Hardware de Controle

**ESP32 com WiFi** — arquitetura modular onde cada ESP32 físico executa uma função específica (controle hidro, câmera, clima, solução nutritiva, dosadora). Um local (fazenda ou expositor) é a composição de vários ESP32s agrupados no app.

---

## 2. Problema e Oportunidade

### Problema Central

Produtores de hortaliças em ambientes urbanos enfrentam dois problemas críticos simultâneos:

**1. Perda pós-colheita elevada**
Plantas colhidas sem pedido firme deterioram rapidamente. A média de desperdício em pequenos produtores urbanos é de 20-35% do volume produzido. A causa raiz é a desconexão entre produção centralizada e demanda distribuída.

**2. Gestão manual e reativa**
Sem visibilidade em tempo real dos expositores (temperatura, nível de água, frescor das plantas), o produtor só descobre o problema quando recebe reclamação ou visita o local. Em expositores desassistidos, isso pode significar a perda de um lote inteiro.

### A Oportunidade

O modelo de **"planta viva no ponto de venda"** resolve o problema de frescor ao eliminar o intermediário e o armazenamento refrigerado — a planta continua crescendo no expositor até o momento da compra. O que faltava era o software para tornar esse modelo operacionalmente viável com múltiplos expositores distribuídos.

### Referência de Mercado

O modelo mais próximo foi validado pela Infarm (Agriculture-as-a-Service com mini-fazendas em supermercados gerenciadas remotamente por cloud). A falência de empresas como Freight Farms (2025) e AeroFarms (2023) demonstra que o risco principal não é tecnológico — é econômico (custo de energia e capital intensivo). O software deve incorporar visibilidade de custos desde o início.

---

## 3. Usuários — Personas

### Persona Principal: O Produtor Urbano

**Nome fictício:** Carlos, 38 anos
**Perfil:** Empreendedor que opera uma fazenda vertical indoor e uma rede de 3 a 10 expositores distribuídos em sua cidade. Não tem formação em TI. Usa smartphone como principal dispositivo. Fica na fazenda parte do dia e visita os expositores 1-2x por semana.

**Objetivos:**
- Saber, a qualquer momento, se tudo está funcionando sem precisar visitar cada local
- Nunca perder um lote por falta de água ou falha de equipamento num expositor desassistido
- Saber exatamente quando repor cada expositor (nem cedo demais, nem tarde demais)
- Atingir sua meta de produção mensal sem fazer contas manualmente

**Frustrações atuais (sem o Cultivee):**
- Descobre que o expositor ficou sem água só quando o parceiro liga reclamando
- Não sabe quantas plantas plantar por semana para manter a produção constante
- Perde tempo visitando expositores que estão funcionando normalmente

**Como usa o app:**
- Manhã: abre o app e confere se há alertas. Resposta esperada em < 30 segundos
- Semana: registra novo lote, verifica agenda semanal (semear, transferir, repor)
- Mês: confere relatório de produção vs. meta

**Dispositivos:** Smartphone (principal), computador (relatórios)

---

### Persona Secundária: O Parceiro do Expositor

**Nome fictício:** Ana, 45 anos
**Perfil:** Dona de padaria ou síndica de condomínio que cedeu espaço para o expositor. Não opera o sistema — apenas reporta problemas ao Carlos quando algo visivelmente errado acontece (planta murchando, expositor apagado).

**Papel no sistema:** Não tem acesso ao app. É o "sensor humano" de último recurso quando os alertas automáticos falham.

---

## 4. Objetivos e Métricas de Sucesso

### Objetivos do Produto

| Objetivo | Métrica | Meta |
|----------|---------|------|
| **Reduzir perda pós-colheita** | % de lotes encerrados como "descartado/perdido" | < 10% dos lotes |
| **Eliminar visitas desnecessárias** | Visitas a expositores sem ocorrência real | Redução de 60% vs. antes |
| **Garantir reposição a tempo** | Expositores com ruptura (zero plantas disponíveis) | < 5% do tempo |
| **Atingir meta de produção** | Produção real / meta mensal | >= 90% da meta |
| **Tempo de resposta a alertas críticos** | Tempo entre P0 disparado e ação do produtor | < 30 minutos |

### Métricas de Engajamento

| Métrica | Meta |
|---------|------|
| Sessões diárias no app | >= 1 por dia ativo de produção |
| Alertas P0/P1 por semana | < 5 na operação normal |
| Lotes com ciclo completo registrado | >= 80% dos lotes iniciados |

---

## 5. Escopo do Produto

### Dentro do Escopo

- Monitoramento em tempo real de sensores da fazenda e expositores via ESP32/WiFi
- Controle remoto de luz e bomba (ligar/desligar, configurar fases)
- Gestão de grupos de módulos (fazenda / expositor) com localização
- Sistema de alertas em 4 níveis (P0 a P3) com notificação push e e-mail
- Cadastro e rastreamento de lotes do plantio ao encerramento
- Receitas por espécie (parâmetros ideais por etapa de cultivo)
- Planejamento de produção com pipeline real vs. ideal e agenda semanal
- Relatórios de produção, perdas e ocupação de expositores
- Progressive Web App (PWA) responsiva — desktop e mobile
- Dashboard offline no próprio ESP32 (acesso local sem internet)
- Autenticação de usuários com conta individual

### Fora do Escopo (v1)

Ver Seção 14.

---

## 6. User Stories

### Módulo 1 — Visão Geral e Locais

| ID | Como... | Quero... | Para... |
|----|---------|---------|--------|
| US-01 | Produtor | Ver todos os meus locais (fazendas e expositores) em um único painel | Entender o status geral da operação em segundos |
| US-02 | Produtor | Ver o status de cada local (online, alerta, offline) representado visualmente | Identificar problemas sem ler texto |
| US-03 | Produtor | Criar um novo local (fazenda ou expositor) com nome e endereço | Organizar minha operação por localização física |
| US-04 | Produtor | Parear um ESP32 físico a um local existente usando um código curto | Adicionar hardware novo sem configuração técnica complexa |
| US-05 | Produtor | Remover um ESP32 de um local | Reorganizar ou substituir hardware |

### Módulo 2 — Alertas e Notificações

| ID | Como... | Quero... | Para... |
|----|---------|---------|--------|
| US-06 | Produtor | Receber notificação push imediata quando um expositor fica offline por mais de 60 minutos | Agir antes de perder as plantas |
| US-07 | Produtor | Receber alerta quando o nível de água de um expositor estiver crítico | Enviar alguém para reabastecer antes das plantas morrerem |
| US-08 | Produtor | Ver todos os alertas ativos agrupados por nível de urgência no topo do dashboard | Priorizar minhas ações sem precisar navegar por cada local |
| US-09 | Produtor | Marcar um alerta como resolvido | Manter o painel limpo e saber o que já foi tratado |
| US-10 | Produtor | Configurar as faixas ideais de temperatura, pH e EC para cada local | Personalizar os limiares de alerta conforme minha realidade |
| US-11 | Produtor | Não receber o mesmo alerta repetidamente enquanto o problema continua | Não ignorar alertas por fadiga de notificações |

### Módulo 3 — Inventário e Ciclo da Planta

| ID | Como... | Quero... | Para... |
|----|---------|---------|--------|
| US-12 | Produtor | Registrar um novo lote de plantio (espécie, quantidade, data) | Iniciar o rastreamento do ciclo de vida da planta |
| US-13 | Produtor | Ver quantos dias faltam para cada lote estar pronto para transferência | Planejar com antecedência a reposição dos expositores |
| US-14 | Produtor | Registrar a transferência de um lote da fazenda para um expositor específico | Saber exatamente o que está em cada expositor |
| US-15 | Produtor | Ver a contagem regressiva de dias restantes para cada lote no expositor | Saber quando cada expositor precisará ser reposto |
| US-16 | Produtor | Ver um indicador visual de frescor (verde/amarelo/vermelho) para cada lote | Priorizar a reposição sem calcular datas manualmente |
| US-17 | Produtor | Registrar o encerramento de um lote (vendido, descartado ou perdido) | Fechar o ciclo e alimentar as métricas de produção |
| US-18 | Produtor | Receber alerta quando um lote no expositor tiver menos de 3 dias restantes | Ter tempo para preparar a reposição |

### Módulo 4 — Planejamento de Produção

| ID | Como... | Quero... | Para... |
|----|---------|---------|--------|
| US-19 | Produtor | Definir minha meta de produção mensal por espécie | Dar ao sistema a referência para calcular o pipeline ideal |
| US-20 | Produtor | Ver quantas plantas devo ter em cada etapa (germinação, berçário, engorda, expositor) | Saber se meu pipeline está saudável ou em risco |
| US-21 | Produtor | Ver a previsão de produção do mês com base nos lotes atuais | Antecipar se vou atingir ou não a meta antes que seja tarde |
| US-22 | Produtor | Receber a agenda semanal de atividades (semear X, transferir Y) | Não precisar calcular quantas sementes plantar esta semana |
| US-23 | Produtor | Receber alerta quando alguma etapa do pipeline estiver abaixo do ideal | Corrigir o problema antes da produção cair |

### Módulo 5 — Controle e Monitoramento

| ID | Como... | Quero... | Para... |
|----|---------|---------|--------|
| US-24 | Produtor | Ver os valores atuais de temperatura, umidade e CO2 da fazenda | Confirmar que o ambiente está dentro da faixa ideal |
| US-25 | Produtor | Ver o pH, EC e nível do reservatório em tempo real | Saber se a solução nutritiva está adequada |
| US-26 | Produtor | Ligar e desligar luz e bomba remotamente | Agir em situações de emergência sem ir ao local |
| US-27 | Produtor | Ver gráficos históricos de todos os sensores (24h, 7d, 30d) | Identificar tendências e problemas recorrentes |
| US-28 | Produtor | Acionar dosagem manual de nutrientes ou ajuste de pH pela dosadora | Corrigir a solução nutritiva remotamente |
| US-29 | Produtor | Ver a imagem capturada pela câmera do local | Confirmar visualmente o estado das plantas sem visita física |

### Módulo 6 — Relatórios

| ID | Como... | Quero... | Para... |
|----|---------|---------|--------|
| US-30 | Produtor | Ver o histórico de produção mês a mês por espécie | Entender a evolução da minha operação ao longo do tempo |
| US-31 | Produtor | Ver a taxa de perda real calculada automaticamente | Calibrar meu planejamento com dados reais, não estimativas |
| US-32 | Produtor | Exportar os dados em CSV | Fazer análises externas em Excel ou compartilhar com parceiros |

---

## 7. Requisitos Funcionais

### RF-01 — Gestão de Locais (Groups)

| ID | Requisito |
|----|-----------|
| RF-01.1 | O sistema deve permitir criar grupos com nome, tipo (fazenda / expositor) e descrição de localização |
| RF-01.2 | O sistema deve exibir cartões de cada grupo no dashboard principal com: nome, tipo, status (online/offline/alerta), número de módulos, número de lotes ativos |
| RF-01.3 | O sistema deve calcular o status do grupo como: Online (todos os módulos reportaram nos últimos 10 min), Alerta (algum módulo offline ou com alerta ativo), Offline (nenhum módulo reportou nos últimos 60 min) |
| RF-01.4 | O sistema deve permitir parear um ESP32 a um grupo usando um código de 4 caracteres |
| RF-01.5 | O sistema deve permitir desparear um ESP32 de um grupo |
| RF-01.6 | O sistema deve permitir editar nome, tipo e localização de um grupo existente |

### RF-02 — Monitoramento de Sensores

| ID | Requisito |
|----|-----------|
| RF-02.1 | O sistema deve receber e armazenar leituras de temperatura, umidade e CO2 do módulo CLIMA a cada 5 minutos (média de leituras brutas do ESP32) |
| RF-02.2 | O sistema deve receber e armazenar leituras de pH, EC/TDS e nível do reservatório do módulo Solução a cada 5 minutos |
| RF-02.3 | O sistema deve exibir o valor atual de cada parâmetro com indicação visual (verde = faixa ideal, amarelo = atenção, vermelho = alerta) |
| RF-02.4 | O sistema deve exibir gráficos de série temporal para cada parâmetro nos períodos: últimas 24h, últimos 7 dias, últimos 30 dias |
| RF-02.5 | O sistema deve registrar `last_seen` para cada módulo a cada comunicação recebida |
| RF-02.6 | O ESP32 deve enviar leitura imediata ao servidor quando um valor ultrapassar o limiar configurado, sem aguardar o intervalo de 5 minutos |

### RF-03 — Controle Remoto

| ID | Requisito |
|----|-----------|
| RF-03.1 | O sistema deve permitir ligar e desligar luz e bomba do módulo HIDRO remotamente via toggle no app |
| RF-03.2 | O sistema deve permitir configurar as fases de cultivo do módulo HIDRO (duração, horário de luz, ciclo de bomba) por fase |
| RF-03.3 | O sistema deve permitir acionar cada bomba da dosadora individualmente (manual) ou configurar modo automático |
| RF-03.4 | No modo automático da dosadora, o servidor deve ler o pH e EC do módulo Solução do mesmo grupo e enviar comandos de dosagem quando fora da faixa configurada |
| RF-03.5 | Comandos enviados ao ESP32 devem ser confirmados e o app deve exibir confirmação de execução |

### RF-04 — Sistema de Alertas

| ID | Requisito |
|----|-----------|
| RF-04.1 | O sistema deve classificar alertas em 4 níveis: P0 (crítico), P1 (alto), P2 (operacional), P3 (informacional) |
| RF-04.2 | Alertas P0 devem gerar notificação push imediata via service worker da PWA |
| RF-04.3 | Alertas P1 devem gerar notificação push e e-mail de backup |
| RF-04.4 | Alertas P2 e P3 devem aparecer apenas no painel de alertas do dashboard |
| RF-04.5 | O sistema deve implementar cooldown: P0 não re-alerta mesma condição por 5 min; P1 por 60 min |
| RF-04.6 | O sistema deve consolidar alertas de módulos do mesmo grupo em um único alerta do grupo |
| RF-04.7 | O produtor deve poder marcar um alerta como resolvido, registrando timestamp e observação opcional |
| RF-04.8 | O sistema deve manter histórico completo de todos os alertas com: tipo, nível, timestamp, status (ativo/resolvido), tempo de resolução |

**Condições de alerta por nível:**

| Nível | Condição | Contexto |
|-------|----------|----------|
| P0 | Módulo offline > 60 min | Expositor (desassistido) |
| P0 | Temperatura > 28°C ou < 12°C | Qualquer local |
| P0 | Nível do reservatório = vazio | Qualquer local |
| P1 | Módulo offline > 10 min | Qualquer local |
| P1 | pH < 5,0 ou > 7,0 | Fazenda |
| P1 | EC < 0,8 ou > 2,5 mS/cm | Fazenda |
| P1 | Temperatura > 25°C ou < 15°C | Expositor |
| P1 | Umidade > 80% | Qualquer local |
| P1 | CO2 < 400 ppm ou > 1.500 ppm | Fazenda |
| P2 | Nível do reservatório = baixo | Qualquer local |
| P2 | Lote no expositor com <= 3 dias restantes | Expositor |
| P2 | Etapa do pipeline com < 70% do ideal | Fazenda |
| P3 | Lote pronto para transferência da fazenda | Fazenda |
| P3 | Agenda semanal disponível (semear, transferir) | Fazenda |
| P3 | Resumo diário da operação | Qualquer local |

### RF-05 — Gestão de Espécies e Receitas

| ID | Requisito |
|----|-----------|
| RF-05.1 | O sistema deve conter catálogo pré-configurado de 6 espécies: Alface Crespa, Alface Americana, Rucula, Cebolinha, Salsinha, Microverdes |
| RF-05.2 | Cada espécie deve ter configurados: dias na fazenda por etapa (germinação, berçário, engorda), dias no expositor, faixas ideais de pH, EC, temperatura e umidade por etapa |
| RF-05.3 | O sistema deve permitir ao produtor ajustar os valores das espécies a partir do catálogo base |

**Catálogo de espécies (valores padrão):**

| Espécie | Germinação | Berçário | Engorda | Pre-colheita | Expositor | Total |
|---------|-----------|---------|---------|-------------|---------|-------|
| Alface Crespa | 5 dias | 10 dias | 13 dias | 2 dias | 7 dias | 37 dias |
| Alface Americana | 5 dias | 12 dias | 16 dias | 2 dias | 7 dias | 42 dias |
| Rucula | 4 dias | 8 dias | 11 dias | 2 dias | 5 dias | 30 dias |
| Cebolinha | 7 dias | 14 dias | 18 dias | 2 dias | 8 dias | 49 dias |
| Salsinha | 7 dias | 14 dias | 18 dias | 2 dias | 8 dias | 49 dias |
| Microverdes | 3 dias | — | 8 dias | 1 dia | 3 dias | 15 dias |

### RF-06 — Gestão de Lotes

| ID | Requisito |
|----|-----------|
| RF-06.1 | O sistema deve permitir registrar um novo lote com: espécie, quantidade de sementes, data de semeadura, local de origem (fazenda) |
| RF-06.2 | O sistema deve gerar automaticamente um código único de rastreabilidade por lote (formato: `{SIG_ESPECIE}-{AAAAMMDD}-{SEQ}`, ex: `ALC-20260401-01`) |
| RF-06.3 | O sistema deve rastrear o lote nos estágios: Germinação → Berçário → Engorda → Pre-colheita → No Expositor → Encerrado |
| RF-06.4 | O sistema deve calcular automaticamente a data prevista de cada transição de estágio com base na espécie |
| RF-06.5 | O sistema deve permitir registrar a transferência de um lote da fazenda para um expositor específico, com data e quantidade real transferida |
| RF-06.6 | O sistema deve exibir contagem regressiva de dias restantes para cada lote no expositor |
| RF-06.7 | O sistema deve exibir indicador visual de frescor por lote: Verde (> 5 dias), Amarelo (3-5 dias), Vermelho (< 3 dias) |
| RF-06.8 | O sistema deve permitir encerrar um lote com motivo: Vendido, Descartado ou Perdido, registrando quantidade real encerrada |
| RF-06.9 | O sistema deve registrar todos os eventos do lote (CTEs) com timestamp: plantio, transições de estágio, transferência, encerramento |

### RF-07 — Planejamento de Produção

| ID | Requisito |
|----|-----------|
| RF-07.1 | O sistema deve permitir ao produtor definir uma meta de produção mensal por espécie |
| RF-07.2 | O sistema deve calcular o pipeline ideal para cada etapa usando a formula: `plantas_etapa = (meta_mensal / 30) × dias_etapa / (1 - fator_perda)` |
| RF-07.3 | O sistema deve exibir o comparativo real vs. ideal por etapa, com percentual de atingimento |
| RF-07.4 | O sistema deve calcular a previsão de produção do mes com base nos lotes ativos |
| RF-07.5 | O sistema deve gerar automaticamente a agenda semanal: quantas sementes plantar e quando transferir lotes para expositores |
| RF-07.6 | O fator de perda padrão inicial deve ser 18%. Após 3 ciclos completos registrados, o sistema deve calcular o fator real a partir do histórico |
| RF-07.7 | O sistema deve recalcular o pipeline quando o número de expositores mudar |

**Tabela de referência (Alface Crespa, meta 1.000 plantas/mes, fator perda 18%):**

| Etapa | Duração | Plantas ideal simultânea |
|-------|---------|--------------------------|
| Germinação | 5 dias | 205 |
| Berçário | 10 dias | 330 |
| Engorda | 13 dias | 429 |
| Pre-colheita | 2 dias | 66 |
| Expositores | 7 dias | 231 |
| **Total no sistema** | — | **~1.261** |
| Sementes a semear/semana | — | 287 |

### RF-08 — Câmera

| ID | Requisito |
|----|-----------|
| RF-08.1 | O sistema deve permitir solicitar uma captura de imagem do módulo CAM remotamente |
| RF-08.2 | O sistema deve armazenar e exibir a última imagem capturada por módulo |
| RF-08.3 | O sistema deve suportar live mode: ESP32 transmite frames continuamente ao servidor e o app exibe em pseudo-stream |

### RF-09 — Relatórios e Exportação

| ID | Requisito |
|----|-----------|
| RF-09.1 | O sistema deve exibir produção real vs. planejada por mês e por espécie |
| RF-09.2 | O sistema deve calcular automaticamente o fator de perda real por etapa (sementes semeadas vs. plantas colhidas) |
| RF-09.3 | O sistema deve exibir taxa de ocupação por expositor ao longo do tempo |
| RF-09.4 | O sistema deve exibir número de ciclos completos e tempo médio por espécie |
| RF-09.5 | O sistema deve permitir exportar todos os dados de lotes em formato CSV |

### RF-10 — Autenticação e Conta

| ID | Requisito |
|----|-----------|
| RF-10.1 | O sistema deve suportar registro de conta com nome, e-mail e senha |
| RF-10.2 | O sistema deve autenticar via token JWT com validade de 30 dias |
| RF-10.3 | Cada usuário vê apenas seus próprios módulos, grupos e lotes |
| RF-10.4 | O sistema deve suportar logout que invalida o token no servidor |

---

## 8. Requisitos Não-Funcionais

### RNF-01 — Disponibilidade

| ID | Requisito |
|----|-----------|
| RNF-01.1 | A plataforma deve estar disponível 99% do tempo (downtime tolerado: ~7h/mes) |
| RNF-01.2 | O ESP32 deve continuar operando autonomamente (fotoperíodo, irrigação) mesmo sem conectividade com o servidor |
| RNF-01.3 | O ESP32 deve manter dashboard local acessível via WiFi local mesmo sem internet |
| RNF-01.4 | O ESP32 deve tentar reconectar ao servidor continuamente após queda de WiFi |

### RNF-02 — Performance

| ID | Requisito |
|----|-----------|
| RNF-02.1 | O dashboard principal deve carregar em menos de 3 segundos em conexão 4G |
| RNF-02.2 | O status dos módulos no dashboard deve ser atualizado a cada 30 segundos sem recarregar a página |
| RNF-02.3 | Notificações push devem ser entregues em menos de 60 segundos após o evento |
| RNF-02.4 | O sistema deve suportar até 50 ESP32s simultâneos sem degradação de performance |

### RNF-03 — Usabilidade

| ID | Requisito |
|----|-----------|
| RNF-03.1 | O app deve ser acessível em smartphone (telas 320px+) e desktop sem perda de funcionalidade |
| RNF-03.2 | O produtor deve conseguir verificar o status de todos os seus locais em menos de 30 segundos após abrir o app |
| RNF-03.3 | O app deve funcionar como PWA instalável no smartphone (sem loja de aplicativos) |
| RNF-03.4 | O app deve exibir estado de carregamento claro enquanto aguarda dados do servidor |
| RNF-03.5 | Ações críticas (transferência de lote, encerramento) devem pedir confirmação antes de executar |

### RNF-04 — Segurança

| ID | Requisito |
|----|-----------|
| RNF-04.1 | Toda comunicação entre browser e servidor deve usar HTTPS (TLS) |
| RNF-04.2 | Tokens JWT devem ser invalidados no logout |
| RNF-04.3 | ESP32s comunicam com o servidor via HTTP (sem HTTPS obrigatório em v1 — rede local ou VPN) |
| RNF-04.4 | Endpoints da API que retornam dados do usuário exigem token válido |
| RNF-04.5 | Upload de imagens da câmera só é aceito de ESP32 com chip_id registrado e vinculado ao usuário |

### RNF-05 — Manutenção e Escalabilidade

| ID | Requisito |
|----|-----------|
| RNF-05.1 | Adicionar um novo tipo de módulo ESP32 não deve exigir alteração nos módulos já existentes |
| RNF-05.2 | O sistema deve armazenar histórico de leituras de sensores por no mínimo 90 dias |
| RNF-05.3 | O deploy de nova versão do servidor não deve causar perda de dados |
| RNF-05.4 | Logs de erro do servidor devem ser persistidos para depuração |

---

## 9. Modelo de Dados

### Entidades Principais

```
users
├── id
├── name
├── email (unique)
├── password_hash
└── created_at

groups
├── id
├── user_id (FK users)
├── name
├── type           ENUM('fazenda', 'expositor', 'estufa', 'avulso')
├── location       TEXT (descrição de endereço)
└── created_at

modules
├── id
├── chip_id        VARCHAR (identificador único do ESP32)
├── user_id        (FK users — após pareamento)
├── group_id       (FK groups — após vinculação ao grupo)
├── type           VARCHAR ('hidro', 'cam', 'clima', 'solucao', 'dosadora')
├── capabilities   JSON
├── ctrl_data      JSON (último status recebido)
├── last_seen      DATETIME
├── ip_address     VARCHAR
└── paired_at      DATETIME

species
├── id
├── name           VARCHAR ('Alface Crespa', etc.)
├── days_germinacao
├── days_bercario
├── days_engorda
├── days_pre_colheita
├── days_expositor
├── ph_min, ph_max
├── ec_min, ec_max
├── temp_min, temp_max
├── humidity_min, humidity_max
└── is_custom      BOOLEAN (true se editada pelo usuário)

lots
├── id
├── code           VARCHAR (ex: ALC-20260401-01)
├── user_id        (FK users)
├── species_id     (FK species)
├── origin_group_id    (FK groups — fazenda de origem)
├── current_group_id   (FK groups — localização atual)
├── quantity_seeded    INTEGER
├── quantity_current   INTEGER (atualizado em cada transição)
├── status         ENUM('germinação','bercario','engorda','pre_colheita','expositor','encerrado')
├── planted_at     DATETIME
├── transferred_at DATETIME
├── closed_at      DATETIME
├── closed_reason  ENUM('vendido','descartado','perdido')
└── notes          TEXT

lot_events
├── id
├── lot_id         (FK lots)
├── event_type     ENUM('plantio','transicao','transferencia','encerramento')
├── from_status    VARCHAR
├── to_status      VARCHAR
├── from_group_id  (FK groups)
├── to_group_id    (FK groups)
├── quantity       INTEGER
├── notes          TEXT
└── created_at     DATETIME

production_plans
├── id
├── user_id        (FK users)
├── species_id     (FK species)
├── monthly_target INTEGER
├── seeding_frequency ENUM('diaria','semanal','quinzenal')
├── loss_factor    FLOAT (default 0.18)
├── active         BOOLEAN
└── created_at     DATETIME

alerts
├── id
├── user_id        (FK users)
├── group_id       (FK groups — nullable)
├── module_id      (FK modules — nullable)
├── lot_id         (FK lots — nullable)
├── level          ENUM('P0','P1','P2','P3')
├── type           VARCHAR (ex: 'module_offline', 'ph_out_of_range', etc.)
├── message        TEXT
├── status         ENUM('ativo','resolvido')
├── last_alerted_at    DATETIME (para cooldown)
├── resolved_at    DATETIME
├── resolution_note TEXT
└── created_at     DATETIME

sensor_readings
├── id
├── module_id      (FK modules)
├── timestamp      DATETIME
├── payload        JSON (todos os valores do sensor naquela leitura)
└── [índices em module_id + timestamp para queries de serie temporal]
```

---

## 10. Fluxos de Navegação

### Estrutura de Telas

```
LOGIN / REGISTRO
      │
      ▼
DASHBOARD PRINCIPAL
├── [Painel de Alertas] ← P0 e P1 sempre visíveis
├── [Card Local 1: Fazenda "Rack 1"]
├── [Card Local 2: Expositor "Padaria"]
├── [Card Local N: ...]
└── [+ Adicionar Local]
      │
      ├── Toque no card → TELA DO LOCAL
      │     ├── [Aba: Status]       ← módulos, leituras atuais, câmera
      │     ├── [Aba: Lotes]        ← inventário, contagem regressiva
      │     ├── [Aba: Controle]     ← toggles, fases, dosadora
      │     └── [Aba: Histórico]    ← gráficos de série temporal
      │
      ├── Toque em "+ Adicionar Local" → WIZARD CRIAR LOCAL
      │     ├── Passo 1: Nome e tipo (fazenda/expositor)
      │     ├── Passo 2: Localização (texto livre)
      │     └── Passo 3: Confirmar
      │
      └── Menu lateral → OUTRAS SEÇÕES
            ├── Planejamento de Produção
            │     ├── Pipeline real vs. ideal (por espécie)
            │     ├── Previsão do mês
            │     └── Agenda da semana
            ├── Relatórios
            │     ├── Produção por mês
            │     ├── Perdas por etapa
            │     └── Exportar CSV
            └── Configurações
                  ├── Espécies e receitas
                  ├── Metas de produção
                  └── Notificações
```

### Fluxo Principal: Dia a Dia do Produtor

```
1. Abre o app
      │
      ▼
2. Dashboard carrega — vê alertas ativos e status dos locais
      │
      ├── Há alertas P0/P1? → Trata o alerta → Marca como resolvido
      │
      ├── Há expositores com lote < 3 dias? → Prepara reposição
      │
      └── Confere agenda da semana
            ├── Tem lote para semear hoje? → Registra novo lote
            ├── Tem transferência pendente? → Registra transferência
            └── Tudo ok → Fecha o app
```

### Fluxo: Registro de Transferência Fazenda → Expositor

```
Tela do Local (Fazenda) → Aba Lotes
      │
      ├── Lote "ALC-0305" — Status: Pre-colheita
      │     └── Botão [Transferir para Expositor]
      │
      ▼
Modal de Transferência
├── Selecionar expositor destino
├── Informar quantidade transferida
└── Confirmar
      │
      ▼
Sistema registra:
- lot_event: transferência, com timestamp
- lots.status → 'expositor'
- lots.transferred_at = agora
- lots.current_group_id = expositor selecionado
      │
      ▼
Alerta P3 disparado: "Lote ALC-0305 transferido para Padaria Centro"
```

---

## 11. Priorização MoSCoW

### Must Have (deve ter no MVP)

| ID | Funcionalidade |
|----|----------------|
| US-01, 02 | Dashboard com status visual dos locais |
| US-03, 04 | Criar local e parear ESP32 |
| US-06, 07 | Alertas P0 (offline e nível crítico de água) com push |
| US-08 | Painel de alertas no dashboard |
| US-12 | Registrar lote de plantio |
| US-14 | Registrar transferência fazenda → expositor |
| US-15, 16 | Contagem regressiva e indicador de frescor |
| US-17 | Encerrar lote (vendido/descartado/perdido) |
| US-18 | Alerta de reposição (< 3 dias) |
| US-24 | Ver leituras atuais de sensores |
| US-26 | Controle remoto de luz e bomba |
| RF-10 | Autenticação com conta individual |

### Should Have (deve ter após MVP)

| ID | Funcionalidade |
|----|----------------|
| US-09 | Marcar alerta como resolvido |
| US-10 | Configurar faixas de alerta por local |
| US-11 | Cooldown anti-fatigue de alertas |
| US-13 | Data prevista de transição de estágio |
| US-19, 20 | Planejamento de produção (meta + pipeline ideal) |
| US-21, 22 | Previsão do mês + agenda semanal |
| US-27 | Gráficos históricos de sensores |
| US-28 | Controle da dosadora |
| US-29 | Câmera (captura e live mode) |

### Could Have (pode ter em versão futura)

| ID | Funcionalidade |
|----|----------------|
| US-23 | Alertas de desvio de pipeline (P2) |
| US-30, 31 | Relatórios de produção e perdas |
| US-32 | Exportação CSV |
| RF-05.3 | Edição de espécies pelo usuário |
| RF-07.6 | Cálculo automático do fator de perda real |

### Won't Have (fora do escopo v1)

Ver Seção 14.

---

## 12. Roadmap de Entregas

**Horizonte:** 6 meses. Ao final, 1 fazenda vertical e 1 expositor operando em produção — hardware e software integrados.
Cada mês é um resultado verificável no mundo real, não apenas no código.

**Visão geral:**

| Mês | O produtor passa a conseguir... | Hardware instalado |
|-----|--------------------------------|--------------------|
| 1 | Controlar a farm pelo celular | HIDRO na farm |
| 2 | Ver e controlar o expositor também | HIDRO no expositor |
| 3 | Rastrear cada bandeja da farm até o expositor | — |
| 4 | Monitorar temperatura, CO2, pH e EC da farm | CLIMA + Solução na farm |
| 5 | Planejar produção e prever o mês seguinte | — |
| 6 | Operar tudo integrado sem suporte técnico | Calibração final |

---

### Mês 1 — Fundação e Controle

1. Instalação e validação do módulo HIDRO em campo (72h)
2. Automação do reservatório com corte automático da bomba
3. Dashboard com locais, módulos e controle remoto
4. Alertas P0/P1 de nível do reservatório via push

**Critério de aceite:** Módulo HIDRO opera 72h sem travamentos. Toggle de luz muda estado do relé em < 30s. Ao esvaziar reservatório, bomba desliga e push chega em < 60s.

---

### Mês 2 — Rede Distribuída e Vigilância

1. Instalação e pareamento do módulo HIDRO no expositor
2. Validação em rede WiFi externa (ambiente do parceiro)
3. Sistema de alertas P0-P3 com push notification e e-mail
4. Detecção de offline para todos os locais cadastrados

**Critério de aceite:** Farm e expositor visíveis no dashboard. Ao desconectar o ESP32 do expositor por 61 min, push chega em < 60s.

---

### Mês 3 — Rastreabilidade e Ciclo de Produção

1. Catálogo de espécies com parâmetros e duração de ciclo
2. Registro e progressão automática de lotes na farm
3. Transferência de lotes farm → expositor com rastreamento
4. Contagem regressiva e alertas de reposição no expositor

**Critério de aceite:** Lote criado na farm, transferido ao expositor — app exibe contagem regressiva correta e dispara P2 no dia certo.

---

### Mês 4 — Instrumentação Ambiental

1. Instalação do módulo CLIMA (temperatura, umidade, CO2)
2. Instalação do módulo Solução (pH, EC) com calibração inicial
3. Histórico de leituras e gráficos de tendência 24h
4. Alertas sensoriais por desvio de faixa configurada

**Critério de aceite:** Dashboard exibe temperatura, CO2, pH e EC da farm em tempo real. Ao simular pH fora da faixa por 30 min, alerta P1 é disparado.

> **Nota:** Módulo DOSADORA fora do escopo deste plano. Ver Seção 14.

---

### Mês 5 — Planejamento e Inteligência Operacional

1. Plano de produção com pipeline ideal por espécie
2. Agenda semanal automática de semeadura e transferências
3. Relatórios de produção real vs. planejado por espécie
4. Alertas de pipeline por etapa abaixo de 70% do ideal

**Critério de aceite:** Com meta de 1.000 plantas/mês, sistema calcula pipeline de 5 estágios e gera agenda semanal automática. Produção real vs. planejada visível no histórico.

---

### Mês 6 — Estabilização e Autonomia Operacional

1. Calibração dos sensores com base em dados reais de campo
2. Revisão de receitas de cultivo com parâmetros observados
3. Documentação operacional e ajustes de UX
4. Backup automatizado e avaliação de escala do sistema

**Critério de aceite:** 1 fazenda vertical e 1 expositor operando com todos os módulos online, lotes rastreados, alertas funcionando e histórico de produção disponível. Produtor opera sem suporte por 30 dias consecutivos.

---

## 13. Critérios de Aceite

### CA-01 — Dashboard Principal

- [ ] Ao abrir o app, o dashboard exibe todos os grupos do usuário em menos de 3 segundos
- [ ] Cada cartão exibe: nome, tipo, status (badge colorido), número de módulos, número de lotes ativos
- [ ] Status "Online" = verde; "Alerta" = amarelo; "Offline" = vermelho
- [ ] Clicar em um cartão navega para a tela do local correspondente

### CA-02 — Detecção de Offline

- [ ] Se um ESP32 não faz polling por 10 minutos, seu status no app muda para offline (P1)
- [ ] Se um ESP32 não faz polling por 60 minutos em um expositor, um alerta P0 é gerado
- [ ] O alerta P0 dispara push notification no dispositivo do usuário em menos de 60 segundos
- [ ] O mesmo alerta não é re-disparado dentro de 5 minutos (cooldown)

### CA-03 — Ciclo Completo de um Lote

- [ ] Produtor cria lote: espécie Alface Crespa, 300 sementes, data hoje
- [ ] Sistema gera código `ALC-{DATA}-01` e calcula data prevista de cada estágio
- [ ] Após 30 dias, sistema exibe lote em status "Pre-colheita"
- [ ] Produtor registra transferencia para expositor "Padaria" com 240 plantas
- [ ] Sistema exibe no card da Padaria: "Alface Crespa — dia 1/7"
- [ ] Após 4 dias, indicador muda para amarelo ("dia 4/7")
- [ ] No dia 4, sistema dispara alerta P2: "Repor em 3 dias"
- [ ] Produtor registra encerramento: Vendido, 230 plantas
- [ ] Sistema atualiza histórico do lote e recalcula fator de perda

### CA-04 — Planejamento de Produção

- [ ] Produtor define meta: 1.000 plantas/mes, Alface Crespa, semeadura semanal
- [ ] Sistema exibe pipeline ideal: Germinação 205, Berçário 330, Engorda 429, Expositores 231
- [ ] Sistema exibe agenda: "Semear 287 sementes esta semana"
- [ ] Com apenas 200 plantas em Berçário (vs. 330 ideal), sistema exibe barra amarela e alerta P2
- [ ] Produção prevista é calculada com base nos lotes reais cadastrados

### CA-05 — Controle Remoto

- [ ] Produtor toca toggle de luz no app → luz do ESP32 muda de estado em menos de 30 segundos
- [ ] App exibe confirmação visual após execução do comando
- [ ] Se o ESP32 estiver offline, o app exibe mensagem de erro claro em vez de silêncio

---

## 14. Fora do Escopo (v1)

| Item | Justificativa |
|------|---------------|
| **Módulo DOSADORA** | Módulo de dosagem automática de nutrientes (pH-up, pH-down, nutriente A/B). Fora do escopo do plano de 6 meses por restrição de tempo dedicado. Será avaliado após estabilização do Solução. |
| **App nativo (iOS/Android)** | PWA atende o caso de uso. App nativo requer publicação em loja e custo de manutenção. |
| **Multiusuário por conta** | Produtor opera sozinho em v1. Compartilhamento de acesso planejado para v2. |
| **Marketplace / e-commerce** | Venda direta pelo app. O Cultivee gerencia produção, não transações comerciais. |
| **MQTT** | HTTP polling é suficiente para < 50 dispositivos. Migrar quando latência for problema real. |
| **ML preditivo / anomalias** | Requer histórico de dados que não existe na v1. |
| **mTLS / Secure Boot ESP32** | Adicionar quando escala de expositores justificar o custo de gestão de certificados. |
| **Rastreabilidade FSMA 204 completa** | Conformidade FDA/EUA para 2028. A estrutura de dados já suporta — a geração de relatórios regulatórios é fase futura. |
| **Controle de estoque de insumos** | Sementes, nutrientes, substratos. Fora do escopo de v1. |
| **Integração com ERPs ou sistemas de venda** | Fora do escopo de v1. |
| **Pagamento de assinatura / billing** | Cultivee é de uso interno em v1. Monetização é planejamento separado. |

---

## 15. Riscos e Mitigações

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| **Expositor offline sem detecção rápida** | Média | Alto | Alertas P0 com push + cooldown anti-fatigue. ESP32 opera localmente sem internet. |
| **Perda de lotes por falta de água** | Média | Alto | Sensor de nível como P0 crítico. Agenda de verificação manual como backup. |
| **Custo de energia tornando o modelo inviável** | Alta | Alto | Monitoramento de consumo por local (fase futura). Otimização de fotoperíodo por espécie. |
| **Fator de perda subestimado no planejamento** | Alta | Médio | Sistema usa 18% como padrão e calibra automaticamente após 3 ciclos reais. |
| **WiFi do expositor cair por tempo prolongado** | Média | Alto | ESP32 opera autonomamente (luz e bomba por timer local). Alerta P0 quando voltar. |
| **Complexidade técnica prematura** | Alta | Médio | Manter stack atual (Flask + SQLite + PWA vanilla). Migrar tecnologia só com gargalo real. |

---

## 16. Restrições técnicas

### Stack Atual (não alterar sem gargalo real)

| Camada | Tecnologia | Restrição |
|--------|-----------|-----------|
| Firmware | Arduino framework (C++) | Não migrar para ESP-IDF/FreeRTOS em v1 |
| Backend | Flask (Python) | Não substituir por Node.js sem razão técnica |
| Banco | SQLite | Migrar para PostgreSQL apenas quando > 20 dispositivos ou queries lentas |
| Frontend | PWA vanilla (JS puro, sem frameworks) | Não adicionar React/Vue — quebra o dashboard offline do ESP32 |
| Comunicação | HTTP polling | Migrar para MQTT apenas quando latência de comandos for problema operacional |
| Infra | Docker + Traefik + VPS | Manter. Kubernetes é overkill para o volume atual. |

### Roadmap Técnico por Volume de Dispositivos

| Volume | Gatilho | Ação |
|--------|---------|------|
| < 20 dispositivos | — | Stack atual (Flask + SQLite + HTTP polling) |
| 20–50 dispositivos | Latência de comandos > 10s | Migrar SQLite → PostgreSQL; avaliar Mosquitto/MQTT |
| > 50 dispositivos | Gestão de frota necessária | EMQX cluster, TimescaleDB, OTA em massa |

---

## 17. Referências

| Fonte | Conteúdo |
|-------|---------|
| Cornell CEA Lettuce Handbook | Parâmetros ótimos de cultivo para folhosas em CEA |
| University of Florida Extension | Valores de referência pH, EC e temperatura para hortaliças |
| Infarm (modelo distribuido) | Referência de operação de mini-fazendas em pontos de venda via cloud |
| Frontiers in Plant Science (2025) | Arquitetura IoT de 4 camadas para agricultura indoor |
| MDPI Sensors (2020) | Microsserviço de IoT agricola: Ingestão, Consulta, Alerta, OTA |
| FSMA 204 (FDA) | Food Traceability Rule — referência para rastreabilidade futura |

---

*Documento gerado a partir do planejamento técnico acumulado do projeto Cultivee.*
*Para detalhes de implementação, arquitetura de firmware e padrões de código, consultar `PLANO-VISAO-GERAL-SOFTWARE.md` e `CLAUDE.md`.*
