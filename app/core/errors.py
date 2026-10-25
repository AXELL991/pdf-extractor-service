"""Errores del dominio de extracción de PDFs.

Cada error lleva un código HTTP y, cuando aplica, la cabecera ``Retry-After``
para que la capa HTTP nunca devuelva un 500 por saturación ni por sobrecarga.
"""
from __future__ import annotations


class ExtractionError(Exception):
    """Error base con metadatos para mapear a respuesta HTTP."""

    status_code: int = 500
    detail: str = "Error al extraer el PDF"
    headers: dict[str, str] | None = None

    def __init__(self, detail: str | None = None, headers: dict[str, str] | None = None):
        self.detail = detail or self.detail
        self.headers = headers or self.headers
        super().__init__(self.detail)


class PdfInvalidError(ExtractionError):
    """El PDF no es válido (no es PDF, está corrupto o cifrado)."""

    status_code = 400
    detail = "PDF inválido"


class QueueFullError(ExtractionError):
    """Cola de extracción llena (saturación)."""

    status_code = 429
    detail = "Cola de extracción llena. Intente más tarde."

    def __init__(self, retry_after: str = "5"):
        super().__init__(
            self.detail,
            headers={"Retry-After": retry_after},
        )


class ExtractionTimeoutError(ExtractionError):
    """Timeout de extracción (servicio temporalmente no disponible)."""

    status_code = 503
    detail = "El servicio de extracción está saturado. Intente más tarde."

    def __init__(self, retry_after: str = "5"):
        super().__init__(
            self.detail,
            headers={"Retry-After": retry_after},
        )
