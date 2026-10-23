"""Core configuration for pdf-extractor-service.
All settings are read from environment variables following Twelve‑Factor principles.
"""
import os

# Logging level (default INFO)
LOGLEVEL = os.getenv("LOGLEVEL", "INFO")

# Maximum file size in megabytes (default 5 MiB)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "5"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Number of workers in the extraction pool (default 2)
WORKER_POOL_SIZE = int(os.getenv("WORKER_POOL_SIZE", "2"))

# Maximum number of pending jobs in the queue before back‑pressure is applied.
# When the queue is full the service returns HTTP 429.
QUEUE_MAXSIZE = int(os.getenv("QUEUE_MAXSIZE", "10"))
"
