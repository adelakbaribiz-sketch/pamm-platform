from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://pamm:pamm_dev_pw@localhost:5432/pamm"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-me"
    jwt_alg: str = "HS256"
    access_token_ttl_min: int = 60
    refresh_token_ttl_days: int = 7
    environment: str = "development"
    log_level: str = "INFO"
    default_tenant: str = "demo-broker"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

_WEAK_SECRETS = {"dev-secret-change-me", "change-me-in-production-please-use-a-long-random-string"}
if settings.environment.lower() == "production" and (
        settings.jwt_secret in _WEAK_SECRETS or len(settings.jwt_secret) < 32):
    raise RuntimeError("JWT_SECRET must be set to a strong (>=32 char) value when ENVIRONMENT=production")
