# pdf-extractor-service

Servicio **sin estado** que extrae texto de archivos PDF y lo devuelve en Markdown.
No usa base de datos. Es invocado por el orquestador (`export-viewer-service`) y
expuesto directamente para pruebas de carga (k6 / Vegeta).

## Endpoints

| Método | Ruta | Descripción | Request | Respuesta |
|--------|------|-------------|---------|-----------|
| POST | `/extract` | Extrae texto de un PDF. | `multipart/form-data` (campo `file`) **o** body binario (`Content-Type: application/pdf`) | `200 { "content", "page_count" }` |
| POST | `/v1/extract` | Endpoint legacy del orquestador (con `X-Internal-Token`). | multipart `file` | `200 { "text", "pages" }` |
| GET | `/health` | Healthcheck simple. | – | `200 { "status": "ok" }` |
| GET | `/health/live` | Liveness probe. | – | `200 { "status": "ok" }` |
| GET | `/health/ready` | Readiness probe (pool disponible). | – | `200 { "status": "ok" }` |
| GET | `/metrics` | Métricas Prometheus. | – | `200` texto plano |

### Códigos de error

| Código | Causa | Cabecera |
|--------|-------|----------|
| 400 | PDF inválido / falta campo `file` / supera páginas | – |
| 401 | Token interno inválido (`/v1/extract`) | – |
| 413 | Archivo mayor a `MAX_FILE_SIZE_MB` | – |
| 429 | Cola de extracción llena (backpressure) | `Retry-After` |
| 503 | Timeout de extracción (saturación) | `Retry-After` |

Nunca se devuelve 500 por saturación.

## Arquitectura

- **Runtime HTTP separado de extracción CPU-bound:** FastAPI/uvicorn en el event loop; la extracción corre en un `ProcessPoolExecutor` (pymupdf) para no bloquear el GIL.
- **Admisión con backpressure:** contador de jobs en vuelo vs `QUEUE_MAXSIZE`; lleno → HTTP 429 inmediato (sin acumular trabajo expirado).
- **Todo en memoria:** el PDF se lee por streaming con tope de tamaño y se pasa a `pymupdf.open(stream=…)`; nunca se vuelca a disco ni se duplican buffers.

## Variables de entorno (Twelve-Factor)

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `LOGLEVEL` | `info` | Nivel de logging (JSON a stdout) |
| `INTERNAL_API_TOKEN` | `change-me-in-production` | Token para `/v1/extract` |
| `MAX_FILE_SIZE_MB` | `15` | Tamaño máximo de PDF en MB |
| `MAX_PAGES` | `500` | Páginas máximas por PDF |
| `EXTRACT_TIMEOUT_SECONDS` | `25` | Timeout del job (menor al timeout de cliente, 30 s) |
| `WORKER_POOL_SIZE` | `1` | Procesos workers del pool |
| `QUEUE_MAXSIZE` | `100` | Trabajos máximos en vuelo |

## Ejecución

### Local (desarrollo)

```bash
cd pdf-extractor-service
uv sync --frozen
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### Con Docker (todo el stack, un único comando)

Desde la raíz del repositorio:

```bash
docker compose up --build
```

Levanta mongodb, pdf-extractor-service (5 réplicas, 1 CPU y 1 GB c/u), document-crud-service, export-viewer-service y traefik. El extractor se expone vía Traefik en el puerto 80.

### Pruebas

```bash
uv run pytest tests/ -v
uv run ruff check app/ tests/
```

## Cierre ordenado

`SIGTERM` (`docker compose stop` / `Ctrl+C`) produce un apagado ordenado: el lifespan espera los jobs del pool hasta 25 s (`--timeout-graceful-shutdown 25` en el Dockerfile).
