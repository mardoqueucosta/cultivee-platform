"""
Cultivee Server — Configuracao unificada
Servidor unico serve todos os tipos de modulo (ctrl, cam, hidro-cam).
Blueprints registrados em multiplos prefixos por tipo.
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
