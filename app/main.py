"""
Punto de entrada del pdf-extractor-service.

Rutas:
  POST /v1/extract          - Extrae texto de un PDF (multipart, campo 'file')
  GET  /health/live         - Liveness probe
  GET  /health/ready        - Readiness probe
  GET  /metrics             - Métricas Prometheus
"""
from __future__ import annotations

import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Header, HTTPException, Request, Response, UploadFile, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.metrics import extraction_duration, extraction_errors
from app.workers.pool import (
    PDFEncryptedError,
    QueueFullError,
    shutdown,
    startup,
    submit_extraction,
)

configure_logging(settings.loglevel.upper())
logger = logging.getLogger(__name__)

MAX_BYTES = settings.max_file_size_bytes
PDF_MAGIC = b"%PDF-"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida: arranca y apaga el pool de procesos."""
    startup()
    logger.info("pdf-extractor-service iniciado")
    try:
        yield
    finally:
        shutdown()
        logger.info("pdf-extractor-service detenido")


app = FastAPI(
    title="pdf-extractor-service",
    description="Servicio sin estado para extraer texto de PDFs",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Middleware: X-Request-ID
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Health endpoints (exentos de auth interna)
# ---------------------------------------------------------------------------
@app.get("/health/live", tags=["health"])
async def health_live():
    """Liveness probe: el proceso está vivo."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    """Readiness probe: el pool está disponible."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------
@app.get("/metrics", include_in_schema=False)
async def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Autenticación interna
# ---------------------------------------------------------------------------
def verify_internal_token(x_internal_token: str | None) -> None:
    if not secrets.compare_digest(
        (x_internal_token or "").encode(),
        settings.internal_api_token.encode(),
    ):
        raise HTTPException(status_code=401, detail="Token interno inválido")


# ---------------------------------------------------------------------------
# POST /v1/extract
# ---------------------------------------------------------------------------
@app.post("/v1/extract", tags=["extracción"])
async def extract(
    request: Request,
    file: UploadFile = File(..., description="Archivo PDF a procesar"),
    x_internal_token: str | None = Header(default=None),
):
    """
    Extrae texto de un PDF.

    Errores:
    - 413: El archivo supera MAX_FILE_SIZE_MB.
    - 415: El archivo no es un PDF (magic bytes incorrectos).
    - 422: El PDF está cifrado o corrupto.
    - 429: Cola llena (incluye cabecera Retry-After).
    - 504: Timeout en la extracción.
    """
    verify_internal_token(x_internal_token)

    # Leer desde el UploadFile en chunks, cortando al superar el límite
    chunks: list[bytes] = []
    total = 0
    chunk_size = 65536  # 64 KiB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTES:
            extraction_errors.labels(error_type="too_large").inc()
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"El archivo supera el límite de {settings.max_file_size_mb} MB",
            )
        chunks.append(chunk)

    pdf_bytes = b"".join(chunks)

    # Validar magic bytes
    if not pdf_bytes.startswith(PDF_MAGIC):
        extraction_errors.labels(error_type="not_pdf").inc()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El archivo no es un PDF válido",
        )

    # Enviar al pool de procesos
    t0 = time.perf_counter()
    try:
        result = await submit_extraction(pdf_bytes)
    except QueueFullError:
        extraction_errors.labels(error_type="queue_full").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Cola de extracción llena. Intente más tarde.",
            headers={"Retry-After": "5"},
        )
    except TimeoutError:
        extraction_errors.labels(error_type="timeout").inc()
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timeout al extraer el PDF",
        )
    except PDFEncryptedError:
        extraction_errors.labels(error_type="encrypted").inc()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El PDF está cifrado o protegido con contraseña",
        )
    except Exception as exc:
        extraction_errors.labels(error_type="corrupt").inc()
        logger.exception("Error inesperado al extraer PDF")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El PDF está corrupto o no se puede procesar",
        ) from exc
    finally:
        elapsed = time.perf_counter() - t0
        extraction_duration.observe(elapsed)

    # Verificar límite de páginas
    if result["pages"] > settings.max_pages:
        extraction_errors.labels(error_type="too_many_pages").inc()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El PDF supera el límite de {settings.max_pages} páginas",
        )

    return {"text": result["text"], "pages": result["pages"]}
