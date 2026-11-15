"""Contratos de entrada y salida de la API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .motor_service import motor

SYMPTOMS = set(motor.SYMPTOM_OPTIONS.values())
ROTATION_CROPS = set(motor.ROT_ENUMS["last_crops"])


class EvaluacionIn(BaseModel):
    """Datos que envía el frontend. Solo lat/lon son obligatorios: el resto sale del bundle territorial."""

    lat: float = Field(..., ge=-90, le=90, examples=[6.6425])
    lon: float = Field(..., ge=-180, le=180, examples=[-76.075])
    cultivo: str = Field("otro", examples=["maiz"], description="Clave de cultivo (ver GET /api/v1/catalogo).")
    etapa: str = Field("no_especificada", examples=["vegetativo"], description="Clave de etapa fenológica.")
    campo: dict[str, Any] | None = Field(
        None, examples=[{"soil_ph": 6.2, "organic_matter": 1.5, "symptoms": ["clorosis_hojas_viejas"]}],
        description="Lo medido u observado en el lote. Manda sobre el bundle territorial.")
    historial: list[list[str]] | None = Field(
        None, examples=[[["maiz"], ["frijol"]]],
        description="Ciclos anteriores para la rotación, el más reciente primero.")
    rastrojo: Literal["incorporated", "surface_mulch", "removed", "burned"] | None = None
    fertilizacion_n: Literal["none_or_low", "high"] | None = None
    encharcamiento: bool | None = None
    serie_nasa_power: dict[str, Any] | None = Field(
        None, description="Respuesta JSON diaria de NASA POWER para el punto (opcional).")
    serie_csv: str | None = Field(
        None, description="Serie diaria en CSV: tmax, tmin, rh, rain, soil_moisture, fecha (opcional).")
    referencia_cliente: str | None = Field(
        None, max_length=128, description="Id libre del frontend (lote, usuario, sesión) para consultar después.")

    @field_validator("cultivo")
    @classmethod
    def _cultivo(cls, v: str) -> str:
        if v not in motor.CROPS:
            raise ValueError(f"cultivo debe ser uno de {list(motor.CROPS)}")
        return v

    @field_validator("etapa")
    @classmethod
    def _etapa(cls, v: str) -> str:
        if v not in motor.STAGES:
            raise ValueError(f"etapa debe ser una de {list(motor.STAGES)}")
        return v

    @field_validator("campo")
    @classmethod
    def _campo(cls, v: dict | None) -> dict | None:
        if not v:
            return v
        for key, value in v.items():
            kind = motor.KNOWN_VARIABLES.get(key)
            if kind is None:
                raise ValueError(f"campo.{key}: variable desconocida. Válidas: {sorted(motor.KNOWN_VARIABLES)}")
            if value is None:
                continue
            if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError(f"campo.{key} debe ser numérico")
            if key == "soil_texture" and value not in motor.VALID_TEXTURES:
                raise ValueError(f"campo.soil_texture debe ser una de {sorted(motor.VALID_TEXTURES)}")
            if kind == "list":
                if not isinstance(value, list) or any(s not in SYMPTOMS for s in value):
                    raise ValueError(f"campo.{key} debe ser una lista con valores de {sorted(SYMPTOMS)}")
        return v

    @field_validator("historial")
    @classmethod
    def _historial(cls, v: list[list[str]] | None) -> list[list[str]] | None:
        for i, cycle in enumerate(v or []):
            bad = [c for c in cycle if c not in ROTATION_CROPS]
            if bad:
                raise ValueError(f"historial[{i}]: cultivos desconocidos {bad}. Válidos: {sorted(ROTATION_CROPS)}")
        return v

    @model_validator(mode="after")
    def _una_sola_serie(self):
        if self.serie_nasa_power and self.serie_csv:
            raise ValueError("Envíe serie_nasa_power o serie_csv, no ambas.")
        return self


class EvaluacionResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    referencia_cliente: str | None
    lat: float
    lon: float
    grid_id: str
    celda_lat: float
    celda_lon: float
    distancia_celda_km: float
    cultivo: str
    etapa: str
    agricola: bool
    estado: str
    hallazgos: int
    riesgo_global: str
    version_motor: str
    version_cuaderno: str | None


class EvaluacionOut(EvaluacionResumen):
    entrada: dict[str, Any]
    resultado: dict[str, Any] = Field(description="Salida completa del motor (payload para el agente).")


class EvaluacionLista(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EvaluacionResumen]
