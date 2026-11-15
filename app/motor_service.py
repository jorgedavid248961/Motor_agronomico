"""Envoltura del motor agronómico 4.1: carga una sola vez el cuaderno y el índice territorial y evalúa puntos.

El índice territorial se construye con los datos de la API canónica (TERRITORIAL_API_URL), en segundo
plano y con reintentos: la API arranca enseguida y /health informa «loading» hasta que el índice está listo.
"""
from __future__ import annotations

import logging
import multiprocessing
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

from . import territorial_api
from .config import ROOT, TERRITORIAL_API_TIMEOUT, TERRITORIAL_API_URL

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import motor_agronomico_v41 as motor  # noqa: E402

log = logging.getLogger("uvicorn.error")


class MotorService:
    def __init__(self) -> None:
        self.nb: dict | None = None
        self.index: dict | None = None
        self.territorial_error: str | None = None
        self._loader: threading.Thread | None = None

    def load(self) -> None:
        self.nb = motor.load_notebook()
        if self._loader is None:
            self._loader = threading.Thread(target=self._load_territory, name="territorial-index", daemon=True)
            self._loader.start()

    def _load_territory(self) -> None:
        delay = 2.0
        while self.index is None:
            try:
                started = time.monotonic()
                self.index = build_index_isolated()
                self.territorial_error = None
                log.info("Índice territorial listo desde la API: %d celdas, registros %s (%.1f s).",
                         self.index["n_cells"], self.index["bundle"].get("records"), time.monotonic() - started)
            except Exception as exc:  # la API territorial puede no estar lista todavía: se reintenta
                self.territorial_error = f"{type(exc).__name__}: {exc}"
                log.warning("Territorio no disponible desde %s (%s). Reintento en %.0f s.",
                            TERRITORIAL_API_URL, self.territorial_error, delay)
                time.sleep(delay)
                delay = min(delay * 2, 60.0)

    @property
    def ready(self) -> bool:
        return self.nb is not None and self.index is not None

    def evaluar(self, req) -> dict:
        """De la petición del frontend a la salida estructurada del motor (payload para el agente)."""
        series, info = None, None
        if req.serie_nasa_power:
            series, info = motor.series_from_nasa_power(req.serie_nasa_power)
        elif req.serie_csv:
            series, info = motor.series_from_csv(req.serie_csv)
        return motor.evaluate_point(
            self.nb, self.index, req.lat, req.lon, req.cultivo, req.etapa,
            field=req.campo, series=series, series_info=info,
            history=req.historial, residue=req.rastrojo, nitrogen=req.fertilizacion_n,
            waterlogging=req.encharcamiento,
        )


def build_index(base_url: str = TERRITORIAL_API_URL, timeout: float = TERRITORIAL_API_TIMEOUT) -> dict:
    """Índice territorial del motor (sin preparar) a partir de la API canónica."""
    bundle = territorial_api.fetch_bundle(base_url, timeout)
    counts = {name: sum(len(b["data"]) for b in blocks) for name, blocks in bundle["variables"].items()}
    missing = sorted(set(territorial_api.FIELDS) - set(counts))
    if missing:
        log.warning("La API territorial no tiene las variables %s: quedan sin dato.", missing)
    return motor.build_territorial_index(bundle, {
        "origin": "api_canonica", "fetched_at_utc": datetime.now(timezone.utc).isoformat(), "records": counts})


def build_index_isolated() -> dict:
    """build_index en un proceso aparte. Los ~830 mil registros que llegan de la API ocupan ~1 GB mientras
    se arma el índice; en el mismo proceso la fragmentación del heap retendría ~650 MB para siempre.
    Así, al terminar el subproceso se libera todo y aquí solo queda el índice (pocos MB)."""
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        index = pool.submit(build_index, TERRITORIAL_API_URL, TERRITORIAL_API_TIMEOUT).result()
    return motor._prepare_index(index)


servicio = MotorService()
