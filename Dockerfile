# API del motor agronómico 4.1 (FastAPI + PostgreSQL), lista para Railway.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Dependencias primero para aprovechar la caché de capas
COPY requirements.txt .
RUN pip install -r requirements.txt

# Código y cuaderno. Los datos del territorio NO van en la imagen: se piden a la API canónica (TERRITORIAL_API_URL).
COPY motor_agronomico_v41.py cuaderno_agronomico_unificado_2.3.json ./
COPY app ./app

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4)"

# Railway inyecta $PORT. `exec` deja a uvicorn como PID 1 para que reciba SIGTERM.
# WEB_CONCURRENCY (opcional) fija el número de workers de uvicorn.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --proxy-headers --forwarded-allow-ips="*"
