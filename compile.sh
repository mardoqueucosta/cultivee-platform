#!/bin/bash
# Compilar firmware Cultivee com OTA (min_spiffs)
# Uso: bash compile.sh [upload]
#   bash compile.sh                       → só compila, gera .bin em build/
#   bash compile.sh upload                → compila e grava via USB (default COM7)
#   PORT=COM17 bash compile.sh upload    → grava em outra porta (segundo HIDRO, etc.)

set -e

ARDUINO_CLI="C:/Users/user/arduino-cli/arduino-cli.exe"
FQBN="esp32:esp32:esp32doit-devkit-v1"
FIRMWARE_DIR="$(cd "$(dirname "$0")" && pwd)/firmware"
BUILD_DIR="$(cd "$(dirname "$0")" && pwd)/build"
PORT="${PORT:-COM7}"  # aceita override via env: PORT=COM17 bash compile.sh upload

echo "=== Compilando Cultivee Hidro ==="

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
echo "Para atualizar via OTA: abra http://192.168.4.1/update e envie build/firmware.ino.bin"
