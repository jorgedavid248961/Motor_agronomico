"""Envoltura del motor agronómico 4.1: carga una sola vez el cuaderno y el índice territorial y evalúa puntos."""
from __future__ import annotations

import sys

from .config import DATA_DIR, ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import motor_agronomico_v41 as motor  # noqa: E402


class MotorService:
    def __init__(self) -> None:
        self.nb: dict | None = None
        self.index: dict | None = None

    def load(self) -> None:
        self.nb = motor.load_notebook()
        # Sin el bundle crudo (821 MB) presente, el motor usa directamente territorial_index_v41.json.
        self.index = motor.load_territorial_index(DATA_DIR, log=print)

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


servicio = MotorService()
