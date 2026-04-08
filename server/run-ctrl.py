"""Launcher para dev local — produto Ctrl (Hidroponia)"""
import os

# Resolve caminhos absolutos baseado no diretorio deste script
_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_dir)

os.environ["MODULE_TYPE"] = "ctrl"
os.environ["PORT"] = "5002"
os.environ["API_PREFIX"] = "/api/ctrl"
os.environ["DB_PATH"] = os.path.join(_dir, "data", "cultivee-ctrl.db")

from app import app
app.run(host="0.0.0.0", port=5002, debug=False)
