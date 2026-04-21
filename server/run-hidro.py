"""Launcher para dev local — produto Hidro (Hidroponia)

Antes: run-ctrl.py com env MODULE_TYPE=ctrl e DB cultivee-ctrl.db.
v4.1.28: renomeado para run-hidro.py. Se voce tem um cultivee-ctrl.db legado,
o DB antigo continua vivo em data/cultivee-ctrl.db (nao e apagado); este
launcher agora usa data/cultivee-hidro.db como novo nome. Mova/apague o
antigo se nao precisar mais."""
import os

# Resolve caminhos absolutos baseado no diretorio deste script
_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_dir)

os.environ["MODULE_TYPE"] = "hidro"
os.environ["PORT"] = "5002"
os.environ["API_PREFIX"] = "/api/hidro"
os.environ["DB_PATH"] = os.path.join(_dir, "data", "cultivee-hidro.db")

from app import app
app.run(host="0.0.0.0", port=5002, debug=False)
