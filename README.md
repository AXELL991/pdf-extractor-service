# pdf-extractor-service

Servicio **sin estado** que extrae texto de archivos PDF. No usa base de datos. Es invocado por el orquestador (`export-viewer-service`) y expuesto directamente para pruebas de carga (k6 / Vegeta).

## Endpoints

| Método | Ruta | Descripción | Request | Respuesta |
|--------|------|-------------|---------|-----------|
| POST | `/extract` | Extrae texto de un PDF (contrato TP) | multipart `file` o body binario `application/pdf` | `200 { "content", "page_count" }` |
| POST | `/v1/extract` | Endpoint legacy del orquestador (token) | multipart `file` | `200 { "text", "pages" }` |
| GET | `/health` | Healthcheck simple | — | `200 { "status": "ok" }` |
| GET | `/health/live` | Liveness probe | — | `200 { "status": "ok" }` |
| GET | `/health/ready` | Readiness probe (pool disponible) | — | `200 { "status": "ok" }` |
| GET | `/metrics` | Métricas Prometheus | — | texto plano |

### Códigos de error

| Código | Causa | Cabecera |
|--------|-------|----------|
| 400 | PDF inválido / falta campo `file` / supera páginas | — |
| 401 | Token interno inválido (`/v1/extract`) | — |
| 413 | Archivo mayor a `MAX_FILE_SIZE_MB` | — |
| 429 | Cola de extracción llena (backpressure) | `Retry-After` |
| 503 | Timeout de extracción (saturación) | `Retry-After` |

Nunca se devuelve 500 por saturación.

## Arquitectura

- **Runtime HTTP separado de extracción CPU-bound:** FastAPI/uvicorn en el event loop; la extracción corre en un `ProcessPoolExecutor` (pymupdf) para no bloquear el GIL.
- **Admisión con backpressure:** contador de jobs en vuelo vs `QUEUE_MAXSIZE`; lleno → HTTP 429 inmediato (sin acumular trabajo expirado).
- **Todo en memoria:** el PDF se lee por streaming con tope de tamaño y se pasa a `pymupdf.open(stream=…)`; nunca se vuelca a disco ni se duplican buffers.

## Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `LOGLEVEL` | `info` | Nivel de logging (JSON a stdout) |
| `INTERNAL_API_TOKEN` | — | Token para `/v1/extract` (requerido, sin default inseguro) |
| `MAX_FILE_SIZE_MB` | `15` | Tamaño máximo de PDF en MB |
| `MAX_PAGES` | `500` | Páginas máximas por PDF |
| `EXTRACT_TIMEOUT_SECONDS` | `25` | Timeout del job (menor al timeout de cliente, 30 s) |
| `WORKER_POOL_SIZE` | `1` | Procesos workers del pool |
| `QUEUE_MAXSIZE` | `100` | Trabajos máximos en vuelo |

## Ejecución

### Standalone (solo el extractor)

```bash
cd pdf-extractor-service
docker compose up --build -d
```

### Desde el orquestador (stack completo, 5 réplicas)

```bash
cd ../export-viewer-service
docker compose up --build -d
```

El extractor no publica puerto en el host (5 réplicas = conflicto de bind). Se accede vía la red interna de Docker: `http://pdf-extractor-service:8000/extract`.

## Pruebas

```bash
uv run pytest tests/ -v
uv run ruff check app/ tests/
```

## PDFs de estrés

En `tests/stress/pdfs/`:
- `stress_1mb.pdf` (~1 MB)
- `stress_3mb.pdf` (~3 MB)
- `stress_6mb.pdf` (~6 MB)
- `stress_9mb.pdf` (~9 MB)

## Cierre ordenado

`SIGTERM` (`docker compose stop` / `Ctrl+C`) produce un apagado ordenado: el lifespan espera los jobs del pool hasta 25 s (`--timeout-graceful-shutdown 25` en el Dockerfile).