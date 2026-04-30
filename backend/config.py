import sys
from functools import lru_cache

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import structlog
    _logger = structlog.get_logger(__name__)
    def _log_error(msg: str) -> None:
        _logger.error(msg)
except ImportError:
    def _log_error(msg: str) -> None:  # type: ignore[misc]
        print(f"ERROR: {msg}", file=sys.stderr)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # LLM — Ollama (no API key needed, uses local models)
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_embed_model: str = "nomic-embed-text"

    # Kept optional for backward compat — not required when using Ollama
    openai_api_key: str = "ollama-local"
    langchain_api_key: str = "no-tracing"
    langchain_tracing_v2: bool = False

    # Database
    database_url: str
    postgres_user: str
    postgres_password: str
    postgres_db: str

    # Redis / Celery
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    # ChromaDB
    chromadb_host: str
    chromadb_port: int = 8000

    # Application
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            _log_error(f"Missing or invalid required environment variable: {field}")
        sys.exit(1)


settings = get_settings()
