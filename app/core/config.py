from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:
    BaseSettings = None
    SettingsConfigDict = None


def _read_dotenv_value(key: str) -> str | None:
    env_path = Path(".env")
    if not env_path.exists():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_key, env_value = stripped.split("=", 1)
        if env_key.strip() == key:
            return env_value.strip().strip('"').strip("'")
    return None


def _get_env(key: str, default: str = "") -> str:
    return os.getenv(key) or _read_dotenv_value(key) or default


class DeepSeekSettingsMixin:
    @property
    def is_deepseek_configured(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @property
    def llm_mode(self) -> str:
        return "deepseek" if self.is_deepseek_configured else "mock/fallback"

    @property
    def llm_status(self) -> str:
        if self.is_deepseek_configured:
            return "DeepSeek API key configured; live LLM calls are available."
        return "DEEPSEEK_API_KEY is not configured; using mock/fallback mode."

    @property
    def is_rag_enabled(self) -> bool:
        return str(self.rag_enabled).strip().lower() in {"1", "true", "yes", "on"}

    @property
    def is_doubao_configured(self) -> bool:
        return bool(self.doubao_api_key.strip())


if BaseSettings is not None:

    class Settings(DeepSeekSettingsMixin, BaseSettings):
        deepseek_api_key: str = Field(default="")
        deepseek_base_url: str = Field(default="https://api.deepseek.com")
        deepseek_model: str = Field(default="deepseek-chat")
        rag_enabled: str = Field(default="true")
        rag_embedding_model: str = Field(
            default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        rag_top_k: int = Field(default=5)
        rag_chunk_size: int = Field(default=800)
        rag_chunk_overlap: int = Field(default=120)
        doubao_api_key: str = Field(default="")
        doubao_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3")
        doubao_vision_model: str = Field(default="")
        mysql_host: str = Field(default="127.0.0.1")
        mysql_port: int = Field(default=3306)
        mysql_user: str = Field(default="root")
        mysql_password: str = Field(default="")
        mysql_database: str = Field(default="ai_data_workbench")
        mysql_charset: str = Field(default="utf8mb4")
        mysql_connect_timeout: int = Field(default=10)

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

else:

    class Settings(DeepSeekSettingsMixin, BaseModel):
        deepseek_api_key: str = Field(
            default_factory=lambda: _get_env("DEEPSEEK_API_KEY")
        )
        deepseek_base_url: str = Field(
            default_factory=lambda: _get_env(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            )
        )
        deepseek_model: str = Field(
            default_factory=lambda: _get_env("DEEPSEEK_MODEL", "deepseek-chat")
        )
        rag_enabled: str = Field(default_factory=lambda: _get_env("RAG_ENABLED", "true"))
        rag_embedding_model: str = Field(
            default_factory=lambda: _get_env(
                "RAG_EMBEDDING_MODEL",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            )
        )
        rag_top_k: int = Field(default_factory=lambda: int(_get_env("RAG_TOP_K", "5")))
        rag_chunk_size: int = Field(
            default_factory=lambda: int(_get_env("RAG_CHUNK_SIZE", "800"))
        )
        rag_chunk_overlap: int = Field(
            default_factory=lambda: int(_get_env("RAG_CHUNK_OVERLAP", "120"))
        )
        doubao_api_key: str = Field(default_factory=lambda: _get_env("DOUBAO_API_KEY"))
        doubao_base_url: str = Field(
            default_factory=lambda: _get_env(
                "DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
            )
        )
        doubao_vision_model: str = Field(default_factory=lambda: _get_env("DOUBAO_VISION_MODEL"))
        mysql_host: str = Field(default_factory=lambda: _get_env("MYSQL_HOST", "127.0.0.1"))
        mysql_port: int = Field(default_factory=lambda: int(_get_env("MYSQL_PORT", "3306")))
        mysql_user: str = Field(default_factory=lambda: _get_env("MYSQL_USER", "root"))
        mysql_password: str = Field(default_factory=lambda: _get_env("MYSQL_PASSWORD", ""))
        mysql_database: str = Field(default_factory=lambda: _get_env("MYSQL_DATABASE", "ai_data_workbench"))
        mysql_charset: str = Field(default_factory=lambda: _get_env("MYSQL_CHARSET", "utf8mb4"))
        mysql_connect_timeout: int = Field(default_factory=lambda: int(_get_env("MYSQL_CONNECT_TIMEOUT", "10")))


@lru_cache
def get_settings() -> Settings:
    return Settings()

