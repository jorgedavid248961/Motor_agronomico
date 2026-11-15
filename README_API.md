# API del motor agronómico 4.1

FastAPI + PostgreSQL. Ejecuta `evaluate_point` del motor y guarda la entrada y la salida completa en la tabla `evaluaciones`.

Los datos del territorio (NDVI, lluvia, suelos IGAC) salen de la **API territorial canónica** (`API_CANONICA`),
indicada en `TERRITORIAL_API_URL`. Al arrancar, la API del motor pide a `GET /v1/export/{ndvi,precipitation_amount,soil}`
solo los campos que necesita y construye en memoria el índice por celda (~10-20 s, en un subproceso para no retener memoria).
Mientras tanto `/health` responde `"status": "loading"` y el POST devuelve 503. Si la API canónica no responde,
reintenta sola (2 s, 4 s… hasta 60 s) y el error aparece en `territorial_error` de `/health`.
Al cambiar los datos de la API canónica, reiniciar el motor para recargar el índice.

## Local

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # y poner DATABASE_URL y TERRITORIAL_API_URL
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Requiere la API canónica corriendo (p. ej. `docker compose up -d` dentro de `API_CANONICA`, que la publica en `http://127.0.0.1:8001`).

Documentación interactiva: http://127.0.0.1:8000/docs

## Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| GET  | `/health` | estado del motor e índice (`loading` hasta tener el territorio; `territorial_error` si la API canónica falla) |
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

## Docker

```bash
docker compose up --build -d     # motor http://localhost:8000 + PostgreSQL + API canónica http://127.0.0.1:8001
```

`docker-compose.yml` incluye el `docker-compose.yml` de la API canónica (por defecto en `../../API_CANONICA`;
si está en otra ruta: `API_CANONICA_DIR=/ruta/API_CANONICA docker compose up --build -d`). El motor espera a que
la API canónica esté sana y la consume por la red interna en `http://canonica:8000`.
Docker Desktop necesita al menos 4 GB de memoria (la API canónica ocupa ~1.6 GB).

O solo la imagen:

```bash
docker build -t motor-agronomico .
docker run -p 8000:8000 -e DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB \
  -e TERRITORIAL_API_URL=http://HOST:8001 motor-agronomico
```

## Despliegue en Railway

1. Subir esta carpeta **sin** `territorial_canonical_unified.json` ni `.env` (ya están en `.gitignore` y `.dockerignore`).
   Deben ir `motor_agronomico_v41.py` y `cuaderno_agronomico_unificado_2.3.json`. (`territorial_index_v41.json` ya no lo usa la API;
   solo la interfaz Streamlit y la CLI del motor.)
2. En el proyecto de Railway: **New → Database → PostgreSQL** y **New → GitHub Repo** con este repositorio.
   `railway.json` hace que Railway construya con el `Dockerfile` y use `/health` como healthcheck.
3. Variables del servicio: `DATABASE_URL=${{Postgres.DATABASE_URL}}` (red interna), `TERRITORIAL_API_URL` (URL privada
   de la API canónica desplegada en el mismo proyecto), `CORS_ORIGINS`, `CORS_ORIGIN_REGEX`, `API_KEY`.
   Opcional: `WEB_CONCURRENCY` para más workers de uvicorn (cada uno construye y guarda su propio índice).
4. El contenedor escucha en `$PORT` (lo pone Railway). En **Settings → Networking → Generate Domain** se obtiene el dominio `*.up.railway.app` con HTTPS.
