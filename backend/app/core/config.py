"""Configuration. Invalid configuration must prevent boot, never degrade silently."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "staging", "production"] = "development"

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    vector_backend: Literal["qdrant", "pgvector"] = "qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "chunks"

    jwt_secret: str
    jwt_issuer: str = "rag-api"
    jwt_audience: str = "rag-web"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 604800

    embedding_provider: Literal["openai", "local"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    llm_model: str = "claude-sonnet-4-6"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Accuracy pipeline. Each stage is independently switchable so its
    # contribution can be measured rather than assumed.
    enable_query_rewrite: bool = True
    enable_hybrid_search: bool = True
    enable_rerank: bool = True
    enable_verification: bool = True
    rerank_model: str = "BAAI/bge-reranker-base"
    retrieve_candidates: int = 40      # pre-rerank width, all permitted
    top_k: int = 5                     # post-rerank chunks sent to the model
    rrf_k: int = 60                    # reciprocal rank fusion constant
    mmr_lambda: float = 0.7            # 1.0 = pure relevance, 0.0 = pure diversity
    context_token_budget: int = 6000
    min_rerank_score: float = 0.05     # below this, treat as no usable context

    chunk_size_tokens: int = 600
    chunk_overlap_tokens: int = 80

    debug_trace: bool = False
    cors_origins: str = "http://localhost:3000"

    @field_validator("jwt_secret")
    @classmethod
    def _secret_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def assert_safe_for_env(self) -> None:
        """Called at startup. Exits the process rather than starting unsafely."""
        if self.env == "production":
            if self.debug_trace:
                raise SystemExit("DEBUG_TRACE must be false in production")
            if "null" in self.cors_list:
                raise SystemExit("CORS origin 'null' (file://) is development only")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
