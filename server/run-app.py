"""Roda servidor unificado Cultivee na porta 5002 (dev local)."""
import os
os.environ.setdefault("PORT", "5002")
os.environ.setdefault("DB_PATH", "data/cultivee.db")
os.environ.setdefault("DATA_DIR", "data")

from app import app
app.run(host="0.0.0.0", port=5002, debug=True)
