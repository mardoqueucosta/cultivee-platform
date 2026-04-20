#!/bin/bash
# Compilar firmware Cultivee CAM com OTA (min_spiffs)
# Uso: bash compile-cam.sh [upload]
#   bash compile-cam.sh          → só compila, gera .bin em build/
#   bash compile-cam.sh upload   → compila e grava via USB (COM7)
#
# IMPORTANTE: firmware/config.h deve estar com `#include "../products/cam.h"`
# descomentado (e hidro.h/hidro-farm.h comentados).
#
# Historico: a partir da v4.1.8 o Cam migrou de `no_ota` (2 MB) pra `min_spiffs`
# (1.9 MB + 1.9 MB OTA). A PRIMEIRA gravacao precisa ser via USB (muda a
# partition table). Dai em diante, atualizacoes podem ser via OTA remoto
# (`bash ota-remote.sh <chip_id> build/firmware.ino.bin <token>`).

set -e

ARDUINO_CLI="C:/Users/user/arduino-cli/arduino-cli.exe"
FQBN="esp32:esp32:esp32wroverkit"
FIRMWARE_DIR="$(cd "$(dirname "$0")" && pwd)/firmware"
BUILD_DIR="$(cd "$(dirname "$0")" && pwd)/build"
PORT="COM7"

echo "=== Compilando Cultivee Cam (min_spiffs, com OTA) ==="

"$ARDUINO_CLI" compile \
  --fqbn "$FQBN" \
  --build-property "build.partitions=min_spiffs" \
  --build-property "upload.maximum_size=1966080" \
  --output-dir "$BUILD_DIR" \
  "$FIRMWARE_DIR"

echo ""
echo "Binario gerado: $BUILD_DIR/firmware.ino.bin"
ls -lh "$BUILD_DIR/firmware.ino.bin"

if [ "$1" = "upload" ]; then
  echo ""
  echo "=== Gravando via USB ($PORT) ==="
  "$ARDUINO_CLI" upload --fqbn "$FQBN" -p "$PORT" --input-dir "$BUILD_DIR"
  echo "Gravado!"
fi

echo ""
echo "Para atualizar via OTA remoto:"
echo "  bash ota-remote.sh <chip_id> $BUILD_DIR/firmware.ino.bin <token>"
