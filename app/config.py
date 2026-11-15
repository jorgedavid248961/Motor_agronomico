"""Configuración leída de variables de entorno (o de un archivo .env en local)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _normalize_db_url(url: str) -> str:
    """Railway entrega postgres:// o postgresql://; SQLAlchemy + psycopg 3 necesita postgresql+psycopg://."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalize_db_url(os.environ.get("DATABASE_URL", ""))
if not DATABASE_URL:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL.")

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
CORS_ORIGIN_REGEX = os.environ.get("CORS_ORIGIN_REGEX") or None
API_KEY = os.environ.get("API_KEY") or None

# API territorial canónica (API_CANONICA): fuente de los datos del territorio (NDVI, lluvia, suelos).
TERRITORIAL_API_URL = (os.environ.get("TERRITORIAL_API_URL") or "").strip().rstrip("/")
if not TERRITORIAL_API_URL:
    raise RuntimeError("Falta la variable de entorno TERRITORIAL_API_URL (URL de la API territorial canónica).")
TERRITORIAL_API_TIMEOUT = float(os.environ.get("TERRITORIAL_API_TIMEOUT") or 120)
