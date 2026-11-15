"""API del motor agronómico Space Wanderers 4.1.

Local:     .venv\\Scripts\\uvicorn app.main:app --reload
Docs:      http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import math
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import API_KEY, CORS_ORIGIN_REGEX, CORS_ORIGINS
from .db import Evaluacion, get_session, init_db
from .motor_service import motor, servicio
from .schemas import EvaluacionIn, EvaluacionLista, EvaluacionOut


@asynccontextmanager
async def lifespan(_: FastAPI):
    servicio.load()
    init_db()
    yield


app = FastAPI(
    title="Space Wanderers · Motor agronómico",
    version=motor.VERSION,
    description="Evalúa un lote por coordenadas con el motor agronómico 4.1 y guarda el resultado en PostgreSQL.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if API_KEY and not (x_api_key and secrets.compare_digest(x_api_key, API_KEY)):
        raise HTTPException(status_code=401, detail="X-API-Key inválida o ausente.")


@app.get("/health", tags=["sistema"])
def health():
    idx = servicio.index or {}
    return {"status": "ok" if servicio.ready else "loading", "engine_version": motor.VERSION,
            "cells": idx.get("n_cells"), "index_built_at_utc": idx.get("built_at_utc")}


@app.get("/api/v1/catalogo", tags=["motor"])
def catalogo():
    """Valores válidos para construir el formulario del frontend."""
    return {
        "cultivos": motor.CROPS,
        "etapas": motor.STAGES,
        "variables_campo": {k: {"tipo": t, "etiqueta": motor.var_label(k)} for k, t in motor.KNOWN_VARIABLES.items()},
        "texturas": sorted(motor.VALID_TEXTURES),
        "sintomas": {v: k for k, v in motor.SYMPTOM_OPTIONS.items()},
        "cultivos_rotacion": sorted(motor.ROT_ENUMS["last_crops"]),
        "rastrojo": {k: v for k, v in motor.RESIDUE_OPTIONS.items() if k},
        "fertilizacion_n": {k: v for k, v in motor.NITROGEN_OPTIONS.items() if k},
        "fuentes_territoriales": (servicio.index or {}).get("sources"),
    }


@app.post("/api/v1/evaluaciones", tags=["motor"], status_code=201, response_model=EvaluacionOut,
          dependencies=[Depends(require_api_key)])
def crear_evaluacion(req: EvaluacionIn, session: Session = Depends(get_session)):
    """Ejecuta el motor para el punto, guarda entrada y salida en la BD y devuelve el registro completo."""
    if not servicio.ready:
        raise HTTPException(status_code=503, detail="El motor aún se está cargando.")
    try:
        payload = servicio.evaluar(req)
    except ValueError as exc:                       # serie NASA POWER / CSV mal formada
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cell = payload["territory"]["cell"]
    row = Evaluacion(
        referencia_cliente=req.referencia_cliente,
        lat=req.lat, lon=req.lon,
        grid_id=str(cell["grid_id"]), celda_lat=cell["latitude"], celda_lon=cell["longitude"],
        distancia_celda_km=cell["distance_km"],
        cultivo=req.cultivo, etapa=req.etapa,
        agricola=bool(payload["territory"]["agricultural"]),
        estado=payload["inference"]["status"],
        hallazgos=payload["inference"]["findings_count"],
        riesgo_global=payload["risk_overview"]["overall"],
        version_motor=payload["schema_version"], version_cuaderno=payload.get("notebook_version"),
        entrada=req.model_dump(mode="json", exclude_none=True),
        resultado=payload,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@app.get("/api/v1/evaluaciones", tags=["consultas"], response_model=EvaluacionLista)
def listar_evaluaciones(
    session: Session = Depends(get_session),
    grid_id: str | None = None,
    cultivo: str | None = None,
    etapa: str | None = None,
    riesgo: str | None = Query(None, description="none | low | medium | high"),
    referencia_cliente: str | None = None,
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    radio_km: float | None = Query(None, gt=0, le=200),
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Resúmenes (sin el JSON completo), del más reciente al más antiguo."""
    conds = []
    if grid_id:
        conds.append(Evaluacion.grid_id == grid_id)
    if cultivo:
        conds.append(Evaluacion.cultivo == cultivo)
    if etapa:
        conds.append(Evaluacion.etapa == etapa)
    if riesgo:
        conds.append(Evaluacion.riesgo_global == riesgo)
    if referencia_cliente:
        conds.append(Evaluacion.referencia_cliente == referencia_cliente)
    if desde:
        conds.append(Evaluacion.created_at >= desde)
    if hasta:
        conds.append(Evaluacion.created_at < hasta)
    if lat is not None and lon is not None and radio_km:
        dlat = radio_km / 111.32
        dlon = radio_km / (111.32 * max(math.cos(math.radians(lat)), 1e-6))
        conds += [Evaluacion.celda_lat.between(lat - dlat, lat + dlat),
                  Evaluacion.celda_lon.between(lon - dlon, lon + dlon)]

    total = session.scalar(select(func.count()).select_from(Evaluacion).where(*conds))
    items = session.scalars(select(Evaluacion).where(*conds)
                            .order_by(Evaluacion.created_at.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/api/v1/evaluaciones/{evaluacion_id}", tags=["consultas"], response_model=EvaluacionOut)
def obtener_evaluacion(evaluacion_id: uuid.UUID, session: Session = Depends(get_session)):
    row = session.get(Evaluacion, evaluacion_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")
    return row
