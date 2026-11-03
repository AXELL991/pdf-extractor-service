"""
Nota sobre límite de tasa en pdf-extractor-service.

Este servicio NO implementa rate limiting por cliente (IP). La protección
contra sobrecarga se maneja mediante:

1. La cola acotada (QUEUE_MAXSIZE): cuando está llena, responde HTTP 429
   inmediatamente con cabecera Retry-After (backpressure real).
2. El middleware `ratelimit` de Traefik en el gateway, aplicado a los
   routers de cada microservicio.

El rate limiting por IP vive exclusivamente en Traefik, no en este servicio.
"""