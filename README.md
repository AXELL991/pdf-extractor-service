# pdf-extractor-service

Servicio sin estado que extrae texto de archivos PDF. Es invocado por el orquestador (`export-viewer-service`) y expuesto directamente para pruebas de carga. No usa base de datos ni persiste información.

## Responsabilidades

- Extraer texto de PDFs usando `pymupdf`
- Devolver el texto extraído y el conteo de páginas
- Validar que el archivo sea un PDF válido (magic bytes)
- Aplicar límites de tamaño y número de páginas
- Proporcionar backpressure mediante cola acotada (429 cuando está llena)

## Endpoints

| Método | Ruta | Autenticación | Descripción |
|--------|------|---------------|-------------|
| POST | `/extract` | No | Extrae texto (multipart `file` o body binario `application/pdf`) |
| POST | `/v1/extract` | `X-Internal-Token` | Endpoint legacy del orquestador |
| GET | `/health` | No | Healthcheck simple |
| GET | `/health/live` | No | Sonda de vitalidad |
| GET | `/health/ready` | No | Sonda de readiness (pool disponible) |
| GET | `/metrics` | No | Métricas Prometheus |

### Códigos de error

| Código | Causa |
|--------|-------|
| 400 | PDF inválido o falta el campo `file` |
| 413 | Archivo supera `MAX_FILE_SIZE_MB` |
| 429 | Cola de extracción llena (backpressure, con `Retry-After`) |
| 503 | Timeout de extracción (saturación, con `Retry-After`) |

Nunca se devuelve 500 por saturación.

## Arquitectura interna

- **Runtime HTTP:** FastAPI + uvicorn (1 worker por contenedor)
- **Extracción CPU-bound:** `ProcessPoolExecutor` para no bloquear el event loop con el GIL de Python
- **Admisión acotada:** contador de trabajos en vuelo vs `QUEUE_MAXSIZE`; lleno → HTTP 429 inmediato
- **Todo en memoria:** el PDF se lee por streaming con tope de tamaño y se pasa a `pymupdf.open(stream=…)`; nunca se escribe a disco

## Variables de entorno

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `LOGLEVEL` | Nivel de logging | `info` |
| `INTERNAL_API_TOKEN` | Token para `/v1/extract` | `your-secure-token` |
| `MAX_FILE_SIZE_MB` | Tamaño máximo de PDF en MB | `15` |
| `MAX_PAGES` | Páginas máximas por PDF | `500` |
| `EXTRACT_TIMEOUT_SECONDS` | Timeout del job en segundos | `25` |
| `WORKER_POOL_SIZE` | Procesos workers del pool | `8` |
| `QUEUE_MAXSIZE` | Trabajos máximos en vuelo | `100` |

## Cómo ejecutar

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

## PDFs de estrés

En `tests/stress/pdfs/`:
- `stress_1mb.pdf` (~1 MB)
- `stress_3mb.pdf` (~3 MB)
- `stress_6mb.pdf` (~6 MB)
- `stress_9mb.pdf` (~9 MB)

## Tests

```bash
uv run pytest tests/ -v
uv run ruff check app/ tests/
```

## Cierre ordenado

`SIGTERM` (`docker compose stop` / `Ctrl+C`) produce un apagado ordenado: el lifespan espera los jobs del pool hasta 25 segundos (`--timeout-graceful-shutdown 25` en el Dockerfile).