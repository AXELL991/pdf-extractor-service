"""Entry point for the pdf-extractor-service.

This is a stub implementation that starts a FastAPI app with a single
/health endpoint. Replace the placeholder logic with the real service.
"""

from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

