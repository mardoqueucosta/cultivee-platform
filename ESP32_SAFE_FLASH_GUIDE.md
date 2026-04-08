# Guia de Segurança para Compilação e Upload de Firmware no ESP32 via Claude Code

**Versão:** 1.0  
**Data:** 2026-03-27  
**Autor:** Mardoqueu (Biopdi) — gerado com pesquisa profunda via Claude  
**Objetivo:** Instruções obrigatórias para o compilador/agente do Claude Code seguir ao trabalhar com projetos ESP32, evitando danos ao hardware durante o processo de flash/upload.

---

## 1. Contexto do Problema

O ESP32 pode sofrer danos irreversíveis durante a etapa de **upload/flash** do firmware (não durante a compilação em si, que roda inteiramente no host). As causas documentadas pela comunidade e pela Espressif são:

- **Brownout do regulador AMS1117** presente em DevKits baratos: o pico de corrente durante o flash (até 300mA) pode exceder a capacidade do regulador de 3.3V, causando subtensão ou queima permanente do regulador e, consequentemente, do chip ESP32.
- **Cabos USB de baixa qualidade** (longos, finos, ou "só carga"): introduzem resistência que causa queda de tensão durante picos de corrente do flash.
- **Portas USB frontais ou hubs sem alimentação própria**: fornecem tensão instável (< 4.75V).
- **Velocidade de upload excessiva** (921600 ou 2000000 baud): aumenta a probabilidade de pacotes corrompidos, falhas de escrita parcial na flash e boot loops que superaquecem o chip. Velocidades de 230400 sao seguras para a maioria dos modulos; 115200 como fallback para casos problematicos.
- **Flash mode incompatível** (QIO em chips que só suportam DIO): o upload parece bem-sucedido mas o chip não consegue ler a flash de volta, entrando em loop de reset contínuo e superaquecimento.
- **Periféricos conectados nos GPIOs durante upload**: podem interferir nos pinos SPI da flash (GPIO 6-11) ou no GPIO0/EN usados para o boot mode.
- **Revisão antiga do silício** (ESP32 rev v0/v1, módulos sem sufixo "E"): têm bugs conhecidos de brownout e power-on sequence.

---

## 2. Regra Fundamental: Separar COMPILAÇÃO de UPLOAD

```
COMPILAÇÃO (build)  →  Roda 100% no host (PC/Mac/Linux). Seguro. Sem risco ao hardware.
UPLOAD (flash)      →  Interage com o ESP32 via USB/Serial. ZONA DE RISCO.
```

O Claude Code DEVE:
1. **Compilar primeiro, sem upload automático.**
2. **Exibir um aviso antes de qualquer comando de flash.**
3. **Usar parâmetros conservadores (detalhados abaixo).**

---

## 3. Parâmetros Obrigatórios de Upload

### 3.1 Para projetos ESP-IDF (`idf.py`)

```bash
# NAO USAR (padrao agressivo)
idf.py flash

# USAR (parametros conservadores explicitos)
idf.py -b 230400 flash
```

No `sdkconfig` ou via `idf.py menuconfig`, configurar:

```ini
# Serial Flasher Config
CONFIG_ESPTOOLPY_BAUD_230400B=y          # Upload a 230400 baud (seguro; fallback: 115200)
CONFIG_ESPTOOLPY_FLASHMODE_DIO=y          # Flash mode DIO (compatível com todos os chips)
CONFIG_ESPTOOLPY_FLASHFREQ_40M=y          # Flash frequency 40MHz (não 80MHz)
CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y          # Ajustar ao tamanho real da flash
CONFIG_ESPTOOLPY_BEFORE_RESET=y           # default_reset antes do flash
CONFIG_ESPTOOLPY_AFTER_RESET=y            # hard_reset após o flash
CONFIG_ESPTOOLPY_COMPRESSED=y             # Comprimir dados (reduz tempo de transferência)

# Bootloader Config (proteção contra brownout)
CONFIG_BOOTLOADER_VDDSDIO_BOOST_1_9V=y   # Boost de 1.8V para 1.9V (previne brownout na flash)
```

Ou via variaveis de ambiente:

```bash
export ESPBAUD=230400
idf.py flash
```

### 3.2 Para projetos PlatformIO (`platformio.ini`)

```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino

; === CONFIGURACOES DE SEGURANCA OBRIGATORIAS ===
upload_speed = 230400                    ; Baud rate seguro (fallback: 115200)
monitor_speed = 115200                   ; Monitor serial
board_build.flash_mode = dio             ; Modo DIO (mais seguro que QIO)
board_build.f_flash = 40000000L          ; Flash a 40MHz (não 80MHz)

; === OPCIONAIS MAS RECOMENDADOS ===
upload_protocol = esptool
build_flags = 
    -DCORE_DEBUG_LEVEL=3                 ; Debug level Info para diagnóstico
```

### 3.3 Para Arduino CLI (usado no projeto Cultivee)

```bash
# Compilar (seguro, roda no host)
arduino-cli compile --fqbn esp32:esp32:esp32cam "D:/01-projetos-claude/cultivee/firmware-cam"

# Upload com parametros conservadores
arduino-cli upload --fqbn esp32:esp32:esp32cam -p COM9 \
    --board-options "UploadSpeed=230400,FlashMode=dio,FlashFreq=40" \
    "D:/01-projetos-claude/cultivee/firmware-cam"
```

Portas do projeto Cultivee:
- **COM9** — ESP32-CAM AI-Thinker e ESP32-WROVER-CAM
- **COM7** — ESP32-WROOM-32D (firmware-ctrl, hidroponia)

### 3.4 Para Arduino IDE (referencia manual)

```
Tools > Upload Speed     → 230400 (ou 115200 se falhar)
Tools > Flash Frequency  → 40MHz
Tools > Flash Mode       → DIO
Tools > Erase All Flash  → Enabled (no primeiro upload)
```

### 3.5 Para esptool.py direto (linha de comando)

```bash
# ✅ Comando seguro completo
python -m esptool \
    --chip esp32 \
    --port COM9 \
    --baud 115200 \
    --before default-reset \
    --after hard-reset \
    write-flash \
    --flash_mode dio \
    --flash_freq 40m \
    --flash_size detect \
    --compress \
    0x1000 build/bootloader/bootloader.bin \
    0x8000 build/partition_table/partition-table.bin \
    0x10000 build/firmware.bin
```

---

## 4. Checklist Pré-Upload (Claude Code deve exibir antes de qualquer flash)

```
+--------------------------------------------------------------+
|              CHECKLIST PRE-UPLOAD ESP32                      |
+--------------------------------------------------------------+
|                                                              |
|  [ ] Cabo USB: curto (< 1m), blindado, de DADOS             |
|  [ ] Porta USB: traseira do desktop ou hub alimentado        |
|  [ ] Perifericos: TODOS desconectados dos GPIOs              |
|  [ ] Breadboard: ESP32 REMOVIDO da breadboard                |
|  [ ] Upload speed: 230400 baud (ou 115200 fallback)          |
|  [ ] Flash mode: DIO                                         |
|  [ ] Flash frequency: 40MHz                                  |
|  [ ] Serial monitor: FECHADO (nao pode competir pela porta)  |
|                                                              |
|  CONFIRMAR antes de prosseguir com o upload.                 |
|                                                              |
+--------------------------------------------------------------+
```

---

## 5. Sequência Segura de Operações

### Passo 1: Compilar SEM upload

```bash
# Arduino CLI (projeto Cultivee)
arduino-cli compile --fqbn esp32:esp32:esp32cam "D:/01-projetos-claude/cultivee/firmware-cam"

# ESP-IDF
idf.py build

# PlatformIO
pio run              # Apenas compila, sem upload
```

### Passo 2: Verificar saida da compilacao

- Confirmar que nao ha erros.
- Verificar tamanho do binario (nao deve exceder o tamanho da particao).
- Conferir uso de RAM (nao deve exceder 90%).

### Passo 3: Upload com parametros seguros

```bash
# Arduino CLI (projeto Cultivee)
arduino-cli upload --fqbn esp32:esp32:esp32cam -p COM9 \
    --board-options "UploadSpeed=230400,FlashMode=dio,FlashFreq=40" \
    "D:/01-projetos-claude/cultivee/firmware-cam"

# ESP-IDF
idf.py -b 230400 flash

# PlatformIO
pio run --target upload

# esptool.py direto (ver secao 3.5)
```

### Passo 4: Verificar boot

```bash
# Arduino CLI
arduino-cli monitor -p COM9 --config baudrate=115200

# ESP-IDF
idf.py -b 115200 monitor

# PlatformIO
pio device monitor --baud 115200
```

Verificar que o output NÃO mostra:
- `flash read err, 1000` → flash corrompida ou modo incompatível
- `rst:0x10 (RTCWDT_RTC_RESET)` em loop → chip não consegue ler firmware
- `Brownout detector was triggered` → fonte de alimentação insuficiente
- Caracteres ilegíveis (`⸮⸮⸮`) → baud rate do monitor não corresponde ao código

---

## 6. Procedimento de Recuperação (se o ESP32 não responde)

### 6.1 Erase total da flash

```bash
python -m esptool \
    --chip esp32 \
    --port COM9 \
    --baud 115200 \
    erase_flash
```

**Importante:** Segurar o botão BOOT durante o comando, ou manter GPIO0 em LOW.

### 6.2 Flash manual do bootloader limpo

```bash
python -m esptool \
    --chip esp32 \
    --port COM9 \
    --baud 115200 \
    --before default-reset \
    --after hard-reset \
    write-flash \
    --flash_mode dio \
    --flash_freq 40m \
    0x1000 bootloader.bin
```

### 6.3 Se o chip esquenta ao conectar USB

**PARE IMEDIATAMENTE.** Desconecte o USB. Isso indica:
- Regulador AMS1117 danificado → componente substituível (SMD, barato).
- Curto-circuito interno no chip ESP32 → chip morto, substituir o módulo.

---

## 7. Comandos Proibidos (Claude Code NUNCA deve executar)

```bash
# NUNCA executar sem confirmacao explicita do usuario
espefuse.py burn_efuse ...          # Queima eFuses IRREVERSIVEL
espefuse.py burn_key ...            # Queima chave IRREVERSIVEL
espsecure.py ...                    # Operacoes de Secure Boot

# NUNCA usar baud rate > 460800 em primeira tentativa
--baud 921600
--baud 2000000
-b 921600

# NUNCA usar QIO sem confirmacao do modelo do modulo
--flash_mode qio
board_build.flash_mode = qio

# NUNCA usar 80MHz flash sem confirmacao do modulo
--flash_freq 80m
board_build.f_flash = 80000000L
```

---

## 8. Configurações Seguras por Tipo de Módulo

| Módulo | Flash Mode | Flash Freq | Notas |
|--------|-----------|------------|-------|
| ESP32-WROOM-32 | DIO | 40MHz | Revisão antiga, mais sensível |
| ESP32-WROOM-32D | DIO | 40MHz | Melhoria sobre WROOM-32 |
| ESP32-WROOM-32E | DIO | 40MHz | **Recomendado** — bugs de brownout corrigidos |
| ESP32-WROVER | DIO | 40MHz | Tem PSRAM — cuidado com GPIOs 16/17 |
| ESP32-WROVER-E | DIO | 40MHz | **Recomendado** — versão corrigida |
| ESP32-S3-WROOM-1 | DIO | 40MHz | Suporta USB nativo |
| ESP32-S3-WROOM-2 | DIO/OPI | 40MHz | Verificar PSRAM config no menuconfig |
| ESP32-C3-MINI-1 | DIO | 40MHz | Single core, RISC-V |

**Regra geral:** Na dúvida, usar DIO + 40MHz. Funciona em TODOS os módulos.

---

## 9. Diagnóstico Rápido de Problemas

| Sintoma | Causa Provável | Solução |
|---------|---------------|---------|
| `Failed to connect` / `Timed out` | GPIO0 não em LOW, cabo ruim, porta ocupada | Segurar BOOT, trocar cabo, fechar monitor |
| `flash read err, 1000` | Flash mode incompatível | Mudar para DIO, erase_flash, re-upload |
| `Brownout detector was triggered` | Alimentação insuficiente | Trocar cabo, usar fonte externa 5V/1A |
| `MD5 of file does not match` | Periféricos nos pinos SPI, cabo ruim | Remover periféricos, trocar cabo |
| `Serial data stream stopped` | Baud rate alto demais, interferência | Reduzir para 115200 |
| Chip esquenta ao conectar | Regulador AMS1117 queimado | **NÃO conectar mais.** Substituir AMS1117 ou módulo |
| Boot loop infinito | Firmware corrompido + brownout | erase_flash + re-upload com DIO/40MHz |
| `Write protected` | eFuse ou flash danificada | Verificar com `espefuse.py summary` |

---

## 10. Template de Projeto Seguro para Claude Code

### 10.1 PlatformIO — `platformio.ini` padrão seguro

```ini
; ============================================================
; TEMPLATE SEGURO PARA ESP32 — Biopdi/Claude Code
; ============================================================
; Este template usa configurações conservadoras para prevenir
; danos ao hardware durante o upload.
; ============================================================

[env:esp32-safe]
platform = espressif32
board = esp32dev
framework = arduino

; --- Upload Seguro ---
upload_speed = 230400                    ; Seguro; usar 115200 se falhar
upload_protocol = esptool

; --- Flash Config Conservador ---
board_build.flash_mode = dio
board_build.f_flash = 40000000L
board_build.partitions = default.csv

; --- Monitor ---
monitor_speed = 115200
monitor_rts = 0
monitor_dtr = 0

; --- Build ---
build_flags =
    -DCORE_DEBUG_LEVEL=3
    -DBOARD_HAS_PSRAM=0              ; Trocar para 1 se usar WROVER (8MB PSRAM)

; --- Extras ---
; Descomente para erase total antes do upload:
; upload_flags = --erase-all
```

### 10.2 ESP-IDF — `sdkconfig.defaults` padrão seguro

```ini
# ============================================================
# SDKCONFIG SEGURO PARA ESP32 — Biopdi/Claude Code
# ============================================================

# Serial Flasher
CONFIG_ESPTOOLPY_BAUD_230400B=y          # Seguro; fallback: 115200
CONFIG_ESPTOOLPY_FLASHMODE_DIO=y
CONFIG_ESPTOOLPY_FLASHFREQ_40M=y
CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y
CONFIG_ESPTOOLPY_BEFORE="default_reset"
CONFIG_ESPTOOLPY_AFTER="hard_reset"
CONFIG_ESPTOOLPY_COMPRESSED=y

# Bootloader
CONFIG_BOOTLOADER_VDDSDIO_BOOST_1_9V=y
CONFIG_BOOTLOADER_WDT_ENABLE=y
CONFIG_BOOTLOADER_WDT_TIME_MS=9000

# Brownout Detector
CONFIG_ESP32_BROWNOUT_DET=y
CONFIG_ESP32_BROWNOUT_DET_LVL_SEL_0=y

# Console
CONFIG_ESP_CONSOLE_UART_BAUDRATE=115200
```

---

## 11. Instruções Específicas para o Agente Claude Code

Ao trabalhar com qualquer projeto ESP32, o agente Claude Code DEVE:

1. **ANTES de qualquer build:** verificar se `platformio.ini` ou `sdkconfig` contém os parâmetros seguros listados na Seção 3. Se não contiver, adicionar automaticamente.

2. **NUNCA executar `idf.py flash`, `pio run -t upload` ou `arduino-cli upload` sem:**
   - Avisar o usuario sobre o checklist da Secao 4.
   - Confirmar que os parametros de baud, flash_mode e flash_freq estao corretos.
   - Para arduino-cli, sempre incluir `--board-options "UploadSpeed=230400,FlashMode=dio,FlashFreq=40"`.

3. **NUNCA usar `espefuse.py`** em nenhuma circunstância sem aprovação explícita e documentada do usuário.

4. **Se o upload falhar:**
   - NÃO repetir imediatamente com parâmetros mais agressivos.
   - Sugerir diagnóstico conforme tabela da Seção 9.
   - Sugerir erase_flash antes de nova tentativa.

5. **Se o usuário reportar chip esquentando:**
   - Instruir a desconectar IMEDIATAMENTE.
   - NÃO sugerir "tente de novo".
   - Orientar verificação do regulador AMS1117 com multímetro (deve mostrar 3.3V entre output e GND).

6. **Ao criar novos projetos ESP32:**
   - Usar os templates da Seção 10 como base.
   - Sempre incluir `upload_speed = 230400` e `board_build.flash_mode = dio`.

7. **Ao modificar projetos existentes:**
   - Verificar e alertar se `upload_speed > 460800` ou `flash_mode = qio`.
   - Sugerir mudança para valores seguros.

---

## 12. Referências

- Espressif esptool documentation: https://docs.espressif.com/projects/esptool/en/latest/
- ESP-IDF Flash Modes: https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/flash-modes.html
- ESP-IDF Flashing Troubleshooting: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/flashing-troubleshooting.html
- Arduino ESP32 Troubleshooting: https://docs.espressif.com/projects/arduino-esp32/en/latest/troubleshooting.html
- ESP32 Hardware Design Guidelines (power/decoupling): https://www.espressif.com/sites/default/files/documentation/esp32_hardware_design_guidelines_en.pdf
- PlatformIO ESP32 Config: https://docs.platformio.org/en/latest/platforms/espressif32.html
- Community reports (ESP32 Forum, Arduino Forum, GitHub Issues): compilados neste documento

---

## 13. Integracao com CLAUDE.md

Este guia complementa o CLAUDE.md do projeto Cultivee. As secoes de compilacao/upload no CLAUDE.md
devem referenciar este documento para parametros seguros. Em caso de conflito, este guia prevalece
para questoes de seguranca de hardware.

Resumo das regras para o agente:
- Upload sempre com `--board-options "UploadSpeed=230400,FlashMode=dio,FlashFreq=40"`
- Nunca executar upload sem avisar o usuario (checklist secao 4)
- Se falhar, reduzir para 115200 antes de tentar novamente
- Nunca usar espefuse.py sem aprovacao explicita
