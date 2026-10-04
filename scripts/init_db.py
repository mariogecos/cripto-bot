"""Crea las tablas necesarias en PostgreSQL y no depende del arranque del bot."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import get_db


if __name__ == "__main__":
    db = get_db()
    db.init_db()
    if db.enabled:
        print("DB inicializada correctamente")
    else:
        print("No se pudo conectar a PostgreSQL. Revisa POSTGRES_DSN, el usuario/contraseña y que el servicio esté levantado.")
        raise SystemExit(1)
