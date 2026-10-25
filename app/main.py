"""
Punto de entrada del pdf-extractor-service.

Rutas:
  POST /extract           - Contrato del TP: multipart (campo 'file') o body binario
                            (Content-Type: application/pdf). Responde
                            {"content","page_count"}. Sin auth interna.
  POST /v1/extract        - Endpoint legacy del orquestador (token interno,
                            {"text","pages"}).
  GET  /health            - Healthcheck simple.
  GET  /health/live       - Liveness probe.
  GET  /health/ready      - Readiness probe (pool disponible).
  GET  /metrics           - Métricas Prometheus.
"""
from __future__ import annotations

import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import settings
from app.core.errors import (
    ExtractionTimeoutError,
    PdfInvalidError,
    QueueFullError,
)
from app.core.logging_config import configure_logging
from app.core.metrics import extraction_duration, extraction_errors
from app.workers.pool import get_pool, shutdown, startup, submit_extraction

configure_logging(settings.loglevel.upper())
logger = logging.getLogger(__name__)

MAX_BYTES = settings.max_file_size_bytes
PDF_MAGIC = b"%PDF-"
CHUNK_SIZE = 65536  # 64 KiB


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
# Health endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
async def health():
    """Healthcheck simple."""
    return {"status": "ok"}


@app.get("/health/live", tags=["health"])
async def health_live():
    """Liveness probe: el proceso está vivo."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    """Readiness probe: el pool está disponible."""
    get_pool()  # lanza si el pool no está inicializado
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------
@app.get("/metrics", include_in_schema=False)
async def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Autenticación interna (solo endpoint legacy /v1/extract)
# ---------------------------------------------------------------------------
def verify_internal_token(x_internal_token: str | None) -> None:
    if not secrets.compare_digest(
        (x_internal_token or "").encode(),
        settings.internal_api_token.encode(),
    ):
        raise HTTPException(status_code=401, detail="Token interno inválido")


# ---------------------------------------------------------------------------
# Lectura del payload con límite de tamaño (streaming, sin disco)
# ---------------------------------------------------------------------------
async def _read_with_cap(source: AsyncIterator[bytes], max_bytes: int) -> bytes:
    """Lee chunks de un async-iterable cortando al superar ``max_bytes`` (413)."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in source:
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            extraction_errors.labels(error_type="too_large").inc()
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"El archivo supera el límite de {settings.max_file_size_mb} MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_upload(upload: UploadFile) -> bytes:
    """Lee un UploadFile en chunks con tope de tamaño."""

    async def _gen():
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk

    return await _read_with_cap(_gen(), MAX_BYTES)


async def _read_pdf_payload(request: Request) -> bytes:
    """Lee el PDF: multipart/form-data (campo 'file') o body binario raw."""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falta el campo 'file' en el multipart/form-data",
            )
        return await _read_upload(upload)
    # Body binario directo (Content-Type: application/pdf)
    return await _read_with_cap(request.stream(), MAX_BYTES)


async def _extract_pdf_bytes(pdf_bytes: bytes) -> dict:
    """Valida magic bytes y envía al pool de procesos. Devuelve {"text","pages"}."""
    if not pdf_bytes.startswith(PDF_MAGIC):
        raise PdfInvalidError("El archivo no es un PDF válido")
    return await submit_extraction(pdf_bytes)


def _map_pool_error(exc: Exception, legacy: bool) -> HTTPException:
    """Mapea errores del pool a HTTPException según el contrato del endpoint."""
    if isinstance(exc, QueueFullError):
        return HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=exc.headers,
        )
    if isinstance(exc, ExtractionTimeoutError):
        code = status.HTTP_504_GATEWAY_TIMEOUT if legacy else status.HTTP_503_SERVICE_UNAVAILABLE
        return HTTPException(status_code=code, detail=exc.detail, headers=exc.headers)
    if isinstance(exc, PdfInvalidError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY if legacy else status.HTTP_400_BAD_REQUEST
        return HTTPException(status_code=code, detail=exc.detail)
    extraction_errors.labels(error_type="corrupt").inc()
    logger.exception("Error inesperado al extraer PDF")
    code = status.HTTP_422_UNPROCESSABLE_ENTITY if legacy else status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=code, detail="El PDF está corrupto o no se puede procesar"
    )


async def _process_pdf(pdf_bytes: bytes, legacy: bool) -> dict:
    """Extrae y valida límite de páginas. Mapea errores del pool a HTTP."""
    t0 = time.perf_counter()
    try:
        result = await _extract_pdf_bytes(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 - se mapea a error controlado
        extraction_duration.observe(time.perf_counter() - t0)
        raise _map_pool_error(exc, legacy=legacy) from None
    extraction_duration.observe(time.perf_counter() - t0)

    if result["pages"] > settings.max_pages:
        extraction_errors.labels(error_type="too_many_pages").inc()
        code = status.HTTP_422_UNPROCESSABLE_ENTITY if legacy else status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=code,
            detail=f"El PDF supera el límite de {settings.max_pages} páginas",
        )
    return result


# ---------------------------------------------------------------------------
# POST /extract  (contrato del TP: sin auth, {"content","page_count"})
# ---------------------------------------------------------------------------
@app.post("/extract", tags=["extracción"])
async def extract(request: Request):
    """
    Extrae texto de un PDF.

    Admite multipart/form-data (campo ``file``) y body binario directo
    (Content-Type: application/pdf).

    Errores:
    - 400: PDF inválido / falta el campo file.
    - 413: archivo demasiado grande.
    - 429: cola llena (cabecera Retry-After).
    - 503: saturación/timeout de extracción (cabecera Retry-After).
    """
    pdf_bytes = await _read_pdf_payload(request)
    result = await _process_pdf(pdf_bytes, legacy=False)
    return {"content": result["text"], "page_count": result["pages"]}


# ---------------------------------------------------------------------------
# POST /v1/extract  (legacy orquestador: token, {"text","pages"})
# ---------------------------------------------------------------------------
@app.post("/v1/extract", tags=["extracción"])
async def extract_v1(
    file: UploadFile = File(..., description="Archivo PDF a procesar"),
    x_internal_token: str | None = Header(default=None),
):
    verify_internal_token(x_internal_token)

    pdf_bytes = await _read_upload(file)
    result = await _process_pdf(pdf_bytes, legacy=True)
    return {"text": result["text"], "pages": result["pages"]}
