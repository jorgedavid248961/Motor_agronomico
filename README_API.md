# API del motor agronómico 4.1

FastAPI + PostgreSQL. Ejecuta `evaluate_point` del motor con el índice territorial
(`territorial_index_v41.json`) y guarda la entrada y la salida completa en la tabla `evaluaciones`.

## Local

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # y poner DATABASE_URL
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Documentación interactiva: http://127.0.0.1:8000/docs

## Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| GET  | `/health` | estado del motor e índice |
| GET  | `/api/v1/catalogo` | cultivos, etapas, síntomas, variables de campo, opciones de rotación |
| POST | `/api/v1/evaluaciones` | ejecuta el motor, guarda y devuelve `{id, resumen…, entrada, resultado}` |
| GET  | `/api/v1/evaluaciones` | lista resúmenes; filtros: `grid_id, cultivo, etapa, riesgo, referencia_cliente, lat+lon+radio_km, desde, hasta, limit, offset` |
| GET  | `/api/v1/evaluaciones/{id}` | registro completo (incluye `resultado` = payload del agente) |

### POST /api/v1/evaluaciones

Solo `lat` y `lon` son obligatorios.

```json
{
  "lat": 6.6425,
  "lon": -76.075,
  "cultivo": "maiz",
  "etapa": "vegetativo",
  "campo": { "soil_ph": 6.2, "organic_matter": 1.5, "symptoms": ["clorosis_hojas_viejas"] },
  "historial": [["frijol"]],
  "rastrojo": "incorporated",
  "fertilizacion_n": "none_or_low",
  "encharcamiento": false,
  "referencia_cliente": "lote-123"
}
```

Opcional: `serie_nasa_power` (JSON diario de NASA POWER) **o** `serie_csv` (texto CSV).
Si se define `API_KEY` en el entorno, el POST exige la cabecera `X-API-Key`.

### Desde el frontend (Next.js, route handler en el servidor)

```ts
// app/api/evaluar/route.ts
export async function POST(req: Request) {
  const body = await req.json();
  const r = await fetch(`${process.env.MOTOR_API_URL}/api/v1/evaluaciones`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": process.env.MOTOR_API_KEY ?? "" },
    body: JSON.stringify(body),
  });
  return new Response(await r.text(), { status: r.status, headers: { "Content-Type": "application/json" } });
}
```

## Despliegue en Railway

1. Subir esta carpeta **sin** `territorial_canonical_unified.json` ni `.env` (ya están en `.gitignore`).
   Deben ir `motor_agronomico_v41.py`, `cuaderno_agronomico_unificado_2.3.json` y `territorial_index_v41.json`.
2. Variables del servicio: `DATABASE_URL=${{Postgres.DATABASE_URL}}` (red interna), `CORS_ORIGINS`, `API_KEY`.
3. El `Procfile` arranca uvicorn en `$PORT`. Railway sirve el dominio `*.up.railway.app` con HTTPS.
