"""PostgreSQL: cada evaluación del motor se guarda completa (JSONB) junto con columnas indexadas para consultar."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Evaluacion(Base):
    __tablename__ = "evaluaciones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    referencia_cliente: Mapped[str | None] = mapped_column(String(128), index=True)

    # Ubicación pedida y celda de la grilla (~1 km²) donde cayó
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    grid_id: Mapped[str] = mapped_column(String(16), index=True)
    celda_lat: Mapped[float] = mapped_column(Float)
    celda_lon: Mapped[float] = mapped_column(Float)
    distancia_celda_km: Mapped[float] = mapped_column(Float)

    # Contexto y resumen del resultado (para filtrar sin abrir el JSON)
    cultivo: Mapped[str] = mapped_column(String(32))
    etapa: Mapped[str] = mapped_column(String(32))
    agricola: Mapped[bool] = mapped_column(Boolean)
    estado: Mapped[str] = mapped_column(String(32))
    hallazgos: Mapped[int] = mapped_column(Integer)
    riesgo_global: Mapped[str] = mapped_column(String(16), index=True)
    version_motor: Mapped[str] = mapped_column(String(16))
    version_cuaderno: Mapped[str | None] = mapped_column(String(32))

    entrada: Mapped[dict] = mapped_column(JSONB)      # lo que envió el frontend
    resultado: Mapped[dict] = mapped_column(JSONB)    # salida completa del motor (payload del agente)

    __table_args__ = (
        Index("ix_evaluaciones_cultivo_etapa", "cultivo", "etapa"),
        Index("ix_evaluaciones_celda_lat_lon", "celda_lat", "celda_lon"),
        # Permite consultas por contenido: resultado @> '{"inference": {"status": "findings_generated"}}'
        Index("ix_evaluaciones_resultado_gin", "resultado", postgresql_using="gin",
              postgresql_ops={"resultado": "jsonb_path_ops"}),
    )


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    with SessionLocal() as session:
        yield session
