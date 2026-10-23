"""Métricas Prometheus para pdf-extractor-service."""
from prometheus_client import Counter, Gauge, Histogram

extraction_duration = Histogram(
    "pdf_extraction_duration_seconds",
    "Duración de la extracción de PDF en segundos",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
)

extraction_errors = Counter(
    "pdf_extraction_errors_total",
    "Errores de extracción por tipo",
    labelnames=["error_type"],
)

queue_size = Gauge(
    "pdf_extraction_queue_size",
    "Número actual de trabajos en cola",
)
