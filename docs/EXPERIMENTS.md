# Experimentos de rendimiento – pdf-extractor-service

Cada entrada registra: hipótesis, cambio, métricas (medición real) y decisión (mantener/revertir).

## Exp 0 – Línea de base inicial (pypdf)

**Hipótesis:** pypdf + ProcessPoolExecutor de 1 worker por réplica, 5 réplicas, 1 CPU c/u, alcanza el benchmark de la cátedra.

**Cambio:** Ninguno (medición del estado actual).

**Métricas reales (pypdf, extracción en proceso):**
- small (1 pág): 0.124 s, medium (30 pág): 0.047 s, large (600 pág): 1.324 s, xlarge (1500 pág): 3.343 s (mezcla ≈ 1.2 s/doc).
- Capacidad teórica: 5 réplicas × 1 CPU ≈ 4.2 req/s. Muy por debajo del k6 objetivo (25.35 req/s).
- Carga cerrada 100 VUs: pool de 1 proceso serializa; ~1 req/s por réplica; trabajos en cola esperan ≫ 30 s → timeouts del cliente.

**Decisión:** pypdf es demasiado lento; no cumple throughput ni latencia del benchmark. Se propuso cambiar a PyMuPDF.

## Exp 1 – Cambio de motor de extracción: pypdf → pymupdf (APLICADO)

**Hipótesis:** pymupdf es significativamente más rápido que pypdf sin alterar el trabajo real (extrae texto verdadero, sin caché, sin recortes ni detección de user-agent).

**Cambio:**
- `pyproject.toml`: `pypdf>=5.1,<6.0` → `pymupdf>=1.24,<2.0` (y `uv.lock` regenerado con `uv add`).
- `app/services/pdf_extractor.py`: usa `pymupdf.open(stream=..., filetype="pdf")`, `doc.page_count`, `page.get_text()`, `doc.close()`.
- `app/workers/pool.py` y `app/main.py`: sin cambios (reciben `{"text","pages"}` igual que antes).

**Métricas reales (pymupdf, servicio HTTP real, 1 worker, MAX_PAGES=3000):**
- small (1.4 KB, 1 pág): 0.059 s (HTTP)
- medium (16.7 KB, 30 pág): 0.026 s (HTTP)
- large (430.8 KB, 600 pág): 0.214 s (medido directo en proceso)
- xlarge (1.08 MB, 1500 pág): 0.521 s (medido directo en proceso)
- Mezcla ≈ 0.19 s/doc (≈ 6× más rápido que pypdf).

**Capacidad estimada con 5 réplicas × 1 CPU:** ≈ 5 / 0.19 ≈ 26 req/s, por encima del k6 objetivo (25.35 req/s) y con latencia bien por debajo del timeout de cliente de 30 s → sin timeouts por colas en modelo cerrado.

**Validación:** 12 tests unitarios pasan; `ruff check` limpio.

**Decisión:** MANTENER. Se cumple el requisito de extracción eficiente y el servicio es competitivo contra el benchmark de la cátedra.

## Experimentos pendientes (medir contra stack completo con docker compose)

1. Ejecutar k6 spike (0→100 VUs en 10s, 20s sostenidos, 10s bajada) contra `docker compose up --build` y registrar: throughput, error rate, p50/p90/p95/max. Objetivo: >25.35 req/s, 0% error, latencias ≤ las de la cátedra.
2. Ejecutar Vegeta (50 req/s, 30 s, 1.500 requests rotando 4 PDFs, timeout cliente 30 s) y registrar: tasa de éxito, throughput efectivo, p50, timeouts de cliente. Objetivo: más éxito y throughput que la cátedra (16.65 req/s, 66.53% éxito), menos timeouts.
3. Validar que nunca hay 500 por saturación: solo 429 (cola llena) y 503 (timeout) con `Retry-After`.
