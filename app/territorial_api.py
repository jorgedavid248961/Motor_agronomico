"""Cliente de la API territorial canónica (API_CANONICA): de ahí salen los datos del territorio.

Reemplaza la lectura del JSON local. Pide a la API, variable por variable, solo los campos que
`motor.build_territorial_index` usa, y arma con ellos un bundle con el mismo esquema canónico.
El índice del motor se sigue construyendo con la misma función, así que el resultado es idéntico.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BUNDLE_SCHEMA = "territorial_canonical_bundle"

# Campos de cada registro que lee motor.build_territorial_index. Lo demás no viaja por la red.
_CELL = ("grid_id", "latitude", "longitude", "value", "quality_flag", "source", "product")
FIELDS: dict[str, tuple[str, ...]] = {
    "ndvi": _CELL + ("time_start", "time_end", "statistic", "spatial_coverage", "valid_scene_count"),
    "precipitation_amount": _CELL + ("time_start", "time_end", "statistic", "version", "unit", "geometry_status",
                                     "spatial_support", "station_id", "station_name", "observed_days", "expected_days"),
    "soil": _CELL + ("variable",),
}


class TerritorialAPIError(RuntimeError):
    """La API territorial no respondió, o respondió algo que no es el bundle canónico completo."""


def _open(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": "motor-agronomico"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", "replace")
        raise TerritorialAPIError(f"{url} respondió {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TerritorialAPIError(f"No se pudo conectar con {url}: {exc.reason}") from exc


def _get_json(base: str, path: str, timeout: float) -> dict:
    with _open(base + path, timeout) as resp:
        return json.load(resp)


def _export(base: str, variable: str, fields: tuple[str, ...], timeout: float) -> list[dict]:
    """GET /v1/export/{variable} (NDJSON en streaming) → lista de registros, verificando que llegaron todos."""
    url = f"{base}/v1/export/{urllib.parse.quote(variable)}?" + urllib.parse.urlencode({"fields": ",".join(fields)})
    records: list[dict] = []
    tail = b""
    with _open(url, timeout) as resp:
        expected = resp.headers.get("X-Record-Count")
        while chunk := resp.read(1 << 20):
            lines = (tail + chunk).split(b"\n")
            tail = lines.pop()
            records.extend(json.loads(line) for line in lines if line)
    if tail.strip():
        records.append(json.loads(tail))
    if expected is not None and int(expected) != len(records):
        raise TerritorialAPIError(f"{variable}: se esperaban {expected} registros y llegaron {len(records)}.")
    return records


def fetch_bundle(base_url: str, timeout: float = 120.0) -> dict:
    """Bundle canónico con solo las variables y campos que el motor usa, leído desde la API."""
    base = base_url.rstrip("/")
    summary = _get_json(base, "/v1/summary", timeout)
    if summary.get("schema") != BUNDLE_SCHEMA:
        raise TerritorialAPIError(f"{base} no sirve un bundle «{BUNDLE_SCHEMA}» (schema={summary.get('schema')!r}).")
    available = {item["name"] for item in _get_json(base, "/v1/variables", timeout).get("items", [])}
    return {
        "schema": BUNDLE_SCHEMA,
        "schema_version": summary.get("schema_version"),
        "generated_at_utc": summary.get("generated_at_utc"),
        "manifest": summary.get("manifest") or [],
        # Lo que la API no tenga queda sin dato (el motor no lo inventa).
        "variables": {name: [{"data": _export(base, name, fields, timeout)}]
                      for name, fields in FIELDS.items() if name in available},
    }
