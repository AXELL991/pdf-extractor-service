# Contract – PDF Extractor Service

## Overview
A stateless FastAPI service whose sole responsibility is to **extract text from PDF files** and return it in Markdown format. It does **not** persist any data and does not communicate with MongoDB.

---

## Endpoints
| Method | Path | Description | Request | Response | Errors |
|--------|------|-------------|---------|----------|--------|
| **POST** | `/extract` | Extract text from a PDF. | `multipart/form-data` with a file field `file` **or** raw binary body with `Content-Type: application/pdf`. | `200 OK` `{ "content": "<markdown>", "page_count": <int> }` | `400 Bad Request` – invalid PDF or missing file. <br> `413 Payload Too Large` – exceeds `MAX_FILE_SIZE_MB`. <br> `429 Too Many Requests` – back‑pressure / queue limit. <br> `503 Service Unavailable` – internal worker pool saturated. |
| **GET** | `/health` | Basic health check (runtime only). | – | `200 OK` `{ "status": "healthy", "environment": "<env>", "version": "<ver>", "timestamp": <unix> }` | `503 Service Unavailable` – if service cannot start workers. |
| **GET** | `/metrics` | Prometheus‑compatible metrics (optional). | – | `200 OK` plain‑text metrics. | – |

---

## Non‑functional Requirements (NFRs)
- **Performance**: extraction work is off‑loaded to a configurable pool of workers (processes or threads). Must handle up to **5 concurrent replicas**, each limited to **1 CPU** and **512 MiB–1 GiB RAM**.
- **Back‑pressure**: a request queue with a configurable timeout; if the queue is full, respond with **429** or **503** instead of buffering indefinitely.
- **Resource limits**: Docker‑file must expose `CPUS` and `MEMORY` limits; the service must respect them.
- **Logging**: JSON logs to stdout, log level controlled by `LOGLEVEL` env var.
- **Configuration**: All settings via environment variables (`MAX_FILE_SIZE_MB`, `WORKER_POOL_SIZE`, etc.) following the Twelve‑Factor app methodology.
- **Security**: Validate PDF magic numbers, sanitize filenames, limit size before reading full content.

---

## Contracts (JSON Schema snippets)
```json
{ "type": "object", "properties": { "content": { "type": "string" }, "page_count": { "type": "integer", "minimum": 0 } }, "required": ["content", "page_count"] }
```

---

*Document version*: 1.0 – **2026‑10‑22**
