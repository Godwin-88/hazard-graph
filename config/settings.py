"""HazardGraph — Pydantic BaseSettings loaded from .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "HazardGraph"
    app_version: str = "1.0.0"
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Neo4j
    neo4j_uri: str = "neo4j+s://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # PostgreSQL
    postgres_dsn: str = "postgresql+asyncpg://user:pass@localhost:5432/hazardgraph"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()