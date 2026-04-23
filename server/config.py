"""
Cultivee Server — Configuracao unificada
Blueprints registrados por capability: /api/hidro, /api/hidro-farm, /api/cam, /api/gallery.
(/api/ctrl continua como alias deprecated de /api/hidro ate ESP32s em campo migrarem — v4.1.28)
"""

import os

# Diretorio base do servidor (onde este arquivo esta)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Configuracao do servidor ---
PORT = int(os.environ.get("PORT", "5002"))

# DB_PATH: se relativo, resolve a partir do diretorio do servidor
_db = os.environ.get("DB_PATH", "data/cultivee.db")
DB_PATH = _db if os.path.isabs(_db) else os.path.join(_BASE_DIR, _db)

# Nome do produto (para logs)
PRODUCT_NAME = "Cultivee"

# Versao unica — usada pelo sw.js (cache), app.js (UI) e footer
# Incrementar quando mudar app.js, style.css ou index.html
APP_VERSION = "4.1.32"
