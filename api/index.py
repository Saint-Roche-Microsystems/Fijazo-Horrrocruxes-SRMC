"""Punto de entrada para Vercel.

Vercel busca un fichero de entrada (``index.py``, ``main.py``, ...) en la raíz o en
``api/``, ``app/`` o ``src/``, y carga de él la variable ``app``. El paquete real vive en
``src/fijazo_api``, así que aquí solo se reexporta la aplicación ya construida.

El instalador de Vercel resuelve las dependencias de ``pyproject.toml`` con uv, pero no
garantiza instalar *este* paquete (layout ``src/``). Si no lo instala, ``fijazo_api`` no
estaría en el path y la función fallaría al arrancar, así que se añade ``src/`` como
respaldo antes de importar.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fijazo_api.main import app  # noqa: E402

__all__ = ["app"]
