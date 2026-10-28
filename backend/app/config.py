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

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
