# pdf-extractor-service

Servicio **sin estado** que extrae texto de archivos PDF mediante un pool de procesos (CPU-bound).
No usa base de datos. Es invocado exclusivamente por el orquestador (`export-viewer-service`).

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/v1/extract` | Extrae texto de un PDF (multipart, campo `file`) |
| GET | `/health/live` | Liveness probe |
| GET | `/health/ready` | Readiness probe |
| GET | `/metrics` | Métricas Prometheus |

### Códigos de error

| Código | Causa |
|--------|-------|
| 401 | Token interno inválido (`X-Internal-Token`) |
| 413 | Archivo mayor a `MAX_FILE_SIZE_MB` |
| 415 | No es un PDF (magic bytes incorrectos) |
| 422 | PDF cifrado o corrupto |
| 429 | Cola llena (cabecera `Retry-After: 5`) |
| 504 | Timeout del job de extracción |

## Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `LOGLEVEL` | `info` | Nivel de logging |
| `INTERNAL_API_TOKEN` | `change-me` | Token de autenticación interna |
| `MAX_FILE_SIZE_MB` | `10` | Tamaño máximo de PDF en MB |
| `MAX_PAGES` | `500` | Número máximo de páginas |
| `EXTRACT_TIMEOUT_SECONDS` | `60` | Timeout por job de extracción |
| `WORKER_POOL_SIZE` | `2` | Procesos workers en el pool |
| `QUEUE_MAXSIZE` | `10` | Tamaño máximo de la cola |

## Ejecución

```bash
cp .env.example .env
# Editar .env con los valores reales
uv sync --frozen
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Tests

```bash
uv run pytest tests/ -v
uv run ruff check app/ tests/
```

## Cierre ordenado

`Ctrl+C` en la terminal produce un apagado ordenado (espera los jobs en curso hasta 25 s).
