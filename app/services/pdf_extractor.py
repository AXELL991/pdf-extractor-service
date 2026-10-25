"""Extracción de texto de PDFs (capa de dominio, sin HTTP).

Toda la lógica corre sobre ``bytes`` en memoria: nunca se vuelca el PDF a
disco ni se duplican buffers innecesariamente. Usa ``pymupdf`` sobre un
buffer en memoria.
"""
from __future__ import annotations

from app.core.errors import PdfInvalidError

PDF_MAGIC = b"%PDF-"


def extract_pdf_bytes(pdf_bytes: bytes) -> dict[str, object]:
    """Extrae texto y conteo de páginas de un PDF en memoria.

    Devuelve ``{"text": str, "pages": int}``. Lanza :class:`PdfInvalidError`
    si el archivo no es un PDF válido, está cifrado o no se puede parsear.
    """
    if not pdf_bytes.startswith(PDF_MAGIC):
        raise PdfInvalidError("El archivo no es un PDF válido")

    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

    if doc.is_encrypted:
        raise PdfInvalidError("El PDF está cifrado o protegido con contraseña")

    pages = doc.page_count
    texts: list[str] = []
    for page in doc:
        try:
            texts.append(page.get_text() or "")
        except Exception:
            texts.append("")

    doc.close()

    return {"text": "\n".join(texts), "pages": pages}
