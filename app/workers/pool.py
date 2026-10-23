"""
Pool de procesos para extracción CPU-bound de PDFs.

Usa ``ProcessPoolExecutor`` porque pypdf es CPU-bound y el GIL bloquearía
un ``ThreadPoolExecutor``. Cada job corre en un proceso separado y la extracción
nunca se ejecuta sobre el event loop de FastAPI.

La cola es acotada mediante un contador que solo se toca desde el event loop
(asyncio es single-threaded, así que no hay race condition). Cuando la cola
está llena se lanza ``QueueFullError`` inmediatamente para responder 429 sin
colgar la petición.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor

from app.core.config import settings
from app.core.metrics import queue_size

logger = logging.getLogger(__name__)

# El pool global se inicializa en el lifespan de FastAPI.
_pool: ProcessPoolExecutor | None = None
# Número de trabajos en curso (solo modificado desde el event loop).
_in_flight = 0


def get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        raise RuntimeError("Pool no inicializado")
    return _pool


def _init_pool() -> ProcessPoolExecutor:
    """Crea y devuelve un nuevo ProcessPoolExecutor."""
    logger.info("Iniciando ProcessPoolExecutor con %d workers", settings.worker_pool_size)
    return ProcessPoolExecutor(max_workers=settings.worker_pool_size)


def _recycle_pool() -> None:
    """Desecha el pool actual (sin esperar) y crea uno nuevo."""
    global _pool
    old = _pool
    _pool = _init_pool()
    if old is not None:
        try:
            old.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001 - se descarta el pool viejo
            logger.warning("No se pudo apagar limpiamente el pool previo")


def startup() -> None:
    """Inicializa el pool. Llamar desde el lifespan."""
    global _pool, _in_flight
    _in_flight = 0
    _pool = _init_pool()


def shutdown() -> None:
    """Cierra el pool ordenadamente, esperando los jobs en curso."""
    global _pool, _in_flight
    if _pool is not None:
        logger.info("Cerrando ProcessPoolExecutor (esperando jobs en curso)...")
        _pool.shutdown(wait=True, cancel_futures=False)
        _pool = None
        logger.info("ProcessPoolExecutor cerrado")


async def submit_extraction(pdf_bytes: bytes) -> dict:
    """
    Envía un trabajo de extracción al pool de procesos.

    - Si la cola está llena (``_in_flight >= QUEUE_MAXSIZE``), lanza
      ``QueueFullError`` inmediatamente.
    - Si el job supera ``EXTRACT_TIMEOUT_SECONDS``, lanza ``TimeoutError`` y
      recicla el pool.
    - Si el pool está roto (``BrokenExecutor``/``BrokenProcessPool``), lo recrea.
    """
    global _in_flight, _pool

    if _in_flight >= settings.queue_maxsize:
        raise QueueFullError("Cola de extracción llena")

    _in_flight += 1
    queue_size.set(_in_flight)

    try:
        loop = asyncio.get_running_loop()
        pool = get_pool()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(pool, _extract_sync, pdf_bytes),
                timeout=settings.extract_timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            logger.error("Timeout en la extracción. Reciclando pool...")
            _recycle_pool()
            raise
        except BrokenExecutor:
            logger.error("ProcessPoolExecutor roto. Reciclando pool...")
            _recycle_pool()
            raise
    finally:
        _in_flight -= 1
        queue_size.set(_in_flight)


def _extract_sync(pdf_bytes: bytes) -> dict:
    """
    Función que corre en el proceso hijo. Extrae texto de los bytes del PDF.
    Importa pypdf aquí para aislar el import en el proceso hijo.
    """
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))

    if reader.is_encrypted:
        raise PDFEncryptedError("El PDF está cifrado")

    pages = len(reader.pages)
    texts = []
    for page in reader.pages:
        texts.append(page.extract_text() or "")

    return {"text": "\n".join(texts), "pages": pages}


class QueueFullError(Exception):
    """Se lanza cuando la cola de extracción está llena."""


class PDFEncryptedError(Exception):
    """Se lanza cuando el PDF está cifrado."""
