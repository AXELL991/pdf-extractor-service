"""Fixtures compartidos para los tests del pdf-extractor-service."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def valid_pdf_bytes() -> bytes:
    """Genera un PDF mínimo y válido en memoria."""
    # PDF mínimo que pypdf puede parsear
    pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000101 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
164
%%EOF"""
    return pdf


@pytest.fixture
def token_header() -> dict:
    return {"X-Internal-Token": settings.internal_api_token}
