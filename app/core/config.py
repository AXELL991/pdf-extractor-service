"""Configuración central del pdf-extractor-service (pydantic-settings)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Logging
    loglevel: str = "INFO"

    # Límites de extracción
    max_file_size_mb: int = 10
    max_pages: int = 500
    extract_timeout_seconds: float = 60.0

    # Pool de procesos
    worker_pool_size: int = 2
    queue_maxsize: int = 10

    # Auth interna (requerido, sin valor por defecto inseguro)
    internal_api_token: str

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()
