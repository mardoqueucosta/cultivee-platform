# Otimização completa de captura de imagem e vídeo no ESP32-WROVER-CAM

O ESP32-WROVER-CAM é capaz de atingir **12–25 FPS em VGA** e **até 50 FPS em QQVGA** com configuração adequada, mas extrair esse desempenho exige domínio de hardware, memória PSRAM, parâmetros do sensor e rede. Este guia técnico cobre todas as dimensões críticas — da pinagem ao streaming MJPEG, do gerenciamento térmico ao processamento on-device — com dados quantitativos, código de referência e soluções comprovadas pela comunidade. A diferença entre um sistema que entrega 2 FPS com imagens corrompidas e outro que transmite vídeo fluido a 15+ FPS reside quase inteiramente na configuração de software e na qualidade da alimentação.

---

## 1. Pinagem, XCLK e configuração de hardware

### Mapeamento de pinos por modelo

A pinagem varia entre placas e é a primeira fonte de erros de inicialização. As duas placas mais populares usam configurações distintas:

| Sinal | ESP32-WROVER-KIT (Freenove) | AI-Thinker ESP32-CAM |
|-------|---------------------------|---------------------|
| D0–D7 | 4, 5, 18, 19, 36, 39, 34, 35 | 5, 18, 19, 21, 36, 39, 34, 35 |
| VSYNC / HREF / PCLK | 25 / 23 / 22 | 25 / 23 / 22 |
| XCLK | **GPIO 21** | **GPIO 0** (strapping pin!) |
| SIOD / SIOC | 26 / 27 | 26 / 27 |
| PWDN | -1 (não conectado) | **GPIO 32** (ativo HIGH) |
| RESET | -1 (software) | -1 |

**GPIO 16 e GPIO 17 são reservados para PSRAM no ESP32-WROVER** — usá-los para qualquer outro propósito corrompe a PSRAM e causa Guru Meditation Errors. O UART2 (que usa esses pinos por padrão) deve ser remapeado: `Serial2.begin(115200, SERIAL_8N1, 14, 12)`.

A AI-Thinker usa GPIO 0 para XCLK, que é um strapping pin — deve estar em LOW durante o upload de firmware, o que complica a programação. O Freenove WROVER-CAM usa GPIO 21 para XCLK (sem conflito) e inclui programador USB integrado, eliminando a necessidade de FTDI externo.

### Frequência XCLK e impacto no desempenho

O XCLK é o clock mestre fornecido pelo ESP32 ao sensor de câmera. Sua frequência controla diretamente o timing interno do sensor e afeta tanto o frame rate quanto a estabilidade da imagem:

| XCLK | Comportamento | Recomendação |
|------|--------------|--------------|
| **20 MHz** | Padrão em todos os exemplos Espressif. Melhor equilíbrio estabilidade/FPS | ✅ Recomendado para uso geral |
| **10 MHz** | Ativa o clock doubler interno do OV2640 em modo JPEG (efetivamente 20 MHz PCLK) | ✅ Experimental, pode dobrar FPS |
| **8 MHz** | Muito estável, FPS reduzido. Mínimo do ESPHome | Para captura low-power |
| **16 MHz** | Pode causar artefatos em alguns módulos OV2640 | ⚠️ Não recomendado no ESP32 original |
| **24 MHz** | FPS mais alto possível, mas glitches em JPEG | ⚠️ Apenas para testes |

**Descoberta crítica sobre WiFi:** A frequência XCLK gera EMI que interfere diretamente no WiFi. Testes documentados mostram que a **20 MHz o ping médio sobe para 1435 ms com 50 timeouts em 60**, enquanto a **8 MHz o ping cai para 35 ms com zero timeouts**. Para aplicações que dependem de WiFi estável, considere XCLK de 8–10 MHz.

O ESP32 original tem limite de **8 MHz no PCLK** (pixel clock) via interface I2S. O ESP32-S3, com interface LCD_CAM dedicada, suporta até **40 MHz PCLK**, resultando em desempenho significativamente superior.

### Alimentação e integridade de sinal

O módulo deve ser alimentado a **5V via pino VIN** (não 3.3V). O consumo durante WiFi TX + captura pode atingir **310–500 mA**, e alimentação insuficiente é a causa #1 de brownouts e imagens corrompidas. Recomendações: fonte 5V/2A, capacitor de **100–470 µF** entre VCC e GND, cabos USB curtos e grossos. O regulador AMS1117 presente nas placas AI-Thinker dissipa calor significativo (0.5W a 300 mA) e tem corrente quiescente de 5–10 mA — um gargalo para projetos a bateria.

---

## 2. PSRAM: o recurso mais subestimado e crítico

### Configuração e modos de operação

A PSRAM externa (4 MB no ESP32-WROVER-E) é absolutamente necessária para resoluções acima de CIF e para qualquer formato não-JPEG em resoluções úteis. Um único frame UXGA em RGB565 ocupa **3.75 MB** — impossível sem PSRAM.

Configurações essenciais no ESP-IDF menuconfig:

| Flag | Valor recomendado | Impacto |
|------|-------------------|---------|
| `CONFIG_SPIRAM` | `y` | Habilita PSRAM |
| `CONFIG_SPIRAM_SPEED` | **80 MHz** | Dobra o throughput vs 40 MHz |
| `CONFIG_SPIRAM_MODE` | QIO | Máximo throughput (quad I/O) |
| `CONFIG_SPIRAM_USE_CAPS_ALLOC` | `y` | Permite alocação seletiva via `heap_caps_malloc()` |
| `CONFIG_SPIRAM_MEMTEST` | Desabilitar | Economiza ~1 segundo no boot |

A **80 MHz** a PSRAM oferece ~40 MB/s teórico e ~20 MB/s prático. A 40 MHz, esses valores caem pela metade. Na prática, a latência de acesso à PSRAM é de **10–20 ciclos de CPU** contra 1–2 ciclos para SRAM interna. O cache de 32 KB mantém dados <16 KB em velocidade rápida; acima disso, a performance degrada para a velocidade bruta da PSRAM.

### Alocação de frame buffers e fb_count

O parâmetro `fb_count` determina quantos buffers de frame são pré-alocados na inicialização:

**`fb_count = 1`**: modo bloqueante. O driver espera VSYNC, inicia DMA, captura um frame, para. Mais controle, menor FPS. Indicado para captura única e placas sem PSRAM.

**`fb_count = 2`**: double-buffering. I2S funciona em modo contínuo — enquanto um buffer é processado pela aplicação, o outro está sendo preenchido por DMA. **Dobra o frame rate** efetivamente. Padrão recomendado para streaming.

**`fb_count ≥ 3`**: triple-buffering. Útil quando há três consumidores (captura → processamento → transmissão) ou para gravação em burst no cartão SD. Retornos decrescentes após 2 no ESP32 original.

O tamanho de cada buffer depende da resolução e da qualidade JPEG configurada na inicialização. O driver usa tiers de compressão:

| jpeg_quality na init | Ratio de compressão | Buffer UXGA | Buffer VGA |
|---------------------|---------------------|-------------|------------|
| 0–5 | 5:1 | ~960 KB | ~122 KB |
| 6–10 | 10:1 | ~384 KB | ~49 KB |
| 11–63 | 20:1 | ~240 KB | ~30 KB |

Com `fb_count=2` e quality 6–10 em UXGA, são necessários **768 KB de PSRAM** apenas para buffers. Com quality 0–5, são 1.92 MB. A PSRAM de 4 MB é compartilhada entre buffers de câmera (~750 KB–1.9 MB), buffers WiFi (~30–50 KB), stack TCP/IP e código da aplicação, restando tipicamente **2–3 MB** para uso geral.

### Fragmentação e monitoramento

Alocações e desalocações repetidas fragmentam a PSRAM. A prevenção mais eficaz: **alocar buffers de câmera uma única vez no boot e nunca liberá-los**. Sempre chamar `esp_camera_fb_return(fb)` após `esp_camera_fb_get()` — a falha em retornar buffers é a causa mais comum de memory leaks. Monitore a saúde da memória com `heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM)`.

A variante de **8 MB** PSRAM existe no ESP32-WROVER-IE, mas apenas 4 MB são diretamente endereçáveis. Os 4 MB adicionais requerem a Himem API (bank switching), disponível apenas no ESP-IDF (não no Arduino IDE). Para a maioria das aplicações de câmera, 4 MB são suficientes.

---

## 3. Parâmetros de captura: resolução, formato e qualidade JPEG

### Resoluções e formatos de pixel

O enum `framesize_t` atual inclui resoluções de 96×96 até 2592×1944 (5MP, apenas OV5640). Para o OV2640, o máximo é **UXGA (1600×1200)**. As resoluções mais relevantes para streaming:

| Resolução | Pixels | JPEG típico (q=12) | RGB565 | Uso recomendado |
|-----------|--------|---------------------|--------|-----------------|
| QQVGA (160×120) | 19.2K | 2–5 KB | 38 KB | IoT, thumbnails, máximo FPS |
| QVGA (320×240) | 76.8K | 5–15 KB | 154 KB | Face detection, ML inference |
| VGA (640×480) | 307K | 15–40 KB | 614 KB | **Sweet spot para streaming** |
| SVGA (800×600) | 480K | 25–60 KB | 960 KB | Monitoramento de qualidade |
| XGA (1024×768) | 786K | 40–100 KB | 1.5 MB | Captura still |
| UXGA (1600×1200) | 1.92M | 80–200 KB | 3.75 MB | Máxima qualidade, FPS baixo |

**Regra crítica do README oficial:** "Para ESP32, não use resoluções acima de QVGA quando não estiver em JPEG." Formatos raw (RGB565, YUV422) sobrecarregam a escrita na PSRAM, especialmente com WiFi ativo, resultando em dados faltantes. A abordagem recomendada: **capturar em JPEG, converter para RGB via `fmt2rgb888()` se necessário**.

O OV2640 possui **encoder JPEG por hardware** — quando `PIXFORMAT_JPEG` está selecionado, a compressão é feita no próprio sensor sem consumo de CPU. Para sensores sem JPEG hardware (OV7670), o `frame2jpg()` faz compressão por software, consumindo **100–300 ms por frame em VGA**.

### jpeg_quality: o parâmetro mais impactante

O range é **0–63** (menor = maior qualidade, maior arquivo). Valores recomendados: **10–12** para qualidade geral, **20–30** para priorizar velocidade e baixo bandwidth. **Armadilha importante:** se a qualidade em runtime produzir imagens maiores que o buffer alocado na inicialização, as imagens serão **truncadas/corrompidas**. Sempre inicialize com um valor de `jpeg_quality` menor (buffer maior) que o valor usado em runtime.

---

## 4. Maximizando frame rate: técnicas e benchmarks

### Benchmarks reais por resolução

Com OV2640, JPEG, XCLK=20 MHz e `fb_count=2` (captura contínua sem streaming):

| Resolução | FPS (capture-only) | FPS (MJPEG via WiFi) |
|-----------|--------------------|-----------------------|
| QQVGA | **35–50** | 25–30 |
| QVGA | **25–30** | 20–25 |
| VGA | **12–15** | 10–12 |
| SVGA | **12–13** | 8–10 |
| XGA | **8–10** | 5–8 |
| UXGA | **~5** | 2–3 |

O WiFi reduz o FPS em **20–40%** devido à contenção no barramento da PSRAM e overhead HTTP. Em CIF (400×296), o throughput total máximo é atingido: **308 MB em 15 minutos** de streaming contínuo segundo benchmarks acadêmicos de 2025.

### grab_mode: WHEN_EMPTY vs LATEST

`CAMERA_GRAB_WHEN_EMPTY` (padrão): preenche buffers quando vazios. Se a aplicação é lenta para processar, `esp_camera_fb_get()` retorna um **frame antigo** capturado segundos antes. CPU usage menor.

`CAMERA_GRAB_LATEST` (recomendado para streaming): sobrescreve continuamente buffers antigos. O `esp_camera_fb_get()` sempre retorna o **frame mais recente**. Essencial para aplicações real-time. Requer `fb_count ≥ 2` para funcionar corretamente.

```c
// Configuração ótima para streaming
config.fb_count = 2;
config.grab_mode = CAMERA_GRAB_LATEST;
config.pixel_format = PIXFORMAT_JPEG;

// Configuração ótima para captura periódica (bateria)
config.fb_count = 1;
config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
```

### Checklist para FPS máximo

Usar **PIXFORMAT_JPEG** (compressão hardware, zero overhead de CPU). Configurar **fb_count=2** com **CAMERA_GRAB_LATEST**. Reduzir resolução para VGA ou inferior. Aumentar `jpeg_quality` para 20–30 (arquivos menores, transmissão mais rápida). Configurar PSRAM e Flash a **80 MHz** no menuconfig. Minimizar processamento de imagem no ESP32 — delegar ao receptor. Usar XCLK a **20 MHz** (estável) ou **10 MHz** (experimental com clock doubler). Separar captura e transmissão em tasks FreeRTOS em **cores diferentes**.

### Medição de FPS em código

```c
#include "esp_timer.h"
uint64_t start = esp_timer_get_time();
int frames = 0;
for (int i = 0; i < 100; i++) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) { frames++; esp_camera_fb_return(fb); }
}
float fps = frames * 1000000.0f / (esp_timer_get_time() - start);
```

Um bug de cálculo de FPS no exemplo oficial CameraWebServer persistiu de 2018 a 2025 — verifique que seu firmware usa a versão corrigida.

---

## 5. Streaming MJPEG: implementação e otimização de rede

### Arquitetura do servidor HTTP

O exemplo oficial CameraWebServer usa **dois servidores httpd separados**: porta 80 para a UI web e porta 81 para o stream. A configuração recomendada:

```c
httpd_config_t config = HTTPD_DEFAULT_CONFIG();
config.max_uri_handlers = 16;
config.stack_size = 8192;     // Default 4096 é insuficiente
config.core_id = 0;           // Fixar no PRO_CPU se câmera roda no APP_CPU
config.lru_purge_enable = true; // Auto-fechar conexões stale
```

O stream MJPEG usa **multipart/x-mixed-replace** com chunked transfer encoding. Cada frame é enviado como uma parte separada com `Content-Type: image/jpeg` e `Content-Length` individual:

```c
static const char *STREAM_CONTENT_TYPE = 
    "multipart/x-mixed-replace;boundary=123456789000000000000987654321";
static const char *STREAM_BOUNDARY = 
    "\r\n--123456789000000000000987654321\r\n";
static const char *STREAM_PART = 
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";
```

O fluxo no handler: capturar frame → verificar formato (converter se não-JPEG) → enviar boundary → enviar headers → enviar dados JPEG → **retornar frame buffer imediatamente** → verificar erros → repetir.

### Otimizações de rede TCP/WiFi

Para throughput máximo, as seguintes configurações sdkconfig são recomendadas pela Espressif:

```
CONFIG_LWIP_TCP_SND_BUF_DEFAULT=65534
CONFIG_LWIP_TCP_WND_DEFAULT=65534
CONFIG_ESP32_WIFI_STATIC_RX_BUFFER_NUM=16
CONFIG_ESP32_WIFI_DYNAMIC_TX_BUFFER_NUM=64
CONFIG_ESP32_WIFI_AMPDU_TX_ENABLED=y
```

**Desabilitar WiFi power saving é obrigatório para streaming:** `esp_wifi_set_ps(WIFI_PS_NONE)`. O modo padrão de power saving causa latências de 200+ ms nos pings. Usar **canal WiFi fixo** (1, 6 ou 11) em vez de auto-seleção, e HT20 em vez de HT40 no congestionado espectro 2.4 GHz.

### Multi-client e alternativas ao MJPEG

O exemplo oficial suporta **apenas um stream simultâneo**. Para multi-client, o projeto `esp32-cam-mjpeg-multiclient` de Anatoli Arkhipenko usa três tasks FreeRTOS (captura, servidor web, distribuição de frames) com semáforos e filas, suportando até **10 clientes simultâneos**.

**WebSocket streaming** oferece latência mais baixa (~50–100 ms vs 100–500 ms do MJPEG) enviando frames JPEG como mensagens binárias WebSocket, com comunicação bidirecional no mesmo socket. **RTSP** (via `esp32cam-rtsp` ou `Micro-RTSP`) integra com NVRs e VLC, ideal para vigilância profissional. Para FPV com latência mínima (90–110 ms), projetos como `hx-esp32-cam-fpv` usam transporte UDP customizado.

---

## 6. Configurações avançadas do sensor OV2640/OV5640

### API sensor_t: controle completo via SCCB

Após inicialização, `sensor_t *s = esp_camera_sensor_get()` fornece acesso a dezenas de parâmetros:

**Auto Gain Control (AGC):** `set_gain_ctrl(s, 1)` habilita, `set_agc_gain(s, 0-30)` define ganho manual, `set_gainceiling(s, 0-6)` limita o teto (0=2x, 2=8x padrão, 6=128x). Ganho alto amplifica ruído — manter ceiling em **2x–8x** para qualidade, aumentar para **64x–128x** apenas em condições de pouca luz aceitando ruído significativo.

**Auto Exposure Control (AEC):** `set_exposure_ctrl(s, 1)` habilita, `set_aec_value(s, 0-1200)` define exposição manual, `set_aec2(s, 1)` habilita night mode (permite ao sensor reduzir FPS para exposição mais longa). `set_ae_level(s, -2 a 2)` ajusta compensação de exposição.

**Auto White Balance (AWB):** `set_whitebal(s, 1)` habilita, `set_wb_mode(s, mode)` seleciona preset — 0=Auto, 1=Sunny, 2=Cloudy, 3=Office, 4=Home. O AWB precisa de **3–5 frames para estabilizar** após boot — os primeiros frames frequentemente têm tonalidade amarelada.

**Brightness/Contrast/Saturation:** Range de **-2 a 2** para todos. Um bug conhecido no OV2640 faz com que apenas o último parâmetro configurado tenha efeito, porque o DSP usa um registrador SDE compartilhado. O workaround requer escrita direta nos registros 0x7C/0x7D.

**Efeitos especiais:** `set_special_effect(s, 0-6)` — None, Negative, Grayscale, Red Tint, Green Tint, Blue Tint, Sepia. Mirror e flip via `set_hmirror(s, 0/1)` e `set_vflip(s, 0/1)`. O OV5640 (BSI sensor) produz imagem espelhada por padrão.

### Acesso direto a registros

```c
s->set_reg(s, 0xFF, 0xFF, 0x01);  // Selecionar Bank 1 (sensor)
int pid = s->get_reg(s, 0x0A, 0xFF);  // Product ID High (0x26 para OV2640)
```

O OV2640 tem dois bancos de registros: Bank 0 (DSP — processamento, JPEG, formato) e Bank 1 (sensor — AEC, AGC, timing). O filtro de banding (50/60 Hz) para luz artificial é configurado via registros 0x0C, 0x4F e 0x50 no Bank 1, com detecção automática habilitada por COM8[5].

### Configurações por cenário

Para **ambientes internos/escritório**: wb_mode=3 (Office), gainceiling=8x, banding filter 50/60 Hz conforme região. Para **captura outdoor**: wb_mode=1 (Sunny), gainceiling=2x (mínimo ruído), saturation=1, contrast=1. Para **baixa luminosidade**: aec2=1 (night mode), gainceiling=128x, brightness=1, ae_level=2. Para **captura de alta velocidade**: desabilitar AEC e AGC, exposure manual baixo (~100), gain manual baixo (~5), usar QVGA/CIF.

---

## 7. Processamento de imagem on-device

O ESP32 tem capacidade limitada mas funcional para processamento de imagem leve. **Face detection** usando MTMN (variante do MTCNN com blocos MobileNet) atinge **5–10 FPS em QVGA** para detecção pura e ~1 FPS com reconhecimento facial incluso. O reconhecimento facial requer PSRAM e suporta até ~7 faces armazenadas. No ESP32-S3, a detecção é **4.5x mais rápida** que no ESP32 original.

**Motion detection** via frame differencing é altamente eficiente: capturar em grayscale em resolução reduzida (80×60), comparar pixels contra frame anterior, triggerar quando a porcentagem de pixels alterados excede um threshold. Tempo de processamento: **~4 ms por frame**, permitindo 10+ FPS de detecção de movimento. Bibliotecas como `EloquentEsp32Cam` e `CameraWifiMotion` encapsulam essa lógica.

A **ESP-DL v3.x** (sucessora da dl_lib legada) suporta inferência de redes neurais com formato `.espdl`, quantização automática via ESP-PPQ, e modelos pré-treinados incluindo YOLO11n, detecção de pedestres e detecção de face de gato. **TensorFlow Lite Micro** roda no ESP32 com inferência de ~700 ms para person detection (96×96 grayscale) e ~200 ms no ESP32-S3.

**Leitura de QR code** é possível via `ESP32QRCodeReader` (baseada em Quirc), mas requer PSRAM, boa iluminação e QR codes de pelo menos 5×5 cm. O OV5640 (5MP) melhora significativamente a leitura de QR codes pequenos versus o OV2640.

**Limitação fundamental:** modelos de ML devem ser INT8 quantizados e ter no máximo ~250 KB. Processamento pesado deve usar uma arquitetura de pipeline com tasks FreeRTOS separadas — Core 0 para captura (prioridade alta), Core 1 para processamento/streaming.

---

## 8. Consumo de energia e desafios térmicos

### Medições de corrente por modo

| Modo | Corrente (a 5V) |
|------|-----------------|
| Streaming ativo (WiFi + câmera) | **100–160 mA** |
| Streaming + flash LED | ~270 mA |
| Idle com WiFi conectado | ~80 mA |
| Deep sleep (placa stock AI-Thinker) | **2.8–5 mA** |
| Deep sleep (AMS1117 removido + mods) | **260 µA** |
| ESP32 chip deep sleep (datasheet) | ~10 µA |

O **AMS1117 é o maior obstáculo** para baixo consumo em deep sleep — sua corrente quiescente sozinha é 5–10 mA. Projetos a bateria devem substituí-lo por um LDO de baixo quiescente (HT7333, ~4 µA) ou usar regulador switching.

### Deep sleep entre capturas

Após deep sleep, o CPU reinicia do `setup()`. A câmera deve ser totalmente reinicializada via `esp_camera_init()` (200–500 ms). Os **primeiros 3–4 frames terão tonalidade verde** (bug conhecido) e devem ser descartados. Para reconexão WiFi rápida (<500 ms vs 1–3 s), armazenar canal WiFi e BSSID em memória RTC e usar IP estático.

O OV5640 tem um **problema crítico de deep sleep**: não entra corretamente em modo de baixo consumo via software, consumindo ~0.5W mesmo com ESP32 dormindo (vs 0.032W do OV2640). A solução é um MOSFET controlado por GPIO para cortar completamente a alimentação da câmera.

Com bateria 18650 (3000 mAh): streaming contínuo dura ~18 horas; deep sleep com captura horária de 10 s pode durar **meses**.

### Gerenciamento térmico

Durante streaming contínuo, a temperatura interna atinge **76–80°C** na AI-Thinker e **>80°C** no XIAO ESP32S3 Sense. Após 24+ horas, falhas de frame aumentam e o streaming pode cair. Soluções: heatsink de alumínio no módulo ESP32, duty cycling (stream X minutos, pausa Y minutos), reduzir resolução/FPS, substituir AMS1117 por switching regulator (elimina ~0.5W de dissipação térmica), e garantir ventilação adequada no enclosure.

---

## 9. Os 12 problemas mais comuns e como resolvê-los

**"Camera init failed" (0x20001, 0x20004, 0x105):** verificar que apenas UM `#define CAMERA_MODEL_*` está descomentado, recolocar o cabo ribbon firmemente, alimentar a 5V (não 3.3V). Para erro 0xffffffff após `ESP.restart()`: o DMA não é liberado corretamente — usar power cycle completo ou chamar `esp_camera_deinit()` antes do restart.

**Brownout detector triggered:** alimentação insuficiente durante picos de corrente WiFi TX. Corrigir com fonte 5V/2A + capacitor 100–470 µF. Desabilitar o detector via `WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0)` é workaround temporário que mascara o problema real.

**Imagens corrompidas/garbled:** causas incluem PSRAM com sinal ruidoso, XCLK alto demais (tentar 10 MHz), `jpeg_quality` muito baixa para o buffer alocado, ou uso de formatos raw com WiFi ativo. **Tonalidade verde/rosa** nos primeiros frames após init: descartar 3–4 frames iniciais com delay de 100 ms entre cada.

**Memory leaks:** todo `esp_camera_fb_get()` DEVE ser pareado com `esp_camera_fb_return(fb)`. Buffers não retornados esgotam a memória e `fb_get()` passará a retornar NULL.

**Conflitos com SD card (AI-Thinker):** o SD card em modo 4-bit usa GPIOs 2, 4, 12, 13, 14, 15 — conflitando com flash LED (GPIO 4) e strapping pin (GPIO 12). Usar **modo 1-bit** via `SD_MMC.begin("/sdcard", true)` libera GPIO 4, 12 e 13.

**WiFi desconecta durante streaming:** a operação da câmera gera ruído que interfere no rádio WiFi. Usar antena externa (conector IPEX), reduzir resolução para diminuir atividade no barramento, ou considerar Ethernet (W5500) para conexões confiáveis.

---

## 10. OV2640 vs OV5640 vs OV3660: qual sensor para cada caso

| Especificação | OV2640 | OV5640 | OV3660 |
|--------------|--------|--------|--------|
| Resolução máx | 2MP (1600×1200) | **5MP (2592×1944)** | 3MP (2048×1536) |
| Autofoco | Não | Sim (variante AF) | Não |
| JPEG hardware | ✅ | ✅ | ✅ |
| FPS real no ESP32 (VGA) | **25–30** | 22 | ~25 |
| FPS real no ESP32 (UXGA) | **12** | 4–6 | ~10 |
| Low-light | Mediano | Mediano | **Bom** |
| Power (deep sleep) | **0.032W** ✅ | **0.5W** ⚠️ | Moderado |
| Preço | $2–5 | $8–15 | $6–12 |
| Driver maturity | Excelente (referência) | Bom | Bom |

O driver esp32-camera suporta 17+ sensores, incluindo OV7670, GC0308, SC031GS (global shutter mono) e HM0360 — mas OV2640, OV5640 e OV3660 compartilham o **mesmo conector ribbon de 24 pinos** e são fisicamente intercambiáveis na maioria das placas.

**Recomendações por caso de uso:** streaming de vídeo → **OV2640** (FPS mais alto, menor latência, melhor suporte). Captura de fotos/documentos → **OV5640** (5MP, autofoco). QR code scanning → **OV5640 AF**. Baixa luminosidade/ML → **OV3660**. Projetos a bateria → **OV2640** (deep sleep funcional). Iniciantes → **OV2640** (compatibilidade universal, mais tutoriais).

---

## 11. Código de referência, bibliotecas e configurações de produção

### Driver e API oficial

O **esp32-camera v2.1.4** (novembro 2024, requer IDF v5.1+) é o driver oficial. A API central:

```c
esp_err_t esp_camera_init(const camera_config_t *config);
camera_fb_t *esp_camera_fb_get();
void esp_camera_fb_return(camera_fb_t *fb);
sensor_t *esp_camera_sensor_get();
```

### Configuração de produção recomendada

```c
camera_config_t config;
config.xclk_freq_hz = 20000000;
config.pixel_format = PIXFORMAT_JPEG;
config.frame_size = FRAMESIZE_VGA;
config.jpeg_quality = 12;
config.fb_count = 2;
config.fb_location = CAMERA_FB_IN_PSRAM;
config.grab_mode = CAMERA_GRAB_LATEST;
```

Para PlatformIO, `build_flags` obrigatórias: `-DBOARD_HAS_PSRAM -mfix-esp32-psram-cache-issue`. Partition scheme: `huge_app.csv` (3MB app sem OTA) ou `min_spiffs.csv` (1.9MB com OTA).

### Repositórios essenciais

Os repositórios mais relevantes para desenvolvimento: **espressif/esp32-camera** (driver oficial, 2.5k+ stars), **easytarget/esp32-cam-webserver** (web server aprimorado com OTA), **arkhipenko/esp32-cam-mjpeg-multiclient** (streaming multi-client com RTOS), **rzeldent/esp32cam-rtsp** (servidor RTSP completo), **jomjol/AI-on-the-edge-device** (leitura de medidores com IA), e **RomanLut/hx-esp32-cam-fpv** (FPV com latência mínima de 90 ms via UDP).

### Padrão de captura com deep sleep

```c
void setup() {
    esp_camera_init(&config);
    // Descartar frames com tinta verde
    for (int i = 0; i < 4; i++) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) esp_camera_fb_return(fb);
        delay(100);
    }
    camera_fb_t *fb = esp_camera_fb_get();
    // Enviar/salvar foto...
    esp_camera_fb_return(fb);
    esp_camera_deinit();
    esp_wifi_stop();
    esp_deep_sleep(INTERVAL_US);
}
```

## Conclusão

A otimização da captura no ESP32-WROVER-CAM converge em três eixos: **alimentação estável** (5V/2A, capacitores, fonte adequada), **configuração de PSRAM agressiva** (80 MHz, QIO, fb_count=2, GRAB_LATEST), e **escolha inteligente de resolução/qualidade** (VGA JPEG quality 12 é o sweet spot para streaming). O sensor OV2640 permanece a melhor escolha para a maioria dos projetos por seu equilíbrio entre FPS, consumo e maturidade do driver. O gargalo fundamental do ESP32 original é o limite de 8 MHz no PCLK via I2S — o ESP32-S3 com sua interface LCD_CAM a 40 MHz representa um salto significativo para aplicações que exigem maior performance. Para produção, priorize simplicidade (JPEG sempre), monitore temperatura em operação contínua, e nunca subestime a qualidade da alimentação elétrica como fator determinante da estabilidade do sistema.