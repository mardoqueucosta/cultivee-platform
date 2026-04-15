#!/bin/bash
# Compilar firmware Cultivee HIDRO-FARM com OTA (min_spiffs)
# Uso: bash compile-hidrofarm.sh [upload]
#   bash compile-hidrofarm.sh          → só compila, gera .bin em build/
#   bash compile-hidrofarm.sh upload   → compila e grava via USB (COM16)
#
# IMPORTANTE: firmware/config.h deve estar com `#include "../products/hidro-farm.h"`
# descomentado (e hidro.h/cam.h comentados).

set -e

ARDUINO_CLI="C:/Users/user/arduino-cli/arduino-cli.exe"
FQBN="esp32:esp32:esp32doit-devkit-v1"
FIRMWARE_DIR="$(cd "$(dirname "$0")" && pwd)/firmware"
BUILD_DIR="$(cd "$(dirname "$0")" && pwd)/build"
PORT="COM16"

echo "=== Compilando Cultivee Hidro Farm ==="

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
echo "Para atualizar via OTA: abra http://<ip-do-esp32>/update e envie build/firmware.ino.bin"
