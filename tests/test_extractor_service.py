"""Tests del pdf-extractor-service (contrato del TP: endpoint /extract)."""
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


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200


def test_health_ready(client):
    r = client.get("/health/ready")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /extract  (contrato del TP)
# ---------------------------------------------------------------------------
def test_extract_multipart_valid(client, valid_pdf_bytes):
    r = client.post(
        "/extract",
        files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert "content" in body
    assert "page_count" in body
    assert isinstance(body["page_count"], int)


def test_extract_raw_binary_valid(client, valid_pdf_bytes):
    r = client.post(
        "/extract",
        content=valid_pdf_bytes,
        headers={"Content-Type": "application/pdf"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "content" in body
    assert "page_count" in body


def test_extract_not_pdf(client):
    r = client.post(
        "/extract",
        files={"file": ("notapdf.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 400


def test_extract_too_large(client):
    big = b"%PDF-" + b"x" * (settings.max_file_size_bytes + 1)
    r = client.post(
        "/extract",
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert r.status_code == 413


def test_extract_missing_file_field(client):
    r = client.post(
        "/extract",
        files={"other": ("f.txt", b"x", "text/plain")},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /v1/extract  (legacy orquestador)
# ---------------------------------------------------------------------------
def test_extract_v1_no_token(client, valid_pdf_bytes):
    r = client.post(
        "/v1/extract",
        files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 401


def test_extract_v1_not_pdf(client, token_header):
    r = client.post(
        "/v1/extract",
        files={"file": ("notapdf.txt", b"hello world", "text/plain")},
        headers=token_header,
    )
    assert r.status_code == 422


def test_extract_v1_too_large(client, token_header):
    big = b"%PDF-" + b"x" * (settings.max_file_size_bytes + 1)
    r = client.post(
        "/v1/extract",
        files={"file": ("big.pdf", big, "application/pdf")},
        headers=token_header,
    )
    assert r.status_code == 413


def test_extract_v1_valid(client, valid_pdf_bytes, token_header):
    r = client.post(
        "/v1/extract",
        files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
        headers=token_header,
    )
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        body = r.json()
        assert "text" in body
        assert "pages" in body
