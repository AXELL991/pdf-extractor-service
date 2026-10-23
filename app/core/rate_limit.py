"""
Nota sobre límite de tasa en pdf-extractor-service:

Este servicio NO implementa rate limiting por cliente (IP). La protección
contra sobrecarga se maneja mediante la cola acotada (QUEUE_MAXSIZE).
Cuando la cola está llena, el servicio responde HTTP 429 inmediatamente.

El rate limiting por IP está implementado en el orquestador (export-viewer-service).
"""
