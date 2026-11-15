"""
SPACE WANDERERS — Motor agronómico 4.1
======================================
Un solo programa + un cuaderno de conocimiento + los datos reales del territorio.

  motor_agronomico_v41.py                   este archivo: motor + interfaz + autopruebas
  cuaderno_agronomico_unificado_2.3.json    afirmaciones, reglas, interacciones, prácticas,
                                            parámetros y fuentes externas
  territorial_canonical_unified.json        datos REALES procesados por el equipo de datos
                                            (NDVI Sentinel-2, lluvia GPM / NASA POWER / IDEAM, suelos IGAC)
  territorial_index_v41.json                índice compacto por celda; el motor lo genera solo la primera vez

Ejecutar la interfaz:       streamlit run motor_agronomico_v41.py
Ejecutar las autopruebas:   python motor_agronomico_v41.py --selftest
Construir el índice:        python motor_agronomico_v41.py --build-index
Evaluar un punto (JSON):    python motor_agronomico_v41.py --punto 6.6425 -76.075 --cultivo maiz --etapa vegetativo

Qué cambia en la 4.1 respecto a la 3.1 (las reglas y su lógica no cambian: cambia de dónde salen los datos)
  * SIN DATOS SINTÉTICOS: la interfaz ya no tiene sliders con valores inventados ni series simuladas.
    Las variables salen del bundle territorial, de una serie diaria real que se cargue, o de lo que
    se mida u observe en el lote. (El generador de series queda solo para las autopruebas.)
  * EL LOTE SE UBICA EN LA GRILLA: por coordenadas → celda más cercana (≈ 1 km²).
  * VARIABLES CON INCERTIDUMBRE: el IGAC describe clases («reacción muy fuerte a fuertemente ácida»,
    fase «f2», piso «templado»). El motor las lee como INTERVALOS (pH 4.5–5.5, pendiente 50–75 %,
    1000–2000 msnm) y evalúa en tres estados: se cumple con todo el intervalo, no se cumple con
    nada, o «no se puede decidir con este dato».
  * CONSENSO ENTRE FUENTES: GPM y NASA POWER miden la misma lluvia y discrepan; una regla solo se
    activa si se cumple con ambas.
  * LO QUE NO HAY, NO SE INVENTA: el bundle no trae temperatura, humedad relativa, humedad del suelo,
    materia orgánica ni series diarias. Las reglas que los necesitan se informan como no evaluadas.
  * LLUVIA MENSUAL → SEMANAL: se usa el equivalente semanal del acumulado mensual, marcado como
    estimación; los hallazgos que dependen de él quedan con certeza «baja».
  * PROCEDENCIA REAL en la Vista del Porqué: fuente, producto, periodo, método y calidad de cada dato.
  * ANTIGÜEDAD: si los datos tienen más de 45 días, el motor lo advierte.
  * VISTA TERRITORIAL (B2G): cuántas celdas y hectáreas aproximadas activan cada regla en un radio.

Qué incorpora la 3.1 respecto a la 2.1 (la lógica de la 2.1 se conserva intacta)
  * CUADERNO 2.3: 85 reglas de alerta, 117 de rotación, 86 interacciones y 76 prácticas.
  * AUDITORÍA EN DOS NIVELES: errores (rompen la lógica) y advertencias (trazabilidad incompleta).
  * REGLAS EN CUARENTENA: una regla mal escrita se aparta y se informa; no tumba al resto.
  * VISTA DEL PORQUÉ: cada hallazgo dice qué dato lo activó, con qué valor, contra qué umbral
    y de qué fuente prevista (NASA / IGAC / campo) vendría ese dato.
  * REVISIÓN DOCUMENTAL ≠ VALIDACIÓN EN CAMPO: los nuevos estados del cuaderno se reconocen,
    pero la certeza sigue topada en «media» hasta que un técnico valide la regla.
  * INTERACCIONES ROBUSTAS: suma neta de modificadores (no depende del orden), salvaguardas
    (delta 0) y la misma evidencia no se cuenta dos veces.
  * SEÑALES QUE SE PRECISAN: enlaza la regla general con la específica que la contiene.
  * ROTACIÓN AMPLIADA: plátano y Las Tres Hermanas como candidatos, herencia de exclusiones a los
    sistemas asociados, cobertura muerta / quema del rastrojo, pendiente, reglas del lote y
    orientaciones generales separadas de las razones que deciden.
  * PRÁCTICAS PRIORIZADAS y con su evidencia bibliográfica.
  * DATOS REALES: lee series diarias de NASA POWER (JSON) o de un CSV, además de la serie sintética.
  * SEMÁFORO por módulo para la vista del agricultor.

Qué incorpora la 2.1 respecto a la 0.5
  * TIEMPO: series de días (con huecos y errores) y reglas de persistencia,
    alternancia, acumulación y tendencia.
  * CALIDAD DE DATOS: limpieza, cobertura mínima y datos insuficientes declarados.
  * REGLAS QUE SE HABLAN: unas reemplazan a otras (supersede), otras suben o bajan
    la confianza (modifier) y otras se combinan en una síntesis (synthesis).
  * CERTEZA VISIBLE: ningún resultado figura como «alta» hasta que un técnico valide la regla.
  * REVISIÓN TÉCNICA: hoja de revisión descargable y validaciones cargables.
  * CUADERNO APROVECHADO: prácticas contextuales, conocimiento por cultivo/etapa/altitud
    y panel de cobertura.
  * ROTACIÓN integrada, y pendiente del lote como segunda variable de contexto.

Prototipo educativo y experimental: no sustituye análisis de suelo, diagnóstico
fitopatológico ni asesoría agronómica local. No calcula dosis de fertilizantes.
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

VERSION = "4.1.0"
SCHEMA_VERSION = "4.1.0"
ENGINE_NAME = "space_wanderers_agronomic_engine"
NOTEBOOK_CANDIDATES = ("cuaderno_agronomico_unificado_2.3.json", "cuaderno_agronomico.json")


def _default_notebook_path() -> Path:
    """El cuaderno vive junto al motor. Se prefiere el unificado 2.3; el 2.1 sigue siendo legible."""
    for name in NOTEBOOK_CANDIDATES:
        path = Path(__file__).with_name(name)
        if path.exists():
            return path
    return Path(__file__).with_name(NOTEBOOK_CANDIDATES[0])


NOTEBOOK_PATH = _default_notebook_path()

# =====================================================================
# 1. VOCABULARIO
# =====================================================================
CROPS = {
    "tres_hermanas": "Sistema Tres Hermanas (maíz + fríjol + calabaza)",
    "maiz": "Maíz",
    "frijol": "Fríjol común",
    "calabaza": "Calabaza / ahuyama",
    "caupi": "Fríjol caupí",
    "platano": "Plátano",
    "cana_panelera": "Caña panelera",
    "canavalia": "Canavalia (abono verde)",
    "otro": "Otro / no especificado",
}
STAGES = {
    "no_especificada": "No especificada",
    "establecimiento": "Establecimiento / emergencia",
    "vegetativo": "Crecimiento vegetativo",
    "floracion": "Floración",
    "fructificacion": "Formación de frutos / vainas",
    "llenado": "Llenado",
    "maduracion": "Maduración",
}
# Un sistema compuesto activa lo de todos sus cultivos componentes.
CROP_EXPANSION = {"tres_hermanas": {"tres_hermanas", "maiz", "frijol", "calabaza"}}

VALID_TEXTURES = {"Arenosa", "Franca", "Arcillosa"}
VALID_SEVERITIES = {"low", "medium", "high"}
VALID_CONFIDENCE = {"low", "moderate", "high"}
SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
VALID_THRESHOLD_BASIS = {"claim", "claim_partial", "engine_heuristic", "engine_heuristic_no_universal", "none"}
# Estados que pone un técnico agropecuario (validación en campo).
FIELD_VALIDATION_STATUS = {"sin_validar", "validada", "ajustar", "rechazada"}
# Estados de revisión DOCUMENTAL del cuaderno 2.3: alguien comprobó que las fuentes respaldan el
# principio general. NO equivalen a validación en campo: la certeza sigue topada en «media».
DOCUMENTARY_STATUS = {
    "revision_documental_con_fuentes_externas": "revisión documental con fuentes externas",
    "verificada_principio_general": "principio general verificado en la fuente",
}
VALID_VALIDATION_STATUS = FIELD_VALIDATION_STATUS | set(DOCUMENTARY_STATUS)

# Variables que pueden usar las reglas de alerta (tipo).
# --- 8 variables del usuario + contexto del lote ---
KNOWN_VARIABLES = {
    "temperature": "number", "relative_humidity": "number", "rain_7d": "number",
    "soil_moisture": "number", "soil_ph": "number", "organic_matter": "number",
    "soil_texture": "category", "symptoms": "list",
    "altitude_masl": "number", "slope_pct": "number",
    # --- variables reales del bundle territorial que el cuaderno aún no usa (listas para nuevas reglas) ---
    "ndvi": "number",                       # NDVI medio del periodo (Sentinel-2)
    "rain_month": "number",                 # lluvia acumulada del periodo mensual (mm)
    # --- variables derivadas de una serie temporal (requieren «Serie temporal») ---
    "sat_days_consecutive": "number",       # días seguidos con humedad del suelo > 80 %
    "dry_days_consecutive": "number",       # días seguidos con lluvia < 1 mm
    "tmin_mean_7d": "number",               # temperatura mínima media de 7 días
    "hot_days_7d": "number",                # días con Tmáx ≥ 32 °C en 7 días
    "wet_dry_alternations_14d": "number",   # alternancias lluvia/seco en 14 días
    "rain_last14": "number",                # lluvia de los últimos 14 días
    "rain_prev14": "number",                # lluvia de los 14 días anteriores
}
TEMPORAL_FEATURES = {
    "sat_days_consecutive", "dry_days_consecutive", "tmin_mean_7d", "hot_days_7d",
    "wet_dry_alternations_14d", "rain_last14", "rain_prev14",
}
VARIABLE_LABELS = {
    "altitude_masl": "Altitud del lote", "slope_pct": "Pendiente del lote",
    "sat_days_consecutive": "Días seguidos con suelo saturado (serie temporal)",
    "dry_days_consecutive": "Días secos consecutivos (serie temporal)",
    "tmin_mean_7d": "Temperatura mínima media de 7 días (serie temporal)",
    "hot_days_7d": "Días calurosos en 7 días (serie temporal)",
    "wet_dry_alternations_14d": "Alternancias lluvia/seco en 14 días (serie temporal)",
    "rain_last14": "Lluvia de los últimos 14 días (serie temporal)",
    "rain_prev14": "Lluvia de los 14 días anteriores (serie temporal)",
}
BASE_LABELS = {
    "temperature": "Temperatura del aire (°C)", "relative_humidity": "Humedad relativa (%)",
    "rain_7d": "Lluvia de los últimos 7 días (mm)", "soil_moisture": "Humedad del suelo (%)",
    "soil_ph": "pH del suelo", "organic_matter": "Materia orgánica (%)",
    "soil_texture": "Textura del suelo", "symptoms": "Síntomas observados",
    "ndvi": "NDVI (vigor de la vegetación)", "rain_month": "Lluvia acumulada del mes (mm)",
}


def var_label(var: str) -> str:
    return VARIABLE_LABELS.get(var) or BASE_LABELS.get(var, var)


# VISTA DEL PORQUÉ: de dónde vendría cada dato en la arquitectura del proyecto (espacio + tierra).
# Es la fuente PREVISTA: en el modo «Foto» el valor lo escribe el usuario, y el motor lo dice.
PLANNED_DATA_SOURCES = {
    "temperature": ("NASA POWER (T2M) · MODIS / ECOSTRESS (temperatura superficial)", "satélite / reanálisis"),
    "relative_humidity": ("NASA POWER (RH2M)", "reanálisis"),
    "rain_7d": ("GPM IMERG · NASA POWER (PRECTOTCORR)", "satélite"),
    "soil_moisture": ("SMAP · NASA POWER (GWETROOT)", "satélite"),
    "soil_ph": ("IGAC (estudio de suelos) o análisis de suelo del lote", "suelo local"),
    "organic_matter": ("IGAC (estudio de suelos) o análisis de suelo del lote", "suelo local"),
    "soil_texture": ("IGAC (estudio de suelos) o análisis de suelo del lote", "suelo local"),
    "symptoms": ("Observación directa del agricultor o del técnico", "campo"),
    "altitude_masl": ("SRTM (modelo de elevación)", "satélite"),
    "slope_pct": ("SRTM (pendiente derivada) · IGAC (geomorfología)", "satélite / suelo local"),
    "sat_days_consecutive": ("SMAP · NASA POWER (GWETROOT), serie diaria", "satélite"),
    "dry_days_consecutive": ("GPM IMERG · NASA POWER (PRECTOTCORR), serie diaria", "satélite"),
    "tmin_mean_7d": ("NASA POWER (T2M_MIN) · MODIS (temperatura nocturna), serie diaria", "satélite / reanálisis"),
    "hot_days_7d": ("NASA POWER (T2M_MAX), serie diaria", "reanálisis"),
    "wet_dry_alternations_14d": ("GPM IMERG · NASA POWER (PRECTOTCORR), serie diaria", "satélite"),
    "rain_last14": ("GPM IMERG · NASA POWER (PRECTOTCORR), serie diaria", "satélite"),
    "rain_prev14": ("GPM IMERG · NASA POWER (PRECTOTCORR), serie diaria", "satélite"),
    "ndvi": ("Sentinel-2 L2A (NDVI mensual)", "satélite"),
    "rain_month": ("GPM IMERG · NASA POWER (PRECTOTCORR) · IDEAM", "satélite / estación"),
}
OP_TEXT = {"lt": "<", "lte": "≤", "gt": ">", "gte": "≥", "eq": "=", "neq": "≠", "in": "en",
           "contains": "incluye", "contains_any": "incluye alguno de", "contains_all": "incluye todos"}

OPERATORS = {
    "lt": lambda a, b: a < b, "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b, "gte": lambda a, b: a >= b,
    "eq": lambda a, b: a == b, "neq": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: b in a,
    "contains_any": lambda a, b: any(i in a for i in b),
    "contains_all": lambda a, b: all(i in a for i in b),
}
LIST_OPERATORS = {"contains", "contains_any", "contains_all"}
NUMERIC_OPERATORS = {"lt", "lte", "gt", "gte"}


# ---------------------------------------------------------------------
# Valores con incertidumbre (datos reales que llegan como clase o desde varias fuentes)
# ---------------------------------------------------------------------
class Range(NamedTuple):
    """Número del que solo se conoce un intervalo: [lo, hi) —o [lo, hi] si closed—.

    Es lo que entrega una clase cartográfica del IGAC («fuertemente ácida» = pH 5.0–5.5) o dos
    fuentes que miden lo mismo (lluvia según GPM y según NASA POWER)."""
    lo: float
    hi: float
    closed: bool = False

    def text(self) -> str:
        return f"{self.lo:g} a {self.hi:g}"


class OneOf(frozenset):
    """Categoría de la que solo se conoce un conjunto de posibilidades («texturas finas a medias»)."""

    def text(self) -> str:
        return " o ".join(sorted(self))


def is_uncertain(value) -> bool:
    return isinstance(value, (Range, OneOf))


def show_value(value) -> str:
    """Texto legible de un valor del motor (número, intervalo, conjunto, lista…)."""
    if is_uncertain(value):
        return value.text()
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v) for v in value) or "ninguno"
    return str(value)


def jsonable(obj):
    """Copia serializable a JSON: los intervalos y conjuntos se escriben de forma explícita."""
    if isinstance(obj, Range):
        return {"min": obj.lo, "max": obj.hi, "max_inclusive": obj.closed, "text": obj.text()}
    if isinstance(obj, OneOf):
        return {"one_of": sorted(obj), "text": obj.text()}
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(jsonable(v) for v in obj)
    return obj


def compare_uncertain(value, op: str, ref) -> bool | None:
    """Compara un intervalo o un conjunto con el umbral de una regla.

    True  = la condición se cumple para TODOS los valores posibles.
    False = no se cumple para NINGUNO.
    None  = depende de cuál sea el valor real: el dato no alcanza para decidir.
    """
    if isinstance(value, OneOf):
        if op in ("eq", "neq"):
            hit = True if value == {ref} else False if ref not in value else None
            return hit if op == "eq" or hit is None else not hit
        if op == "in":
            return True if value <= set(ref) else False if not (value & set(ref)) else None
        return None
    lo, hi, closed = value
    if lo == hi:                                             # intervalo degenerado: es un número
        return OPERATORS[op](lo, ref) if op in OPERATORS and op not in LIST_OPERATORS else None
    below_all = hi < ref or (hi == ref and not closed)      # todo el intervalo está por debajo del umbral
    if op == "lt":
        return True if below_all else False if lo >= ref else None
    if op == "lte":
        return True if hi <= ref else False if lo > ref else None
    if op == "gt":
        return True if lo > ref else False if hi <= ref else None
    if op == "gte":
        return True if lo >= ref else False if below_all else None
    if op in ("eq", "neq"):
        outside = ref < lo or ref > hi or (ref == hi and not closed)
        return (op == "neq") if outside else None
    return None


def thermal_floor(altitude_masl) -> str | None:
    """Clasificación altitudinal clásica (Caldas). Solo informativa."""
    if altitude_masl is None:
        return None
    if isinstance(altitude_masl, Range):
        floors = []
        for alt in (altitude_masl.lo, altitude_masl.hi - (0 if altitude_masl.closed else 1)):
            name = thermal_floor(alt)
            if name not in floors:
                floors.append(name)
        return " a ".join(floors)
    if altitude_masl < 1000:
        return "cálido"
    if altitude_masl < 2000:
        return "templado"
    if altitude_masl < 3000:
        return "frío"
    return "páramo"


# =====================================================================
# 2. CONDICIONES: evaluación de TRES estados (True / False / None = desconocido)
# =====================================================================
def eval3(cond: dict, ctx: dict) -> tuple[bool | None, set[str]]:
    """Evalúa una condición declarativa. Devuelve (resultado, variables_faltantes).

    Un dato desconocido NUNCA se trata como «no aplica»: si no se puede decidir,
    el resultado es None y se informa qué variable faltó.
    """
    if "all" in cond:
        results = [eval3(c, ctx) for c in cond["all"]]
        if any(r is False for r, _ in results):
            return False, set()
        missing = set().union(*(m for _, m in results))
        return (None, missing) if any(r is None for r, _ in results) else (True, set())
    if "any" in cond:
        results = [eval3(c, ctx) for c in cond["any"]]
        if any(r is True for r, _ in results):
            return True, set()
        missing = set().union(*(m for _, m in results))
        return (None, missing) if any(r is None for r, _ in results) else (False, set())
    if "not" in cond:
        r, m = eval3(cond["not"], ctx)
        return (None, m) if r is None else (not r, set())
    value = ctx.get(cond["var"])
    if value is None:
        return None, {cond["var"]}
    if is_uncertain(value):                                  # dato real conocido solo como intervalo o conjunto
        result = compare_uncertain(value, cond["op"], cond["value"])
        return (None, {cond["var"]}) if result is None else (result, set())
    return OPERATORS[cond["op"]](value, cond["value"]), set()


def explain_condition(cond: dict, ctx: dict) -> list[dict]:
    """VISTA DEL PORQUÉ: las comparaciones concretas que hicieron verdadera una condición.

    Devuelve, para cada dato decisivo, su valor observado, el umbral de la regla y la fuente
    prevista del dato. No interpreta nada: solo muestra lo que el motor comparó.
    """
    out: list[dict] = []

    def walk(c: dict, want: bool) -> None:
        if eval3(c, ctx)[0] is not want:
            return
        if "all" in c or "any" in c:
            for child in c.get("all", c.get("any", [])):
                walk(child, want)
        elif "not" in c:
            walk(c["not"], not want)
        else:
            source, kind = PLANNED_DATA_SOURCES.get(c["var"], ("no especificada", "no especificada"))
            out.append({
                "variable": c["var"], "label": var_label(c["var"]), "observed": ctx.get(c["var"]),
                "operator": OP_TEXT.get(c["op"], c["op"]) if want else "no " + OP_TEXT.get(c["op"], c["op"]),
                "threshold": c["value"], "planned_source": source, "source_kind": kind,
            })

    try:
        walk(cond, True)
    except (KeyError, TypeError):
        return []
    return out


def condition_vars(cond: dict) -> set[str]:
    if "all" in cond or "any" in cond:
        return set().union(*(condition_vars(c) for c in cond.get("all", cond.get("any", []))))
    if "not" in cond:
        return condition_vars(cond["not"])
    return {cond["var"]}


def _validate_condition(cond, path: str, errors: list[str], known: dict) -> None:
    if not isinstance(cond, dict):
        errors.append(f"{path}: la condición debe ser un objeto JSON.")
        return
    combinators = [k for k in ("all", "any", "not") if k in cond]
    if len(combinators) > 1:
        errors.append(f"{path}: mezcla combinadores {combinators}; use uno por nivel.")
        return
    if combinators:
        key = combinators[0]
        if key == "not":
            _validate_condition(cond["not"], f"{path}.not", errors, known)
        else:
            children = cond[key]
            if not isinstance(children, list) or not children:
                errors.append(f"{path}.{key}: debe ser una lista no vacía.")
                return
            for i, child in enumerate(children):
                _validate_condition(child, f"{path}.{key}[{i}]", errors, known)
        return
    missing = [k for k in ("var", "op", "value") if k not in cond]
    if missing:
        errors.append(f"{path}: faltan campos {missing}.")
        return
    var, op, value = cond["var"], cond["op"], cond["value"]
    if var not in known:
        errors.append(f"{path}: variable desconocida '{var}'.")
        return
    if op not in OPERATORS:
        errors.append(f"{path}: operador desconocido '{op}'.")
        return
    kind = known[var]
    if kind == "list" and op not in LIST_OPERATORS:
        errors.append(f"{path}: '{var}' es una lista; use contains / contains_any / contains_all.")
    if kind != "list" and op in LIST_OPERATORS:
        errors.append(f"{path}: el operador '{op}' solo aplica a listas (variable '{var}').")
    if kind == "bool" and op not in ("eq", "neq"):
        errors.append(f"{path}: '{var}' es booleana; use eq o neq.")
    if op in NUMERIC_OPERATORS and (isinstance(value, bool) or not isinstance(value, (int, float))):
        errors.append(f"{path}: '{op}' requiere un valor numérico.")
    if op in ("in", "contains_any", "contains_all") and not isinstance(value, list):
        errors.append(f"{path}: '{op}' requiere una lista como valor.")
    if var == "soil_texture" and op in ("eq", "neq") and value not in VALID_TEXTURES:
        errors.append(f"{path}: textura '{value}' no válida (use {sorted(VALID_TEXTURES)}).")


# =====================================================================
# 3. ROTACIÓN: vocabulario
# =====================================================================
ROT_CROPS = {
    "maiz": ("Maíz", "Poaceae"),
    "frijol": ("Fríjol común", "Fabaceae"),
    "caupi": ("Fríjol caupí", "Fabaceae"),
    "calabaza": ("Calabaza / ahuyama", "Cucurbitaceae"),
    "canavalia": ("Canavalia (abono verde)", "Fabaceae"),
    "cana_panelera": ("Caña panelera", "Poaceae"),
    "platano": ("Plátano", "Musaceae"),
    "tres_hermanas": ("Las Tres Hermanas (maíz + fríjol + calabaza)", "mixed"),
}
# Un sistema asociado se evalúa como sistema y, además, hereda las exclusiones de sus componentes.
ROT_COMPONENTS = {"tres_hermanas": ["maiz", "frijol", "calabaza"]}
MIXED_FAMILY = "mixed"
HISTORY_EXTRA = {"otro": "Otro cultivo (sin reglas)"}
FAMILIES = {"Poaceae": "Gramíneas", "Fabaceae": "Leguminosas", "Cucurbitaceae": "Cucurbitáceas", "Musaceae": "Musáceas"}
FAMILY_LABELS = {**FAMILIES, MIXED_FAMILY: "Asociación de varias familias"}
ROT_VARS = {
    "candidate_crop": "category", "candidate_family": "category",
    "last_crops": "list", "last_families": "list", "same_family_as_last": "bool",
    "altitude_masl": "number", "slope_pct": "number", "residue_management": "category",
    "recent_n_fertilization": "category", "waterlogging_prone": "bool",
}
CANDIDATE_VARS = {"candidate_crop", "candidate_family", "same_family_as_last"}
ROT_ENUMS = {
    "candidate_crop": set(ROT_CROPS), "candidate_family": set(FAMILIES),
    "last_crops": set(ROT_CROPS) | set(HISTORY_EXTRA), "last_families": set(FAMILIES),
    "residue_management": {"incorporated", "removed", "surface_mulch", "burned"},
    "recent_n_fertilization": {"none_or_low", "high"},
}
ROT_EFFECTS = {"block", "discourage", "favor", "note"}
ROT_VAR_LABELS = {
    "altitude_masl": "Altitud del lote (msnm)",
    "slope_pct": "Pendiente del lote (%)",
    "residue_management": "Manejo del rastrojo del último ciclo",
    "recent_n_fertilization": "Fertilización nitrogenada reciente",
    "waterlogging_prone": "Si el lote es propenso a encharcamiento",
    "same_family_as_last": "Cultivos del último ciclo clasificados por familia",
}
ROT_STATUS_ORDER = {"favorecido": 0, "aceptable": 1, "con_reservas": 2, "desaconsejado": 3, "sin_evaluar": 4}
VERIFY_BEFORE_ACTING = [
    "Aptitud del cultivo para la zona del lote (zonificaciones de UPRA a escala 1:100.000).",
    "Análisis de suelo del lote (pH, materia orgánica, textura y nutrientes).",
    "Revisión de un técnico agropecuario local antes de decidir.",
]

# =====================================================================
# 4. VALIDACIÓN DEL CUADERNO
# =====================================================================
ALERT_REQUIRED = [
    "id", "module", "title", "when", "severity", "confidence", "message", "recommendation",
    "cautions", "evidence_basis", "evidence_status", "threshold_basis", "validation",
]
ROT_REQUIRED = ["id", "title", "effect", "when", "message", "cautions", "threshold_basis", "validation"]
SECTIONS = ["claims", "alert_rules", "rotation_rules", "interactions", "practices", "parameters"]


def _check_enums(cond, path: str, errors: list[str]) -> None:
    if not isinstance(cond, dict):
        return
    for key in ("all", "any"):
        if key in cond and isinstance(cond[key], list):
            for i, child in enumerate(cond[key]):
                _check_enums(child, f"{path}.{key}[{i}]", errors)
    if "not" in cond:
        _check_enums(cond["not"], f"{path}.not", errors)
    if {"var", "op", "value"} <= set(cond):
        allowed = ROT_ENUMS.get(cond["var"])
        if allowed is None:
            return
        values = cond["value"] if isinstance(cond["value"], list) else [cond["value"]]
        for v in values:
            if v not in allowed:
                errors.append(f"{path}: valor '{v}' no válido para '{cond['var']}' (use {sorted(allowed)}).")


def _check_validation_block(rule: dict, where: str, errors: list[str]) -> None:
    v = rule.get("validation")
    if not isinstance(v, dict) or v.get("status") not in VALID_VALIDATION_STATUS:
        errors.append(f"{where}: bloque 'validation' inválido (status debe estar en {sorted(VALID_VALIDATION_STATUS)}).")


def _check_context(applies: dict, where: str, errors: list[str]) -> None:
    for crop in applies.get("crops", []):
        if crop not in CROPS:
            errors.append(f"{where}: cultivo desconocido '{crop}' en applies_to.")
    for stage in applies.get("stages", []):
        if stage not in STAGES:
            errors.append(f"{where}: etapa desconocida '{stage}' en applies_to.")


def reference_registry(nb: dict) -> dict[str, dict]:
    """Fichas de las fuentes externas del cuaderno: external_sources (SRC_xxx, respaldan alertas e
    interacciones) y la bibliografía de las prácticas. Los dos espacios de IDs no se mezclan."""
    meta = nb.get("meta", {})
    registry: dict[str, dict] = {}
    for s in meta.get("external_sources", []) or []:
        registry[s["id"]] = {"id": s["id"], "title": s.get("title", ""), "publisher": s.get("publisher", ""),
                             "url": s.get("url", ""), "kind": "external_source"}
    for b in (meta.get("practices_expansion", {}) or {}).get("bibliography", []) or []:
        registry[b["id"]] = {"id": b["id"], "title": b.get("citation", ""), "publisher": "",
                             "url": b.get("url", ""), "kind": "practice_bibliography"}
    return registry


def claim_usage(nb: dict) -> dict[str, set[str]]:
    """Qué elementos usan cada afirmación: lo que declara used_by MÁS lo que de verdad la cita.
    Así la cobertura no depende de que el cuaderno tenga used_by al día."""
    usage = {c["claim_id"]: set(c.get("used_by", [])) for c in nb["claims"]}
    for section in ("alert_rules", "rotation_rules", "interactions", "practices", "parameters"):
        for e in nb[section]:
            for cid in e.get("source_claim_ids", []):
                if cid in usage:
                    usage[cid].add(e["id"])
    return usage


def validate_notebook(nb: dict) -> list[str]:
    """Devuelve errores legibles. Lista vacía = cuaderno coherente. (Las advertencias: audit_notebook.)"""
    return audit_notebook(nb)["errors"]


def audit_notebook(nb: dict) -> dict:
    """Auditoría del cuaderno en dos niveles.

    errors   : rompen la lógica del motor (IDs repetidos, variables u operadores desconocidos,
               referencias a reglas que no existen…).
    warnings : no impiden evaluar, pero la trazabilidad está incompleta (used_by desactualizado,
               fuentes citadas sin ficha, evidencia duplicada, prácticas sin contexto…).
    """
    errors: list[str] = []
    warnings: list[str] = []
    for section in SECTIONS:
        if not isinstance(nb.get(section), list):
            errors.append(f"El cuaderno debe contener la lista '{section}'.")
    if errors:
        return {"errors": errors, "warnings": warnings}
    registry = reference_registry(nb)

    # --- IDs únicos entre TODAS las secciones ---
    ids: dict[str, str] = {}
    for section in SECTIONS:
        for e in nb[section]:
            eid = e.get("claim_id", e.get("id"))
            if eid in ids:
                errors.append(f"[{eid}]: ID repetido (en '{ids[eid]}' y '{section}').")
            ids[eid] = section

    alert_ids = {r["id"] for r in nb["alert_rules"] if "id" in r}
    synth_ids = {i["id"] for i in nb["interactions"] if i.get("type") == "synthesis"}
    finding_ids = alert_ids | synth_ids

    # --- reglas de alerta ---
    for r in nb["alert_rules"]:
        w = f"[{r.get('id', '?')}]"
        for f in ALERT_REQUIRED:
            if f not in r:
                errors.append(f"{w}: falta el campo obligatorio '{f}'.")
        if r.get("severity") not in VALID_SEVERITIES:
            errors.append(f"{w}: severidad inválida '{r.get('severity')}'.")
        if r.get("confidence") not in VALID_CONFIDENCE:
            errors.append(f"{w}: confianza inválida '{r.get('confidence')}'.")
        if r.get("threshold_basis") not in VALID_THRESHOLD_BASIS:
            errors.append(f"{w}: threshold_basis inválido '{r.get('threshold_basis')}'.")
        if "cautions" in r and not isinstance(r["cautions"], list):
            errors.append(f"{w}: 'cautions' debe ser una lista.")
        _check_context(r.get("applies_to", {}), w, errors)
        _check_validation_block(r, w, errors)
        if "when" in r:
            _validate_condition(r["when"], f"{w}.when", errors, KNOWN_VARIABLES)
        lost = [sid for sid in r.get("external_source_ids", []) if sid not in registry]
        if lost:
            warnings.append(f"{w}: cita fuentes externas sin ficha en el cuaderno: {', '.join(lost)}.")

    # --- reglas de rotación ---
    for r in nb["rotation_rules"]:
        w = f"[{r.get('id', '?')}]"
        for f in ROT_REQUIRED:
            if f not in r:
                errors.append(f"{w}: falta el campo obligatorio '{f}'.")
        if r.get("effect") not in ROT_EFFECTS:
            errors.append(f"{w}: efecto inválido '{r.get('effect')}'.")
        if r.get("threshold_basis") not in VALID_THRESHOLD_BASIS:
            errors.append(f"{w}: threshold_basis inválido '{r.get('threshold_basis')}'.")
        _check_validation_block(r, w, errors)
        if "when" in r:
            _validate_condition(r["when"], f"{w}.when", errors, ROT_VARS)
            _check_enums(r["when"], f"{w}.when", errors)

    # --- interacciones ---
    for i in nb["interactions"]:
        w = f"[{i.get('id', '?')}]"
        t = i.get("type")
        if t == "supersede":
            for k in ("winners", "losers"):
                for rid in i.get(k, []):
                    if rid not in finding_ids:
                        errors.append(f"{w}: {k} referencia '{rid}', que no es una regla de alerta ni una síntesis.")
            if not i.get("winners") or not i.get("losers"):
                errors.append(f"{w}: supersede requiere 'winners' y 'losers'.")
        elif t == "modifier":
            if i.get("target") not in finding_ids:
                errors.append(f"{w}: target '{i.get('target')}' no existe.")
            if not i.get("when_any") and not i.get("when_all"):
                errors.append(f"{w}: modifier requiere when_any o when_all.")
            for rid in i.get("when_any", []) + i.get("when_all", []):
                if rid not in finding_ids:
                    errors.append(f"{w}: condición referencia '{rid}', que no existe.")
            if isinstance(i.get("delta"), bool) or i.get("delta") not in (-2, -1, 0, 1, 2):
                errors.append(f"{w}: delta debe ser -2, -1, 0 (salvaguarda), 1 o 2.")
        elif t == "synthesis":
            for f in ("title", "severity", "confidence", "message", "recommendation", "cautions", "when_all"):
                if f not in i:
                    errors.append(f"{w}: falta el campo obligatorio '{f}'.")
            if i.get("severity") not in VALID_SEVERITIES:
                errors.append(f"{w}: severidad inválida.")
            if i.get("confidence") not in VALID_CONFIDENCE:
                errors.append(f"{w}: confianza inválida.")
            for rid in i.get("when_all", []) + i.get("when_any", []):
                if rid not in alert_ids:
                    errors.append(f"{w}: componente '{rid}' no es una regla de alerta.")
        else:
            errors.append(f"{w}: tipo de interacción inválido '{t}'.")
    seen_mods: dict[tuple, str] = {}
    for i in nb["interactions"]:
        if i.get("type") != "modifier":
            continue
        key = (i.get("target"), i.get("delta"), tuple(sorted(i.get("when_any", []))), tuple(sorted(i.get("when_all", []))))
        if key in seen_mods:
            warnings.append(f"[{i.get('id', '?')}]: repite la misma evidencia que {seen_mods[key]} "
                            "(mismo objetivo, delta y disparadores); el motor la cuenta una sola vez.")
        else:
            seen_mods[key] = i.get("id", "?")

    # --- prácticas ---
    for p in nb["practices"]:
        w = f"[{p.get('id', '?')}]"
        for f in ("id", "title", "text", "cautions", "applies_to", "trigger_findings"):
            if f not in p:
                errors.append(f"{w}: falta el campo obligatorio '{f}'.")
        _check_context(p.get("applies_to", {}), w, errors)
        for rid in p.get("trigger_findings", []):
            if rid not in finding_ids:
                errors.append(f"{w}: trigger_findings referencia '{rid}', que no existe.")
        if p.get("when"):
            _validate_condition(p["when"], f"{w}.when", errors, KNOWN_VARIABLES)
        ap = p.get("applies_to", {})
        if not p.get("trigger_findings") and not p.get("when") and not ap.get("crops") and not ap.get("stages"):
            warnings.append(f"{w}: práctica sin disparadores ni cultivo o etapa: se mostrará siempre, como orientación general.")

    # --- referencias cruzadas con las afirmaciones (simétricas) ---
    claims = {c["claim_id"]: c for c in nb["claims"]}
    element_claims = {}
    for section in ("alert_rules", "rotation_rules", "interactions", "practices", "parameters"):
        for e in nb[section]:
            element_claims[e["id"]] = set(e.get("source_claim_ids", []))
    uncatalogued: dict[str, int] = {}
    for eid, cids in element_claims.items():
        for c in cids:
            if c in claims:
                if eid not in claims[c].get("used_by", []):
                    warnings.append(f"[{eid}]: cita a {c}, pero {c} no lista a {eid} en used_by.")
            elif c.startswith("CLAIM_"):
                errors.append(f"[{eid}]: referencia a la afirmación inexistente '{c}'.")
            elif c not in registry:                     # p. ej. FAO_…, MINAMBIENTE_… en las reglas de rotación
                uncatalogued[c] = uncatalogued.get(c, 0) + 1
    for ref, n in sorted(uncatalogued.items()):
        warnings.append(f"[{ref}]: referencia documental citada por {n} elemento(s) sin ficha en el cuaderno "
                        "(no es una afirmación ni una fuente externa catalogada).")
    usage = claim_usage(nb)
    for c in claims.values():
        for eid in c.get("used_by", []):
            if eid not in element_claims:
                errors.append(f"[{c['claim_id']}]: used_by referencia al elemento inexistente '{eid}'.")
            elif c["claim_id"] not in element_claims[eid]:
                warnings.append(f"[{c['claim_id']}]: lista a {eid}, pero {eid} no cita a {c['claim_id']}.")
        if c.get("implementation_status") == "implemented" and not usage[c["claim_id"]]:
            errors.append(f"[{c['claim_id']}]: marcada como 'implemented' pero ningún elemento la usa.")
    return {"errors": errors, "warnings": warnings}


def load_notebook(path: str | Path = NOTEBOOK_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def param(nb: dict, name: str, default=None):
    """Lee un parámetro del cuaderno (con respaldo en una afirmación)."""
    for p in nb.get("parameters", []):
        if p["name"] == name:
            return p["value"]
    return default

# =====================================================================
# 5. TIEMPO: SERIES DE DÍAS, CALIDAD DE DATOS Y VARIABLES DERIVADAS
# =====================================================================
# Cada día es un dict con: tmax, tmin (°C), rh (%), rain (mm), soil_moisture (% de saturación).
# El día más reciente va al FINAL de la lista. Cualquier valor puede ser None (hueco).
SERIES_VARS = ["tmax", "tmin", "rh", "rain", "soil_moisture"]
VALID_RANGES = {
    "tmax": (-10.0, 50.0), "tmin": (-10.0, 40.0), "rh": (0.0, 100.0),
    "rain": (0.0, 500.0), "soil_moisture": (0.0, 100.0),
}
SCENARIOS = {
    "normal": "Tiempo normal",
    "sequia": "Sequía (veranillo)",
    "lluviosa": "Temporada lluviosa persistente",
    "transicion": "Transición de lluvioso a seco con calor",
    "alternancia": "Alternancia de periodos húmedos y secos",
    "noches_calidas": "Noches cálidas",
    "ola_calor": "Ola de calor al final de la serie",
    "encharcamiento": "Lluvias torrenciales y suelo saturado",
}
MIN_COVERAGE = 0.7          # fracción mínima de días válidos en una ventana para calcular una variable
SAT_THRESHOLD = 80.0        # % de saturación (afirmación 37)
HOT_TMAX = 32.0             # °C (mismo umbral de CLIMATE_001)


def _scenario_params(name: str, d: int, n: int):
    """(prob_lluvia, lluvia_media_mm, dT, dHR, dRango, lluvia_minima_mm) para el día d de n."""
    if name == "normal":
        return 0.35, 9.0, 0.0, 0.0, 0.0, 0.0
    if name == "sequia":
        return 0.03, 4.0, 3.0, -15.0, 0.0, 0.0
    if name == "lluviosa":
        return 0.85, 16.0, -1.0, 12.0, 0.0, 0.0
    if name == "transicion":
        return (0.85, 16.0, -1.0, 12.0, 0.0, 0.0) if d < n / 2 else (0.03, 4.0, 4.0, -12.0, 0.0, 0.0)
    if name == "alternancia":
        return (0.95, 14.0, -0.5, 10.0, 0.0, 6.0) if (d // 3) % 2 == 0 else (0.02, 3.0, 3.0, -10.0, 0.0, 0.0)
    if name == "noches_calidas":
        return 0.35, 9.0, 3.0, 0.0, -5.0, 0.0
    if name == "ola_calor":
        return (0.0, 0.0, 7.0, -15.0, 4.0, 0.0) if d >= n - 5 else (0.35, 9.0, 0.0, 0.0, 0.0, 0.0)
    if name == "encharcamiento":
        return (1.0, 15.0, 0.0, 10.0, 0.0, 15.0) if d >= n - 6 else (0.35, 9.0, 0.0, 0.0, 0.0, 0.0)
    raise ValueError(f"Escenario desconocido: {name}")


def generate_series(n_days: int = 30, scenario: str = "normal", tmean: float = 22.0,
                    diurnal_range: float = 10.0, rh_base: float = 75.0, soil_start: float = 50.0,
                    noise: float = 1.0, gap_pct: float = 0.0, outlier_pct: float = 0.0,
                    seed: int = 7) -> list[dict]:
    """Serie diaria SINTÉTICA y reproducible (misma semilla = misma serie).

    gap_pct   : % de valores que se pierden (huecos, como en un sensor o una API reales).
    outlier_pct: % de días con un valor imposible (error de sensor).
    """
    rng = random.Random(seed)
    sm = soil_start
    series: list[dict] = []
    for d in range(n_days):
        p_rain, rain_mean, dT, dRH, dRange, rain_min = _scenario_params(scenario, d, n_days)
        rain = 0.0
        if rain_mean > 0 and rng.random() < p_rain:
            rain = round(rain_min + rng.expovariate(1.0 / rain_mean), 1)
        tm = tmean + dT + rng.gauss(0, noise)
        rng_day = max(2.0, diurnal_range + dRange + rng.gauss(0, noise * 0.5))
        tmax, tmin = tm + rng_day / 2, tm - rng_day / 2
        rh = min(100.0, max(20.0, rh_base + dRH + (8.0 if rain > 0 else -3.0) + rng.gauss(0, 2 * noise)))
        et = max(0.5, 2.5 + 0.12 * (tmax - 25.0))             # pérdida diaria en puntos de saturación
        sm = min(100.0, max(0.0, sm + 0.8 * rain - et))       # 1 mm de lluvia ≈ +0.8 puntos
        series.append({"tmax": round(tmax, 1), "tmin": round(tmin, 1), "rh": round(rh, 1),
                       "rain": rain, "soil_moisture": round(sm, 1)})
    for day in series:
        for var in SERIES_VARS:
            if rng.random() < gap_pct / 100.0:
                day[var] = None
    bad = {"tmax": 61.0, "tmin": -25.0, "rh": 135.0, "rain": -5.0, "soil_moisture": 140.0}
    for day in series:
        if rng.random() < outlier_pct / 100.0:
            var = rng.choice(SERIES_VARS)
            if day[var] is not None:
                day[var] = bad[var]
    return series


def tmean_day(day: dict) -> float | None:
    if day.get("tmax") is None or day.get("tmin") is None:
        return None
    return (day["tmax"] + day["tmin"]) / 2.0


def adjust_series_altitude(series: list[dict], cell_altitude: float, lot_altitude: float,
                           lapse_c_per_100m: float) -> tuple[list[dict], float]:
    """Corrige la temperatura de una celda grande (p. ej. de un satélite) a la altitud del lote.

    Devuelve (serie_corregida, grados_de_corrección). El gradiente sale del cuaderno
    (afirmación 29: ~0.6 °C por cada 100 m).
    """
    delta = -lapse_c_per_100m * (lot_altitude - cell_altitude) / 100.0
    out = []
    for d in series:
        d2 = dict(d)
        for var in ("tmax", "tmin"):
            if d2.get(var) is not None:
                d2[var] = round(d2[var] + delta, 1)
        out.append(d2)
    return out, round(delta, 2)


# ---------------------------------------------------------------------
# Datos reales: NASA POWER (JSON) y CSV
# ---------------------------------------------------------------------
# El motor NO descarga nada: recibe el archivo que ya bajó el equipo de datos (ETL).
POWER_PARAMS = {"tmax": ["T2M_MAX"], "tmin": ["T2M_MIN"], "rh": ["RH2M"],
                "rain": ["PRECTOTCORR", "PRECTOT"], "soil_moisture": ["GWETROOT", "GWETTOP"]}
CSV_ALIASES = {
    "tmax": {"tmax", "t2m_max", "temp_max", "temperatura_maxima"},
    "tmin": {"tmin", "t2m_min", "temp_min", "temperatura_minima"},
    "rh": {"rh", "rh2m", "hr", "humedad_relativa"},
    "rain": {"rain", "prectotcorr", "prectot", "lluvia", "precipitacion"},
    "soil_moisture": {"soil_moisture", "gwetroot", "gwettop", "humedad_suelo"},
}
CSV_DATE_COLUMNS = {"date", "fecha", "dia", "day"}


def series_from_nasa_power(payload: dict) -> tuple[list[dict], dict]:
    """Convierte la respuesta JSON diaria de NASA POWER (un punto) en una serie del motor.

    Espera `properties.parameter` con T2M_MAX, T2M_MIN, RH2M, PRECTOTCORR y GWETROOT (o GWETTOP).
    El valor de relleno de POWER (-999) se convierte en hueco. GWET* viene como fracción 0–1 y se
    pasa a % de saturación. Lo que falte queda como hueco: no se inventa.
    """
    params = payload.get("properties", {}).get("parameter")
    if not isinstance(params, dict) or not params:
        raise ValueError("El archivo no tiene la estructura de NASA POWER (falta properties.parameter).")
    fill = payload.get("header", {}).get("fill_value", -999.0)
    chosen, absent = {}, []
    for var, codes in POWER_PARAMS.items():
        code = next((c for c in codes if isinstance(params.get(c), dict)), None)
        if code is None:
            absent.append(var)
        chosen[var] = code
    dates = sorted({d for code in chosen.values() if code for d in params[code]})
    series = []
    for d in dates:
        day = {}
        for var, code in chosen.items():
            v = params[code].get(d) if code else None
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v == fill or v <= -900 or math.isnan(v):
                v = None
            elif var == "soil_moisture":
                v = round(v * 100.0, 1)
            day[var] = v
        series.append(day)
    info = {"source": "NASA POWER", "n_days": len(series), "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None, "parameters_used": chosen, "variables_absent": absent}
    return series, info


def series_from_csv(text: str) -> tuple[list[dict], dict]:
    """Lee una serie diaria desde un CSV (separado por coma o punto y coma; decimales con punto o coma).

    Columnas reconocidas (en cualquier orden): tmax, tmin, rh, rain, soil_moisture y, opcional, date/fecha.
    Si hay columna de fecha, se ordena por ella; el día más reciente queda al final.
    """
    text = text.lstrip("﻿")
    first = text.split("\n", 1)[0]
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if first.count(";") > first.count(",") else ",")
    if not reader.fieldnames:
        raise ValueError("El CSV está vacío.")
    columns, date_col = {}, None
    for name in reader.fieldnames:
        key = (name or "").strip().lower()
        if key in CSV_DATE_COLUMNS:
            date_col = name
        for var, aliases in CSV_ALIASES.items():
            if key in aliases and var not in columns:
                columns[var] = name
    if not columns:
        raise ValueError("El CSV no tiene ninguna columna reconocida (tmax, tmin, rh, rain, soil_moisture).")

    def num(raw):
        raw = (raw or "").strip().replace(",", ".")
        try:
            v = float(raw)
        except ValueError:
            return None
        return None if math.isnan(v) or v <= -900 else v

    rows = list(reader)
    if date_col:
        rows.sort(key=lambda r: (r.get(date_col) or "").strip())
    series = [{var: (num(r.get(columns[var])) if var in columns else None) for var in SERIES_VARS} for r in rows]
    info = {"source": "CSV", "n_days": len(series), "columns_used": columns,
            "first_date": (rows[0].get(date_col) or "").strip() if date_col and rows else None,
            "last_date": (rows[-1].get(date_col) or "").strip() if date_col and rows else None,
            "variables_absent": [v for v in SERIES_VARS if v not in columns]}
    return series, info


# ---------------------------------------------------------------------
# Calidad de datos
# ---------------------------------------------------------------------
def clean_series(series: list[dict]) -> tuple[list[dict], dict]:
    """Quita valores imposibles y devuelve (serie_limpia, informe_de_calidad).

    No inventa datos: lo que se descarta queda como hueco (None) y se informa.
    """
    cleaned = [dict(d) for d in series]
    removed, inconsistent = [], []
    for i, d in enumerate(cleaned):
        for var, (lo, hi) in VALID_RANGES.items():
            v = d.get(var)
            if v is not None and not (lo <= v <= hi):
                removed.append({"day": i, "variable": var, "value": v})
                d[var] = None
        if d.get("tmax") is not None and d.get("tmin") is not None and d["tmin"] > d["tmax"]:
            inconsistent.append({"day": i, "tmax": d["tmax"], "tmin": d["tmin"]})
            d["tmax"] = d["tmin"] = None

    stuck = []
    for var in ("tmax", "tmin", "rh"):          # un sensor «pegado» repite el mismo valor
        run_start, run_len, prev = 0, 0, object()
        for i, d in enumerate(cleaned + [{var: object()}]):
            v = d.get(var)
            if v is not None and v == prev:
                run_len += 1
            else:
                if run_len >= 5:
                    stuck.append({"variable": var, "start_day": run_start, "length": run_len})
                run_start, run_len, prev = i, 1, v

    n = len(cleaned)
    def cov(days):
        if not days:
            return {v: 0.0 for v in SERIES_VARS}
        return {v: round(sum(1 for d in days if d.get(v) is not None) / len(days), 3) for v in SERIES_VARS}
    coverage, coverage_14 = cov(cleaned), cov(cleaned[-14:])
    overall = round(sum(coverage_14.values()) / len(coverage_14), 3)
    flags = []
    if removed:
        flags.append(f"{len(removed)} valor(es) imposibles descartados.")
    if inconsistent:
        flags.append(f"{len(inconsistent)} día(s) con temperatura mínima mayor que la máxima descartados.")
    if stuck:
        flags.append(f"{len(stuck)} posible(s) sensor(es) con valor repetido 5 días o más (no se descartan: revisar).")
    if overall < MIN_COVERAGE:
        flags.append("Cobertura de los últimos 14 días inferior a 70 %: varias variables derivadas no se calcularán.")
    return cleaned, {
        "n_days": n, "coverage": coverage, "coverage_last14": coverage_14, "overall_coverage_last14": overall,
        "removed_out_of_range": removed, "inconsistent_days": inconsistent, "possible_stuck_sensors": stuck,
        "flags": flags,
    }


# ---------------------------------------------------------------------
# Variables derivadas de la serie
# ---------------------------------------------------------------------
def _tail(series, n):
    return series[-n:] if len(series) >= 1 else []


def _valid(vals):
    return [v for v in vals if v is not None]


def _scaled_sum(vals, window, min_cov=MIN_COVERAGE):
    """Suma de una ventana; si faltan días la reescala proporcionalmente (y exige cobertura mínima)."""
    v = _valid(vals)
    if len(vals) < window or len(v) / window < min_cov:
        return None
    return sum(v) * window / len(v)


def count_alternations(rains: list, min_run: int = 2, wet_mm: float = 5.0, dry_mm: float = 1.0) -> int:
    """Cuenta cambios entre periodos lluviosos (≥ wet_mm) y secos (< dry_mm) de al menos min_run días.

    Definición OPERATIVA del motor: el documento fuente (afirmación 61) describe la
    alternancia pero no fija cantidades.
    """
    labels = []
    for r in rains:
        if r is None:
            labels.append(None)
        elif r >= wet_mm:
            labels.append("W")
        elif r < dry_mm:
            labels.append("D")
        else:
            labels.append("N")
    runs, cur, length = [], None, 0
    for lab in labels + [None]:
        if lab == cur and lab in ("W", "D"):
            length += 1
        else:
            if cur in ("W", "D") and length >= min_run:
                runs.append(cur)
            cur, length = lab, (1 if lab in ("W", "D") else 0)
    return sum(1 for a, b in zip(runs, runs[1:]) if a != b)


def growing_degree_days(series: list[dict], tbase: float, tcap: float) -> float | None:
    """Grados-día acumulados con tope superior (afirmación 29). Informativo."""
    total, valid = 0.0, 0
    for d in series:
        if d.get("tmax") is None or d.get("tmin") is None:
            continue
        valid += 1
        total += max(0.0, (min(d["tmax"], tcap) + max(d["tmin"], tbase)) / 2.0 - tbase)
    if not series or valid / len(series) < MIN_COVERAGE:
        return None
    return round(total, 1)


def compute_features(series: list[dict], crop: str | None = None, nb: dict | None = None) -> tuple[dict, dict]:
    """Calcula las variables que usan las reglas a partir de una serie ya limpia.

    Devuelve (variables, motivos). Una variable queda en None (no se inventa) cuando la
    cobertura de su ventana es insuficiente; `motivos` explica por qué.
    """
    f: dict = {}
    why: dict = {}
    n = len(series)

    def need(name, cond, reason):
        if not cond:
            f[name] = None
            why[name] = reason
        return cond

    # --- las variables «de foto», ahora derivadas de la serie ---
    tm3 = _valid([tmean_day(d) for d in _tail(series, 3)])
    f["temperature"] = round(sum(tm3) / len(tm3), 1) if len(tm3) >= 2 else None
    if f["temperature"] is None:
        why["temperature"] = "menos de 2 días válidos entre los últimos 3"
    rh3 = _valid([d.get("rh") for d in _tail(series, 3)])
    f["relative_humidity"] = round(sum(rh3) / len(rh3), 1) if len(rh3) >= 2 else None
    if f["relative_humidity"] is None:
        why["relative_humidity"] = "menos de 2 días válidos entre los últimos 3"
    r7 = _scaled_sum([d.get("rain") for d in _tail(series, 7)], 7)
    f["rain_7d"] = round(r7, 1) if r7 is not None else None
    if r7 is None:
        why["rain_7d"] = "menos de 5 días válidos entre los últimos 7"
    sm = _valid([d.get("soil_moisture") for d in _tail(series, 2)])
    f["soil_moisture"] = sm[-1] if sm else None
    if not sm:
        why["soil_moisture"] = "sin dato de humedad del suelo en los últimos 2 días"

    # --- persistencia (hacia atrás desde el último día; un hueco corta la cuenta: cota inferior) ---
    last = series[-1] if series else {}
    if need("sat_days_consecutive", last.get("soil_moisture") is not None, "sin humedad del suelo en el último día"):
        cnt = 0
        for d in reversed(series):
            v = d.get("soil_moisture")
            if v is None or v <= SAT_THRESHOLD:
                break
            cnt += 1
        f["sat_days_consecutive"] = cnt
    if need("dry_days_consecutive", last.get("rain") is not None, "sin dato de lluvia en el último día"):
        cnt = 0
        for d in reversed(series):
            v = d.get("rain")
            if v is None or v >= 1.0:
                break
            cnt += 1
        f["dry_days_consecutive"] = cnt

    # --- ventanas ---
    tmin7 = [d.get("tmin") for d in _tail(series, 7)]
    if need("tmin_mean_7d", len(tmin7) >= 7 and len(_valid(tmin7)) / 7 >= MIN_COVERAGE, "cobertura insuficiente de Tmín en 7 días"):
        v = _valid(tmin7)
        f["tmin_mean_7d"] = round(sum(v) / len(v), 1)
    tmax7 = [d.get("tmax") for d in _tail(series, 7)]
    if need("hot_days_7d", len(tmax7) >= 7 and len(_valid(tmax7)) / 7 >= MIN_COVERAGE, "cobertura insuficiente de Tmáx en 7 días"):
        f["hot_days_7d"] = sum(1 for v in _valid(tmax7) if v >= HOT_TMAX)
    rain14 = [d.get("rain") for d in _tail(series, 14)]
    if need("wet_dry_alternations_14d", len(rain14) >= 14 and len(_valid(rain14)) / 14 >= MIN_COVERAGE, "cobertura insuficiente de lluvia en 14 días"):
        f["wet_dry_alternations_14d"] = count_alternations(rain14)
    if n >= 28:
        last14 = _scaled_sum([d.get("rain") for d in series[-14:]], 14)
        prev14 = _scaled_sum([d.get("rain") for d in series[-28:-14]], 14)
    else:
        last14 = prev14 = None
    for name, v in (("rain_last14", last14), ("rain_prev14", prev14)):
        f[name] = round(v, 1) if v is not None else None
        if v is None:
            why[name] = "se necesitan 28 días y cobertura suficiente de lluvia en cada ventana de 14 días"

    # --- informativo: grados-día del cultivo (no activa reglas) ---
    f["gdd_total"] = None
    if nb is not None and crop:
        tbases = param(nb, "gdd_base_temp_c", {})
        tcap = param(nb, "gdd_tmax_cap_c", 35)
        key = "maiz" if crop == "tres_hermanas" else crop
        if key in tbases:
            f["gdd_total"] = growing_degree_days(series, tbases[key], tcap)
    return f, why

# =====================================================================
# 5b. TERRITORIO: DATOS REALES  (bundle canónico → índice compacto → entradas del motor)
# =====================================================================
# El bundle `territorial_canonical_unified.json` (≈ 800 MB) agrupa, sobre una grilla maestra de
# celdas, lo que el equipo de datos ya procesó: NDVI (Sentinel-2), lluvia mensual (GPM IMERG,
# NASA POWER y estaciones IDEAM) y el estudio de suelos del IGAC (texto por unidad cartográfica).
#
# El motor NO inventa lo que el bundle no trae. Lo que sí hace:
#   * lee cada dato con su fuente, periodo y bandera de calidad;
#   * traduce las CLASES del IGAC (reacción, textura, fase de pendiente, piso térmico) a los
#     intervalos que esas clases definen → variables de tipo Range / OneOf, no números falsos;
#   * cuando dos fuentes miden lo mismo (GPM y POWER), usa el intervalo entre ambas: una regla
#     solo se activa si se cumple con las dos;
#   * lo que falta (temperatura, humedad relativa, humedad del suelo, serie diaria, síntomas)
#     queda SIN DATO y las reglas que lo necesitan se informan como no evaluadas.
TERRITORIAL_BUNDLE_NAME = "territorial_canonical_unified.json"
TERRITORIAL_INDEX_NAME = "territorial_index_v41.json"
TERRITORIAL_INDEX_SCHEMA = "space_wanderers_territorial_index/1"
SOIL_FIELDS = [
    "soil_unit_code", "soil_unit_phase", "soil_characteristics_text", "soil_climate_class", "soil_landscape",
    "soil_relief", "soil_parent_material", "soil_taxonomic_components", "soil_component_percentages_text",
    "soil_profile_reference",
]
NON_AGRICULTURAL = {"Cuerpo de agua", "Zona urbana", "Misceláneo rocoso"}
# Nivel de calidad de cada variable (alimenta la certeza): 3 = dato directo válido,
# 2 = derivado de una clase cartográfica (intervalo), 1 = estimado por cambio de resolución temporal.
QUALITY_DIRECT, QUALITY_CLASS, QUALITY_ESTIMATED = 3, 2, 1
STALE_DATA_DAYS = 45

# --- Clases de reacción del suelo (Soil Survey Manual; son las que usa el IGAC en sus leyendas) ---
PH_ACID = {"extremad": (3.5, 4.5), "muy fuerte": (4.5, 5.0), "fuerte": (5.0, 5.5), "moderad": (5.5, 6.0), "liger": (6.0, 6.5)}
PH_NEUTRAL = (6.5, 7.3)
PH_ALKALINE = {"liger": (7.3, 7.8), "moderad": (7.8, 8.4), "fuerte": (8.4, 9.0), "muy fuerte": (9.0, 10.0), "extremad": (9.0, 10.0)}
_PH_INTENSITY = ("extremad", "muy fuerte", "fuerte", "moderad", "liger")
_REACTION_TOKEN = re.compile(r"extremad\w*|muy\s+fuerte\w*|fuerte\w*|moderad\w*|liger\w*|neutr\w*|ácid\w*|alcalin\w*")
# --- Familias texturales del IGAC → las tres categorías que usan las reglas del cuaderno ---
TEXTURE_ORDINAL = {"gruesa": 1, "moderadamente gruesa": 2, "media": 3, "moderadamente fina": 4, "fina": 5, "muy fina": 6}
TEXTURE_CATEGORY = {1: "Arenosa", 2: "Franca", 3: "Franca", 4: "Franca", 5: "Arcillosa", 6: "Arcillosa"}
_TEXTURE_TOKEN = re.compile(r"muy\s+finas?|moderadamente[,\s]+finas?|moderadamente[,\s]+gruesas?|moderadamente(?=\s*(?:,|$))|finas?|medias?|gruesas?")
_TEXTURE_END = r"(?:reacci|fertilidad|erosi|saturaci|alto contenido|inunda|encharc|algunos|a veces|con fragmento|con substrato|material|$)"
# --- Fases cartográficas del IGAC: letra = clase de pendiente (%), dígito = grado de erosión ---
SLOPE_CLASSES = {"a": (0, 3), "b": (3, 7), "c": (7, 12), "d": (12, 25), "e": (25, 50), "f": (50, 75), "g": (75, 150)}
EROSION_DEGREE = {1: "ligera", 2: "moderada", 3: "severa", 4: "muy severa"}
PHASE_MODIFIERS = {"p": "pedregosa", "r": "rocosa", "i": "inundable"}
# --- Pisos térmicos (franjas altitudinales, msnm) ---
THERMAL_FLOORS = [("muy frío", (3000, 3600)), ("frío", (2000, 3000)), ("templado", (1000, 2000)), ("cálido", (0, 1000))]


def parse_reaction(text: str) -> Range | None:
    """«reacción muy fuerte a fuertemente ácida» → Range(4.5, 5.5). None si el texto no la describe."""
    low = (text or "").lower()
    m = re.search(r"reacci[oó]n(.*?)(?:fertilidad|erosi[oó]n|$)", low, re.S)
    if m:
        phrase = re.split(r"[;.]", m.group(1))[0]
    else:
        phrase = next((c for c in re.split(r"[,;.]", low) if re.search(r"ácid|alcalin", c) and "satur" not in c), None)
    if not phrase:
        return None
    pending, spans = [], []
    for tok in _REACTION_TOKEN.findall(phrase):
        tok = re.sub(r"\s+", " ", tok)
        if tok.startswith("ácid"):
            spans += [PH_ACID[k] for k in pending]
            pending = []
        elif tok.startswith("alcalin"):
            spans += [PH_ALKALINE[k] for k in pending]
            pending = []
        elif tok.startswith("neutr"):
            spans.append(PH_NEUTRAL)
        else:
            pending.append(next(k for k in _PH_INTENSITY if tok.startswith(k)))
    if not spans:
        return None
    return Range(min(s[0] for s in spans), max(s[1] for s in spans))


def parse_texture(text: str):
    """«texturas finas a medias» → OneOf({Arcillosa, Franca}); «texturas medias» → "Franca"; «variadas» → None."""
    low = (text or "").lower()
    m = re.search(r"textura\w*(.*?)" + _TEXTURE_END, low, re.S)
    if not m:
        return None
    phrase = m.group(1)
    ords = set()
    for tok in _TEXTURE_TOKEN.findall(phrase):
        tok = re.sub(r"[,\s]+", " ", tok).strip()
        tok = " ".join(w[:-1] if w.endswith("s") else w for w in tok.split())
        ords.add(TEXTURE_ORDINAL.get(tok, 4))               # «moderadamente» suelto: se toma como moderadamente fina
    if not ords:
        return None
    if re.search(r"\ba\b", phrase):                           # «de … a …» es un rango: incluye lo intermedio
        ords = set(range(min(ords), max(ords) + 1))
    cats = {TEXTURE_CATEGORY[o] for o in ords}
    return next(iter(cats)) if len(cats) == 1 else OneOf(cats)


def parse_drainage(text: str, phase_modifiers: list[str] | None = None) -> tuple[str | None, bool | None]:
    """(descripción, propenso_a_encharcamiento). El segundo es None cuando la unidad mezcla suelos bien y mal drenados."""
    low = (text or "").lower()
    flood = bool(re.search(r"inunda|encharc|pantanos", low)) or "inundable" in (phase_modifiers or [])
    good = poor = False
    for clause in re.split(r"[,;.]", low):
        if "dren" in clause:
            good |= bool(re.search(r"\bbien\b|\bbuen|excesiv|moderad", clause))
            poor |= bool(re.search(r"pobre|imperfect|pantanos", clause))
    if not (good or poor or flood):
        return None, None
    label = ("drenaje variable (de bueno a pobre)" if good and poor else
             "drenaje pobre o imperfecto" if poor else "bien drenado" if good else "drenaje no descrito")
    if flood:
        return label + ", con inundaciones o encharcamiento", True
    return label, (True if poor and not good else False if good and not poor else None)


def parse_phase(phase: str, unit_code: str) -> dict:
    """«YAf2» → pendiente 50–75 % (clase f), erosión moderada (grado 2)."""
    suffix = phase[len(unit_code):] if phase and unit_code and phase.startswith(unit_code) else ""
    m = re.fullmatch(r"([a-g])([a-z]*)(\d?)", suffix)
    if not m:
        return {"slope": None, "slope_class": None, "erosion_degree": None, "modifiers": []}
    return {"slope": Range(*SLOPE_CLASSES[m.group(1)]), "slope_class": m.group(1),
            "erosion_degree": int(m.group(3)) if m.group(3) else None,
            "modifiers": [PHASE_MODIFIERS[c] for c in m.group(2) if c in PHASE_MODIFIERS]}


def parse_climate(text: str) -> tuple[Range | None, list[str]]:
    """«Templado húmedo a muy húmedo» → (Range(1000, 2000), ["templado"])."""
    rest, floors, spans = (text or "").lower(), [], []
    for name, span in THERMAL_FLOORS:                         # «muy frío» antes que «frío»
        if name in rest:
            floors.append(name)
            spans.append(span)
            rest = rest.replace(name, " ")
    if not spans:
        return None, []
    return Range(min(s[0] for s in spans), max(s[1] for s in spans)), floors


def parse_soil_unit(unit: dict) -> dict:
    """Todo lo que el motor puede leer de una unidad de suelos del IGAC."""
    text = unit.get("soil_characteristics_text") or ""
    agricultural = text not in NON_AGRICULTURAL and bool(text)
    phase = parse_phase(unit.get("soil_unit_phase") or "", unit.get("soil_unit_code") or "")
    altitude, floors = parse_climate(unit.get("soil_climate_class") or "")
    low = text.lower()
    drainage, prone = parse_drainage(text, phase["modifiers"]) if agricultural else (None, None)
    fert = re.search(r"fertilidad\s+(?:es\s+)?(.*?)(?:,|;|\.|\s+erosi|$)", low)
    aluminum = None
    if re.search(r"(?:alta|alto contenido y|alto contenido de)\s+(?:saturación de\s+)?aluminio|saturación de aluminio alta", low):
        aluminum = "alta en parte de la unidad" if re.search(r"algunos|baja y alta", low) else "alta"
    return {
        "agricultural": agricultural,
        "soil_ph": parse_reaction(text) if agricultural else None,
        "soil_texture": parse_texture(text) if agricultural else None,
        "slope_pct": phase["slope"], "slope_class": phase["slope_class"],
        "erosion_degree": phase["erosion_degree"], "phase_modifiers": phase["modifiers"],
        "altitude_masl": altitude, "thermal_floors": floors,
        "drainage": drainage, "waterlogging_prone": prone,
        "fertility": re.sub(r"\s+y$", "", fert.group(1).strip()) if fert else None, "aluminum_saturation": aluminum,
        "depth": re.split(r"[,;]", text)[0].strip() if agricultural else None,
    }


# ---------------------------------------------------------------------
# Índice compacto
# ---------------------------------------------------------------------
def _latest(records: list[dict]) -> tuple[str | None, str | None, int]:
    """(inicio, fin, registros_de_otros_periodos): si el bundle trae varios meses, se usa el más reciente."""
    ends = [r["time_end"] for r in records if r.get("time_end")]
    if not ends:
        return None, None, 0
    end = max(ends)
    start = next(r.get("time_start") for r in records if r.get("time_end") == end)
    return start, end, sum(1 for e in ends if e != end)


def _cell_side_km(lats: list[float], lons: list[float]) -> float | None:
    """Lado típico de una celda: mediana de la distancia entre celdas de numeración consecutiva
    (vecinas dentro de una misma fila de la grilla maestra)."""
    steps = sorted(_km(lats[i], lons[i], lats[i + 1], lons[i + 1]) for i in range(len(lats) - 1))
    return steps[len(steps) // 2] if steps else None


def build_territorial_index(bundle: dict, source_info: dict | None = None) -> dict:
    """Reduce el bundle canónico (cientos de MB) a un índice por celda de pocos MB.

    No transforma ningún valor: solo reorganiza por celda, conserva fuente, periodo y bandera de
    calidad, y descarta lo que una bandera declara inválido (queda como hueco).
    """
    if bundle.get("schema") != "territorial_canonical_bundle" or not isinstance(bundle.get("variables"), dict):
        raise ValueError("El archivo no es un bundle territorial canónico (schema «territorial_canonical_bundle»).")
    variables = bundle["variables"]
    cells: dict[str, dict] = {}

    def cell(r: dict) -> dict:
        c = cells.get(r["grid_id"])
        if c is None:
            c = cells[r["grid_id"]] = {"lat": r["latitude"], "lon": r["longitude"], "rain": {}, "soil": {}}
        return c

    sources: dict = {"ndvi": None, "rain": {}, "soil": None}
    ignored = 0

    ndvi = [r for block in variables.get("ndvi", []) for r in block["data"]]
    start, end, other = _latest(ndvi)
    ignored += other
    for r in ndvi:
        if r.get("time_end") != end:
            continue
        c = cell(r)
        c["ndvi"] = r["value"] if r.get("quality_flag") == "valid" else None
        c["ndvi_cov"] = r.get("spatial_coverage")
        c["ndvi_scenes"] = r.get("valid_scene_count")
        if sources["ndvi"] is None:
            sources["ndvi"] = {"source": r.get("source"), "product": r.get("product"), "statistic": r.get("statistic"),
                               "period_start": start, "period_end": end}

    rain = [r for block in variables.get("precipitation_amount", []) for r in block["data"]]
    start, end, other = _latest(rain)
    ignored += other
    stations = []
    for r in rain:
        if r.get("time_end") != end:
            continue
        if r.get("spatial_support") == "station_point":
            usable = r.get("value") is not None and r.get("quality_flag") in ("valid", "preliminary")
            stations.append({"grid_id": r["grid_id"], "station_id": r.get("station_id"), "name": r.get("station_name"),
                             "lat": r["latitude"], "lon": r["longitude"], "value": r["value"] if usable else None,
                             "quality_flag": r.get("quality_flag"), "observed_days": r.get("observed_days"),
                             "expected_days": r.get("expected_days"), "source": r.get("source")})
            continue
        src = r.get("source") or "desconocida"
        cell(r)["rain"][src] = r["value"] if r.get("quality_flag") == "valid" else None
        if src not in sources["rain"]:
            sources["rain"][src] = {"product": r.get("product"), "version": r.get("version"), "unit": r.get("unit"),
                                    "statistic": r.get("statistic"), "geometry_status": r.get("geometry_status"),
                                    "period_start": start, "period_end": end}

    for block in variables.get("soil", []):
        for r in block["data"]:
            c = cell(r)
            c["soil"][r["variable"]] = r["value"]
            if r.get("quality_flag") != "valid":
                c["soil_partial"] = True
            if sources["soil"] is None:
                sources["soil"] = {"source": r.get("source"), "product": r.get("product")}

    ids = sorted(cells, key=lambda g: (0, int(g)) if g.isdigit() else (1, g))
    units: dict[tuple, int] = {}
    soil_idx = []
    for g in ids:
        s = cells[g]["soil"]
        if not s:
            soil_idx.append(-1)
            continue
        key = tuple(s.get(f) for f in SOIL_FIELDS)
        soil_idx.append(units.setdefault(key, len(units)))
    rain_sources = sorted(sources["rain"])
    lats, lons = [cells[g]["lat"] for g in ids], [cells[g]["lon"] for g in ids]
    side = _cell_side_km(lats, lons)
    cell_km2 = side * side if side else None

    def rnd(v, n):
        return None if v is None else round(v, n)

    return {
        "schema": TERRITORIAL_INDEX_SCHEMA, "engine_version": VERSION,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "bundle": {"schema_version": bundle.get("schema_version"), "generated_at_utc": bundle.get("generated_at_utc"),
                   "manifest": bundle.get("manifest", []), **(source_info or {})},
        "sources": sources, "records_from_older_periods_ignored": ignored,
        "n_cells": len(ids), "cell_km2": rnd(cell_km2, 3),
        "cells": {
            "id": ids, "lat": [rnd(v, 6) for v in lats], "lon": [rnd(v, 6) for v in lons],
            "ndvi": [rnd(cells[g].get("ndvi"), 4) for g in ids],
            "ndvi_cov": [rnd(cells[g].get("ndvi_cov"), 3) for g in ids],
            "ndvi_scenes": [cells[g].get("ndvi_scenes") for g in ids],
            "rain": {src: [rnd(cells[g]["rain"].get(src), 1) for g in ids] for src in rain_sources},
            "soil": soil_idx, "soil_partial": [1 if cells[g].get("soil_partial") else 0 for g in ids],
        },
        "soil_units": [list(k) for k in units],
        "stations": stations,
    }


_INDEX_CACHE: dict[str, dict] = {}


def _prepare_index(index: dict) -> dict:
    index["_pos"] = {g: i for i, g in enumerate(index["cells"]["id"])}
    index["_parsed"] = {}
    return index


def load_territorial_index(folder: str | Path | None = None, rebuild: bool = False, log=None) -> dict:
    """Devuelve el índice territorial. Lo construye (una sola vez, ~1 min) si no existe o si el bundle cambió."""
    folder = Path(folder) if folder else Path(__file__).parent
    bundle_path, index_path = folder / TERRITORIAL_BUNDLE_NAME, folder / TERRITORIAL_INDEX_NAME
    say = log or (lambda msg: None)
    fingerprint = None
    if bundle_path.exists():
        stat = bundle_path.stat()
        fingerprint = {"file": bundle_path.name, "size_bytes": stat.st_size, "mtime": int(stat.st_mtime)}
    key = str(index_path)
    if not rebuild and key in _INDEX_CACHE and (fingerprint is None or all(
            _INDEX_CACHE[key]["bundle"].get(k) == v for k, v in fingerprint.items())):
        return _INDEX_CACHE[key]
    if not rebuild and index_path.exists():
        with open(index_path, encoding="utf-8") as fh:
            index = json.load(fh)
        fresh = fingerprint is None or all(index.get("bundle", {}).get(k) == v for k, v in fingerprint.items())
        if index.get("schema") == TERRITORIAL_INDEX_SCHEMA and fresh:
            _INDEX_CACHE[key] = _prepare_index(index)
            return _INDEX_CACHE[key]
        say("El índice territorial no corresponde al bundle actual: se reconstruye.")
    if fingerprint is None:
        raise FileNotFoundError(f"No se encontró {TERRITORIAL_BUNDLE_NAME} ni un índice válido en {folder}.")
    say(f"Leyendo {bundle_path.name} ({fingerprint['size_bytes'] / 1e6:.0f} MB); esto ocurre una sola vez…")
    try:
        with open(bundle_path, encoding="utf-8") as fh:
            bundle = json.load(fh)
    except MemoryError as exc:
        raise MemoryError("No hay memoria suficiente para leer el bundle territorial completo. "
                          "Construya el índice en un equipo con más RAM y copie el archivo "
                          f"{TERRITORIAL_INDEX_NAME} junto al motor.") from exc
    index = build_territorial_index(bundle, fingerprint)
    del bundle
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, separators=(",", ":"))
    say(f"Índice territorial escrito: {index_path.name} ({index_path.stat().st_size / 1e6:.1f} MB, {index['n_cells']} celdas).")
    _INDEX_CACHE[key] = _prepare_index(index)
    return _INDEX_CACHE[key]


# ---------------------------------------------------------------------
# De la celda a las entradas del motor
# ---------------------------------------------------------------------
def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2.0))
    y = math.radians(lat2 - lat1)
    return 6371.0 * math.hypot(x, y)


def find_cell(index: dict, lat: float, lon: float) -> tuple[int, float]:
    """(posición de la celda más cercana, distancia en km a su centro)."""
    lats, lons = index["cells"]["lat"], index["cells"]["lon"]
    k = math.cos(math.radians(lat)) ** 2
    pos = min(range(len(lats)), key=lambda i: (lats[i] - lat) ** 2 + k * (lons[i] - lon) ** 2)
    return pos, _km(lat, lon, lats[pos], lons[pos])


def cells_within(index: dict, lat: float, lon: float, radius_km: float) -> list[int]:
    lats, lons = index["cells"]["lat"], index["cells"]["lon"]
    dlat = radius_km / 111.32
    return [i for i in range(len(lats)) if abs(lats[i] - lat) <= dlat and _km(lat, lon, lats[i], lons[i]) <= radius_km]


def _period_days(start: str | None, end: str | None) -> int | None:
    try:
        return max(1, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days)
    except (TypeError, ValueError):
        return None


def _period_label(start: str | None, end: str | None) -> str:
    return f"{start[:10]} a {end[:10]}" if start and end else "sin periodo declarado"


def territorial_inputs(index: dict, pos: int, now: datetime | None = None) -> dict:
    """Entradas del motor para una celda, cada una con su procedencia y su nivel de calidad.

    Devuelve {cell, agricultural, inputs, provenance, var_quality, context, notes, unavailable}.
    `inputs` solo contiene lo que el bundle realmente respalda; nada se rellena por defecto.
    """
    c, src = index["cells"], index["sources"]
    inputs, prov, quality, notes = {}, {}, {}, []

    def put(var, value, level, source, method, basis=None, period=None):
        if value is None:
            return
        inputs[var] = value
        quality[var] = level
        prov[var] = {"source": source, "method": method, "basis": basis, "period": period, "quality_level": level}

    # ---- suelo (IGAC) ----
    unit_i = c["soil"][pos]
    unit = dict(zip(SOIL_FIELDS, index["soil_units"][unit_i])) if unit_i >= 0 else {}
    parsed = index["_parsed"].get(unit_i)
    if parsed is None:
        parsed = index["_parsed"][unit_i] = parse_soil_unit(unit) if unit else {"agricultural": False}
    agricultural = bool(parsed.get("agricultural"))
    soil_src = " · ".join(str(v) for v in (src.get("soil") or {}).values() if v) or "IGAC"
    penalty = 1 if c["soil_partial"][pos] else 0
    if unit_i < 0:
        notes.append("La celda no tiene unidad de suelos del IGAC en el bundle.")
    elif not agricultural:
        notes.append(f"La celda está clasificada como «{unit.get('soil_characteristics_text')}»: no es un suelo agrícola.")
    else:
        if penalty:
            notes.append("La unidad de suelos cubre solo una parte de la celda (cobertura espacial parcial).")
        level = max(1, QUALITY_CLASS - penalty)
        text = unit["soil_characteristics_text"]
        put("soil_ph", parsed["soil_ph"], level, soil_src, "intervalo de la clase de reacción descrita por el IGAC", text)
        put("soil_texture", parsed["soil_texture"], level, soil_src, "familia textural descrita por el IGAC", text)
        put("slope_pct", parsed["slope_pct"], level, soil_src,
            f"clase de pendiente «{parsed['slope_class']}» de la fase cartográfica", unit["soil_unit_phase"])
        put("altitude_masl", parsed["altitude_masl"], level, soil_src,
            "franja altitudinal del piso térmico de la unidad climática", unit["soil_climate_class"])

    # ---- lluvia (varias fuentes) ----
    rain_values, rain_period, days = {}, None, None
    for name, meta in src.get("rain", {}).items():
        v = c["rain"].get(name, [None] * (pos + 1))[pos]
        if v is not None:
            rain_values[f"{name} ({meta.get('product')})"] = v
            rain_period = _period_label(meta.get("period_start"), meta.get("period_end"))
            days = _period_days(meta.get("period_start"), meta.get("period_end"))
    for st in index.get("stations", []):
        if st["grid_id"] == c["id"][pos] and st["value"] is not None:
            rain_values[f"{st['source']} estación {st['name']} ({st['quality_flag']})"] = st["value"]
    if rain_values:
        lo, hi = min(rain_values.values()), max(rain_values.values())
        detail = "; ".join(f"{k}: {v:.1f} mm" for k, v in rain_values.items())
        month = lo if lo == hi else Range(lo, hi, True)
        put("rain_month", month, QUALITY_DIRECT, " + ".join(rain_values), "acumulado del periodo; si hay varias fuentes, el intervalo entre ellas",
            detail, rain_period)
        if len(rain_values) > 1 and hi > 0 and (hi - lo) / hi > 0.25:
            notes.append(f"Las fuentes de lluvia discrepan {100 * (hi - lo) / hi:.0f} % en esta celda ({detail}).")
        if days:
            week = round(lo * 7.0 / days, 1) if lo == hi else Range(round(lo * 7.0 / days, 1), round(hi * 7.0 / days, 1), True)
            put("rain_7d", week, QUALITY_ESTIMATED, " + ".join(rain_values),
                f"equivalente semanal del acumulado de {days} días (reparto uniforme: NO es la lluvia de la última semana)",
                detail, rain_period)

    # ---- vegetación (NDVI) ----
    ndvi_meta = src.get("ndvi") or {}
    ndvi = c["ndvi"][pos]
    ndvi_period = _period_label(ndvi_meta.get("period_start"), ndvi_meta.get("period_end"))
    put("ndvi", ndvi, QUALITY_DIRECT, f"{ndvi_meta.get('source')} · {ndvi_meta.get('product')}",
        f"media del periodo ({c['ndvi_scenes'][pos]} escena(s) válidas, {100 * (c['ndvi_cov'][pos] or 0):.0f} % de la celda despejada)",
        None, ndvi_period)
    if ndvi is None:
        notes.append("Sin NDVI válido en el periodo (nubosidad o cobertura insuficiente).")

    # ---- antigüedad de los datos ----
    ends = [m.get("period_end") for m in list(src.get("rain", {}).values()) + [ndvi_meta] if m.get("period_end")]
    age_days = None
    if ends:
        try:
            age_days = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(max(ends))).days
        except (TypeError, ValueError):
            age_days = None
    if age_days is not None and age_days > STALE_DATA_DAYS:
        notes.append(f"Los datos de lluvia y vegetación terminan hace {age_days} días: describen ese periodo, no las condiciones de hoy.")

    context = {
        "soil_unit_code": unit.get("soil_unit_code"), "soil_unit_phase": unit.get("soil_unit_phase"),
        "soil_taxonomy": unit.get("soil_taxonomic_components"), "soil_description": unit.get("soil_characteristics_text"),
        "landscape": unit.get("soil_landscape"), "relief": unit.get("soil_relief"),
        "parent_material": unit.get("soil_parent_material"), "climate_class": unit.get("soil_climate_class"),
        "thermal_floors": parsed.get("thermal_floors", []), "depth": parsed.get("depth"),
        "drainage": parsed.get("drainage"), "waterlogging_prone": parsed.get("waterlogging_prone"),
        "fertility": parsed.get("fertility"), "aluminum_saturation": parsed.get("aluminum_saturation"),
        "erosion_degree": EROSION_DEGREE.get(parsed.get("erosion_degree")), "phase_modifiers": parsed.get("phase_modifiers", []),
        "rain_by_source_mm": rain_values, "rain_period": rain_period, "ndvi": ndvi, "ndvi_period": ndvi_period,
        "data_age_days": age_days,
    }
    unavailable = [v for v in ("temperature", "relative_humidity", "soil_moisture", "organic_matter", "symptoms") if v not in inputs]
    return {
        "cell": {"grid_id": c["id"][pos], "latitude": c["lat"][pos], "longitude": c["lon"][pos], "approx_km2": index.get("cell_km2")},
        "agricultural": agricultural, "inputs": inputs, "provenance": prov, "var_quality": quality,
        "context": context, "notes": notes, "unavailable": unavailable,
    }


FIELD_SOURCE = "Medición u observación en el lote"
SERIES_SOURCE = "Serie diaria cargada"


def merge_inputs(territorial: dict | None, series_features: dict | None = None, field: dict | None = None,
                 series_info: dict | None = None, series_coverage: float | None = None) -> tuple[dict, dict, dict]:
    """Une las tres capas de datos REALES. Manda la más cercana al lote:
    territorio (bundle) < serie diaria cargada (NASA POWER / CSV) < medición u observación en campo.
    Devuelve (entradas, procedencia, calidad_por_variable)."""
    inputs = dict(territorial["inputs"]) if territorial else {}
    prov = dict(territorial["provenance"]) if territorial else {}
    quality = dict(territorial["var_quality"]) if territorial else {}
    series_level = data_quality_level(series_coverage)
    for var, value in (series_features or {}).items():
        if value is None or var == "gdd_total":
            if var in TEMPORAL_FEATURES:
                inputs[var] = None                       # la serie existe pero no alcanza: «datos insuficientes»
            continue
        inputs[var] = value
        quality[var] = series_level
        prov[var] = {"source": f"{SERIES_SOURCE} ({(series_info or {}).get('source', 'archivo')})",
                     "method": "derivada de la serie diaria limpia", "basis": None,
                     "period": _period_label((series_info or {}).get("first_date"), (series_info or {}).get("last_date")),
                     "quality_level": series_level}
    for var, value in (field or {}).items():
        if value is None:
            continue
        inputs[var] = value
        quality[var] = QUALITY_DIRECT
        prov[var] = {"source": FIELD_SOURCE, "method": "valor declarado por el usuario", "basis": None,
                     "period": None, "quality_level": QUALITY_DIRECT}
    return inputs, prov, quality


def rotation_profile_from_inputs(inputs: dict, territorial: dict | None, history: list, residue=None,
                                 nitrogen=None, waterlogging=None) -> dict:
    """Perfil de rotación con la altitud, la pendiente y el drenaje reales del lote."""
    if waterlogging is None and territorial:
        waterlogging = territorial["context"].get("waterlogging_prone")
    return {"altitude_masl": inputs.get("altitude_masl"), "slope_pct": inputs.get("slope_pct"), "history": history,
            "residue_management": residue, "recent_n_fertilization": nitrogen, "waterlogging_prone": waterlogging}


def evaluate_area(nb: dict, index: dict, lat: float, lon: float, radius_km: float, crop: str = "otro",
                  stage: str = "no_especificada", disabled_ids: set[str] | None = None, max_cells: int = 4000) -> dict:
    """VISTA TERRITORIAL (B2G): evalúa las alertas en todas las celdas dentro de un radio y cuenta
    en cuántas se activa cada regla y en cuántas no se pudo decidir por ambigüedad de los datos."""
    positions = cells_within(index, lat, lon, radius_km)
    truncated = len(positions) > max_cells
    positions = positions[:max_cells]
    fired: dict[str, int] = {}
    ambiguous: dict[str, int] = {}
    meta: dict[str, dict] = {}
    agricultural = 0
    for pos in positions:
        t = territorial_inputs(index, pos)
        if not t["agricultural"]:
            continue
        agricultural += 1
        findings, skipped = evaluate_alerts(t["inputs"], nb["alert_rules"], crop, stage, disabled_ids)
        findings = apply_interactions(findings, nb["interactions"])
        for f in findings:
            if not f["superseded_by"]:
                fired[f["rule_id"]] = fired.get(f["rule_id"], 0) + 1
                meta.setdefault(f["rule_id"], {"title": f["title"], "severity": f["severity"], "module": f["module"]})
        for s in skipped:
            if s["reason"] == "ambiguous_range":
                ambiguous[s["rule_id"]] = ambiguous.get(s["rule_id"], 0) + 1
    km2 = index.get("cell_km2") or 0
    titles = {r["id"]: r for r in nb["alert_rules"]}
    rows = [{"rule_id": rid, **meta[rid], "cells": n, "share_of_agricultural": round(n / agricultural, 3),
             "approx_hectares": round(n * km2 * 100) if km2 else None, "cells_undecided": ambiguous.get(rid, 0)}
            for rid, n in fired.items()]
    rows.sort(key=lambda r: (-SEVERITY_ORDER.get(r["severity"], 0), -r["cells"]))
    undecided = [{"rule_id": rid, "title": titles[rid]["title"], "cells_undecided": n}
                 for rid, n in sorted(ambiguous.items(), key=lambda kv: -kv[1]) if rid not in fired and rid in titles]
    return {"center": {"latitude": lat, "longitude": lon}, "radius_km": radius_km, "crop_key": crop, "stage_key": stage,
            "cells_total": len(positions), "cells_agricultural": agricultural, "truncated": truncated,
            "approx_hectares_agricultural": round(agricultural * km2 * 100) if km2 else None,
            "rules": rows, "undecided_only": undecided,
            "caution": "Conteo de celdas de la grilla (≈ 1 km²), no de predios. Solo usa los datos del bundle territorial: "
                       "las reglas que dependen de temperatura, humedad o síntomas no participan."}


# =====================================================================
# 6. ALERTAS
# =====================================================================
def applies_to_context(item: dict, crop: str, stage: str) -> bool:
    """Lista vacía = aplica a todos. Con «Otro / no especificado» las restringidas NO se activan."""
    applies = item.get("applies_to", {})
    crops, stages = set(applies.get("crops", [])), set(applies.get("stages", []))
    if crops and not (crops & CROP_EXPANSION.get(crop, {crop})):
        return False
    if stages and stage not in stages:
        return False
    return True


CONF_LEVEL = {"low": 1, "moderate": 2, "high": 3}
LEVEL_CONF = {1: "low", 2: "moderate", 3: "high"}
THRESHOLD_LEVEL = {"claim": 3, "claim_partial": 2, "engine_heuristic": 1, "engine_heuristic_no_universal": 1, "none": 3}
CERTAINTY_LABEL = {1: "baja", 2: "media", 3: "alta"}
FACTOR_LABEL = {
    "confianza_de_la_regla": "confianza de la regla",
    "origen_de_umbrales": "origen de los umbrales",
    "calidad_de_datos": "calidad de los datos",
    "sin_validacion_tecnica": "sin validación técnica",
    "solo_revision_documental": "solo revisión documental, sin validación en campo",
}


def _skip_reason(missing: set[str], inputs: dict) -> str:
    absent = [v for v in missing if v not in inputs]
    if any(v in TEMPORAL_FEATURES for v in absent):
        return "needs_series"
    if absent:
        return "missing_input"
    if any(is_uncertain(inputs.get(v)) for v in missing):
        return "ambiguous_range"                             # hay dato, pero su intervalo cruza el umbral de la regla
    return "insufficient_data"


def evaluate_alerts(inputs: dict, rules: list[dict], crop: str = "otro", stage: str = "no_especificada",
                    disabled_ids: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Evalúa las reglas de alerta. Devuelve (hallazgos, reglas_no_evaluadas)."""
    disabled_ids = disabled_ids or set()
    findings: list[dict] = []
    skipped: list[dict] = []
    for rule in rules:
        rid = rule["id"]
        status = rule.get("validation", {}).get("status", "sin_validar")
        if not rule.get("enabled", True) or rid in disabled_ids or status == "rechazada":
            skipped.append({"rule_id": rid, "reason": "disabled"})
            continue
        if not applies_to_context(rule, crop, stage):
            skipped.append({"rule_id": rid, "reason": "not_applicable_to_context"})
            continue
        # CUARENTENA: una regla mal escrita (campo ausente, tipo incompatible…) se aparta y se informa.
        try:
            result, missing = eval3(rule["when"], inputs)
            base = {
                "module": rule["module"], "title": rule["title"], "severity": rule["severity"],
                "confidence": rule["confidence"], "confidence_level": CONF_LEVEL[rule["confidence"]],
                "threshold_level": THRESHOLD_LEVEL[rule["threshold_basis"]],
                "observation": rule["message"], "recommendation": rule["recommendation"],
                "cautions": list(rule["cautions"]), "evidence_basis": rule["evidence_basis"],
                "evidence_status": rule["evidence_status"],
            }
        except (KeyError, TypeError, AttributeError) as exc:
            skipped.append({"rule_id": rid, "reason": "invalid_rule", "detail": f"{type(exc).__name__}: {exc}"})
            continue
        if result is None:
            skipped.append({"rule_id": rid, "reason": _skip_reason(missing, inputs), "missing": sorted(missing)})
            continue
        if not result:
            continue
        findings.append({
            "rule_id": rid, "kind": "rule", "module": rule["module"], "title": rule["title"],
            "severity": rule["severity"], "confidence": rule["confidence"],
            "confidence_level": base["confidence_level"], "confidence_base": rule["confidence"],
            "why": explain_condition(rule["when"], inputs),
            "applies_to": {"crops": list(rule.get("applies_to", {}).get("crops", [])),
                           "stages": list(rule.get("applies_to", {}).get("stages", []))},
            "threshold_status": rule.get("threshold_status"),
            "external_source_ids": list(rule.get("external_source_ids", [])),
            "refines": [], "refined_by": [],
            "threshold_level": THRESHOLD_LEVEL[rule["threshold_basis"]],
            "observation": rule["message"], "recommendation": rule["recommendation"],
            "cautions": list(rule["cautions"]), "evidence_basis": rule["evidence_basis"],
            "evidence_status": rule["evidence_status"], "threshold_basis": rule["threshold_basis"],
            "validation_status": status, "source_claim_ids": list(rule.get("source_claim_ids", [])),
            "interaction_notes": [], "integrated_in": [], "superseded_by": None, "components": [],
        })
    return findings, skipped


# =====================================================================
# 7. REGLAS QUE SE HABLAN
# =====================================================================
def apply_interactions(findings: list[dict], interactions: list[dict]) -> list[dict]:
    """Aplica, en este orden: modificadores, síntesis y reemplazos. Devuelve los hallazgos ordenados."""
    by_id = {f["rule_id"]: f for f in findings}

    # 1) Modificadores: suben o bajan la confianza de un hallazgo.
    #    - Se SUMAN todos los que aplican y se acota una sola vez (el resultado no depende del orden).
    #    - La misma evidencia (mismos hallazgos disparadores, mismo sentido) cuenta una sola vez.
    #    - delta 0 = SALVAGUARDA: deja constancia de que esa coincidencia NO debe cambiar la confianza.
    net: dict[str, int] = {}
    counted: dict[str, set] = {}
    for it in interactions:
        if it["type"] != "modifier" or it["target"] not in by_id:
            continue
        any_ids, all_ids = it.get("when_any", []), it.get("when_all", [])
        if (not any_ids or any(i in by_id for i in any_ids)) and all(i in by_id for i in all_ids):
            target = by_id[it["target"]]
            delta = it["delta"]
            matched = sorted({i for i in any_ids if i in by_id} | set(all_ids))
            note = {"interaction_id": it["id"], "note": it.get("note", ""), "delta": delta,
                    "triggered_by": matched, "claim_ids": it.get("source_claim_ids", [])}
            evidence = (tuple(matched), delta > 0)
            if delta == 0:
                note["effect"] = "salvaguarda: no cambia la confianza"
            elif evidence in counted.setdefault(it["target"], set()):
                note["effect"] = "evidencia ya contada: no se suma otra vez"
                note["delta"] = 0
            else:
                counted[it["target"]].add(evidence)
                net[it["target"]] = net.get(it["target"], 0) + delta
                note["effect"] = "sube la confianza" if delta > 0 else "baja la confianza"
            target["interaction_notes"].append(note)
    for rid, delta in net.items():
        target = by_id[rid]
        new_level = max(1, min(3, target["confidence_level"] + delta))
        target["confidence_net_delta"] = delta
        target["confidence_level"] = new_level
        target["confidence"] = LEVEL_CONF[new_level]

    # 2) Síntesis: hallazgos compuestos que integran a sus componentes
    for it in interactions:
        if it["type"] != "synthesis":
            continue
        all_ids, any_ids = it["when_all"], it.get("when_any", [])
        if not all(i in by_id for i in all_ids):
            continue
        if any_ids and not any(i in by_id for i in any_ids):
            continue
        comps = all_ids + [i for i in any_ids if i in by_id]
        comp_f = [by_id[i] for i in comps]
        level = min([CONF_LEVEL[it["confidence"]]] + [c["confidence_level"] for c in comp_f])
        syn = {
            "rule_id": it["id"], "kind": "synthesis", "module": "synthesis", "title": it["title"],
            "severity": it["severity"], "confidence": LEVEL_CONF[level], "confidence_level": level,
            "threshold_level": min(c["threshold_level"] for c in comp_f),
            "observation": it["message"], "recommendation": it["recommendation"],
            "cautions": list(it["cautions"]),
            "evidence_basis": "Combina señales de varias reglas que se refuerzan o se aclaran entre sí.",
            "evidence_status": "synthesis_of_risk_signals", "threshold_basis": "derived",
            "validation_status": "validada" if all(c["validation_status"] == "validada" for c in comp_f) else "sin_validar",
            "source_claim_ids": list(it.get("source_claim_ids", [])),
            "interaction_notes": [], "integrated_in": [], "superseded_by": None, "components": comps,
            "confidence_base": it["confidence"], "why": [w for c in comp_f for w in c.get("why", [])],
            "applies_to": {"crops": [], "stages": []}, "threshold_status": None,
            "external_source_ids": [], "refines": [], "refined_by": [],
        }
        for c in comp_f:
            c["integrated_in"].append(it["id"])
        findings.append(syn)
        by_id[it["id"]] = syn

    # 3) Reemplazos: la señal específica reemplaza a la general
    for it in interactions:
        if it["type"] != "supersede":
            continue
        winner = next((w for w in it["winners"] if w in by_id), None)
        if winner is None:
            continue
        for loser in it["losers"]:
            if loser in by_id and by_id[loser]["superseded_by"] is None and loser != winner:
                by_id[loser]["superseded_by"] = winner

    order = {f["rule_id"]: i for i, f in enumerate(findings)}
    findings.sort(key=lambda f: (-SEVERITY_ORDER.get(f["severity"], 0), f["kind"] != "synthesis", order[f["rule_id"]]))
    return findings


# ---------------------------------------------------------------------
# Señales que se precisan (general ↔ específica)
# ---------------------------------------------------------------------
def _as_box(cond: dict) -> dict | None:
    """Convierte una condición hecha solo de comparaciones unidas por «all» en una «caja»:
    {variable: intervalo numérico | valor exacto | elementos requeridos}. None si no se puede."""
    leaves = cond.get("all", [cond]) if isinstance(cond, dict) else None
    if not leaves:
        return None
    box: dict = {}
    for leaf in leaves:
        if not isinstance(leaf, dict) or not {"var", "op", "value"} <= set(leaf):
            return None
        var, op, value = leaf["var"], leaf["op"], leaf["value"]
        if op in NUMERIC_OPERATORS:
            prev = box.get(var, ("num", -math.inf, False, math.inf, False))
            if prev[0] != "num":
                return None
            _, lo, lo_in, hi, hi_in = prev
            if op in ("gt", "gte") and (value > lo or (value == lo and op == "gt")):
                lo, lo_in = value, op == "gte"
            if op in ("lt", "lte") and (value < hi or (value == hi and op == "lt")):
                hi, hi_in = value, op == "lte"
            box[var] = ("num", lo, lo_in, hi, hi_in)
        elif op == "eq" and var not in box:
            box[var] = ("eq", value)
        elif op == "contains" and var not in box:
            box[var] = ("has", value)
        else:
            return None
    return box


def _box_implies(a: dict, b: dict) -> bool:
    """¿Todo lo que cumple la caja `a` cumple también la caja `b`? (inclusión lógica, no agronomía)"""
    for var, cb in b.items():
        ca = a.get(var)
        if ca is None or ca[0] != cb[0]:
            return False
        if cb[0] != "num":
            if ca[1] != cb[1]:
                return False
            continue
        _, alo, alo_in, ahi, ahi_in = ca
        _, blo, blo_in, bhi, bhi_in = cb
        if alo < blo or (alo == blo and alo_in and not blo_in):
            return False
        if ahi > bhi or (ahi == bhi and ahi_in and not bhi_in):
            return False
    return True


def _context_within(a: dict, b: dict) -> bool:
    """¿El contexto (cultivos/etapas) de la regla `a` cabe dentro del de `b`? Lista vacía = todos."""
    for key in ("crops", "stages"):
        sa, sb = set(a.get("applies_to", {}).get(key, [])), set(b.get("applies_to", {}).get(key, []))
        if sb and (not sa or not sa <= sb):
            return False
    return True


def link_refinements(findings: list[dict], rules: list[dict]) -> None:
    """Enlaza cada señal general con la señal específica que la contiene.

    Dos hallazgos activos del mismo módulo se enlazan cuando la condición y el contexto del
    específico están lógicamente DENTRO de los del general (p. ej. «maíz joven con suelo < 20 %»
    dentro de «suelo < 25 %»). Es un enlace informativo: no oculta ni borra ninguno de los dos.
    """
    by_rule = {r["id"]: r for r in rules}
    boxes = {}
    for f in findings:
        rule = by_rule.get(f["rule_id"])
        if f["kind"] == "rule" and rule is not None:
            try:
                box = _as_box(rule["when"])
            except TypeError:
                box = None
            if box:
                boxes[f["rule_id"]] = box
    for a in findings:
        for b in findings:
            ia, ib = a["rule_id"], b["rule_id"]
            if ia == ib or ia not in boxes or ib not in boxes or a["module"] != b["module"]:
                continue
            ra, rb = by_rule[ia], by_rule[ib]
            forward = _box_implies(boxes[ia], boxes[ib]) and _context_within(ra, rb)
            backward = _box_implies(boxes[ib], boxes[ia]) and _context_within(rb, ra)
            if forward and not backward:
                a["refines"].append(ib)
                b["refined_by"].append(ia)


def risk_overview(findings: list[dict]) -> dict:
    """SEMÁFORO: gravedad máxima y número de hallazgos visibles por módulo (para la vista del agricultor)."""
    modules: dict[str, dict] = {}
    for f in findings:
        if f["superseded_by"]:
            continue
        m = modules.setdefault(f["module"], {"severity": "low", "findings": 0})
        m["findings"] += 1
        if SEVERITY_ORDER.get(f["severity"], 0) > SEVERITY_ORDER[m["severity"]]:
            m["severity"] = f["severity"]
    overall = max((m["severity"] for m in modules.values()), key=lambda s: SEVERITY_ORDER[s], default="none")
    return {"overall": overall, "by_module": dict(sorted(modules.items(), key=lambda kv: -SEVERITY_ORDER[kv[1]["severity"]]))}


_SRC_CODE = re.compile(r"\bSRC_\d+\b")


def attach_sources(findings: list[dict], nb: dict) -> None:
    """Resuelve las fuentes externas de cada hallazgo (las que declara la regla y los códigos
    [SRC_xxx] citados en su texto o en sus notas) contra las fichas del cuaderno."""
    registry = reference_registry(nb)
    for f in findings:
        ids = list(f.get("external_source_ids", []))
        texts = [f.get("observation", "")] + [n.get("note", "") for n in f.get("interaction_notes", [])]
        for code in _SRC_CODE.findall(" ".join(texts)):
            if code not in ids:
                ids.append(code)
        f["external_sources"] = [{k: registry[i][k] for k in ("id", "title", "publisher", "url")} for i in ids if i in registry]
        f["external_sources_unresolved"] = [i for i in ids if i not in registry]


# =====================================================================
# 8. CERTEZA VISIBLE
# =====================================================================
def data_quality_level(coverage: float | None) -> int:
    """None = dato declarado directamente por el usuario (sliders)."""
    if coverage is None or coverage >= 0.85:
        return 3
    return 2 if coverage >= 0.6 else 1


def add_certainty(findings: list[dict], coverage: float | None = None, var_quality: dict | None = None) -> None:
    """Calcula la certeza de cada hallazgo: el mínimo de sus factores, con tope «media»
    mientras ningún técnico haya validado la regla.

    Con datos reales, la calidad se mide POR HALLAZGO: es la del dato más débil entre los que lo
    activaron (`var_quality`: 3 directo, 2 derivado de una clase, 1 estimado)."""
    base_dq = data_quality_level(coverage)
    for f in findings:
        dq = base_dq
        if var_quality is not None:
            levels = [var_quality.get(w["variable"], 3) for w in f.get("why", [])]
            dq = min(levels) if levels else 3
        factors = {
            "confianza_de_la_regla": f["confidence_level"],
            "origen_de_umbrales": f["threshold_level"],
            "calidad_de_datos": dq,
        }
        level = min(factors.values())
        limiting = [FACTOR_LABEL[k] for k, v in factors.items() if v == level and level < 3]
        # Solo «validada» (por un técnico, en campo) levanta el tope. La revisión documental no.
        if f["validation_status"] != "validada":
            level = min(level, 2)
            limiting.append(FACTOR_LABEL["solo_revision_documental" if f["validation_status"] in DOCUMENTARY_STATUS
                                         else "sin_validacion_tecnica"])
        f["certainty"] = {
            "level": CERTAINTY_LABEL[level],
            "limiting_factors": limiting,
            "factors": {k: CERTAINTY_LABEL[v] for k, v in factors.items()},
        }


# =====================================================================
# 9. REVISIÓN TÉCNICA
# =====================================================================
def apply_validations(nb: dict, validations: list[dict]) -> tuple[dict, dict]:
    """Aplica validaciones de un técnico. Devuelve (cuaderno_con_validaciones, informe).

    Cada validación: {rule_id, status, by, date, notes}. status en
    validada | ajustar | rechazada | sin_validar. Una regla «rechazada» deja de evaluarse.
    """
    nb2 = json.loads(json.dumps(nb))
    targets = {r["id"]: r for sec in ("alert_rules", "rotation_rules") for r in nb2[sec]}
    report = {"applied": 0, "unknown_ids": [], "invalid": [], "by_status": {}}
    for v in validations:
        rid, status = v.get("rule_id"), v.get("status")
        if rid not in targets:
            report["unknown_ids"].append(rid)
            continue
        if status not in VALID_VALIDATION_STATUS:
            report["invalid"].append({"rule_id": rid, "status": status})
            continue
        targets[rid]["validation"] = {
            "status": status, "by": v.get("by"), "date": v.get("date"), "notes": v.get("notes", ""),
        }
        report["applied"] += 1
        report["by_status"][status] = report["by_status"].get(status, 0) + 1
    return nb2, report


def validation_summary(nb: dict) -> dict:
    counts = {s: 0 for s in sorted(VALID_VALIDATION_STATUS)}
    for sec in ("alert_rules", "rotation_rules"):
        for r in nb[sec]:
            counts[r["validation"]["status"]] += 1
    counts["total"] = sum(counts.values())
    return counts


def review_sheet_csv(nb: dict) -> str:
    """Hoja de revisión para que un técnico marque cada regla (se abre en Excel)."""
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["id", "tipo", "titulo", "origen_de_umbrales", "afirmaciones", "estado_validacion", "revisado_por", "fecha", "observaciones"])
    for sec, kind in (("alert_rules", "alerta"), ("rotation_rules", "rotación")):
        for r in nb[sec]:
            v = r["validation"]
            w.writerow([r["id"], kind, r["title"], r["threshold_basis"], " ".join(r.get("source_claim_ids", [])),
                        v["status"], v.get("by") or "", v.get("date") or "", v.get("notes", "")])
    for i in nb["interactions"]:
        if i["type"] == "synthesis":
            w.writerow([i["id"], "síntesis", i["title"], "derived", " ".join(i.get("source_claim_ids", [])), "sin_validar", "", "", ""])
    return buf.getvalue()


def validation_template(nb: dict) -> list[dict]:
    """Plantilla JSON que un técnico llena y se vuelve a cargar."""
    return [{"rule_id": r["id"], "status": r["validation"]["status"], "by": r["validation"].get("by"),
             "date": r["validation"].get("date"), "notes": r["validation"].get("notes", "")}
            for sec in ("alert_rules", "rotation_rules") for r in nb[sec]]


# =====================================================================
# 10. PRÁCTICAS Y CONOCIMIENTO DEL CUADERNO
# =====================================================================
def practice_evidence(nb: dict | None, practice_id: str) -> dict | None:
    """Evidencia bibliográfica de una práctica (cuaderno 2.3): estado del respaldo, alcance y fuentes."""
    if nb is None:
        return None
    expansion = nb.get("meta", {}).get("practices_expansion", {}) or {}
    ev = (expansion.get("evidence_by_practice", {}) or {}).get(practice_id)
    if not ev:
        return None
    bib = {b["id"]: b for b in expansion.get("bibliography", []) or []}
    return {"status": ev.get("status"), "scope_note": ev.get("scope_note", ""),
            "sources": [{"id": s, "citation": bib[s].get("citation", ""), "url": bib[s].get("url", "")}
                        for s in ev.get("source_ids", []) if s in bib]}


def evaluate_practices(practices: list[dict], inputs: dict, crop: str, stage: str, active_ids: set[str],
                       nb: dict | None = None, limit: int | None = None) -> list[dict]:
    """Prácticas de Nivel 1 que corresponden al contexto o a los hallazgos activos.

    Con 76 prácticas en el cuaderno, se ORDENAN por relevancia (sin puntajes agronómicos: solo
    cuenta por qué se muestra cada una): responde a un hallazgo activo > cumple una condición del
    lote > coincide con cultivo y etapa > coincide con uno de los dos > orientación general.
    """
    out = []
    for p in practices:
        if not applies_to_context(p, crop, stage):
            continue
        triggers, when = p.get("trigger_findings", []), p.get("when")
        applies = p.get("applies_to", {})
        why, relevance = [], 0
        hit = [t for t in triggers if t in active_ids]
        if hit:
            why.append({"type": "finding", "ids": hit})
            relevance += 6 + min(len(hit), 3)
        if when:
            try:
                r, _ = eval3(when, inputs)
            except (KeyError, TypeError):
                r = None
            if r is True:
                why.append({"type": "context_condition"})
                relevance += 4
        if not triggers and not when:
            specific = bool(applies.get("crops")) + bool(applies.get("stages"))
            why.append({"type": "context" if specific else "general"})
            relevance += specific
        elif why:
            relevance += bool(applies.get("crops")) + bool(applies.get("stages"))
        if why:
            out.append({"practice_id": p["id"], "title": p["title"], "text": p["text"], "tier": p.get("tier", 1),
                        "cautions": p["cautions"], "source_claim_ids": p.get("source_claim_ids", []), "why": why,
                        "relevance": relevance, "evidence": practice_evidence(nb, p["id"])})
    out.sort(key=lambda x: -x["relevance"])                 # orden estable: a igual relevancia, el del cuaderno
    return out[:limit] if limit else out


def _altitude_within(altitude, lo: float, hi: float) -> bool | None:
    """¿La altitud del lote (número o franja) está dentro de [lo, hi]? None = la franja lo cruza."""
    if altitude is None:
        return None
    if isinstance(altitude, Range):
        top = altitude.hi if altitude.closed else altitude.hi - 1
        if lo <= altitude.lo and top <= hi:
            return True
        return False if top < lo or altitude.lo > hi else None
    return lo <= altitude <= hi


def relevant_knowledge(nb: dict, crop: str, stage: str, altitude_masl,
                       active_ids: set[str], limit: int = 8) -> list[dict]:
    """Afirmaciones del cuaderno que importan para este cultivo, etapa y altitud,
    aunque ninguna regla se haya activado."""
    selected = CROP_EXPANSION.get(crop, {crop})
    usage = claim_usage(nb)
    scored = []
    for c in nb["claims"]:
        if c["tier"] == "out_of_scope":
            continue
        linked = bool(usage[c["claim_id"]] & active_ids)
        # Una afirmación con regla también es conocimiento útil si coincide con la etapa o la altitud actuales.
        in_stage = bool(c["stages"]) and stage in c["stages"]
        in_altitude = bool(c.get("altitude_masl")) and _altitude_within(altitude_masl, *c["altitude_masl"]) is True
        if c["tier"] != "knowledge" and not (linked or in_stage or in_altitude):
            continue
        crops = set(c["crops"])
        score, why = 0, []
        if crops & selected:
            score += 3
            why.append("coincide con el cultivo")
        elif "general" in crops:
            score += 1
            why.append("aplica a cualquier cultivo")
        elif not linked:
            continue
        if c["stages"]:
            if stage in c["stages"]:
                score += 3
                why.append("coincide con la etapa")
            elif stage != "no_especificada":
                score -= 3
        if c.get("altitude_masl") and altitude_masl is not None:
            within = _altitude_within(altitude_masl, *c["altitude_masl"])
            if within is True:
                score += 3
                why.append("la altitud está dentro del rango citado")
            elif within is False:
                continue                                     # None: la franja del lote cruza el rango → ni suma ni descarta
        if linked:
            score += 4
            why.append("respalda un hallazgo activo")
        if score > 0:
            scored.append((score, c["doc_order"], c, why))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"claim_id": c["claim_id"], "doc_order": c["doc_order"], "claim": c["claim"],
             "explanation": c["explanation"], "conditions": c["conditions"], "source": c["source"],
             "doi": c["doi"], "source_verified": c["source_verified"], "score": s, "why": why}
            for s, _, c, why in scored[:limit]]


def coverage_report(nb: dict) -> dict:
    """Cuánto del cuaderno se aprovecha y qué dato nuevo desbloquearía más afirmaciones."""
    kinds = {}
    for sec, kind in (("alert_rules", "alertas"), ("rotation_rules", "rotación"), ("interactions", "interacciones"),
                      ("practices", "prácticas"), ("parameters", "parámetros")):
        for e in nb[sec]:
            kinds[e["id"]] = kind
    counts = {"en_uso": 0, "conocimiento_contextual": 0, "pendiente_de_umbral": 0, "bloqueada": 0, "fuera_del_alcance": 0}
    by_kind: dict[str, int] = {}
    unlock: dict[str, list[int]] = {}
    usage = claim_usage(nb)
    for c in nb["claims"]:
        used = {kinds[u] for u in usage[c["claim_id"]] if u in kinds}
        if used:
            counts["en_uso"] += 1
            for k in used:
                by_kind[k] = by_kind.get(k, 0) + 1
        elif c["tier"] == "out_of_scope":
            counts["fuera_del_alcance"] += 1
        elif c["implementation_status"] == "blocked_needs_input":
            counts["bloqueada"] += 1
        elif c["implementation_status"] == "ready_pending_threshold":
            counts["pendiente_de_umbral"] += 1
        else:
            counts["conocimiento_contextual"] += 1
        if c["implementation_status"] == "blocked_needs_input":
            for need in c["needs"]:
                unlock.setdefault(need, []).append(c["doc_order"])
    return {
        "total": len(nb["claims"]), "counts": counts, "used_by_kind": by_kind,
        "unlock_map": dict(sorted(unlock.items(), key=lambda kv: -len(kv[1]))),
    }

# =====================================================================
# 11. ROTACIÓN Y ASOCIACIÓN
# =====================================================================
def validate_rotation_profile(profile: dict) -> list[str]:
    errors: list[str] = []
    def bad(value, top):                                    # número o intervalo (Range) dentro de [0, top]
        if value is None:
            return False
        if isinstance(value, Range):
            return not 0 <= value.lo <= value.hi <= top
        return isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= top

    if bad(profile.get("altitude_masl"), 5000):
        errors.append("La altitud debe ser un número o un intervalo entre 0 y 5000 msnm (o None si no se conoce).")
    if bad(profile.get("slope_pct"), 200):
        errors.append("La pendiente debe ser un porcentaje o un intervalo entre 0 y 200 (o None si no se conoce).")
    history = profile.get("history", [])
    if not isinstance(history, list):
        errors.append("El historial debe ser una lista de ciclos (más reciente primero).")
    else:
        valid = ROT_ENUMS["last_crops"]
        for i, cycle in enumerate(history):
            if not isinstance(cycle, list):
                errors.append(f"Ciclo #{i + 1}: debe ser una lista de cultivos.")
                continue
            for crop in cycle:
                if crop not in valid:
                    errors.append(f"Ciclo #{i + 1}: cultivo desconocido '{crop}'.")
    residue = profile.get("residue_management")
    if residue is not None and residue not in ROT_ENUMS["residue_management"]:
        errors.append(f"residue_management debe ser uno de {sorted(ROT_ENUMS['residue_management'])} o None.")
    if profile.get("recent_n_fertilization") not in (None, "none_or_low", "high"):
        errors.append("recent_n_fertilization debe ser 'none_or_low', 'high' o None.")
    if profile.get("waterlogging_prone") not in (None, True, False):
        errors.append("waterlogging_prone debe ser True, False o None.")
    return errors


def crop_families(crop: str) -> list[str]:
    """Familias botánicas de un cultivo. Un sistema asociado aporta las de todos sus componentes."""
    comps = ROT_COMPONENTS.get(crop, [crop])
    return sorted({ROT_CROPS[c][1] for c in comps if c in ROT_CROPS})


def expand_cycle(cycle: list[str]) -> list[str]:
    """Un ciclo con un sistema asociado cuenta también como cada uno de sus cultivos componentes."""
    out: list[str] = []
    for crop in cycle:
        for c in [crop] + ROT_COMPONENTS.get(crop, []):
            if c not in out:
                out.append(c)
    return out


def rotation_context(profile: dict, candidate: str) -> dict:
    history = profile.get("history") or []
    last = expand_cycle(list(history[0])) if history else []
    last_families = sorted({fam for c in last for fam in crop_families(c)})
    cand_families = crop_families(candidate)
    return {
        "candidate_crop": candidate,
        "candidate_family": cand_families[0] if len(cand_families) == 1 else MIXED_FAMILY,
        "last_crops": last, "last_families": last_families,
        "same_family_as_last": any(f in last_families for f in cand_families) if last_families else None,
        "altitude_masl": profile.get("altitude_masl"),
        "slope_pct": profile.get("slope_pct"),
        "residue_management": profile.get("residue_management"),
        "recent_n_fertilization": profile.get("recent_n_fertilization"),
        "waterlogging_prone": profile.get("waterlogging_prone"),
    }


def rule_scope(rule: dict) -> str:
    """Clasificación ESTRUCTURAL de una regla de rotación (no agronómica), según las variables que mira:

    lot        : no menciona al cultivo candidato → habla del lote (p. ej. «no quemar el rastrojo»).
    generic    : solo mira qué cultivo es el candidato → se cumple siempre para ese cultivo;
                 es una orientación general y no dice nada sobre este lote en particular.
    contextual : cruza el candidato con el historial o con datos del lote → es la que decide.
    """
    variables = condition_vars(rule["when"])
    if not variables & CANDIDATE_VARS:
        return "lot"
    if variables <= {"candidate_crop", "candidate_family"}:
        return "generic"
    return "contextual"


def _rot_reason(rule: dict) -> dict:
    return {
        "rule_id": rule["id"], "title": rule["title"], "message": rule["message"], "effect": rule["effect"],
        "cautions": rule["cautions"], "claim_ids": rule.get("source_claim_ids", []),
        "threshold_basis": rule["threshold_basis"], "validation_status": rule["validation"]["status"],
        "scope": rule_scope(rule),
    }


def _fired_rules(ctx: dict, rules: list[dict], disabled_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """(reglas que se cumplen, reglas que no se pudieron evaluar) para un contexto de rotación."""
    fired, unknown = [], []
    for rule in rules:
        if not rule.get("enabled", True) or rule["id"] in disabled_ids or rule.get("validation", {}).get("status") == "rechazada":
            continue
        try:
            result, missing = eval3(rule["when"], ctx)
        except (KeyError, TypeError):                      # una regla mal escrita no tumba al resto
            unknown.append({"rule_id": rule["id"], "missing": [], "reason": "invalid_rule"})
            continue
        if result is True:
            fired.append(rule)
        elif result is None:
            unknown.append({"rule_id": rule["id"], "missing": sorted(missing)})
    return fired, unknown


_ROT_BUCKET = {"block": "blocking", "discourage": "against", "favor": "in_favor", "note": "notes"}


def _empty_candidate(candidate: str, status: str) -> dict:
    label, family = ROT_CROPS[candidate]
    return {"crop_key": candidate, "crop": label, "family": FAMILY_LABELS[family], "status": status,
            "blocking": [], "against": [], "in_favor": [], "notes": [], "general_guidance": [], "unevaluated": []}


def evaluate_candidate(profile: dict, candidate: str, rules: list[dict], disabled_ids: set[str]) -> dict:
    entry = _empty_candidate(candidate, "aceptable")
    crop_rules = [r for r in rules if rule_scope(r) != "lot"]
    fired, unknown = _fired_rules(rotation_context(profile, candidate), crop_rules, disabled_ids)
    entry["unevaluated"] = unknown
    for rule in fired:
        if rule_scope(rule) == "generic" and rule["effect"] in ("favor", "note"):
            entry["general_guidance"].append(_rot_reason(rule))     # no decide el estado
        else:
            entry[_ROT_BUCKET[rule["effect"]]].append(_rot_reason(rule))

    # Un sistema asociado hereda las exclusiones y reservas de cada uno de sus componentes
    # (p. ej. Las Tres Hermanas contienen maíz: no deben ir junto o después de la caña).
    seen = {r["id"] for r in fired}
    for comp in ROT_COMPONENTS.get(candidate, []):
        comp_fired, _ = _fired_rules(rotation_context(profile, comp), crop_rules, disabled_ids)
        for rule in comp_fired:
            if (rule["id"] in seen or rule["effect"] not in ("block", "discourage") or rule_scope(rule) != "contextual"
                    or "same_family_as_last" in condition_vars(rule["when"])):
                continue
            seen.add(rule["id"])
            entry[_ROT_BUCKET[rule["effect"]]].append({**_rot_reason(rule), "inherited_from": ROT_CROPS[comp][0]})

    if entry["blocking"]:
        entry["status"] = "desaconsejado"
    elif entry["against"]:
        entry["status"] = "con_reservas"
    elif entry["in_favor"]:
        entry["status"] = "favorecido"
    return entry


def recommend_rotation(profile: dict, rules: list[dict], disabled_ids: set[str] | None = None) -> dict:
    """Evalúa qué sembrar a continuación. Sin puntajes: categorías explicables, con sus razones."""
    disabled_ids = disabled_ids or set()
    history = profile.get("history") or []
    last = expand_cycle(list(history[0])) if history else []
    situation, candidates = "sin_historial", list(ROT_CROPS)
    if last:
        situation = "rotacion"
        if "cana_panelera" in last:
            situation = "cana_establecida"
            candidates = [c for c in candidates if c != "cana_panelera"]
    results = []
    for crop in candidates:
        results.append(evaluate_candidate(profile, crop, rules, disabled_ids) if last else _empty_candidate(crop, "sin_evaluar"))
    results.sort(key=lambda r: (ROT_STATUS_ORDER[r["status"]], len(r["against"]) - len(r["in_favor"])))

    # Reglas que hablan del lote y no de un cultivo: se informan una sola vez y no «bloquean» a todos los candidatos.
    lot_rules = [r for r in rules if rule_scope(r) == "lot"]
    lot_fired, lot_unknown = _fired_rules(rotation_context(profile, candidates[0]), lot_rules, disabled_ids)
    lot_findings = [_rot_reason(r) for r in lot_fired]

    missing: dict[str, dict] = {}

    def note_missing(unknown, crop_label):
        for u in unknown:
            for var in u["missing"]:
                m = missing.setdefault(var, {"variable": var, "label": ROT_VAR_LABELS.get(var, var),
                                             "affects_rules": set(), "affects_crops": set()})
                m["affects_rules"].add(u["rule_id"])
                m["affects_crops"].add(crop_label)

    for r in results:
        note_missing(r["unevaluated"], r["crop"])
    note_missing(lot_unknown, "todo el lote")

    families_last = {fam for c in last for fam in crop_families(c)}
    cautions = [
        "El cuaderno solo respalda reglas sobre el ciclo inmediatamente anterior: los ciclos más antiguos se registran, pero todavía no modifican el resultado.",
        "La rotación es menos efectiva contra plagas de vuelo largo (como las polillas de Spodoptera frugiperda) o royas dispersadas por el viento si las fincas vecinas mantienen el cultivo hospedero (afirmación 47).",
        "Las opciones no consideran mercado, mano de obra, semilla disponible ni las preferencias del agricultor.",
        "Las «orientaciones generales» se cumplen siempre para ese cultivo: informan, pero no cambian su categoría.",
    ]
    if len(families_last) >= 2:
        cautions.append(
            "El último ciclo combinó varias familias (como Las Tres Hermanas). El cuaderno no ofrece reglas para secuenciar después de una asociación completa: "
            "el resultado se evalúa familia por familia y debe revisarlo un técnico.")
    return {
        "situation": situation, "candidates": results, "lot_findings": lot_findings,
        "missing_inputs": [{**m, "affects_rules": sorted(m["affects_rules"]), "affects_crops": sorted(m["affects_crops"])}
                           for m in missing.values()],
        "verify_before_acting": VERIFY_BEFORE_ACTING, "global_cautions": cautions,
        "profile": {**profile, "thermal_floor": thermal_floor(profile.get("altitude_masl"))},
    }


# =====================================================================
# 12. SALIDA ESTRUCTURADA PARA EL AGENTE DE IA
# =====================================================================
GLOBAL_CAUTIONS = [
    "Las reglas son heurísticas preliminares y no están calibradas para una localidad o variedad específica.",
    "Ninguna regla ha sido validada por un técnico: la certeza máxima mostrada es «media» hasta que eso ocurra.",
    "La ausencia de hallazgos no demuestra que el cultivo esté sano.",
    "No se calcularon dosis de fertilizantes, plaguicidas ni riego.",
    "Los síntomas visuales generan hipótesis, no diagnósticos confirmados.",
]


def global_cautions(nb: dict) -> list[str]:
    """Las advertencias globales, con la de validación ajustada al estado real del cuaderno."""
    vs = validation_summary(nb)
    out = list(GLOBAL_CAUTIONS)
    documentary = sum(vs.get(s, 0) for s in DOCUMENTARY_STATUS)
    if vs.get("validada", 0):
        out[1] = (f"Solo {vs['validada']} de {vs['total']} reglas han sido validadas por un técnico: "
                  "las demás no pasan de certeza «media».")
    if documentary:
        out.insert(2, f"{documentary} reglas tienen revisión documental de sus fuentes: eso respalda el principio general, "
                      "pero NO equivale a validación en campo ni calibra sus umbrales.")
    out.append("Las alertas ambientales no confirman la presencia de patógenos, insectos ni virus: exigen observación o diagnóstico.")
    return out


def attach_provenance(findings: list[dict], provenance: dict | None) -> None:
    """Vista del Porqué con datos reales: a cada dato decisivo se le añade su fuente efectiva,
    el método con que se obtuvo, el periodo y su nivel de calidad."""
    for f in findings:
        for w in f.get("why", []):
            p = (provenance or {}).get(w["variable"])
            w["observed_text"] = show_value(w["observed"])
            w["data_source"] = p["source"] if p else None
            w["method"] = p["method"] if p else None
            w["period"] = p["period"] if p else None
            w["quality_level"] = CERTAINTY_LABEL.get(p["quality_level"]) if p else None


def analyze(nb: dict, inputs: dict, crop: str = "otro", stage: str = "no_especificada",
            disabled_ids: set[str] | None = None, coverage: float | None = None,
            practice_limit: int | None = None, var_quality: dict | None = None,
            provenance: dict | None = None) -> dict:
    """Inferencia completa en una sola llamada (lo que usan la interfaz y cualquier integración):
    alertas → interacciones → señales que se precisan → certeza → fuentes → prácticas → conocimiento."""
    findings, skipped = evaluate_alerts(inputs, nb["alert_rules"], crop, stage, disabled_ids)
    findings = apply_interactions(findings, nb["interactions"])
    link_refinements(findings, nb["alert_rules"])
    add_certainty(findings, coverage, var_quality)
    attach_sources(findings, nb)
    attach_provenance(findings, provenance)
    active_ids = {f["rule_id"] for f in findings}
    return {
        "findings": findings, "skipped": skipped, "overview": risk_overview(findings),
        "practices": evaluate_practices(nb["practices"], inputs, crop, stage, active_ids, nb=nb, limit=practice_limit),
        "knowledge": relevant_knowledge(nb, crop, stage, inputs.get("altitude_masl"), active_ids),
    }


def build_payload(nb: dict, *, mode: str, inputs: dict, crop: str, stage: str, findings: list[dict],
                  skipped: list[dict], practices: list[dict], knowledge: list[dict],
                  quality: dict | None = None, corrections: list[dict] | None = None,
                  rotation: dict | None = None, data_source: dict | None = None,
                  territorial: dict | None = None, provenance: dict | None = None) -> dict:
    visible = [f for f in findings if not f["superseded_by"]]
    total_rules = len(nb["alert_rules"])
    audit = audit_notebook(nb)
    cautions = global_cautions(nb)
    if territorial:
        cautions = territorial["notes"] + cautions
        if territorial["unavailable"]:
            cautions.append("El bundle territorial no trae: " + ", ".join(var_label(v) for v in territorial["unavailable"])
                            + ". Las reglas que dependen de esos datos no se evaluaron, salvo que se hayan aportado desde el lote.")
    if data_source is None:
        data_source = {"source": {"foto": "valores escritos por el usuario", "territorio": "bundle territorial (datos reales procesados)"}
                       .get(mode, "serie de prueba")}
    return jsonable({
        "schema_version": SCHEMA_VERSION, "engine": ENGINE_NAME, "notebook_version": nb["meta"]["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "context": {
            "crop_or_system": CROPS.get(crop, crop), "crop_key": crop,
            "phenological_stage": STAGES.get(stage, stage), "stage_key": stage,
            "altitude_masl": inputs.get("altitude_masl"), "thermal_floor": thermal_floor(inputs.get("altitude_masl")),
            "slope_pct": inputs.get("slope_pct"), "geographic_context": "not_specified", "cultivar": "not_specified",
        },
        "data_mode": mode,
        "data_source": data_source,
        "territory": None if not territorial else {
            "cell": territorial["cell"], "agricultural": territorial["agricultural"], "context": territorial["context"],
            "notes": territorial["notes"], "variables_not_in_bundle": territorial["unavailable"],
        },
        "input_provenance": provenance or {},
        "input_state": inputs,
        "data_quality": quality,
        "corrections_applied": corrections or [],
        "risk_overview": risk_overview(findings),
        "inference": {
            "status": "findings_generated" if visible else "no_rule_triggered",
            "rules_in_catalog": total_rules, "rules_evaluated": total_rules - len(skipped),
            "rules_skipped": skipped, "findings_count": len(visible), "findings": findings,
            "global_cautions": cautions,
        },
        "notebook_audit": {"errors": len(audit["errors"]), "warnings": len(audit["warnings"]),
                           "base_claims_verified": bool(nb["meta"].get("sources_verified")),
                           "external_sources_verified": bool(nb["meta"].get("external_sources_verified"))},
        "practices": practices,
        "relevant_knowledge": [{k: v for k, v in e.items() if k in ("claim_id", "claim", "explanation", "conditions", "why", "source_verified")}
                               for e in knowledge],
        "rotation": rotation,
        "validation_summary": validation_summary(nb),
        "agent_instructions": {
            "task": "Explicar los hallazgos, las prácticas y las opciones de rotación en lenguaje claro, sin agregar diagnósticos, dosis ni recomendaciones que no estén en el payload.",
            "must_preserve_uncertainty": True,
            "must_report_certainty_level_of_each_finding": True,
            "must_explain_each_finding_with_its_why_block": True,
            "must_name_planned_data_source_as_planned_not_as_measured": True,
            "must_report_intervals_as_intervals_not_as_single_values": True,
            "must_say_which_rules_could_not_be_evaluated_and_why": True,
            "must_state_the_period_and_age_of_the_data": True,
            "must_not_present_weekly_rain_equivalent_as_observed_weekly_rain": True,
            "must_not_present_documentary_review_as_field_validation": True,
            "must_mention_superseded_or_integrated_findings_only_as_context": True,
            "must_not_invent_measurements": True,
            "must_distinguish_risk_from_diagnosis": True,
            "must_not_give_fertilizer_doses": True,
            "must_recommend_technician_review": True,
            "recommended_response_sections": ["estado_general", "hallazgos_prioritarios", "practicas_sugeridas",
                                              "acciones_de_verificacion", "limitaciones"],
        },
    })


def evaluate_point(nb: dict, index: dict, lat: float, lon: float, crop: str = "otro", stage: str = "no_especificada",
                   field: dict | None = None, series: list[dict] | None = None, series_info: dict | None = None,
                   history: list | None = None, residue: str | None = None, nitrogen: str | None = None,
                   waterlogging: bool | None = None, disabled_ids: set[str] | None = None) -> dict:
    """UNA LLAMADA PARA TODO: de unas coordenadas a la salida estructurada del motor.

    lat, lon : ubicación del lote → celda más cercana del bundle territorial.
    field    : lo medido u observado en el lote (análisis de suelo, síntomas…); manda sobre el bundle.
    series   : serie diaria REAL ya leída (series_from_nasa_power / series_from_csv), opcional.
    history  : ciclos anteriores (más reciente primero) para la rotación, opcional.
    """
    pos, distance_km = find_cell(index, lat, lon)
    territorial = territorial_inputs(index, pos)
    territorial["cell"]["requested"] = {"latitude": lat, "longitude": lon}
    territorial["cell"]["distance_km"] = round(distance_km, 3)
    if distance_km > 2.0:
        territorial["notes"].insert(0, f"El punto está a {distance_km:.1f} km de la celda más cercana: queda FUERA de la grilla del bundle.")
    features, quality, coverage = None, None, None
    if series:
        clean, quality = clean_series(series)
        features, _ = compute_features(clean, crop, nb)
        coverage = quality["overall_coverage_last14"]
    inputs, provenance, var_quality = merge_inputs(territorial, features, field, series_info, coverage)
    result = analyze(nb, inputs, crop, stage, disabled_ids, var_quality=var_quality, provenance=provenance)
    rotation = None
    if history:
        profile = rotation_profile_from_inputs(inputs, territorial, history, residue, nitrogen, waterlogging)
        if not validate_rotation_profile(profile):
            rotation = recommend_rotation(profile, nb["rotation_rules"], disabled_ids)
    return build_payload(nb, mode="territorio", inputs=inputs, crop=crop, stage=stage, findings=result["findings"],
                         skipped=result["skipped"], practices=result["practices"], knowledge=result["knowledge"],
                         quality=quality, rotation=rotation, territorial=territorial, provenance=provenance,
                         data_source={"source": "bundle territorial (datos reales procesados)",
                                      "bundle": index.get("bundle"), "layers": index.get("sources"),
                                      "daily_series": series_info, "field_values": sorted(field or {})})

# =====================================================================
# 13. AUTOPRUEBAS  (python motor_agronomico_v41.py --selftest)
# =====================================================================
def _static(**kw):
    base = {"soil_ph": 6.0, "organic_matter": 3.0, "soil_texture": "Franca", "symptoms": [],
            "altitude_masl": 1000, "slope_pct": 10}
    base.update(kw)
    return base


def _foto(**kw):
    base = _static(temperature=25.0, relative_humidity=70, rain_7d=20, soil_moisture=45)
    base.update(kw)
    return base


def _run(inputs, crop="otro", stage="no_especificada", disabled=None, nb=None, coverage=None):
    nb = nb or load_notebook()
    f, s = evaluate_alerts(inputs, nb["alert_rules"], crop, stage, disabled)
    f = apply_interactions(f, nb["interactions"])
    add_certainty(f, coverage)
    return f, s


def _ids(findings, visible=False):
    return {f["rule_id"] for f in findings if not (visible and f["superseded_by"])}


def _serie(scenario, crop="otro", n=30, seed=7, **gen):
    nb = load_notebook()
    clean, qa = clean_series(generate_series(n_days=n, scenario=scenario, seed=seed, **gen))
    feats, why = compute_features(clean, crop, nb)
    return {**_static(), **feats}, feats, qa


def _t_notebook_is_coherent():
    nb = load_notebook()
    assert validate_notebook(nb) == [], validate_notebook(nb)
    assert {k: len(nb[k]) for k in SECTIONS} == {
        "claims": 101, "alert_rules": 85, "rotation_rules": 117, "interactions": 86, "practices": 76, "parameters": 3}
    assert nb["meta"]["sources_verified"] is False and nb["meta"]["version"].startswith("2.3")


def _t_notebook_validation_detects_problems():
    nb = load_notebook()
    def mutated(fn):
        n = json.loads(json.dumps(nb)); fn(n); return "\n".join(validate_notebook(n))
    def warned(fn):
        n = json.loads(json.dumps(nb)); fn(n); return "\n".join(audit_notebook(n)["warnings"])
    assert "ID repetido" in mutated(lambda n: n["practices"].append(dict(n["practices"][0])))
    assert "variable desconocida" in mutated(lambda n: n["alert_rules"][0]["when"].update({"var": "ph"}) if "var" in n["alert_rules"][0]["when"] else n["alert_rules"][0].update({"when": {"var": "ph", "op": "lt", "value": 1}}))
    assert "target 'NOPE'" in mutated(lambda n: n["interactions"][3].update({"target": "NOPE"}))
    assert "delta debe ser" in mutated(lambda n: n["interactions"][3].update({"delta": 5}))
    assert "winners" in mutated(lambda n: n["interactions"][0].update({"winners": ["NOPE"]}))
    assert "sin disparadores" in warned(lambda n: n["practices"].append({"id": "PRAC_X", "title": "t", "text": "x", "cautions": [], "applies_to": {}, "trigger_findings": [], "source_claim_ids": []}))
    assert "bloque 'validation' inválido" in mutated(lambda n: n["alert_rules"][0]["validation"].update({"status": "quizas"}))
    assert "no lista a" in warned(lambda n: n["claims"][0]["used_by"].clear() or n["alert_rules"][0]["source_claim_ids"].append("CLAIM_001"))
    assert "afirmación inexistente" in mutated(lambda n: n["alert_rules"][0]["source_claim_ids"].append("CLAIM_999"))
    assert "valor 'trigo' no válido" in mutated(lambda n: n["rotation_rules"][0].update({"when": {"var": "candidate_crop", "op": "eq", "value": "trigo"}}))
    assert "booleana" in mutated(lambda n: n["rotation_rules"][0].update({"when": {"var": "same_family_as_last", "op": "lt", "value": 1}}))


def _t_three_state_logic():
    ctx = {"a": 1, "b": None}
    T, F = {"var": "a", "op": "eq", "value": 1}, {"var": "a", "op": "eq", "value": 2}
    U = {"var": "b", "op": "eq", "value": 1}
    assert eval3({"all": [T, T]}, ctx) == (True, set())
    assert eval3({"all": [F, U]}, ctx) == (False, set())
    assert eval3({"all": [T, U]}, ctx) == (None, {"b"})
    assert eval3({"any": [T, U]}, ctx) == (True, set())
    assert eval3({"any": [F, U]}, ctx) == (None, {"b"})
    assert eval3({"not": U}, ctx) == (None, {"b"})


# ---------------- tiempo ----------------
def _t_series_generator_is_reproducible_and_injects_problems():
    a = generate_series(30, "normal", seed=3)
    assert a == generate_series(30, "normal", seed=3) and a != generate_series(30, "normal", seed=4)
    assert len(a) == 30 and all(set(d) == set(SERIES_VARS) for d in a)
    holes = generate_series(60, "normal", gap_pct=30, seed=1)
    assert 0.15 < sum(d[v] is None for d in holes for v in SERIES_VARS) / (60 * 5) < 0.45
    outl = generate_series(60, "normal", outlier_pct=40, seed=1)
    assert any(d["rh"] == 135.0 or d["tmax"] == 61.0 or d["rain"] == -5.0 or d["tmin"] == -25.0 or d["soil_moisture"] == 140.0 for d in outl)


def _t_scenarios_produce_the_expected_patterns():
    _, f, _ = _serie("sequia");          assert f["dry_days_consecutive"] >= 10 and f["soil_moisture"] < 25
    _, f, _ = _serie("ola_calor");       assert f["hot_days_7d"] >= 3
    _, f, _ = _serie("noches_calidas");  assert f["tmin_mean_7d"] > 20
    _, f, _ = _serie("alternancia");     assert f["wet_dry_alternations_14d"] >= 2
    _, f, _ = _serie("transicion");      assert f["rain_prev14"] >= 50 and f["rain_last14"] <= 15
    _, f, _ = _serie("encharcamiento");  assert f["sat_days_consecutive"] >= 2
    _, f, _ = _serie("normal");          assert f["sat_days_consecutive"] < 2 and f["hot_days_7d"] == 0 and f["tmin_mean_7d"] < 20


def _t_scenarios_are_robust_across_seeds():
    ok = sum(_serie("encharcamiento", seed=s)[1]["sat_days_consecutive"] >= 2 for s in range(1, 21))
    assert ok >= 16, ok
    ok = sum(_serie("ola_calor", seed=s)[1]["hot_days_7d"] >= 3 for s in range(1, 21))
    assert ok == 20, ok
    ok = sum(_serie("noches_calidas", seed=s)[1]["tmin_mean_7d"] > 20 for s in range(1, 21))
    assert ok == 20, ok
    ok = sum("TIME_003" in _ids(_run(_serie("transicion", "frijol", seed=s, tmean=25.0)[0], "frijol")[0]) for s in range(1, 21))
    assert ok >= 18, ok


def _t_alternation_counter():
    wet, dry = [10] * 3, [0] * 3
    assert count_alternations(wet + dry + wet + dry) == 3
    assert count_alternations(wet * 4) == 0
    assert count_alternations([10, 0, 10, 0, 10, 0]) == 0           # periodos de 1 día no cuentan
    assert count_alternations([10, 10, 3, 0, 0]) == 1               # un día intermedio no rompe la alternancia
    assert count_alternations([10, 10, None, 0, 0]) == 1            # un hueco tampoco inventa nada


def _t_data_quality_cleaning_and_gaps():
    s = generate_series(30, "normal", seed=2)
    s[5]["rh"] = 150.0
    s[6]["tmax"], s[6]["tmin"] = 20.0, 25.0
    for i in range(10, 16):
        s[i]["tmax"] = 28.0
    clean, qa = clean_series(s)
    assert clean[5]["rh"] is None and clean[6]["tmax"] is None and clean[6]["tmin"] is None
    assert qa["removed_out_of_range"][0]["variable"] == "rh" and len(qa["inconsistent_days"]) == 1
    assert any(x["variable"] == "tmax" and x["length"] >= 6 for x in qa["possible_stuck_sensors"])
    assert s[5]["rh"] == 150.0                                          # el original no se modifica
    # con muchos huecos las variables derivadas NO se inventan
    holes, qa2 = clean_series(generate_series(30, "sequia", gap_pct=70, seed=5))
    feats, why = compute_features(holes)
    assert qa2["overall_coverage_last14"] < MIN_COVERAGE and qa2["flags"]
    assert feats["wet_dry_alternations_14d"] is None and "wet_dry_alternations_14d" in why


def _t_altitude_correction_and_gdd():
    nb = load_notebook()
    base = [{"tmax": 30.0, "tmin": 20.0, "rh": 70, "rain": 0.0, "soil_moisture": 50}] * 5
    out, delta = adjust_series_altitude(base, 1000, 2000, param(nb, "lapse_rate_c_per_100m"))
    assert delta == -6.0 and out[0]["tmax"] == 24.0 and out[0]["tmin"] == 14.0 and base[0]["tmax"] == 30.0
    assert adjust_series_altitude(base, 1500, 1500, 0.6)[1] == 0.0
    gdd = growing_degree_days(base, 10, 35)
    assert gdd == 5 * 15.0                                              # (30+20)/2 - 10 = 15 por día
    assert growing_degree_days([{"tmax": 50, "tmin": 40}], 10, 35) == (35 + 40) / 2 - 10   # tope superior


# ---------------- alertas (foto) ----------------
def _t_default_snapshot_has_no_findings():
    f, s = _run(_foto(), "tres_hermanas")
    assert f == []
    reasons = {x["reason"] for x in s}
    assert "needs_series" in reasons                                    # las reglas del tiempo piden una serie


def _t_original_rules_and_altitude_rules():
    assert "SOIL_001" in _ids(_run(_foto(soil_ph=5.0))[0])
    assert "SOIL_001" not in _ids(_run(_foto(soil_ph=5.5))[0])
    assert {"SOIL_003"} <= _ids(_run(_foto(soil_ph=4.8, soil_moisture=85))[0])
    assert "SOIL_004" in _ids(_run(_foto(soil_ph=7.5))[0]) and "SOIL_004" not in _ids(_run(_foto(soil_ph=7.0))[0])
    anth = _foto(altitude_masl=1800, temperature=18, relative_humidity=95)
    assert "DISEASE_005" in _ids(_run(anth, "frijol")[0]) and "DISEASE_005" not in _ids(_run(anth, "maiz")[0])
    for alt, exp in ((1199, False), (1200, True), (2400, True), (2401, False)):
        assert ("DISEASE_005" in _ids(_run({**anth, "altitude_masl": alt}, "frijol")[0])) is exp, alt
    wet = _foto(temperature=26, relative_humidity=90, rain_7d=50)
    sig = lambda alt: tuple(r in _ids(_run({**wet, "altitude_masl": alt}, "platano")[0]) for r in ("DISEASE_004", "DISEASE_006"))
    assert sig(800) == (True, False) and sig(1500) == (True, True) and sig(1800) == (False, True) and sig(2100) == (False, False)
    assert "CLIMATE_003" in _ids(_run(_foto(altitude_masl=1501), "caupi")[0])
    assert "CLIMATE_003" not in _ids(_run(_foto(altitude_masl=1500), "caupi")[0])
    assert "CLIMATE_002" in _ids(_run(_foto(temperature=36), "maiz", "floracion")[0])
    assert "CLIMATE_002" not in _ids(_run(_foto(temperature=36), "maiz", "vegetativo")[0])


def _t_slope_rules():
    assert "SLOPE_001" in _ids(_run(_foto(slope_pct=30, rain_7d=80))[0])
    assert "SLOPE_001" not in _ids(_run(_foto(slope_pct=24, rain_7d=80))[0])
    assert "SLOPE_001" not in _ids(_run(_foto(slope_pct=30, rain_7d=59))[0])
    f, s = _run(_foto(slope_pct=40, soil_texture="Arcillosa"))
    assert "SLOPE_002" not in _ids(f) and any(x["rule_id"] == "SLOPE_002" and x["reason"] == "needs_series" for x in s)


def _t_new_symptom_rules_respect_crop():
    for key, rid, crop in (("necrosis_puntos_crecimiento_frutos_jovenes", "SYMPTOM_005", "calabaza"),
                           ("clorosis_generalizada_hojas_jovenes", "SYMPTOM_006", "maiz"),
                           ("bandas_cloroticas_entrenudos_cortos", "SYMPTOM_007", "maiz"),
                           ("amarillamiento_colapso_hojas_centrales", "SYMPTOM_008", "platano")):
        assert rid in _ids(_run(_foto(symptoms=[key]), crop)[0]), rid
    assert "SYMPTOM_007" not in _ids(_run(_foto(symptoms=["bandas_cloroticas_entrenudos_cortos"]), "frijol")[0])
    assert "SYMPTOM_008" not in _ids(_run(_foto(symptoms=["amarillamiento_colapso_hojas_centrales"]), "maiz")[0])
    f, _ = _run(_foto(symptoms=["amarillamiento_colapso_hojas_centrales"]), "platano")
    text = " ".join(x["recommendation"] + " ".join(x["cautions"]) for x in f)
    assert "ICA" in text and "diagnosticar" in text                     # el Moko se remite a un técnico


# ---------------- alertas (serie temporal) ----------------
def _t_temporal_rules_fire_with_series():
    i, _, _ = _serie("encharcamiento"); assert "TIME_001" in _ids(_run(i, "maiz")[0])
    assert "TIME_001" not in _ids(_run(i, "platano")[0])
    i, _, _ = _serie("encharcamiento"); assert "SLOPE_002" in _ids(_run({**i, "slope_pct": 40, "soil_texture": "Arcillosa"})[0])
    i, _, _ = _serie("noches_calidas"); assert "TIME_004" in _ids(_run(i, "frijol", "floracion")[0])
    assert "TIME_004" not in _ids(_run(i, "frijol", "vegetativo")[0])
    i, _, _ = _serie("transicion", "frijol", tmean=25.0); assert "TIME_003" in _ids(_run(i, "frijol")[0])
    i, _, _ = _serie("transicion", "frijol", tmean=22.0); assert "TIME_003" not in _ids(_run(i, "frijol")[0])   # sin calor no hay señal
    i, _, _ = _serie("alternancia", "frijol"); assert "TIME_002" in _ids(_run(i, "frijol", "llenado")[0])
    assert "TIME_002" not in _ids(_run(i, "frijol", "vegetativo")[0])
    i, _, _ = _serie("sequia"); assert "TIME_005" in _ids(_run(i)[0])
    i, _, _ = _serie("ola_calor"); assert "TIME_006" in _ids(_run(i)[0])
    i, _, _ = _serie("normal"); assert not any(r.startswith("TIME_") for r in _ids(_run(i, "frijol", "floracion")[0]))


def _t_insufficient_data_is_reported_not_guessed():
    clean, qa = clean_series(generate_series(30, "encharcamiento", gap_pct=80, seed=9))
    feats, _ = compute_features(clean)
    f, s = _run({**_static(), **feats}, "maiz")
    assert any(x["reason"] in ("insufficient_data", "needs_series") for x in s)
    assert "TIME_001" not in _ids(f) or feats["sat_days_consecutive"] is not None


# ---------------- reglas que se hablan ----------------
def _t_supersede_collapses_general_rules():
    f, _ = _run(_foto(altitude_masl=1800, temperature=18, relative_humidity=95, rain_7d=40), "frijol")
    by = {x["rule_id"]: x for x in f}
    assert by["DISEASE_001"]["superseded_by"] == "DISEASE_005" and by["DISEASE_005"]["superseded_by"] is None
    f, _ = _run(_foto(soil_moisture=90, soil_texture="Arcillosa", temperature=27), "maiz")
    by = {x["rule_id"]: x for x in f}
    assert by["WATER_002"]["superseded_by"] == "WATER_003"
    f, _ = _run(_foto(temperature=30, relative_humidity=50, rain_7d=5), "frijol")
    by = {x["rule_id"]: x for x in f}
    assert by["PEST_001"]["superseded_by"] == "PEST_003"


def _t_modifiers_change_confidence_with_a_reason():
    f, _ = _run(_foto(symptoms=["clorosis_hojas_viejas"]), "otro")
    base = {x["rule_id"]: x for x in f}["SYMPTOM_001"]["confidence_level"]
    f, _ = _run(_foto(symptoms=["clorosis_hojas_viejas"], soil_moisture=90, soil_texture="Arcillosa", temperature=27), "otro")
    s1 = {x["rule_id"]: x for x in f}["SYMPTOM_001"]
    assert s1["confidence_level"] == max(1, base - 1) and s1["interaction_notes"][0]["interaction_id"] == "MOD_001"
    f, _ = _run(_foto(symptoms=["coloracion_violacea"]), "otro")
    base4 = {x["rule_id"]: x for x in f}["SYMPTOM_004"]["confidence_level"]
    f, _ = _run(_foto(symptoms=["coloracion_violacea"], soil_ph=5.0), "otro")
    s4 = {x["rule_id"]: x for x in f}["SYMPTOM_004"]
    assert s4["confidence_level"] == min(3, base4 + 1) and s4["interaction_notes"][0]["effect"] == "sube la confianza"


def _t_syntheses_combine_components():
    f, _ = _run(_foto(soil_moisture=20, rain_7d=2, temperature=33), "otro")
    syn = {x["rule_id"]: x for x in f}
    assert "SYN_001" in syn and syn["SYN_001"]["kind"] == "synthesis" and set(syn["SYN_001"]["components"]) == {"WATER_001", "CLIMATE_001"}
    assert syn["WATER_001"]["integrated_in"] == ["SYN_001"] and f[0]["rule_id"] == "SYN_001"   # la síntesis va primero
    f, _ = _run(_foto(soil_ph=5.0, symptoms=["coloracion_violacea"]), "otro")
    assert "SYN_002" in _ids(f)
    f, _ = _run(_foto(symptoms=["clorosis_hojas_viejas"], soil_moisture=90, soil_texture="Arcillosa", temperature=27), "maiz")
    assert "SYN_003" in _ids(f)
    i, _, _ = _serie("sequia"); assert "SYN_004" in _ids(_run(i)[0])
    f, _ = _run(_foto(soil_moisture=20, rain_7d=2, temperature=20), "otro")
    assert "SYN_001" not in _ids(f)                                     # sin calor no hay síntesis


# ---------------- certeza y validación técnica ----------------
def _t_certainty_is_capped_until_a_technician_validates():
    nb = load_notebook()
    rule = {"id": "T_1", "module": "t", "title": "t", "when": {"var": "soil_ph", "op": "lt", "value": 5.5}, "severity": "high",
            "confidence": "high", "message": "m", "recommendation": "r", "cautions": [], "evidence_basis": "b",
            "evidence_status": "s", "threshold_basis": "claim", "validation": {"status": "sin_validar"}}
    f, _ = evaluate_alerts(_foto(soil_ph=5.0), [rule]); add_certainty(f)
    assert f[0]["certainty"]["level"] == "media" and "sin validación técnica" in f[0]["certainty"]["limiting_factors"]
    rule["validation"] = {"status": "validada"}
    f, _ = evaluate_alerts(_foto(soil_ph=5.0), [rule]); add_certainty(f)
    assert f[0]["certainty"]["level"] == "alta" and f[0]["certainty"]["limiting_factors"] == []
    f, _ = evaluate_alerts(_foto(soil_ph=5.0), [rule]); add_certainty(f, coverage=0.5)
    assert f[0]["certainty"]["level"] == "baja" and "calidad de los datos" in f[0]["certainty"]["limiting_factors"]
    rule["threshold_basis"] = "engine_heuristic"
    f, _ = evaluate_alerts(_foto(soil_ph=5.0), [rule]); add_certainty(f)
    assert f[0]["certainty"]["level"] == "baja"
    # con el cuaderno real, NADA es «alta» mientras no haya validaciones
    f, _ = _run(_foto(soil_ph=4.8, soil_moisture=90, soil_texture="Arcillosa", temperature=34, rain_7d=80, relative_humidity=95,
                      symptoms=["clorosis_hojas_viejas", "coloracion_violacea"]), "maiz", "floracion", nb=nb)
    assert f and all(x["certainty"]["level"] in ("baja", "media") for x in f)


def _t_validations_apply_reject_and_report():
    nb = load_notebook()
    vals = [{"rule_id": "SOIL_001", "status": "validada", "by": "Ing. Prueba", "date": "2026-11-14", "notes": "ok"},
            {"rule_id": "SOIL_002", "status": "rechazada", "by": "Ing. Prueba", "date": "2026-11-14", "notes": "umbral inadecuado"},
            {"rule_id": "NOPE", "status": "validada"}, {"rule_id": "WATER_001", "status": "tal vez"}]
    nb2, rep = apply_validations(nb, vals)
    assert rep["applied"] == 2 and rep["unknown_ids"] == ["NOPE"] and rep["invalid"][0]["rule_id"] == "WATER_001"
    assert nb["alert_rules"][0]["validation"]["status"] == "sin_validar"            # el original no se toca
    f, s = _run(_foto(soil_ph=5.0, organic_matter=1.0), nb=nb2)
    ids = _ids(f)
    assert "SOIL_001" in ids and "SOIL_002" not in ids
    assert {"rule_id": "SOIL_002", "reason": "disabled"} in s
    assert {x["rule_id"]: x for x in f}["SOIL_001"]["validation_status"] == "validada"
    vs = validation_summary(nb2)
    assert vs["validada"] == 1 and vs["rechazada"] == 1 and vs["total"] == 202


def _t_review_sheet_and_template():
    nb = load_notebook()
    sheet = review_sheet_csv(nb)
    assert sheet.startswith("\ufeff") and "SOIL_001" in sheet and "ROT_017" in sheet and "SYN_004" in sheet
    tpl = validation_template(nb)
    assert len(tpl) == 202 and {"rule_id", "status", "by", "date", "notes"} == set(tpl[0])
    assert "ROT_117" in sheet and "SLOPE_006" in sheet and "SYN_029" in sheet
    nb2, rep = apply_validations(nb, tpl)                                           # la plantilla se puede recargar tal cual
    assert rep["applied"] == 202 and not rep["unknown_ids"] and not rep["invalid"]


# ---------------- prácticas, conocimiento y cobertura ----------------
def _t_practices_follow_findings_and_context():
    nb = load_notebook()
    def pr(inputs, crop="otro", stage="no_especificada"):
        f, _ = _run(inputs, crop, stage, nb=nb)
        return {p["practice_id"]: p for p in evaluate_practices(nb["practices"], inputs, crop, stage, _ids(f))}
    p = pr(_foto(soil_moisture=90, soil_texture="Arcillosa", temperature=27), "maiz")
    assert "PRAC_001" in p and p["PRAC_001"]["why"][0]["type"] == "finding"
    assert "PRAC_001" not in pr(_foto(soil_moisture=90, soil_texture="Arcillosa", temperature=27), "platano")
    assert "PRAC_011" in pr(_foto(slope_pct=12)) and "PRAC_011" not in pr(_foto(slope_pct=9))
    assert "PRAC_012" in pr(_foto(slope_pct=35, soil_texture="Arcillosa")) and "PRAC_012" not in pr(_foto(slope_pct=35))
    assert "PRAC_003" in pr(_foto(soil_texture="Franca", rain_7d=70)) and "PRAC_003" not in pr(_foto(soil_texture="Arcillosa", rain_7d=70))
    assert "PRAC_004" in pr(_foto(), "cana_panelera", "vegetativo") and "PRAC_004" not in pr(_foto(), "maiz", "vegetativo")
    assert "PRAC_013" in pr(_foto(slope_pct=25), "cana_panelera") and "PRAC_013" not in pr(_foto(slope_pct=15), "cana_panelera")
    assert "PRAC_007" in pr(_foto(soil_ph=5.0)) and "PRAC_002" in pr(_foto(soil_moisture=20, rain_7d=2))
    assert "PRAC_005" in pr(_foto(), "otro", "establecimiento") and "PRAC_005" not in pr(_foto(), "otro", "floracion")
    assert all(x["tier"] == 1 for x in pr(_foto(slope_pct=35, soil_texture="Arcillosa", soil_ph=5.0), "cana_panelera", "vegetativo").values())


def _t_relevant_knowledge_uses_crop_stage_and_altitude():
    nb = load_notebook()
    k = {e["doc_order"]: e for e in relevant_knowledge(nb, "maiz", "floracion", 1000, set(), limit=60)}
    assert 35 in k and "coincide con la etapa" in k[35]["why"] and 11 in k
    assert 66 not in k                                                     # caña: no es de este cultivo
    low = {e["doc_order"] for e in relevant_knowledge(nb, "caupi", "no_especificada", 1000, set(), limit=60)}
    high = {e["doc_order"] for e in relevant_knowledge(nb, "caupi", "no_especificada", 2000, set(), limit=60)}
    assert 62 in low and 62 not in high                                     # afirmación 62: solo 0–1,500 msnm
    other = relevant_knowledge(nb, "otro", "no_especificada", None, set(), limit=60)
    assert other and all("general" in nb["claims"][e["doc_order"] - 1]["crops"] for e in other)
    linked = relevant_knowledge(nb, "otro", "no_especificada", None, {"SOIL_001"}, limit=60)
    assert any("respalda un hallazgo activo" in e["why"] for e in linked)
    assert len(relevant_knowledge(nb, "maiz", "floracion", 1000, set(), limit=5)) == 5


def _t_coverage_report():
    nb = load_notebook()
    cov = coverage_report(nb)
    assert cov["total"] == 101 and sum(cov["counts"].values()) == 101
    assert cov["counts"]["en_uso"] >= 56 and cov["counts"]["fuera_del_alcance"] == 2
    assert set(cov["used_by_kind"]) >= {"alertas", "rotación", "prácticas", "interacciones", "parámetros"}
    assert cov["counts"]["en_uso"] >= 90                                 # el cuaderno 2.3 aprovecha casi todas las afirmaciones
    assert cov["unlock_map"] and all(k.startswith(("lab:", "var:")) for k in cov["unlock_map"])


# ---------------- rotación ----------------
_ROT = dict(altitude_masl=1000, slope_pct=10, history=[["maiz"]], residue_management="incorporated",
            recent_n_fertilization="none_or_low", waterlogging_prone=False)


def _rot(**kw):
    nb = load_notebook()
    out = recommend_rotation({**_ROT, **kw}, nb["rotation_rules"])
    return out, {c["crop_key"]: c for c in out["candidates"]}


def _rids(entry, bucket):
    return {r["rule_id"] for r in entry[bucket]}


def _t_rotation_sequences():
    out, c = _rot()
    assert c["frijol"]["status"] == "favorecido" and {"ROT_002", "ROT_009"} <= _rids(c["frijol"], "in_favor")
    assert c["maiz"]["status"] == "con_reservas" and "ROT_001" in _rids(c["maiz"], "against")
    assert c["cana_panelera"]["status"] == "desaconsejado" and "ROT_006" in _rids(c["cana_panelera"], "blocking")
    out, c = _rot(history=[["cana_panelera"]])
    assert out["situation"] == "cana_establecida" and "cana_panelera" not in c
    assert c["maiz"]["status"] == "desaconsejado" and "ROT_005" in _rids(c["maiz"], "blocking")
    assert all("ROT_007" in _rids(c[k], "in_favor") for k in ("frijol", "caupi")) and "ROT_008" in _rids(c["canavalia"], "in_favor")
    out, c = _rot(history=[["maiz", "frijol", "calabaza"]])
    assert all(e["status"] in ("con_reservas", "desaconsejado") for k, e in c.items() if k != "platano")   # el plátano no repite familia
    assert any("asociación completa" in w for w in out["global_cautions"])
    out, c = _rot(history=[])
    assert out["situation"] == "sin_historial" and all(e["status"] == "sin_evaluar" for e in c.values())
    _, a = _rot(history=[["frijol"]]); _, b = _rot(history=[["frijol"], ["maiz"], ["calabaza"]])
    assert {k: v["status"] for k, v in a.items()} == {k: v["status"] for k, v in b.items()}


def _t_rotation_thresholds_and_missing_inputs():
    assert "ROT_011" not in _rids(_rot(altitude_masl=1500)[1]["caupi"], "against")
    assert "ROT_011" in _rids(_rot(altitude_masl=1501)[1]["caupi"], "against")
    for alt, exp in ((1199, False), (1200, True), (2400, True), (2401, False)):
        assert ("ROT_010" in _rids(_rot(altitude_masl=alt)[1]["frijol"], "notes")) is exp, alt
    out, c = _rot(altitude_masl=None)
    miss = {m["variable"]: m for m in out["missing_inputs"]}
    assert set(miss["altitude_masl"]["affects_rules"]) == {"ROT_010", "ROT_011"}
    assert set(miss["altitude_masl"]["affects_crops"]) == {"Fríjol común", "Fríjol caupí"}
    assert "ROT_003" in _rids(_rot(history=[["frijol"]])[1]["maiz"], "in_favor")
    out, c = _rot(history=[["frijol"]], residue_management="removed")
    assert "ROT_003" not in _rids(c["maiz"], "in_favor") and "ROT_004" in _rids(c["maiz"], "notes")
    out, c = _rot(history=[["frijol"]], residue_management=None)
    assert "residue_management" in {m["variable"] for m in out["missing_inputs"]}
    _, c = _rot(recent_n_fertilization="high")
    assert all("ROT_013" in _rids(c[k], "against") for k in ("frijol", "caupi", "canavalia")) and "ROT_013" not in _rids(c["maiz"], "against")
    assert "ROT_012" in _rids(_rot(waterlogging_prone=True)[1]["caupi"], "against")
    assert validate_rotation_profile(_ROT) == [] and validate_rotation_profile({"history": [["trigo"]]})


# ---------------- salida y seguridad ----------------
def _t_payload_contract_and_safety():
    nb = load_notebook()
    inputs, feats, qa = _serie("encharcamiento", "maiz")
    f, s = _run({**inputs, "slope_pct": 40, "soil_texture": "Arcillosa"}, "maiz", "floracion", nb=nb, coverage=qa["overall_coverage_last14"])
    prac = evaluate_practices(nb["practices"], inputs, "maiz", "floracion", _ids(f))
    know = relevant_knowledge(nb, "maiz", "floracion", 1000, _ids(f))
    rot = recommend_rotation(_ROT, nb["rotation_rules"])
    p = build_payload(nb, mode="serie", inputs=inputs, crop="maiz", stage="floracion", findings=f, skipped=s,
                      practices=prac, knowledge=know, quality=qa, rotation=rot)
    json.dumps(p, ensure_ascii=False)                                              # debe ser serializable
    assert p["schema_version"] == SCHEMA_VERSION and p["data_mode"] == "serie" and p["validation_summary"]["total"] == 202
    assert p["risk_overview"]["overall"] == "high" and p["notebook_audit"]["errors"] == 0 and p["notebook_audit"]["warnings"] > 0
    assert p["notebook_audit"]["base_claims_verified"] is False and p["agent_instructions"]["must_explain_each_finding_with_its_why_block"]
    assert p["inference"]["findings_count"] == len([x for x in f if not x["superseded_by"]])
    ai = p["agent_instructions"]
    assert ai["must_not_give_fertilizer_doses"] and ai["must_recommend_technician_review"] and ai["must_report_certainty_level_of_each_finding"]
    assert all("certainty" in x for x in p["inference"]["findings"])


def _t_no_fertilizer_doses_anywhere_in_generated_guidance():
    import re
    nb = load_notebook()
    dose = re.compile(r"\d+([.,]\d+)?\s*(kg|g|l|litros?)\s*(/|por)\s*(ha|hect|planta|árbol)|\bkg\s*n/ha", re.I)
    texts = []
    for sec in ("alert_rules", "rotation_rules"):
        for r in nb[sec]:
            texts += [r["message"], r.get("recommendation", ""), *r["cautions"]]
    for i in nb["interactions"]:
        texts += [i.get("message", ""), i.get("recommendation", ""), i.get("note", ""), *i.get("cautions", [])]
    for p in nb["practices"]:
        texts += [p["text"], *p["cautions"]]
    bad = [t for t in texts if dose.search(t)]
    assert not bad, bad[:2]
    assert all(p["tier"] == 1 for p in nb["practices"])


# ---------------- novedades de la 3.1 ----------------
def _t_v31_audit_has_two_levels():
    audit = audit_notebook(load_notebook())
    w = "\n".join(audit["warnings"])
    assert audit["errors"] == [] and audit["warnings"]
    assert "sin ficha en el cuaderno" in w and "repite la misma evidencia que MOD_002" in w and "[PRAC_074]" in w
    reg = reference_registry(load_notebook())
    assert reg["SRC_001"]["url"].startswith("http") and reg["B01"]["kind"] == "practice_bibliography"


def _t_v31_broken_rule_is_quarantined_not_fatal():
    nb = load_notebook()
    bad_type = {**nb["alert_rules"][2], "id": "BAD_1", "when": {"var": "soil_texture", "op": "lt", "value": 5}}
    no_field = {k: v for k, v in nb["alert_rules"][2].items() if k != "message"}
    no_field["id"] = "BAD_2"
    f, s = evaluate_alerts(_foto(soil_ph=5.0), [bad_type, no_field, nb["alert_rules"][2]])
    assert _ids(f) == {"SOIL_001"}
    assert {x["rule_id"] for x in s if x["reason"] == "invalid_rule"} == {"BAD_1", "BAD_2"}
    out = recommend_rotation(_ROT, [{**nb["rotation_rules"][0], "when": {"var": "altitude_masl", "op": "contains", "value": 1}}])
    assert all(c["status"] == "aceptable" for c in out["candidates"])


def _t_v31_why_view_shows_decisive_data():
    nb = load_notebook()
    r = analyze(nb, _foto(soil_ph=5.0))
    why = {x["rule_id"]: x for x in r["findings"]}["SOIL_001"]["why"]
    assert len(why) == 1 and {k: why[0][k] for k in ("variable", "label", "observed", "operator", "threshold", "planned_source", "source_kind")} == {
        "variable": "soil_ph", "label": "pH del suelo", "observed": 5.0, "operator": "<", "threshold": 5.5,
        "planned_source": PLANNED_DATA_SOURCES["soil_ph"][0], "source_kind": "suelo local"}
    assert why[0]["data_source"] is None and why[0]["observed_text"] == "5"       # sin procedencia declarada, no se inventa una
    assert "IGAC" in why[0]["planned_source"]
    # en un «any» solo aparece la rama que de verdad se cumplió
    r = analyze(nb, _foto(soil_moisture=85, rain_7d=70, soil_texture="Franca"))
    why = {x["rule_id"]: x for x in r["findings"]}["WATER_002"]["why"]
    assert [w["variable"] for w in why] == ["soil_moisture", "rain_7d"] and "SMAP" in why[0]["planned_source"]
    assert all(v in PLANNED_DATA_SOURCES for v in KNOWN_VARIABLES)
    assert explain_condition({"not": {"var": "soil_ph", "op": "lt", "value": 5.5}}, {"soil_ph": 6.0})[0]["operator"] == "no <"


def _t_v31_documentary_review_is_not_field_validation():
    nb = load_notebook()
    r = analyze(nb, _foto(soil_moisture=18, rain_7d=4), "maiz", "vegetativo")
    w4 = {x["rule_id"]: x for x in r["findings"]}["WATER_004"]
    assert w4["validation_status"] == "revision_documental_con_fuentes_externas"
    assert w4["certainty"]["level"] != "alta" and FACTOR_LABEL["solo_revision_documental"] in w4["certainty"]["limiting_factors"]
    assert w4["threshold_status"] == "no_calibrado_localmente" and [s["id"] for s in w4["external_sources"]] == ["SRC_001", "SRC_002"]
    rule = {**nb["alert_rules"][2], "threshold_basis": "claim", "confidence": "high",
            "validation": {"status": "verificada_principio_general"}}
    f, _ = evaluate_alerts(_foto(soil_ph=5.0), [rule]); add_certainty(f)
    assert f[0]["certainty"]["level"] == "media"
    assert any("revisión documental" in c for c in global_cautions(nb))


def _t_v31_modifiers_net_sum_safeguards_and_no_double_counting():
    nb = load_notebook()
    # salvaguarda (delta 0): deja nota y no cambia la confianza
    f, _ = _run(_foto(soil_moisture=18, rain_7d=4, symptoms=["clorosis_hojas_viejas"]), "maiz", "vegetativo", nb=nb)
    p2 = {x["rule_id"]: x for x in f}["PEST_002"]
    assert p2["confidence"] == p2["confidence_base"] and any(n["effect"].startswith("salvaguarda") for n in p2["interaction_notes"])
    # MOD_002 y MOD_013 aportan la MISMA evidencia (SOIL_001 → SYMPTOM_004): cuenta una sola vez
    f, _ = _run(_foto(symptoms=["coloracion_violacea"], soil_ph=5.0), nb=nb)
    s4 = {x["rule_id"]: x for x in f}["SYMPTOM_004"]
    assert s4["confidence_net_delta"] == 1 and [n["effect"] for n in s4["interaction_notes"]] == [
        "sube la confianza", "evidencia ya contada: no se suma otra vez"]
    # el resultado no depende del orden en que estén escritas las interacciones
    inputs = _foto(soil_ph=4.9, organic_matter=1.5, soil_moisture=88, soil_texture="Arcillosa", temperature=27, rain_7d=70,
                   symptoms=["clorosis_hojas_viejas", "necrosis_bordes_hojas_viejas", "coloracion_violacea"])
    a, _ = evaluate_alerts(inputs, nb["alert_rules"], "frijol"); a = apply_interactions(a, nb["interactions"])
    b, _ = evaluate_alerts(inputs, nb["alert_rules"], "frijol"); b = apply_interactions(b, nb["interactions"][::-1])
    assert {x["rule_id"]: x["confidence"] for x in a} == {x["rule_id"]: x["confidence"] for x in b}
    assert any(x.get("confidence_net_delta") for x in a)


def _t_v31_specific_signals_refine_general_ones():
    assert _box_implies(_as_box({"all": [{"var": "a", "op": "lt", "value": 20}, {"var": "b", "op": "lt", "value": 10}]}),
                        _as_box({"all": [{"var": "a", "op": "lt", "value": 25}, {"var": "b", "op": "lt", "value": 10}]}))
    assert not _box_implies(_as_box({"var": "a", "op": "lte", "value": 25}), _as_box({"var": "a", "op": "lt", "value": 25}))
    assert _as_box({"any": [{"var": "a", "op": "lt", "value": 1}]}) is None
    nb = load_notebook()
    by = {x["rule_id"]: x for x in analyze(nb, _foto(soil_moisture=18, rain_7d=4, soil_ph=5.0), "maiz", "vegetativo")["findings"]}
    assert by["WATER_004"]["refines"] == ["WATER_001"] and by["WATER_001"]["refined_by"] == ["WATER_004"]
    assert by["WATER_001"]["superseded_by"] is None                     # enlaza, no oculta
    assert "PEST_002" not in by["WATER_001"]["refined_by"]              # misma condición, pero otro módulo
    by = {x["rule_id"]: x for x in analyze(nb, _foto(soil_ph=5.0), "frijol")["findings"]}
    assert by["SOIL_007"]["refines"] == ["SOIL_001"]                    # misma condición, contexto más estrecho


def _t_v31_new_crops_and_contexts():
    f, _ = _run(_foto(organic_matter=1.5, rain_7d=40), "canavalia", "establecimiento")
    assert "SOIL_009" in _ids(f)
    assert "SOIL_009" not in _ids(_run(_foto(organic_matter=1.5, rain_7d=40), "maiz", "establecimiento")[0])
    assert "SOIL_005" in _ids(_run(_foto(soil_ph=4.7), "tres_hermanas")[0])     # el sistema activa lo de sus componentes
    i, _, _ = _serie("noches_calidas")
    assert "TIME_008" not in _ids(_run(i, "calabaza", "floracion")[0])          # faltan los días calurosos
    assert "SLOPE_004" in _ids(_run(_foto(slope_pct=20, rain_7d=50))[0]) and "SLOPE_004" not in _ids(_run(_foto(slope_pct=25, rain_7d=50))[0])


def _t_v31_rotation_systems_lot_rules_and_general_guidance():
    out, c = _rot(history=[["cana_panelera"]])
    th = c["tres_hermanas"]
    assert th["status"] == "desaconsejado" and th["blocking"][0]["rule_id"] == "ROT_005" and th["blocking"][0]["inherited_from"] == "Maíz"
    out, c = _rot()
    assert {"platano", "tres_hermanas"} <= set(c)
    assert c["platano"]["status"] == "aceptable" and c["platano"]["general_guidance"] and not c["platano"]["in_favor"]
    assert all(r["scope"] == "generic" for e in c.values() for r in e["general_guidance"])
    # la quema del rastrojo es una regla del LOTE: se informa una vez y no bloquea a todos los cultivos
    out, c = _rot(residue_management="burned")
    assert [x["rule_id"] for x in out["lot_findings"]] == ["ROT_042"] and out["lot_findings"][0]["effect"] == "block"
    assert c["frijol"]["status"] == "favorecido" and not any("ROT_042" in _rids(e, "blocking") for e in c.values())
    assert "ROT_035" in _rids(_rot(residue_management="surface_mulch")[1]["frijol"], "in_favor")
    # un ciclo con el sistema asociado equivale a sus componentes
    _, a = _rot(history=[["tres_hermanas"]]); _, b = _rot(history=[["maiz", "frijol", "calabaza"]])
    assert {k: v["status"] for k, v in a.items()} == {k: v["status"] for k, v in b.items()}
    out, c = _rot(slope_pct=None)
    assert "slope_pct" in {m["variable"] for m in out["missing_inputs"]}
    assert "ROT_117" in _rids(_rot(slope_pct=30)[1]["calabaza"], "in_favor") and "ROT_117" not in _rids(_rot(slope_pct=0)[1]["calabaza"], "in_favor")
    assert validate_rotation_profile({**_ROT, "residue_management": "surface_mulch"}) == [] and validate_rotation_profile({**_ROT, "slope_pct": -3})
    nb = load_notebook()
    assert {rule_scope(r) for r in nb["rotation_rules"]} == {"lot", "generic", "contextual"}


def _t_v31_practices_are_ranked_and_carry_evidence():
    nb = load_notebook()
    r = analyze(nb, _foto(soil_ph=5.0, organic_matter=1.5, soil_moisture=18, rain_7d=4, slope_pct=30), "maiz", "vegetativo")
    pr = r["practices"]
    assert [p["relevance"] for p in pr] == sorted((p["relevance"] for p in pr), reverse=True)
    assert pr[0]["why"][0]["type"] == "finding" and pr[-1]["practice_id"] == "PRAC_074" and pr[-1]["why"] == [{"type": "general"}]
    ev = next(p["evidence"] for p in pr if p["evidence"])
    assert ev["status"] and ev["sources"] and ev["sources"][0]["url"].startswith("http")
    assert next(p for p in pr if p["practice_id"] == "PRAC_007")["evidence"] is None      # las 16 prácticas base no traen bibliografía
    assert len(analyze(nb, _foto(soil_ph=5.0), "maiz", "vegetativo", practice_limit=3)["practices"]) == 3
    assert all(p["tier"] == 1 for p in pr)


def _t_v31_real_data_loaders():
    power = {"header": {"fill_value": -999.0}, "properties": {"parameter": {
        "T2M_MAX": {"20261101": 28.5, "20261102": -999.0}, "T2M_MIN": {"20261101": 17.2, "20261102": 16.9},
        "RH2M": {"20261101": 81.0, "20261102": 79.5}, "PRECTOTCORR": {"20261101": 12.3, "20261102": 0.0},
        "GWETROOT": {"20261101": 0.62, "20261102": 0.6}}}}
    s, info = series_from_nasa_power(power)
    assert s[0] == {"tmax": 28.5, "tmin": 17.2, "rh": 81.0, "rain": 12.3, "soil_moisture": 62.0}
    assert s[1]["tmax"] is None and s[1]["soil_moisture"] == 60.0 and info["last_date"] == "20261102" and not info["variables_absent"]
    del power["properties"]["parameter"]["GWETROOT"]
    s, info = series_from_nasa_power(power)
    assert s[0]["soil_moisture"] is None and info["variables_absent"] == ["soil_moisture"]
    try:
        series_from_nasa_power({"foo": 1}); raise AssertionError("debió rechazar el archivo")
    except ValueError:
        pass
    s, info = series_from_csv("fecha;Tmax;tmin;HR;lluvia\n2026-11-02;29,5;18;80;0\n2026-11-01;28;17,5;;12,5\n")
    assert s == [{"tmax": 28.0, "tmin": 17.5, "rh": None, "rain": 12.5, "soil_moisture": None},
                 {"tmax": 29.5, "tmin": 18.0, "rh": 80.0, "rain": 0.0, "soil_moisture": None}]
    assert info["variables_absent"] == ["soil_moisture"] and info["first_date"] == "2026-11-01"
    # una serie real pasa por la misma limpieza y derivación que la sintética
    real = [{"tmax": 30.0, "tmin": 19.0, "rh": 70.0, "rain": 0.0, "soil_moisture": 20.0}] * 30
    clean, qa = clean_series(real)
    feats, _ = compute_features(clean)
    assert feats["dry_days_consecutive"] == 30 and "TIME_005" in _ids(_run({**_static(), **feats})[0])


def _t_v31_analyze_is_complete_and_serializable():
    nb = load_notebook()
    r = analyze(nb, _foto(soil_ph=5.0, soil_moisture=18, rain_7d=4, temperature=33), "maiz", "floracion")
    assert set(r) == {"findings", "skipped", "overview", "practices", "knowledge"}
    assert r["overview"]["overall"] == "high" and r["overview"]["by_module"]["soil"]["severity"] == "high"
    assert all({"why", "certainty", "external_sources", "refines", "refined_by"} <= set(f) for f in r["findings"])
    assert risk_overview([]) == {"overall": "none", "by_module": {}}
    p = build_payload(nb, mode="foto", inputs=_foto(), crop="maiz", stage="floracion", findings=r["findings"], skipped=r["skipped"],
                      practices=r["practices"], knowledge=r["knowledge"])
    json.dumps(p, ensure_ascii=False)
    assert p["data_source"]["source"].startswith("valores escritos")


# ---------------- novedades de la 4.1: datos reales del territorio ----------------
def _mini_bundle() -> dict:
    """Bundle canónico diminuto (mismo esquema que el real) para probar la lectura sin cargar 800 MB."""
    may = {"time_start": "2026-05-01T00:00:00+00:00", "time_end": "2026-06-01T00:00:00+00:00"}
    april = {"time_start": "2026-04-01T00:00:00+00:00", "time_end": "2026-05-01T00:00:00+00:00"}
    pos = {"1": (6.60, -75.90), "2": (6.60, -75.89), "3": (6.61, -75.90)}

    def rec(gid, **kw):
        return {"grid_id": gid, "spatial_id": gid, "latitude": pos[gid][0], "longitude": pos[gid][1], **kw}

    def ndvi(gid, value, flag):
        return rec(gid, value=value, quality_flag=flag, spatial_coverage=0.6 if value else 0.1, valid_scene_count=3 if value else 0,
                   source="COPERNICUS_SENTINEL2", product="S2_L2A", statistic="mean", **may)

    def rain(gid, source, product, value, period=may, **kw):
        return rec(gid, value=value, quality_flag="valid", unit="mm", statistic="sum", source=source, product=product,
                   version=None, geometry_status="x", spatial_support="master_grid_cell", **period, **kw)

    def soil(gid, flag="valid", **fields):
        return [rec(gid, variable=k, value=v, quality_flag=flag, source="IGAC", product="SUELOS_ANTIOQUIA_100K") for k, v in fields.items()]

    water = {f: "Cuerpo de agua" for f in SOIL_FIELDS}
    unit = {**{f: "x" for f in SOIL_FIELDS}, "soil_unit_code": "YA", "soil_unit_phase": "YAe2",
            "soil_characteristics_text": "Profundos, bien drenados, texturas medias, reacción muy fuerte a fuertemente ácida, fertilidad baja",
            "soil_climate_class": "Templado húmedo"}
    station = rec("2", value=None, quality_flag="insufficient_temporal_coverage", source="IDEAM_DHIME", station_id="1",
                  station_name="PRUEBA", observed_days=8, expected_days=31, spatial_support="station_point", **may)
    return {"schema": "territorial_canonical_bundle", "schema_version": "1.0", "generated_at_utc": "2026-11-14T00:00:00+00:00", "manifest": [],
            "variables": {
                "ndvi": [{"data": [ndvi("1", 0.71, "valid"), ndvi("2", 0.1, "valid"), ndvi("3", None, "insufficient_coverage")]}],
                "precipitation_amount": [{"data": [rain("1", "GPM_IMERG", "GPM_3IMERGHHL", 310.0), rain("1", "NASA POWER", "PRECTOTCORR", 280.0),
                                                   rain("1", "GPM_IMERG", "GPM_3IMERGHHL", 5.0, april),
                                                   rain("2", "GPM_IMERG", "GPM_3IMERGHHL", 300.0), rain("3", "GPM_IMERG", "GPM_3IMERGHHL", 290.0)]},
                                         {"data": [station]}],
                "soil": [{"data": soil("1", **unit) + soil("2", "partial_spatial_coverage", **water)}]}}


def _mini_index() -> dict:
    return _prepare_index(build_territorial_index(_mini_bundle()))


def _real_index():
    """El índice del territorio real, si el bundle (o su índice) está junto al motor."""
    try:
        return load_territorial_index()
    except FileNotFoundError:
        return None


def _t_v41_uncertain_values_are_evaluated_in_three_states():
    acid = Range(5.0, 5.5)                                              # «fuertemente ácida»: [5.0, 5.5)
    assert compare_uncertain(acid, "lt", 5.5) is True and compare_uncertain(acid, "gte", 5.5) is False
    assert compare_uncertain(acid, "lt", 5.2) is None and compare_uncertain(acid, "gt", 5.0) is None
    assert compare_uncertain(acid, "gte", 5.0) is True and compare_uncertain(acid, "lt", 5.0) is False
    closed = Range(21.0, 57.3, True)                                    # dos fuentes: el extremo superior sí cuenta
    assert compare_uncertain(closed, "lt", 57.3) is None and compare_uncertain(closed, "lte", 57.3) is True
    assert compare_uncertain(closed, "gte", 60) is False and compare_uncertain(Range(63.2, 70.0, True), "gte", 60) is True
    assert compare_uncertain(Range(5, 5, True), "eq", 5) is True
    tex = OneOf({"Arcillosa", "Franca"})
    assert compare_uncertain(tex, "eq", "Arcillosa") is None and compare_uncertain(tex, "eq", "Arenosa") is False
    assert compare_uncertain(tex, "neq", "Arenosa") is True and compare_uncertain(OneOf({"Franca"}), "eq", "Franca") is True
    assert compare_uncertain(tex, "in", ["Arcillosa", "Franca", "Arenosa"]) is True
    assert eval3({"all": [{"var": "ph", "op": "lt", "value": 5.5}, {"var": "t", "op": "eq", "value": "Arenosa"}]}, {"ph": acid, "t": tex}) == (False, set())
    assert eval3({"var": "ph", "op": "lt", "value": 5.2}, {"ph": acid}) == (None, {"ph"})
    # una regla cuyo umbral cae dentro del intervalo NO se activa ni se descarta: se informa
    f, s = _run({"soil_ph": Range(4.5, 5.5), "symptoms": []})
    assert "SOIL_001" in _ids(f)                                        # pH < 5.5 con todo el intervalo
    assert any(x["rule_id"] == "SOIL_003" and x["reason"] in ("ambiguous_range", "missing_input") for x in s)
    f, s = _run({"soil_ph": Range(4.5, 6.0)})
    assert "SOIL_001" not in _ids(f) and {"rule_id": "SOIL_001", "reason": "ambiguous_range", "missing": ["soil_ph"]} in s
    assert jsonable({"a": acid, "b": tex, "_x": 1}) == {"a": {"min": 5.0, "max": 5.5, "max_inclusive": False, "text": "5 a 5.5"},
                                                         "b": {"one_of": ["Arcillosa", "Franca"], "text": "Arcillosa o Franca"}}
    assert thermal_floor(Range(1000, 2000)) == "templado" and thermal_floor(Range(0, 2000)) == "cálido a templado"


def _t_v41_igac_soil_text_is_read_as_classes():
    assert parse_reaction("…texturas medias, reacción muy fuerte a fuertemente ácida, fertilidad baja") == Range(4.5, 5.5)
    assert parse_reaction("reacción extremada a fuertemente ácida, alta saturación de aluminio") == Range(3.5, 5.5)
    assert parse_reaction("reacción fuertemente ácida a neutra, fertilidad moderada") == Range(5.0, 7.3)
    assert parse_reaction("reacción moderadamente ácida a ligeramente alcalina, fertilidad muy alta") == Range(5.5, 7.8)
    assert parse_reaction("texturas finas y muy finas, fuerte y muy fuertemente ácidos, fertilidad moderada a alta") == Range(4.5, 5.5)
    assert parse_reaction("la reacción es fuerte a ligeramente ácida, fertilidad moderada") == Range(5.0, 6.5)
    assert parse_reaction("Profundos, bien drenados, texturas variadas, fertilidad moderada, erosión ligera a moderada") is None
    assert parse_texture("texturas medias, reacción muy fuerte") == "Franca" and parse_texture("texturas gruesas, fertilidad baja") == "Arenosa"
    assert parse_texture("texturas finas y muy finas, fuerte") == "Arcillosa"
    assert parse_texture("texturas finas a medias, erosión ligera") == OneOf({"Arcillosa", "Franca"})
    assert parse_texture("texturas variables finas a gruesas, erosión moderada") == OneOf({"Arcillosa", "Franca", "Arenosa"})
    assert parse_texture("texturas gruesas y finas y fertilidad moderada") == OneOf({"Arcillosa", "Arenosa"})
    assert parse_texture("texturas finas; moderadamente finas y medias, fertilidad") == OneOf({"Arcillosa", "Franca"})
    assert parse_texture("bien drenados, texturas variadas, fertilidad moderada") is None
    assert parse_drainage("Profundos, bien drenados, texturas medias") == ("bien drenado", False)
    assert parse_drainage("Muy superficiales, drenaje natural pobre a pantanoso, inundables")[1] is True
    assert parse_drainage("Profundos y superficiales, bien a pobremente drenados, texturas variadas")[1] is None
    assert parse_drainage("Profundos, bien drenados", ["inundable"])[1] is True
    ph = parse_phase("YAf2", "YA")
    assert ph["slope"] == Range(50, 75) and ph["erosion_degree"] == 2 and ph["modifiers"] == []
    assert parse_phase("RAai", "RA")["modifiers"] == ["inundable"] and parse_phase("CNfp3", "CN")["modifiers"] == ["pedregosa"]
    assert parse_phase("CA", "CA")["slope"] is None and parse_phase("LHa", "LH")["slope"] == Range(0, 3)
    assert parse_climate("Templado húmedo a muy húmedo") == (Range(1000, 2000), ["templado"])
    assert parse_climate("Frío húmedo y frío muy húmedo")[0] == Range(2000, 3000) and parse_climate("Muy frío y muy húmedo")[0] == Range(3000, 3600)
    assert parse_climate("Cálido seco a cálido húmedo")[0] == Range(0, 1000) and parse_climate("Zona urbana") == (None, [])


def _t_v41_index_keeps_only_what_the_bundle_supports():
    idx = _mini_index()
    assert idx["n_cells"] == 3 and idx["records_from_older_periods_ignored"] == 1 and len(idx["soil_units"]) == 2
    assert set(idx["sources"]["rain"]) == {"GPM_IMERG", "NASA POWER"} and idx["stations"][0]["value"] is None
    t = territorial_inputs(idx, idx["_pos"]["1"], now=datetime(2026, 6, 10, tzinfo=timezone.utc))
    i = t["inputs"]
    assert t["agricultural"] and set(i) == {"soil_ph", "soil_texture", "slope_pct", "altitude_masl", "rain_month", "rain_7d", "ndvi"}
    assert i["soil_ph"] == Range(4.5, 5.5) and i["soil_texture"] == "Franca" and i["slope_pct"] == Range(25, 50)
    assert i["altitude_masl"] == Range(1000, 2000) and i["ndvi"] == 0.71
    assert i["rain_month"] == Range(280.0, 310.0, True) and i["rain_7d"] == Range(63.2, 70.0, True)     # ×7/31, no la última semana
    assert t["var_quality"] == {"soil_ph": 2, "soil_texture": 2, "slope_pct": 2, "altitude_masl": 2, "rain_month": 3, "rain_7d": 1, "ndvi": 3}
    assert "IGAC" in t["provenance"]["soil_ph"]["source"] and "reparto uniforme" in t["provenance"]["rain_7d"]["method"]
    assert set(t["unavailable"]) == {"temperature", "relative_humidity", "soil_moisture", "organic_matter", "symptoms"}
    assert t["context"]["data_age_days"] == 9 and not any("hace" in n for n in t["notes"])
    assert t["context"]["erosion_degree"] == "moderada" and t["context"]["waterlogging_prone"] is False
    old = territorial_inputs(idx, idx["_pos"]["1"], now=datetime(2026, 11, 15, tzinfo=timezone.utc))
    assert any("no las condiciones de hoy" in n for n in old["notes"])
    water = territorial_inputs(idx, idx["_pos"]["2"])
    assert not water["agricultural"] and "soil_ph" not in water["inputs"] and any("no es un suelo agrícola" in n for n in water["notes"])
    bare = territorial_inputs(idx, idx["_pos"]["3"])
    assert "ndvi" not in bare["inputs"] and bare["inputs"]["rain_month"] == 290.0 and any("sin unidad" in n or "no tiene unidad" in n for n in bare["notes"])
    assert find_cell(idx, 6.6001, -75.9001)[0] == idx["_pos"]["1"] and find_cell(idx, 6.6001, -75.9001)[1] < 0.1
    try:
        build_territorial_index({"schema": "otra_cosa"}); raise AssertionError("debió rechazar el bundle")
    except ValueError:
        pass


def _t_v41_engine_runs_on_territory_without_inventing_inputs():
    nb, idx = load_notebook(), _mini_index()
    p = evaluate_point(nb, idx, 6.6001, -75.9001, "maiz", "vegetativo")
    json.dumps(p, ensure_ascii=False)
    assert p["data_mode"] == "territorio" and p["territory"]["cell"]["grid_id"] == "1" and p["territory"]["cell"]["distance_km"] < 0.1
    by = {f["rule_id"]: f for f in p["inference"]["findings"]}
    assert {"SOIL_001", "SLOPE_001"} <= set(by)
    # SOIL_001: dato derivado de una clase → certeza «media»; SLOPE_001 usa la lluvia semanal ESTIMADA → «baja»
    assert by["SOIL_001"]["certainty"]["level"] == "media" and by["SLOPE_001"]["certainty"]["level"] == "baja"
    assert "calidad de los datos" in by["SLOPE_001"]["certainty"]["limiting_factors"]
    w = by["SOIL_001"]["why"][0]
    assert w["observed_text"] == "4.5 a 5.5" and "IGAC" in w["data_source"] and w["quality_level"] == "media"
    reasons = {s["rule_id"]: s["reason"] for s in p["inference"]["rules_skipped"]}
    assert reasons["CLIMATE_001"] == "missing_input" and reasons["SYMPTOM_001"] == "missing_input" and reasons["TIME_005"] == "needs_series"
    assert reasons["SOIL_005"] == "ambiguous_range"                      # pH < 4.8 no se puede decidir con 4.5–5.5
    assert "temperature" not in p["input_state"] and "soil_moisture" not in p["input_state"] and "symptoms" not in p["input_state"]
    assert p["input_state"]["soil_ph"] == {"min": 4.5, "max": 5.5, "max_inclusive": False, "text": "4.5 a 5.5"}
    assert any("no trae" in c for c in p["inference"]["global_cautions"])
    assert p["agent_instructions"]["must_report_intervals_as_intervals_not_as_single_values"]
    far = evaluate_point(nb, idx, 7.5, -75.0)
    assert any("FUERA de la grilla" in n for n in far["territory"]["notes"])


def _t_v41_real_layers_override_the_territory():
    nb, idx = load_notebook(), _mini_index()
    # lo medido en el lote manda sobre la clase del IGAC
    p = evaluate_point(nb, idx, 6.6, -75.9, "maiz", "vegetativo", field={"soil_ph": 6.2, "organic_matter": 1.5, "symptoms": []})
    ids = {f["rule_id"] for f in p["inference"]["findings"]}
    assert "SOIL_001" not in ids and "SOIL_002" in ids
    assert p["input_provenance"]["soil_ph"]["source"] == FIELD_SOURCE and p["input_provenance"]["soil_ph"]["quality_level"] == 3
    assert not any(s["rule_id"].startswith("SYMPTOM") and s["reason"] == "missing_input" for s in p["inference"]["rules_skipped"])
    # una serie diaria REAL reemplaza la lluvia semanal estimada y habilita las reglas del tiempo
    dry = [{"tmax": 33.0, "tmin": 19.0, "rh": 55.0, "rain": 0.0, "soil_moisture": 18.0}] * 30
    p = evaluate_point(nb, idx, 6.6, -75.9, "maiz", "vegetativo", series=dry, series_info={"source": "CSV", "first_date": "2026-10-01", "last_date": "2026-10-30"})
    ids = {f["rule_id"] for f in p["inference"]["findings"]}
    assert {"TIME_005", "WATER_004", "SOIL_001"} <= ids and "SLOPE_001" not in ids
    assert p["input_state"]["rain_7d"] == 0.0 and p["input_provenance"]["rain_7d"]["source"].startswith(SERIES_SOURCE)
    assert p["input_provenance"]["soil_ph"]["source"].startswith("IGAC")
    # una serie con huecos no inventa: la variable queda como «datos insuficientes»
    inputs, prov, q = merge_inputs(None, {"dry_days_consecutive": None, "temperature": 25.0}, {"soil_ph": None})
    assert inputs == {"dry_days_consecutive": None, "temperature": 25.0} and "soil_ph" not in prov


def _t_v41_rotation_uses_real_altitude_slope_and_drainage():
    nb, idx = load_notebook(), _mini_index()
    t = territorial_inputs(idx, idx["_pos"]["1"])
    profile = rotation_profile_from_inputs(t["inputs"], t, [["maiz"]])
    assert profile["altitude_masl"] == Range(1000, 2000) and profile["slope_pct"] == Range(25, 50) and profile["waterlogging_prone"] is False
    assert validate_rotation_profile(profile) == [] and validate_rotation_profile({**profile, "altitude_masl": Range(-5, 9000)})
    out = recommend_rotation(profile, nb["rotation_rules"])
    c = {x["crop_key"]: x for x in out["candidates"]}
    assert "ROT_117" in _rids(c["calabaza"], "in_favor")                 # pendiente > 0 con todo el intervalo
    miss = {m["variable"]: m for m in out["missing_inputs"]}
    assert "ROT_011" in miss["altitude_masl"]["affects_rules"]            # ¿caupí > 1500 msnm? la franja 1000–2000 no lo decide
    high = recommend_rotation({**profile, "altitude_masl": Range(2000, 3000)}, nb["rotation_rules"])
    assert "ROT_011" in _rids({x["crop_key"]: x for x in high["candidates"]}["caupi"], "against")
    assert out["profile"]["thermal_floor"] == "templado"
    k = relevant_knowledge(nb, "caupi", "no_especificada", Range(2000, 3000), set(), limit=60)
    assert 62 not in {e["doc_order"] for e in k}                           # afirmación 62: solo 0–1,500 msnm


def _t_v41_area_view_counts_cells():
    nb, idx = load_notebook(), _mini_index()
    area = evaluate_area(nb, idx, 6.6, -75.9, 5.0, "maiz", "vegetativo")
    assert area["cells_total"] == 3 and area["cells_agricultural"] == 1
    rules = {r["rule_id"]: r for r in area["rules"]}
    assert rules["SOIL_001"]["cells"] == 1 and rules["SOIL_001"]["share_of_agricultural"] == 1.0
    assert any(u["rule_id"] == "SOIL_005" for u in area["undecided_only"])
    assert evaluate_area(nb, idx, 0.0, 0.0, 1.0)["cells_total"] == 0


def _t_v41_real_bundle_when_present():
    idx = _real_index()
    if idx is None:
        return                                                             # sin bundle junto al motor no hay nada que comprobar
    nb = load_notebook()
    assert idx["n_cells"] > 1000 and idx["sources"]["soil"]["source"] == "IGAC" and 0.5 < idx["cell_km2"] < 2.0
    counts = {"agricultural": 0, "soil_ph": 0, "rain_month": 0}
    for pos in range(0, idx["n_cells"], 97):
        t = territorial_inputs(idx, pos)
        counts["agricultural"] += t["agricultural"]
        for var in ("soil_ph", "rain_month"):
            counts[var] += var in t["inputs"]
        assert not ({"temperature", "relative_humidity", "soil_moisture", "symptoms"} & set(t["inputs"]))
        assert all(v is not None for v in t["inputs"].values()) and set(t["inputs"]) == set(t["provenance"]) == set(t["var_quality"])
    assert counts["agricultural"] > 0 and counts["soil_ph"] > 0 and counts["rain_month"] > 0
    st = idx["stations"][0]
    p = evaluate_point(nb, idx, st["lat"], st["lon"], "frijol", "floracion", history=[["maiz"]])
    json.dumps(p, ensure_ascii=False)
    assert p["territory"]["cell"]["distance_km"] < 2.0 and p["rotation"]["candidates"]
    assert all(f["certainty"]["level"] in ("baja", "media") for f in p["inference"]["findings"])


def _t_v41_interface_has_no_synthetic_data():
    import inspect
    src = inspect.getsource(run_app)
    assert "generate_series" not in src and "SCENARIOS" not in src and "st.slider(" not in src.replace('st.slider("Radio', "")
    assert "territorial_inputs" in src and "merge_inputs" in src


def selftest() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("_t_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK    {name[3:]}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FALLA {name[3:]}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed} de {len(tests)} autopruebas aprobadas")
    return failed


# =====================================================================
# 14. INTERFAZ (Streamlit)
# =====================================================================
SYMPTOM_OPTIONS = {
    "Clorosis uniforme en hojas viejas": "clorosis_hojas_viejas",
    "Necrosis / quemazón en bordes de hojas viejas": "necrosis_bordes_hojas_viejas",
    "Clorosis intervenal en hojas viejas": "clorosis_intervenal_hojas_viejas",
    "Coloración violácea en hojas": "coloracion_violacea",
    "Necrosis en puntos de crecimiento o frutos jóvenes": "necrosis_puntos_crecimiento_frutos_jovenes",
    "Clorosis generalizada en hojas jóvenes": "clorosis_generalizada_hojas_jovenes",
    "Bandas cloróticas y entrenudos cortos (maíz)": "bandas_cloroticas_entrenudos_cortos",
    "Amarillamiento y colapso de hojas centrales jóvenes (plátano)": "amarillamiento_colapso_hojas_centrales",
}
SEVERITY_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡", "unknown": "⚪"}
CERTAINTY_ICON = {"baja": "🔻", "media": "◼️", "alta": "🔺"}
BASIS_LABELS = {
    "claim": "del documento fuente", "claim_partial": "parcialmente del documento fuente",
    "engine_heuristic": "heurística del motor", "none": "sin umbrales numéricos",
    "engine_heuristic_no_universal": "heurística de cribado, no universal ni calibrada localmente",
    "derived": "derivados de las reglas componentes",
}
SKIP_REASONS = {
    "disabled": "desactivada o rechazada",
    "not_applicable_to_context": "no aplica al cultivo/etapa",
    "missing_input": "el dato no está en el bundle ni se aportó desde el lote",
    "needs_series": "requiere una serie diaria real (NASA POWER o CSV)",
    "insufficient_data": "datos insuficientes en la serie",
    "ambiguous_range": "no se puede decidir: el intervalo del dato cruza el umbral de la regla",
    "invalid_rule": "regla inválida (ver advertencias)",
}
ROT_STATUS_ICON = {"favorecido": "🟢", "aceptable": "⚪", "con_reservas": "🟠", "desaconsejado": "🔴", "sin_evaluar": "⚫"}
ROT_STATUS_LABEL = {"favorecido": "Favorecida", "aceptable": "Aceptable", "con_reservas": "Con reservas",
                    "desaconsejado": "Desaconsejada", "sin_evaluar": "Sin evaluar"}
RESIDUE_OPTIONS = {None: "No sé", "incorporated": "Reincorporado al lote", "surface_mulch": "Dejado como cobertura sobre el suelo",
                   "removed": "Retirado del lote", "burned": "Quemado"}
STATUS_LABELS = {"sin_validar": "sin validar", "validada": "validada por un técnico", "ajustar": "por ajustar",
                 "rechazada": "rechazada", **DOCUMENTARY_STATUS}
NITROGEN_OPTIONS = {None: "No sé", "none_or_low": "Ninguna o baja", "high": "Alta"}
WATER_OPTIONS = {None: "No sé", True: "Sí", False: "No"}
FEATURE_ORDER = ["temperature", "relative_humidity", "rain_7d", "soil_moisture", "sat_days_consecutive",
                 "dry_days_consecutive", "tmin_mean_7d", "hot_days_7d", "wet_dry_alternations_14d",
                 "rain_last14", "rain_prev14", "gdd_total"]
FEATURE_LABELS = {
    "temperature": "Temperatura (media de los últimos 3 días, °C)", "relative_humidity": "Humedad relativa (media de 3 días, %)",
    "rain_7d": "Lluvia de los últimos 7 días (mm)", "soil_moisture": "Humedad del suelo (último dato, %)",
    **VARIABLE_LABELS, "gdd_total": "Grados-día acumulados en la serie (informativo)",
}


def run_app():
    import streamlit as st

    def show_table(rows):
        try:
            st.dataframe(rows, width="stretch", hide_index=True)
        except TypeError:
            st.dataframe(rows, use_container_width=True, hide_index=True)

    def chart(kind, data):
        """Un gráfico con datos degenerados (p. ej. una columna sin ningún valor) no debe tumbar la aplicación."""
        try:
            (st.line_chart if kind == "line" else st.bar_chart)(data)
        except Exception:  # noqa: BLE001
            st.caption("No se pudo dibujar este gráfico: datos insuficientes.")

    st.set_page_config(page_title="Space Wanderers | Motor agronómico 4.1", page_icon="🌱", layout="wide")

    try:
        nb = load_notebook()
    except (OSError, json.JSONDecodeError) as exc:
        st.error(f"No se pudo leer el cuaderno de conocimiento ({NOTEBOOK_PATH.name}): {exc}")
        st.stop()
    audit = audit_notebook(nb)
    errors = audit["errors"]

    # -----------------------------------------------------------------
    # Encabezado
    # -----------------------------------------------------------------
    st.title("🌱 Space Wanderers — Motor agronómico")
    st.caption(
        f"Versión {VERSION} | Cuaderno v{nb['meta']['version']}: {len(nb['alert_rules'])} reglas de alerta, "
        f"{len(nb['rotation_rules'])} de rotación, {len(nb['interactions'])} interacciones, "
        f"{len(nb['practices'])} prácticas | Motor determinista | Salida estructurada para agente IA"
    )
    st.warning(
        "Prototipo experimental: genera señales preliminares, no diagnósticos confirmados. "
        "Los umbrales deben validarse por cultivo, variedad, suelo y región. Ninguna regla ha sido validada por un técnico."
    )
    with st.expander("¿Cómo leer los resultados?"):
        st.markdown(
            "- **Las reglas** son como un cuaderno de «si pasa esto, avisa de aquello». El motor solo compara; todo lo agronómico está en el cuaderno.\n"
            "- **🔴 🟠 🟡** es la gravedad del hallazgo. **⚡** es una *síntesis*: varias señales que juntas dicen más que por separado.\n"
            "- **Certeza** (🔻 baja, ◼️ media, 🔺 alta) dice cuánto confiar. Depende de la regla, de si sus umbrales vienen del documento, "
            "de la calidad de los datos y de si un técnico la validó. **Sin validación técnica la certeza nunca pasa de «media».**\n"
            "- Una regla **superada** quedó integrada en otra más específica; **sube o baja la confianza** cuando otra señal la refuerza o la contradice.\n"
            "- **Los datos son reales**: salen del bundle territorial (suelos IGAC, lluvia GPM / NASA POWER / IDEAM, NDVI Sentinel-2), "
            "de una serie diaria que cargues o de lo que midas en el lote. Nada se simula ni se rellena por defecto.\n"
            "- **Un intervalo** («pH 4.5 a 5.5») es lo que el dato permite afirmar. La regla se activa solo si se cumple con todo el intervalo; "
            "si el umbral cae dentro, el motor dice «no se puede decidir» en vez de adivinar.\n"
            "- **Reglas no evaluadas**: el bundle no trae temperatura, humedad relativa, humedad del suelo ni síntomas. "
            "Esas reglas se listan como pendientes hasta que aportes el dato.\n"
            "- Todo es **orientación de Nivel 1**: no calcula dosis y no reemplaza al técnico."
        )
    if errors:
        with st.expander(f"⚠️ El cuaderno tiene {len(errors)} problema(s)", expanded=True):
            for err in errors:
                st.write(f"- {err}")
    if audit["warnings"]:
        with st.expander(f"🧾 Auditoría del cuaderno: {len(audit['warnings'])} advertencia(s) de trazabilidad (no impiden evaluar)"):
            st.caption("Referencias cruzadas desactualizadas, fuentes citadas sin ficha o evidencia repetida. "
                       "El motor funciona igual; conviene corregirlas en el cuaderno.")
            for warn in audit["warnings"]:
                st.write(f"- {warn}")

    # -----------------------------------------------------------------
    # Barra lateral
    # -----------------------------------------------------------------
    validation_report = None
    with st.sidebar:
        st.header("Contexto del cultivo")
        crop = st.selectbox("Cultivo o sistema", list(CROPS), format_func=CROPS.get)
        stage = st.selectbox("Etapa fenológica", list(STAGES), format_func=STAGES.get)
        st.caption(
            "Cultivo y etapa filtran las reglas que declaran `applies_to` (p. ej. maíz en floración, fríjol, plátano) "
            "y deciden qué prácticas y qué conocimiento se muestran. Con «Otro / no especificado» solo se evalúan las reglas generales."
        )
        st.divider()
        st.header("Revisión técnica")
        upload = st.file_uploader("Cargar validaciones de un técnico (JSON)", type=["json"],
                                  help="Descarga la plantilla en la pestaña «Revisión técnica», que el técnico llena y tú vuelves a cargar aquí.")
        if upload is not None:
            try:
                nb, validation_report = apply_validations(nb, json.load(upload))
            except (ValueError, TypeError, AttributeError) as exc:
                st.error(f"No se pudo leer el archivo de validaciones: {exc}")
        st.divider()
        st.header("Control de reglas")
        rule_titles = {r["id"]: r["title"] for sec in ("alert_rules", "rotation_rules") for r in nb[sec]}
        disabled_ids = set(
            st.multiselect(
                "Desactivar reglas (solo esta sesión)", options=list(rule_titles),
                format_func=lambda rid: f"{rid} · {rule_titles[rid]}",
                help="Útil para ver qué aporta cada regla. Para desactivarla de forma permanente usa \"enabled\": false en el cuaderno, "
                     "o márcala como «rechazada» en la revisión técnica.",
            )
        )

    # -----------------------------------------------------------------
    # 1. El lote en el territorio (datos reales del bundle)
    # -----------------------------------------------------------------
    @st.cache_resource(show_spinner="Preparando el índice territorial (solo tarda la primera vez)…")
    def territorial_index():
        return load_territorial_index()

    index, territorial = None, None
    try:
        index = territorial_index()
        # Streamlit vuelve a ejecutar este archivo en cada interacción y con ello redefine las clases Range / OneOf.
        # El índice vive en caché entre ejecuciones, así que lo ya interpretado se descarta para no mezclar clases viejas.
        index["_parsed"] = {}
    except (FileNotFoundError, MemoryError, ValueError, OSError) as exc:
        st.error(f"No se pudieron cargar los datos del territorio: {exc}")

    st.subheader("1. El lote en el territorio")
    if index is not None:
        cells, sources = index["cells"], index["sources"]
        layers = [f'{(sources.get("soil") or {}).get("source", "suelos")} (suelos)'] + [f"{name} (lluvia)" for name in sources.get("rain", {})]
        if sources.get("ndvi"):
            layers.append(f'{sources["ndvi"]["source"]} (NDVI)')
        st.caption(f'Datos reales procesados: {index["n_cells"]:,} celdas de ≈ {index["cell_km2"]} km² · capas: ' + " · ".join(layers)
                   + f' · bundle generado el {str(index["bundle"].get("generated_at_utc"))[:10]}.')
        stations = index.get("stations", [])
        how = st.radio("Ubicar el lote por", ["Coordenadas", "Punto de referencia del conjunto de datos", "ID de celda"], horizontal=True)
        lat = lon = None
        if how == "Coordenadas":
            start = (stations[0]["lat"], stations[0]["lon"]) if stations else (cells["lat"][len(cells["lat"]) // 2], cells["lon"][len(cells["lon"]) // 2])
            a, b = st.columns(2)
            lat = a.number_input("Latitud (grados decimales)", -90.0, 90.0, float(start[0]), 0.001, format="%.5f")
            lon = b.number_input("Longitud (grados decimales)", -180.0, 180.0, float(start[1]), 0.001, format="%.5f")
            st.caption("El valor inicial es un punto de referencia del propio conjunto de datos, no la ubicación de ningún lote.")
        elif how.startswith("Punto"):
            if stations:
                pick = st.selectbox("Estación IDEAM incluida en el bundle", range(len(stations)),
                                    format_func=lambda i: f'{stations[i]["name"]} ({stations[i]["lat"]:.4f}, {stations[i]["lon"]:.4f})')
                lat, lon = stations[pick]["lat"], stations[pick]["lon"]
            else:
                st.info("El bundle no trae puntos de referencia.")
        else:
            gid = st.text_input("ID de la celda de la grilla maestra", cells["id"][0]).strip()
            if gid in index["_pos"]:
                lat, lon = cells["lat"][index["_pos"][gid]], cells["lon"][index["_pos"][gid]]
            else:
                st.error("Esa celda no existe en la grilla.")
        if lat is not None:
            pos, distance_km = find_cell(index, lat, lon)
            territorial = territorial_inputs(index, pos)
            territorial["cell"]["requested"] = {"latitude": lat, "longitude": lon}
            territorial["cell"]["distance_km"] = round(distance_km, 3)
            if distance_km > 2.0:
                territorial["notes"].insert(0, f"El punto está a {distance_km:.1f} km de la celda más cercana: queda FUERA de la grilla del bundle.")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Celda", territorial["cell"]["grid_id"])
            m2.metric("Distancia al centro", f"{distance_km:.2f} km")
            m3.metric("Unidad de suelos", territorial["context"]["soil_unit_phase"] or "sin dato")
            m4.metric("Piso térmico", ", ".join(territorial["context"]["thermal_floors"]) or "sin dato")
            for note in territorial["notes"]:
                st.warning(note)
            st.markdown("**Datos reales de la celda que entran al motor**")
            show_table([{"Variable": var_label(v), "Valor": show_value(val),
                         "Fuente": territorial["provenance"][v]["source"],
                         "Cómo se obtuvo": territorial["provenance"][v]["method"],
                         "Periodo": territorial["provenance"][v]["period"] or "—",
                         "Calidad": CERTAINTY_LABEL[territorial["var_quality"][v]]}
                        for v, val in territorial["inputs"].items()])
            st.caption("Un valor «a» (p. ej. «4.5 a 5.5») es un intervalo: es lo que el dato real permite afirmar. "
                       "Una regla solo se activa si se cumple con todo el intervalo. "
                       "El bundle NO trae: " + ", ".join(var_label(v) for v in territorial["unavailable"]) + ".")
            ctx = territorial["context"]
            with st.expander("Ficha de la unidad de suelos y del paisaje (IGAC)"):
                show_table([{"Campo": k, "Valor": v} for k, v in (
                    ("Descripción", ctx["soil_description"]), ("Taxonomía", ctx["soil_taxonomy"]), ("Paisaje", ctx["landscape"]),
                    ("Relieve", ctx["relief"]), ("Material parental", ctx["parent_material"]), ("Clima", ctx["climate_class"]),
                    ("Profundidad", ctx["depth"]), ("Drenaje", ctx["drainage"]), ("Fertilidad", ctx["fertility"]),
                    ("Saturación de aluminio", ctx["aluminum_saturation"]), ("Erosión (fase)", ctx["erosion_degree"]),
                    ("Otras limitantes (fase)", ", ".join(ctx["phase_modifiers"]) or None)) if v])
                st.caption("Estudio general de suelos a escala 1:100.000: describe la unidad cartográfica, no el lote. "
                           "Un análisis de suelo del lote siempre manda (ver el paso 2).")

    # -----------------------------------------------------------------
    # 2. Lo que se mida u observe en el lote (opcional; también son datos reales)
    # -----------------------------------------------------------------
    st.subheader("2. Datos del propio lote (opcionales)")
    st.caption("Nada aquí tiene valor por defecto: lo que no se llene queda «sin dato». Lo medido en el lote manda sobre el bundle.")
    field: dict = {}
    real_series, real_info = None, None
    f1, f2 = st.columns(2)
    with f1:
        with st.expander("🧪 Análisis de suelo del lote"):
            field["soil_ph"] = st.number_input("pH del análisis", 3.0, 9.5, None, 0.1, placeholder="sin dato")
            field["organic_matter"] = st.number_input("Materia orgánica (%)", 0.0, 30.0, None, 0.1, placeholder="sin dato")
            field["soil_texture"] = st.selectbox("Textura determinada en el lote", [None, "Arenosa", "Franca", "Arcillosa"],
                                                 format_func=lambda v: v or "sin dato")
        with st.expander("📏 Mediciones del terreno y del momento"):
            field["altitude_masl"] = st.number_input("Altitud del lote (msnm)", 0.0, 5000.0, None, 10.0, placeholder="sin dato")
            field["slope_pct"] = st.number_input("Pendiente medida (%)", 0.0, 200.0, None, 1.0, placeholder="sin dato")
            field["soil_moisture"] = st.number_input("Humedad del suelo medida (% de saturación)", 0.0, 100.0, None, 1.0, placeholder="sin dato")
            field["temperature"] = st.number_input("Temperatura media reciente (°C)", -5.0, 50.0, None, 0.5, placeholder="sin dato")
            field["relative_humidity"] = st.number_input("Humedad relativa reciente (%)", 0.0, 100.0, None, 1.0, placeholder="sin dato")
            field["rain_7d"] = st.number_input("Lluvia medida en los últimos 7 días (mm)", 0.0, 1000.0, None, 1.0, placeholder="sin dato")
    with f2:
        with st.expander("👀 Observación del cultivo"):
            if st.checkbox("Revisé el cultivo en campo"):
                field["symptoms"] = [SYMPTOM_OPTIONS[s] for s in st.multiselect(
                    "Síntomas observados", options=list(SYMPTOM_OPTIONS),
                    help="Selecciona solo síntomas observados directamente. No selecciones síntomas supuestos.")]
            st.caption("Sin marcar la casilla, las reglas de síntomas quedan sin evaluar. Marcada y sin síntomas significa «revisé y no vi ninguno».")
        with st.expander("📈 Serie diaria real (NASA POWER en JSON, o CSV)"):
            st.caption("Aporta lo que el bundle mensual no tiene: temperatura, humedad relativa, humedad del suelo y lluvia día a día "
                       "(T2M_MAX, T2M_MIN, RH2M, PRECTOTCORR, GWETROOT; o un CSV con tmax, tmin, rh, rain, soil_moisture y fecha). "
                       "El motor no descarga nada: lee el archivo que le des. Conviene cargar al menos 28 días.")
            data_file = st.file_uploader("Archivo de la serie diaria", type=["json", "csv"], key="real_series_file")
            if data_file is not None:
                try:
                    text = data_file.getvalue().decode("utf-8-sig")
                    if data_file.name.lower().endswith(".json"):
                        real_series, real_info = series_from_nasa_power(json.loads(text))
                    else:
                        real_series, real_info = series_from_csv(text)
                    st.success(f'{real_info["source"]}: {real_info["n_days"]} días'
                               + (f' ({real_info["first_date"]} a {real_info["last_date"]})' if real_info.get("first_date") else ""))
                    if real_info.get("variables_absent"):
                        st.warning("El archivo no trae: " + ", ".join(real_info["variables_absent"])
                                   + ". Las reglas que dependan de esos datos quedarán sin evaluar.")
                except (ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError) as exc:
                    st.error(f"No se pudo leer la serie: {exc}")

    # -----------------------------------------------------------------
    # Capas de datos reales → entradas del motor
    # -----------------------------------------------------------------
    quality, corrections, features_why, features = None, [], {}, {}
    coverage = None
    series_mode = bool(real_series)
    if series_mode:
        clean, quality = clean_series(real_series)
        features, features_why = compute_features(clean, crop, nb)
        coverage = quality["overall_coverage_last14"]
        st.markdown("**Serie diaria cargada**")
        chart("line", {"Tmáx (°C)": [d["tmax"] for d in clean], "Tmín (°C)": [d["tmin"] for d in clean]})
        g1, g2 = st.columns(2)
        with g1:
            chart("bar", {"Lluvia (mm)": [d["rain"] for d in clean]})
        with g2:
            chart("line", {"Humedad relativa (%)": [d["rh"] for d in clean],
                           "Humedad del suelo (%)": [d["soil_moisture"] for d in clean]})
        for flag in quality["flags"]:
            st.warning(flag)
    inputs, provenance, var_quality = merge_inputs(territorial, features if series_mode else None, field, real_info, coverage)
    if not inputs:
        st.info("Todavía no hay ningún dato real: ubica el lote en el territorio o aporta datos del lote.")

    # -----------------------------------------------------------------
    # Inferencia
    # -----------------------------------------------------------------
    result = analyze(nb, inputs, crop, stage, disabled_ids, coverage, var_quality=var_quality, provenance=provenance)
    altitude_masl, slope_pct = inputs.get("altitude_masl"), inputs.get("slope_pct")
    findings, skipped, overview = result["findings"], result["skipped"], result["overview"]
    practices, knowledge = result["practices"], result["knowledge"]
    visible = [f for f in findings if not f["superseded_by"]]
    hidden = [f for f in findings if f["superseded_by"]]

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Resultado del motor")
        if not visible:
            st.info("Ninguna regla se activó con los valores actuales. Esto no significa que el cultivo esté libre de problemas.")
        else:
            st.metric("Hallazgos generados", len(visible))
            for item in visible:
                icon = "⚡" if item["kind"] == "synthesis" else SEVERITY_ICON.get(item["severity"], "⚪")
                with st.expander(f'{icon} {item["title"]} · {item["severity"].upper()}', expanded=True):
                    st.write(item["observation"])
                    st.markdown("**Acción preliminar**")
                    st.write(item["recommendation"])
                    cert = item["certainty"]
                    limit = f' (limitada por: {", ".join(cert["limiting_factors"])})' if cert["limiting_factors"] else ""
                    caption = (
                        f'Regla: {item["rule_id"]} | Confianza: {item["confidence"]} | '
                        f'Certeza: {CERTAINTY_ICON[cert["level"]]} {cert["level"]}{limit} | '
                        f'Evidencia: {item["evidence_status"]} | '
                        f'Umbrales: {BASIS_LABELS.get(item.get("threshold_basis"), "n/d")}'
                    )
                    if item.get("source_claim_ids"):
                        caption += f' | Afirmaciones: {", ".join(item["source_claim_ids"])}'
                    st.caption(caption)
                    if item["components"]:
                        st.caption("Integra las reglas: " + ", ".join(item["components"]))
                    if item["integrated_in"]:
                        st.caption("Integrada en la síntesis: " + ", ".join(item["integrated_in"]))
                    for note in item["interaction_notes"]:
                        st.info(f'{note["effect"].capitalize()} ({note["interaction_id"]}): {note["note"]}')
                    if item["why"]:
                        st.markdown("**¿Por qué se activó?** (Vista del Porqué)")
                        for w in item["why"]:
                            origin = (f'{w["data_source"]} — {w["method"]}' + (f' ({w["period"]})' if w["period"] else "")
                                      + f' · calidad {w["quality_level"]}') if w["data_source"] else f'fuente prevista: {w["planned_source"]}'
                            st.write(f'- {w["label"]}: **{w["observed_text"]}** ({w["operator"]} {show_value(w["threshold"])}) · {origin}')
                    if item["refines"]:
                        st.caption("Precisa a la señal general: " + ", ".join(item["refines"]))
                    if item["refined_by"]:
                        st.caption("Hay una señal más específica para este cultivo o etapa: " + ", ".join(item["refined_by"]))
                    if item["external_sources"]:
                        st.caption("Fuentes externas revisadas: " + " · ".join(
                            f'[{s["id"]}]({s["url"]}) {s["publisher"]}' for s in item["external_sources"]))
                    if item["external_sources_unresolved"]:
                        st.caption("Fuentes citadas sin ficha en el cuaderno: " + ", ".join(item["external_sources_unresolved"]))
                    st.markdown("**Limitaciones**")
                    for caution in item["cautions"]:
                        st.write(f"- {caution}")
            if hidden:
                with st.expander(f"Reglas integradas o superadas por una señal más específica ({len(hidden)})"):
                    for item in hidden:
                        st.write(f'- **{item["rule_id"]}** · {item["title"]} — superada por **{item["superseded_by"]}**')

    with right:
        st.subheader("Estado resumido")
        if overview["by_module"]:
            st.markdown("**Semáforo por módulo**")
            for module, info in overview["by_module"].items():
                st.write(f'{SEVERITY_ICON[info["severity"]]} **{module}** — {info["findings"]} hallazgo(s)')
        st.write({
            "cultivo": CROPS[crop], "etapa": STAGES[stage],
            "capas_de_datos": [name for name, on in (("bundle territorial", territorial is not None), ("serie diaria cargada", series_mode),
                                                     ("datos del lote", any(v is not None for v in field.values()))) if on],
            "celda": territorial["cell"]["grid_id"] if territorial else None,
            "altitud_msnm": show_value(altitude_masl) if altitude_masl is not None else "sin dato",
            "piso_termico": thermal_floor(altitude_masl),
            "pendiente_%": show_value(slope_pct) if slope_pct is not None else "sin dato",
            "reglas_de_alerta": len(nb["alert_rules"]),
            "reglas_evaluadas": len(nb["alert_rules"]) - len(skipped),
            "reglas_activadas": len([f for f in findings if f["kind"] == "rule"]),
            "sintesis_generadas": len([f for f in findings if f["kind"] == "synthesis"]),
            "hallazgos_visibles": len(visible),
            "modulos_activos": sorted({f["module"] for f in visible}),
            "practicas_sugeridas": len(practices),
        })
        if skipped:
            with st.expander(f"Reglas no evaluadas ({len(skipped)})"):
                for s in skipped:
                    extra = ""
                    if s.get("missing"):
                        extra = " — " + ", ".join(var_label(v) + (f" ({show_value(inputs[v])})" if is_uncertain(inputs.get(v)) else "")
                                                  for v in s["missing"])
                    st.write(f'- **{s["rule_id"]}**: {SKIP_REASONS.get(s["reason"], s["reason"])}{extra}')
        st.caption("El motor no genera dosis ni ejecuta acciones de manejo.")

    # -----------------------------------------------------------------
    # Módulos del cuaderno (en pestañas para no recargar la página)
    # -----------------------------------------------------------------
    st.divider()
    tabs = st.tabs(["🌿 Prácticas sugeridas", "📚 Conocimiento relevante", "🔄 Rotación", "🛰️ Datos y procedencia",
                    "🗂️ Cobertura del cuaderno", "🧪 Revisión técnica", "🤖 Salida para el agente", "🗺️ Vista territorial"])

    # ---- prácticas ----
    with tabs[0]:
        st.caption("Prácticas de Nivel 1 tomadas del cuaderno: orientan el manejo, no calculan cantidades.")
        if not practices:
            st.info("Ninguna práctica del cuaderno corresponde a este contexto.")
        for p in practices:
            with st.expander(f'🌿 {p["title"]}'):
                st.write(p["text"])
                reasons = []
                for w in p["why"]:
                    if w["type"] == "finding":
                        reasons.append("se activó " + ", ".join(w["ids"]))
                    elif w["type"] == "context_condition":
                        reasons.append("condición del lote")
                    else:
                        reasons.append("contexto del cultivo y la etapa")
                st.caption("Se muestra porque: " + "; ".join(reasons) + " | Afirmaciones: " + ", ".join(p["source_claim_ids"]))
                for c in p["cautions"]:
                    st.caption(f"⚠️ {c}")
                if p["evidence"]:
                    ev = p["evidence"]
                    st.caption(f'Evidencia: {str(ev["status"]).replace("_", " ")} — {ev["scope_note"]}')
                    for src in ev["sources"]:
                        st.caption(f'📖 [{src["id"]}]({src["url"]}) {src["citation"]}')

    # ---- conocimiento ----
    with tabs[1]:
        st.caption("Afirmaciones del cuaderno que importan para este cultivo, etapa y altitud, aunque ninguna regla se haya activado.")
        for k in knowledge:
            with st.expander(f'Afirmación {k["doc_order"]} · {k["claim"][:100]}…'):
                st.write(k["claim"])
                st.markdown("**Por qué ocurre**")
                st.write(k["explanation"])
                st.markdown("**Condiciones o limitaciones**")
                st.write(k["conditions"])
                st.caption("Se muestra porque: " + "; ".join(k["why"]))
                st.caption(f'Fuente (no verificada): {k["source"]}')

    # ---- rotación ----
    rotation = None
    with tabs[2]:
        st.caption("Qué sembrar a continuación según el historial del lote. Nivel 1: orienta secuencias, no calcula dosis. "
                   "Usa la altitud del lote definida arriba.")
        crop_keys = list(ROT_CROPS) + list(HISTORY_EXTRA)
        label = lambda k: ROT_CROPS[k][0] if k in ROT_CROPS else HISTORY_EXTRA.get(k, k)
        r1, r2 = st.columns(2)
        with r1:
            last_cycle = st.multiselect("Cultivo(s) del último ciclo", crop_keys, format_func=label,
                                        help="Si fue una asociación, selecciona todos sus cultivos (p. ej. maíz + fríjol + calabaza).")
            previous_cycle = st.multiselect("Penúltimo ciclo (opcional)", crop_keys, format_func=label)
            third_cycle = st.multiselect("Antepenúltimo ciclo (opcional)", crop_keys, format_func=label)
            st.caption("El documento fuente solo respalda reglas sobre el último ciclo; los anteriores se registran pero aún no cambian el resultado.")
        with r2:
            residue = st.selectbox("Rastrojo del último ciclo", list(RESIDUE_OPTIONS), format_func=RESIDUE_OPTIONS.get)
            nitrogen = st.selectbox("Fertilización nitrogenada reciente", list(NITROGEN_OPTIONS), format_func=NITROGEN_OPTIONS.get)
            drain = territorial["context"].get("waterlogging_prone") if territorial else None
            waterlogging = st.selectbox("¿El lote es propenso a encharcamiento?", list(WATER_OPTIONS), format_func=WATER_OPTIONS.get,
                                        index=list(WATER_OPTIONS).index(drain),
                                        help="El valor inicial sale del drenaje que el IGAC describe para la unidad de suelos; cámbialo si conoces el lote.")
            if territorial and territorial["context"].get("drainage"):
                st.caption(f'Drenaje según el IGAC: {territorial["context"]["drainage"]}.')
        cycles = [last_cycle, previous_cycle, third_cycle]
        while cycles and not cycles[-1]:
            cycles.pop()
        profile = {"altitude_masl": altitude_masl, "slope_pct": slope_pct, "history": cycles, "residue_management": residue,
                   "recent_n_fertilization": nitrogen, "waterlogging_prone": waterlogging}
        problems = validate_rotation_profile(profile)
        if problems:
            for p in problems:
                st.error(p)
        else:
            rotation = recommend_rotation(profile, nb["rotation_rules"], disabled_ids)
            if rotation["situation"] == "sin_historial":
                st.info("Indica al menos el cultivo del último ciclo para poder evaluar las opciones.")
            elif rotation["situation"] == "cana_establecida":
                st.caption("La caña ya está en el lote: se evalúan los cultivos que pueden acompañarla o que conviene evitar.")
            for lot in rotation["lot_findings"]:
                (st.error if lot["effect"] == "block" else st.warning)(f'**Sobre el lote — {lot["title"]}.** {lot["message"]}')
                st.caption(f'Regla {lot["rule_id"]} · aplica a todo el lote, no a un cultivo en particular.')
            for cand in rotation["candidates"]:
                with st.expander(f'{ROT_STATUS_ICON[cand["status"]]} {cand["crop"]} · {ROT_STATUS_LABEL[cand["status"]]}',
                                 expanded=cand["status"] in ("favorecido", "desaconsejado")):
                    st.caption(f'Familia: {cand["family"]}')
                    for title, key in (("⛔ Razón de exclusión", "blocking"), ("A favor", "in_favor"),
                                       ("En contra", "against"), ("A tener en cuenta", "notes")):
                        if cand[key]:
                            st.markdown(f"**{title}**")
                            for r in cand[key]:
                                st.write(f'- {r["message"]}')
                                if r.get("inherited_from"):
                                    st.caption(f'↳ Heredada de un componente de la asociación: {r["inherited_from"]}.')
                                st.caption(f'Regla {r["rule_id"]} · respaldo: ' + ", ".join(c.replace("CLAIM_", "afirmación ") for c in r["claim_ids"])
                                           + f' · {STATUS_LABELS.get(r["validation_status"], r["validation_status"])}')
                                for c in r["cautions"]:
                                    st.caption(f"⚠️ {c}")
                    if cand["status"] == "con_reservas" and cand["in_favor"]:
                        st.caption("Hay razones a favor y en contra: la decisión requiere criterio técnico.")
                    if cand["general_guidance"]:
                        st.markdown(f'**Orientaciones generales para este cultivo ({len(cand["general_guidance"])})** — no cambian su categoría')
                        for r in cand["general_guidance"]:
                            st.caption(f'• {r["title"]} ({r["rule_id"]})')
            if rotation["missing_inputs"]:
                st.markdown("**Datos que afinarían el resultado**")
                for m in rotation["missing_inputs"]:
                    st.write(f'- **{m["label"]}** (afecta a: {", ".join(m["affects_crops"])})')
            st.markdown("**Antes de actuar**")
            for item in rotation["verify_before_acting"]:
                st.write(f"- {item}")
            for c in rotation["global_cautions"]:
                st.caption(f"⚠️ {c}")

    # ---- tiempo y datos ----
    with tabs[3]:
        st.markdown("**De dónde sale cada dato que usó el motor**")
        show_table([{"Variable": var_label(v), "Valor": show_value(inputs[v]), "Fuente": p["source"], "Cómo se obtuvo": p["method"],
                     "Periodo": p["period"] or "—", "Calidad": CERTAINTY_LABEL[p["quality_level"]]}
                    for v, p in provenance.items() if inputs.get(v) is not None])
        st.caption("Calidad «alta» = dato directo válido; «media» = derivado de una clase cartográfica (intervalo); "
                   "«baja» = estimado al cambiar de resolución temporal (lluvia mensual → semanal). La certeza de cada hallazgo "
                   "nunca supera la del dato más débil que lo activó.")
        if not series_mode:
            st.info("No hay una serie diaria cargada. El bundle territorial es mensual, así que las reglas de persistencia, alternancia "
                    "y acumulación quedan sin evaluar. Carga el JSON diario de NASA POWER o un CSV en el paso 2 para activarlas.")
            st.markdown("**Reglas que solo se evalúan con una serie diaria**")
            show_table([{"Regla": r["id"], "Qué detecta": r["title"],
                         "Necesita": ", ".join(VARIABLE_LABELS.get(v, v) for v in sorted(condition_vars(r["when"]) & TEMPORAL_FEATURES))}
                        for r in nb["alert_rules"] if condition_vars(r["when"]) & TEMPORAL_FEATURES])
            missing_vars: dict[str, int] = {}
            for s in skipped:
                if s["reason"] in ("missing_input", "ambiguous_range"):
                    for v in s.get("missing", []):
                        missing_vars[v] = missing_vars.get(v, 0) + 1
            if missing_vars:
                st.markdown("**Qué dato desbloquearía más reglas en este lote**")
                show_table([{"Dato": var_label(v), "Reglas en espera": n,
                             "Situación": "intervalo demasiado amplio" if is_uncertain(inputs.get(v)) else "sin dato"}
                            for v, n in sorted(missing_vars.items(), key=lambda kv: -kv[1])])
        else:
            st.markdown("**Variables derivadas de la serie**")
            show_table([{"Variable": FEATURE_LABELS.get(k, k),
                         "Valor": ("sin dato" if features.get(k) is None else features[k]),
                         "Motivo": features_why.get(k, "")} for k in FEATURE_ORDER if k in features])
            st.markdown("**Calidad de los datos**")
            show_table([{"Variable": v, "Cobertura total": f'{quality["coverage"][v]:.0%}',
                         "Cobertura últimos 14 días": f'{quality["coverage_last14"][v]:.0%}'} for v in SERIES_VARS])
            if quality["removed_out_of_range"]:
                st.markdown("**Valores imposibles descartados**")
                show_table(quality["removed_out_of_range"])
            if quality["possible_stuck_sensors"]:
                st.markdown("**Posibles sensores con valor repetido (revisar)**")
                show_table(quality["possible_stuck_sensors"])
            st.caption("El motor no inventa datos: lo que se descarta o falta queda como hueco, y las variables que no alcanzan la cobertura mínima "
                       f"({MIN_COVERAGE:.0%} de la ventana) no se calculan. Eso se refleja en la certeza de cada hallazgo.")

    # ---- cobertura ----
    with tabs[4]:
        cov = coverage_report(nb)
        used = cov["counts"]["en_uso"]
        st.metric("Afirmaciones con uso directo en el cuaderno", f'{used} de {cov["total"]}')
        labels = {"en_uso": "En uso (reglas, prácticas, interacciones o parámetros)",
                  "conocimiento_contextual": "Conocimiento contextual (se muestra según cultivo, etapa y altitud)",
                  "pendiente_de_umbral": "Evaluable, pero el documento no da un umbral",
                  "bloqueada": "Bloqueada: necesita un dato que el motor aún no recibe",
                  "fuera_del_alcance": "Fuera del alcance del MVP"}
        show_table([{"Categoría": labels[k], "Afirmaciones": v} for k, v in cov["counts"].items()])
        st.markdown("**Dónde se usan**")
        show_table([{"Tipo de elemento": k, "Afirmaciones que respaldan": v} for k, v in cov["used_by_kind"].items()])
        if cov["unlock_map"]:
            st.markdown("**Qué dato nuevo desbloquearía más afirmaciones**")
            show_table([{"Dato necesario": k, "Afirmaciones": ", ".join(map(str, v))} for k, v in cov["unlock_map"].items()])
        st.caption("Las referencias del documento fuente NO han sido verificadas (source_verified = false).")

    # ---- revisión técnica ----
    with tabs[5]:
        vs = validation_summary(nb)
        st.caption("Ninguna regla debe considerarse confiable hasta que un técnico agropecuario la valide. Mientras tanto, la certeza máxima es «media».")
        show_table([{"Estado": k, "Reglas": v} for k, v in vs.items() if k != "total"])
        if validation_report:
            st.success(f'Validaciones aplicadas: {validation_report["applied"]}')
            if validation_report["unknown_ids"]:
                st.warning("IDs desconocidos: " + ", ".join(map(str, validation_report["unknown_ids"])))
            if validation_report["invalid"]:
                st.warning("Estados inválidos: " + ", ".join(f'{x["rule_id"]} ({x["status"]})' for x in validation_report["invalid"]))
        st.download_button("⬇️ Hoja de revisión (CSV para Excel)", data=review_sheet_csv(nb),
                           file_name="hoja_de_revision_tecnica.csv", mime="text/csv")
        st.download_button("⬇️ Plantilla de validaciones (JSON)", data=json.dumps(validation_template(nb), ensure_ascii=False, indent=2),
                           file_name="plantilla_validaciones.json", mime="application/json")
        st.markdown("**Cómo se usa:** el técnico llena `status` (`validada`, `ajustar`, `rechazada`), `by`, `date` y `notes` en la plantilla, "
                    "y tú la cargas en la barra lateral. Una regla `rechazada` deja de evaluarse; una `validada` puede alcanzar certeza «alta».")
        show_table([{"ID": r["id"], "Tipo": "alerta" if sec == "alert_rules" else "rotación", "Regla": r["title"],
                     "Umbrales": BASIS_LABELS.get(r["threshold_basis"], r["threshold_basis"]), "Estado": r["validation"]["status"]}
                    for sec in ("alert_rules", "rotation_rules") for r in nb[sec]])

    # ---- salida para el agente ----
    with tabs[6]:
        payload = build_payload(nb, mode="territorio", inputs=inputs, crop=crop, stage=stage,
                                findings=findings, skipped=skipped, practices=practices, knowledge=knowledge,
                                quality=quality, corrections=corrections, rotation=rotation, territorial=territorial,
                                provenance=provenance,
                                data_source={"source": "datos reales: bundle territorial, serie diaria cargada y datos del lote",
                                             "bundle": index.get("bundle") if index else None,
                                             "layers": index.get("sources") if index else None, "daily_series": real_info,
                                             "field_values": sorted(k for k, v in field.items() if v is not None)})
        json_text = json.dumps(payload, ensure_ascii=False, indent=2)
        st.download_button("⬇️ Descargar salida JSON", data=json_text,
                           file_name="space_wanderers_agronomic_output.json", mime="application/json")
        st.code(json_text, language="json")

    # ---- vista territorial (B2G) ----
    with tabs[7]:
        st.caption("Para alcaldías y gobernación: en cuántas celdas alrededor del punto se activa cada regla con los datos reales del bundle. "
                   "Usa el cultivo y la etapa de la barra lateral; no incluye los datos del lote ni la serie diaria.")
        if territorial is None:
            st.info("Ubica primero el lote en el territorio.")
        else:
            radius = st.slider("Radio alrededor del punto (km)", 1, 15, 3, 1)
            if st.button("Calcular la vista territorial"):
                with st.spinner("Evaluando las celdas del área…"):
                    area = evaluate_area(nb, index, territorial["cell"]["latitude"], territorial["cell"]["longitude"],
                                         float(radius), crop, stage, disabled_ids)
                a1, a2, a3 = st.columns(3)
                a1.metric("Celdas en el área", area["cells_total"])
                a2.metric("Celdas con suelo agrícola", area["cells_agricultural"])
                a3.metric("Hectáreas agrícolas (aprox.)", f'{area["approx_hectares_agricultural"]:,}' if area["approx_hectares_agricultural"] else "—")
                if area["truncated"]:
                    st.warning("El área tiene más celdas de las que se evalúan de una vez: el resultado es parcial. Reduce el radio.")
                if area["rules"]:
                    st.markdown("**Reglas activadas en el área**")
                    show_table([{"Regla": r["rule_id"], "Qué señala": r["title"], "Gravedad": SEVERITY_ICON.get(r["severity"], "⚪"),
                                 "Celdas": r["cells"], "% del área agrícola": f'{r["share_of_agricultural"]:.0%}',
                                 "Hectáreas (aprox.)": r["approx_hectares"], "Celdas sin poder decidir": r["cells_undecided"]}
                                for r in area["rules"]])
                else:
                    st.info("Ninguna regla se activó en el área con los datos del bundle.")
                if area["undecided_only"]:
                    st.markdown("**Reglas que no se pudieron decidir en ninguna celda** (el intervalo del dato cruza su umbral)")
                    show_table([{"Regla": u["rule_id"], "Qué señala": u["title"], "Celdas sin poder decidir": u["cells_undecided"]}
                                for u in area["undecided_only"]])
                st.caption("⚠️ " + area["caution"])
                st.download_button("⬇️ Descargar la vista territorial (JSON)", data=json.dumps(jsonable(area), ensure_ascii=False, indent=2),
                                   file_name="vista_territorial.json", mime="application/json")

    st.caption(
        f"Space Wanderers · {VERSION} · Motor de reglas transparente y ampliable. "
        "No usar como única base para decisiones agronómicas reales."
    )


def _cli_option(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else default


def main():
    if "--selftest" in sys.argv:
        sys.exit(1 if selftest() else 0)
    if "--build-index" in sys.argv:
        index = load_territorial_index(rebuild=True, log=print)
        print(f"{index['n_cells']} celdas · ≈ {index['cell_km2']} km² por celda · fuentes: {json.dumps(index['sources'], ensure_ascii=False)}")
        sys.exit(0)
    if "--punto" in sys.argv:
        i = sys.argv.index("--punto")
        try:
            lat, lon = float(sys.argv[i + 1]), float(sys.argv[i + 2])
        except (IndexError, ValueError):
            sys.exit("Uso: --punto LAT LON [--cultivo maiz] [--etapa vegetativo]")
        crop, stage = _cli_option("--cultivo", "otro"), _cli_option("--etapa", "no_especificada")
        if crop not in CROPS or stage not in STAGES:
            sys.exit(f"Cultivos: {', '.join(CROPS)}\nEtapas: {', '.join(STAGES)}")
        payload = evaluate_point(load_notebook(), load_territorial_index(log=lambda m: print(m, file=sys.stderr)), lat, lon, crop, stage)
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.exit(0)
    run_app()


if __name__ == "__main__":
    main()
