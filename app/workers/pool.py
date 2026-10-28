"""
Pool de procesos para extracción CPU-bound de PDFs.

Usa ``ProcessPoolExecutor`` porque pypdf es CPU-bound y el GIL bloquearía un
``ThreadPoolExecutor``. Cada job corre en un proceso separado y la extracción
nunca se ejecuta sobre el event loop de FastAPI.

La admisión está acotada mediante un contador tocado solo desde el event loop
(asyncio es single-threaded, así que no hay race condition). Cuando la admisión
está llena se lanza :class:`QueueFullError` inmediatamente para responder 429
sin colgar la petición (backpressure real: nunca se acumula trabajo sin límite).
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor

from app.core.config import settings
from app.core.errors import ExtractionTimeoutError, QueueFullError
from app.core.metrics import queue_size

logger = logging.getLogger(__name__)

# El pool global se inicializa en el lifespan de FastAPI.
_pool: ProcessPoolExecutor | None = None
# Número de trabajos admitidos en curso (solo modificado desde el event loop).
_in_flight = 0
# Función de extracción inyectada (inversión de dependencias).
_extract_func = None


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


def startup(extract_func=None) -> None:
    """Inicializa el pool. Llamar desde el lifespan.
    
    Args:
        extract_func: Función de extracción a inyectar. Si no se provee,
                      se importa por defecto desde app.services.pdf_extractor.
    """
    global _pool, _in_flight, _extract_func
    _in_flight = 0
    _pool = _init_pool()
    if extract_func is not None:
        _extract_func = extract_func
    elif _extract_func is None:
        from app.services.pdf_extractor import extract_pdf_bytes as _default_extract
        _extract_func = _default_extract


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

    - Si la admisión está llena (``_in_flight >= QUEUE_MAXSIZE``), lanza
      :class:`QueueFullError` inmediatamente (429 con Retry-After).
    - Si el job supera ``EXTRACT_TIMEOUT_SECONDS``, lanza
      :class:`ExtractionTimeoutError` (503 con Retry-After) y recicla el pool.
    - Si el pool está roto (``BrokenExecutor``), lo recrea.
    """
    global _in_flight, _pool

    if _in_flight >= settings.queue_maxsize:
        raise QueueFullError()

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
            raise ExtractionTimeoutError() from None
        except BrokenExecutor:
            logger.error("ProcessPoolExecutor roto. Reciclando pool...")
            _recycle_pool()
            raise
    finally:
        _in_flight -= 1
        queue_size.set(_in_flight)


def _extract_sync(pdf_bytes: bytes) -> dict:
    """Función que corre en el proceso hijo. Extrae texto de los bytes del PDF."""
    func = _extract_func
    if func is None:
        from app.services.pdf_extractor import extract_pdf_bytes as func
    return func(pdf_bytes)
