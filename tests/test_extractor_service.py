"""Tests del pdf-extractor-service."""
from fastapi.testclient import TestClient


def test_health_live(client: TestClient):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_ready(client: TestClient):
    r = client.get("/health/ready")
    assert r.status_code == 200


def test_metrics_endpoint(client: TestClient):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"pdf_extraction" in r.content


def test_extract_no_token(client: TestClient, valid_pdf_bytes: bytes):
    r = client.post(
        "/v1/extract",
        files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 401


def test_extract_not_pdf(client: TestClient, token_header: dict):
    r = client.post(
        "/v1/extract",
        files={"file": ("notapdf.txt", b"hello world", "text/plain")},
        headers=token_header,
    )
    assert r.status_code == 415


def test_extract_too_large(client: TestClient, token_header: dict):
    # Genera bytes que superan el límite (usa 1 byte más del máximo)
    from app.core.config import settings
    big = b"%PDF-" + b"x" * (settings.max_file_size_bytes + 1)
    r = client.post(
        "/v1/extract",
        files={"file": ("big.pdf", big, "application/pdf")},
        headers=token_header,
    )
    assert r.status_code == 413


def test_extract_valid_pdf(client: TestClient, valid_pdf_bytes: bytes, token_header: dict):
    r = client.post(
        "/v1/extract",
        files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
        headers=token_header,
    )
    # Puede ser 200 (éxito) o 422 (el PDF mínimo no tiene texto extraíble)
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        body = r.json()
        assert "text" in body
        assert "pages" in body
