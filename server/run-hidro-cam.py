"""Launcher para dev local — produto HidroCam"""
import os

# Resolve caminhos absolutos baseado no diretorio deste script
_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_dir)

os.environ["MODULE_TYPE"] = "hidro-cam"
os.environ["PORT"] = "5003"
os.environ["API_PREFIX"] = "/api/hidro-cam"
os.environ["DB_PATH"] = os.path.join(_dir, "data", "cultivee-hidro-cam.db")
os.environ["DATA_DIR"] = os.path.join(_dir, "data")

from app import app
app.run(host="0.0.0.0", port=5003, debug=False)
