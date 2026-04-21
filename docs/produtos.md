# Cultivee — Produtos

> Automação inteligente pro cultivo indoor, com controle na palma da mão.

Três módulos plug-and-play que transformam qualquer estufa, tenda de cultivo ou sistema hidropônico num ambiente monitorado e automatizado. Hardware de qualidade + aplicativo web pronto, sem mensalidade, sem servidor próprio, sem complicação.

---

## Por que Cultivee?

- **Nada de instalar aplicativo** — abre direto no navegador do celular/computador (PWA instalável como app nativo)
- **Funciona de qualquer lugar** — acompanhe e controle pelo 4G, mesmo longe de casa
- **Opera mesmo offline** — se a internet cair, o módulo continua automatizando sozinho
- **Notificações em tempo real** — push no celular + e-mail quando algo precisar de atenção
- **Atualizações automáticas** — novos recursos chegam sem você precisar mexer no hardware
- **Sem mensalidade** — pagou, é seu. Plataforma incluída.

---

## Linha de produtos

### 🌱 Cultivee Hidro — Automação Essencial

**Pra quem está começando ou tem um setup simples.**

Controla os 4 equipamentos fundamentais de qualquer cultivo indoor:

- 💡 **Iluminação** — horário ligado/desligado por fase do ciclo
- 💧 **Bomba d'água** — ciclos dia/noite independentes (ex: 15min on / 45min off)
- 🌬️ **Ventilação** — exaustor/cooler com horários programados
- 💨 **Aeração** — pedra porosa / bomba de ar com ciclos curtos

**Como funciona o sistema de fases:**

Você configura até **10 fases do cultivo** (germinação, vegetativo inicial, vegetativo, floração, etc.), cada uma com sua própria configuração de luz, irrigação, ventilação e aeração. O Hidro conta os dias sozinho e troca automaticamente pra fase seguinte. Nunca mais esquecer de ajustar o timer.

**Hardware incluso:**
- 1× Módulo ESP32 Cultivee Hidro (WiFi + relógio de tempo real)
- 1× Módulo de 4 relés (isolados opticamente, 10A cada)
- Fonte 5V/2A
- Gabinete plástico com ventilação passiva
- Cabos de ligação

**Indicado para:** cultivo caseiro, tendas de cultivo (grow tents), estufas pequenas, sistemas DWC e hidroponia básica.

---

### 🌿 Cultivee Hidro Farm — Premium

**Para quem leva o cultivo a sério.**

Tudo que o Hidro tem + controle de reservatório + sensores ambientais + alertas inteligentes.

**O que ele faz a mais:**

- **💧 Reposição automática de água**
  Duas boias (nível alto + nível baixo) + válvula solenoide monitorando o reservatório 24/7. Quando o nível baixa, abre a válvula. Quando enche, fecha. Nunca mais ficar sem água no meio da viagem.

- **🔔 Alertas de nível baixo**
  Se o reservatório não encher em X minutos (configurável de 1 a 120 min), você recebe:
  - 📱 Notificação push no celular (funciona mesmo com o app fechado)
  - 📧 E-mail com detalhes
  - ⏱️ Contador visual no dashboard mostrando há quanto tempo o nível está baixo

- **🌡️ Temperatura + umidade ambiente**
  Sensor DHT11 integrado reporta temp/umidade no dashboard em tempo real. Essencial pra detectar problemas antes das plantas sofrerem.

- **🔄 Bomba de homogeneização**
  Circuito separado pra misturar nutrientes. Liga manualmente quando precisar.

**Hardware incluso:**
- 1× Módulo ESP32 Cultivee Hidro Farm
- 1× Módulo de 8 relés (6 em uso, 2 livres pra expansão futura)
- 2× Boias tipo reed-switch (aço inox, uso alimentício)
- 1× Sensor DHT11 (temperatura e umidade)
- Fonte 5V/3A reforçada
- Gabinete maior com dissipação melhorada
- Cabos blindados pras boias

**Indicado para:** hidroponia NFT, sistemas de gotejamento, estufas comerciais de pequeno porte, cultivo de maior escala.

---

### 📷 Cultivee Cam — Monitoramento Visual

**Veja as plantas de qualquer lugar.**

Câmera IP standalone que tira fotos programadas e transmite ao vivo.

**O que ela faz:**

- **📸 Captura agendada**
  Tira fotos em intervalos configuráveis (de 1 minuto até 1 hora) direto pro servidor. Monta um timelapse natural do cultivo. Organização automática por pastas.

- **📺 Ao vivo**
  Stream de até 10 minutos pelo app. Útil pra conferir poda, transplante, visita à estufa remotamente.

- **🖼️ Galeria inteligente**
  Todas as fotos ficam organizadas no app. Selecione múltiplas, mova entre pastas, baixe ou apague em lote.

- **⚙️ Resolução + qualidade configuráveis**
  SVGA 800×600 pra uso padrão, UXGA 1600×1200 quando precisar de detalhe máximo (ex: identificar deficiência nutricional, detectar pragas). Qualidade JPEG ajustável de q4 (máxima) a q15 (leve).

**Hardware incluso:**
- 1× Módulo ESP32-WROVER + câmera OV2640 (2MP)
- Lente reposicionável
- Suporte universal (parafuso 1/4" — mesmo padrão de câmera fotográfica)
- Fonte 5V/2A
- Cabo USB longo pra flexibilidade de posicionamento

**Indicado para:** quem quer documentar o cultivo, detectar problemas visualmente, mostrar o progresso pra clientes (profissionais), ter tranquilidade em viagens.

---

## Funcionalidades da plataforma (incluídas em todos os módulos)

### 📱 App web universal
`app.cultivee.com.br` — funciona em qualquer dispositivo com navegador moderno (Android, iOS, Windows, Mac, Linux). Pode ser **instalado como app nativo** na tela inicial do celular (PWA).

### 🔔 Notificações inteligentes
- **Push** no celular (mesmo com o app fechado)
- **E-mail** com detalhes completos
- Cooldown inteligente (não spam você com a mesma informação)
- Horário configurável de quando disparar

### 🌐 Funciona offline
Se a internet cair, cada módulo continua automatizando sozinho com o relógio interno (RTC). Quando a conexão voltar, sincroniza tudo automaticamente.

Se a WiFi da sua casa sair do ar, você ainda pode acessar o módulo **localmente** conectando ao WiFi próprio dele (`Cultivee-Hidro`, `Cultivee-HidroFarm` ou `Cultivee-Cam`).

### 🔄 Atualizações remotas (OTA)
Novos recursos e correções chegam automaticamente, sem você precisar mexer no hardware, trocar cartão, ou abrir o gabinete. Lançamos uma feature nova, seu módulo atualiza sozinho.

### 🔐 Múltiplos módulos numa conta só
Compre quantos módulos quiser — todos aparecem num único dashboard. Reordene, organize em grupos, configure cada um separadamente. A ordem e configuração sincronizam entre celular e desktop.

### 📊 Telemetria de saúde
Cada módulo reporta estado do WiFi (sinal RSSI, quedas desde o último boot, última conexão) — útil pra você saber se precisa aproximar do roteador ou comprar um extensor.

---

## Quadro comparativo

| Recurso | Hidro | Hidro Farm | Cam |
|---|:---:|:---:|:---:|
| Controle de iluminação | ✅ | ✅ | — |
| Controle de bomba | ✅ | ✅ | — |
| Ventilação + aeração | ✅ | ✅ | — |
| Sistema de 10 fases | ✅ | ✅ | — |
| RTC (relógio offline) | ✅ | ✅ | — |
| Reposição automática de água | — | ✅ | — |
| Sensor temperatura + umidade | — | ✅ | — |
| Alertas push + e-mail | — | ✅ | — |
| Bomba de homogeneização | — | ✅ | — |
| Captura de fotos agendada | — | — | ✅ |
| Transmissão ao vivo | — | — | ✅ |
| Galeria com pastas | — | — | ✅ |
| App web incluído | ✅ | ✅ | ✅ |
| Atualizações remotas | ✅ | ✅ | ✅ |
| Modo offline local | ✅ | ✅ | ✅ |
| Notificações push | ✅ | ✅ | ✅ |

---

## Casos de uso reais

### 🏠 **Cultivo caseiro / hobby**
Combinação ideal: **1× Hidro + 1× Cam**
Você automatiza luz/bomba/ventilação pro dia a dia e tem a câmera pra conferir do trabalho, registrar a evolução e compartilhar com amigos.

### 🌱 **Hidroponia séria / cultivo comercial pequeno**
Combinação ideal: **1× Hidro Farm + 1× Cam**
Controle total do reservatório, alertas de nível, monitoramento ambiental + registro visual de todo o cultivo. Nunca mais perder planta por esquecimento de encher o tanque.

### 🏭 **Estufa / viveiro profissional**
Combinação ideal: **Múltiplos Hidro Farm + Múltiplos Cam**
Cada bancada tem seu módulo independente. Todos aparecem num dashboard único. Alertas individualizados por área.

### ✈️ **"Saí de férias e as plantas?"**
Qualquer combinação funciona. Você viaja tranquilo sabendo que:
- O módulo cuida do ciclo sozinho
- Se algo sair do esperado, você recebe alerta imediato
- Pode conferir visualmente a qualquer momento (se tiver Cam)

---

## Como funciona na prática

1. **Receba o módulo** já configurado de fábrica
2. **Conecte na tomada** e nos equipamentos (luz, bomba, etc.)
3. **Abra `app.cultivee.com.br`** no celular
4. **Siga o guia de pareamento** (~2 minutos):
   - Celular se conecta ao WiFi temporário do módulo
   - Você escolhe sua rede WiFi e coloca a senha
   - O módulo reinicia e aparece no app
5. **Configure suas fases de cultivo** (ou use os presets)
6. **Pronto.** O resto é automático.

---

## Garantia e suporte

- **Garantia:** 12 meses contra defeito de fabricação
- **Suporte por WhatsApp + e-mail** pra configuração inicial
- **Tutoriais em vídeo** (canal no YouTube)
- **Comunidade** no Telegram/Discord pra trocar experiências

---

## Especificações técnicas (resumo)

| | Hidro | Hidro Farm | Cam |
|---|---|---|---|
| Microcontrolador | ESP32-WROOM-32D | ESP32-WROOM-32D | ESP32-WROVER (com PSRAM) |
| WiFi | 2.4 GHz b/g/n | 2.4 GHz b/g/n | 2.4 GHz b/g/n |
| Relés | 4 canais (10A cada) | 6 canais (10A cada) | — |
| Sensores integrados | RTC | RTC + DHT11 + 2 boias | Câmera 2MP OV2640 |
| Alimentação | 5V / 2A | 5V / 3A | 5V / 2A |
| Consumo em standby | ~0.8 W | ~1.2 W | ~1.5 W |
| Memória firmware | 2 MB (OTA habilitado) | 2 MB (OTA habilitado) | 2 MB (OTA habilitado) |
| Dimensões aprox. | 15 × 10 × 5 cm | 18 × 12 × 6 cm | 6 × 4 × 3 cm (+ lente) |

---

## Perguntas frequentes

**Precisa de computador sempre ligado?**
Não. O servidor é nosso. Você acessa `app.cultivee.com.br` de qualquer dispositivo.

**Tem mensalidade?**
Não. Plataforma incluída por tempo ilimitado.

**E se minha internet cair?**
O módulo continua automatizando sozinho. Quando a internet voltar, tudo sincroniza.

**Posso acessar de fora de casa?**
Sim. De qualquer lugar com internet — funciona via 4G do celular perfeitamente.

**Posso controlar mais de um módulo?**
Sim, quantos quiser. Todos no mesmo app, mesma conta.

**E se o módulo der defeito?**
12 meses de garantia. Suporte técnico via WhatsApp. Em último caso, reposição.

**Minhas plantas vão aparecer pra outras pessoas?**
Não. Cada conta é privada, isolada. Só você vê seus módulos.

**Preciso ser programador pra usar?**
Não. É plug-and-play. Se você sabe usar um app de celular, sabe usar o Cultivee.

**Posso adicionar sensores depois?**
No Hidro Farm, sim. O gabinete tem slots livres pra sensores extras (pH, EC, CO₂) que estamos preparando pra lançamento futuro.

---

## Pronto pra começar?

Escolha o módulo ideal pro seu cultivo e receba em casa.

> **Entrega em todo o Brasil** · **Pagamento em até 12x** · **Suporte de verdade**

- **[Comprar Cultivee Hidro →]** `R$ XXX,XX`
- **[Comprar Cultivee Hidro Farm →]** `R$ XXX,XX`
- **[Comprar Cultivee Cam →]** `R$ XXX,XX`

**Combos com desconto:**
- **Hidro + Cam:** `R$ XXX,XX` (economize R$ XX)
- **Hidro Farm + Cam:** `R$ XXX,XX` (economize R$ XX)
- **Kit Completo (Hidro Farm + 2× Cam):** `R$ XXX,XX`

---

## Contato

- 📧 **E-mail:** contato@cultivee.com.br
- 📱 **WhatsApp:** (XX) XXXXX-XXXX
- 🌐 **Site:** cultivee.com.br
- 📺 **YouTube:** @cultivee
- 💬 **Telegram:** t.me/cultivee

---

*Cultivee — Tecnologia brasileira pro cultivo inteligente.*
