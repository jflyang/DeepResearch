"""集中配置 - 所有可配置项从 .env 读取，业务代码通过 get_settings() 获取。"""

import json
import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# 基于本文件位置解析项目根目录，确保无论从哪里启动都能找到正确路径
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_SETTINGS_PATH = _PROJECT_ROOT / "config" / "runtime_settings.json"


def _load_runtime_settings() -> dict:
    """加载 runtime_settings.json（优先级高于 .env）。

    每次调用都从磁盘读取，不缓存，确保保存后立即可见。
    """
    if not _RUNTIME_SETTINGS_PATH.exists():
        return {}
    try:
        with open(_RUNTIME_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load runtime_settings.json: %s", e)
        return {}


def save_runtime_settings(section: str, data) -> None:
    """保存 runtime settings 的某个 section。

    使用原子写入：先写 .tmp 文件，再 rename，避免写入中断导致文件损坏。
    """
    current = _load_runtime_settings()
    current[section] = data
    _RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 原子写入
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(_RUNTIME_SETTINGS_PATH.parent),
        prefix=".runtime_settings_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(_RUNTIME_SETTINGS_PATH))
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === App ===
    app_env: str = "development"
    log_level: str = "INFO"

    # === Database ===
    database_url: str = "sqlite:///./data/research.db"

    # === Obsidian ===
    obsidian_vault_path: str = ""

    # === Search Provider Keys ===
    tavily_api_key: str = ""
    brave_api_key: str = ""
    google_books_api_key: str = ""

    # === LLM ===
    enable_llm: bool = True
    ollama_base_url: str = ""
    ollama_model: str = "qwen2.5:7b"
    ollama_default_model: str = "qwen3:8b"
    ollama_timeout_seconds: int = 120

    # === Cloud LLM ===
    enable_cloud_llm: bool = False
    cloud_llm_provider: str = "deepseek"
    cloud_llm_timeout_seconds: int = 120
    enable_deepseek: bool = False
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_default_model: str = "deepseek-chat"
    deepseek_timeout_seconds: int = 120
    enable_openai_compatible: bool = False
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_default_model: str = "gpt-4.1-mini"
    openai_compatible_api_key: str = ""
    openai_compatible_base_url: str = ""
    openai_compatible_default_model: str = ""
    openai_compatible_timeout_seconds: int = 120

    # === Active LLM Provider ===
    active_llm_provider: str = "ollama_lan"

    # === Search Defaults ===
    default_search_depth: int = 3
    default_result_limit: int = 10

    # === Provider Toggles ===
    enable_tavily: bool = True
    enable_brave: bool = True
    enable_google_books: bool = True

    # === Free Search Providers ===
    search_mode: str = "free_first"
    enable_searxng: bool = True
    searxng_base_url: str = ""
    searxng_timeout_seconds: int = 20
    enable_open_library: bool = True
    enable_crossref: bool = True
    crossref_mailto: str = ""
    crossref_timeout_seconds: int = 20
    enable_arxiv: bool = True
    arxiv_timeout_seconds: int = 20
    enable_wikipedia: bool = True
    wikipedia_language: str = "en"
    wikipedia_timeout_seconds: int = 20

    # === Scoring Weights ===
    scoring_authority_weight: float = 0.3
    scoring_relevance_weight: float = 0.4
    scoring_originality_weight: float = 0.2
    scoring_gossip_penalty: float = 0.1

    # === Computed Properties ===

    @property
    def tavily_available(self) -> bool:
        return self.enable_tavily and bool(self.tavily_api_key)

    @property
    def brave_available(self) -> bool:
        return self.enable_brave and bool(self.brave_api_key)

    @property
    def google_books_available(self) -> bool:
        return self.enable_google_books and bool(self.google_books_api_key)

    @property
    def searxng_available(self) -> bool:
        return self.enable_searxng and bool(self.searxng_base_url)

    @property
    def open_library_available(self) -> bool:
        return self.enable_open_library

    @property
    def crossref_available(self) -> bool:
        return self.enable_crossref

    @property
    def arxiv_available(self) -> bool:
        return self.enable_arxiv

    @property
    def wikipedia_available(self) -> bool:
        return self.enable_wikipedia

    @property
    def obsidian_configured(self) -> bool:
        return bool(self.obsidian_vault_path)

    @property
    def obsidian_path(self) -> Path:
        return Path(self.obsidian_vault_path) if self.obsidian_vault_path else Path("")

    @property
    def ollama_configured(self) -> bool:
        """Ollama 是否已配置（有 base_url）。"""
        return bool(self.ollama_base_url)

    @property
    def cloud_llm_configured(self) -> bool:
        """云端 LLM 是否已配置。"""
        if not self.enable_cloud_llm:
            return False
        provider = self.cloud_llm_provider
        if provider == "deepseek":
            return bool(self.deepseek_api_key and self.deepseek_base_url)
        elif provider == "openai":
            return bool(self.openai_api_key and self.openai_base_url)
        elif provider == "openai_compatible":
            return bool(self.openai_compatible_api_key and self.openai_compatible_base_url)
        return False

    @model_validator(mode="after")
    def _apply_runtime_overrides(self) -> "Settings":
        """从 runtime_settings.json 覆盖配置。"""
        runtime = _load_runtime_settings()

        # Ollama overrides
        ollama_rt = runtime.get("ollama", {})
        if ollama_rt.get("base_url"):
            self.ollama_base_url = ollama_rt["base_url"]
        if ollama_rt.get("default_model"):
            self.ollama_default_model = ollama_rt["default_model"]
        if ollama_rt.get("timeout_seconds"):
            self.ollama_timeout_seconds = int(ollama_rt["timeout_seconds"])

        # Cloud LLM overrides
        cloud_rt = runtime.get("cloud_llm", {})
        if "enabled" in cloud_rt:
            self.enable_cloud_llm = bool(cloud_rt["enabled"])
        if cloud_rt.get("provider"):
            self.cloud_llm_provider = cloud_rt["provider"]
        if cloud_rt.get("timeout_seconds"):
            self.cloud_llm_timeout_seconds = int(cloud_rt["timeout_seconds"])

        # Apply cloud provider-specific overrides from runtime
        cloud_provider = cloud_rt.get("provider", "")
        if cloud_provider == "deepseek":
            if cloud_rt.get("api_key"):
                self.deepseek_api_key = cloud_rt["api_key"]
            if cloud_rt.get("base_url"):
                self.deepseek_base_url = cloud_rt["base_url"]
            if cloud_rt.get("default_model"):
                self.deepseek_default_model = cloud_rt["default_model"]
        elif cloud_provider == "openai":
            if cloud_rt.get("api_key"):
                self.openai_api_key = cloud_rt["api_key"]
            if cloud_rt.get("base_url"):
                self.openai_base_url = cloud_rt["base_url"]
            if cloud_rt.get("default_model"):
                self.openai_default_model = cloud_rt["default_model"]
        elif cloud_provider == "openai_compatible":
            if cloud_rt.get("api_key"):
                self.openai_compatible_api_key = cloud_rt["api_key"]
            if cloud_rt.get("base_url"):
                self.openai_compatible_base_url = cloud_rt["base_url"]
            if cloud_rt.get("default_model"):
                self.openai_compatible_default_model = cloud_rt["default_model"]

        # Active provider override
        if runtime.get("active_provider"):
            self.active_llm_provider = runtime["active_provider"]

        # Search provider overrides
        search_rt = runtime.get("search", {})
        tavily_rt = search_rt.get("tavily", {})
        if "enabled" in tavily_rt:
            self.enable_tavily = bool(tavily_rt["enabled"])
        if tavily_rt.get("api_key"):
            self.tavily_api_key = tavily_rt["api_key"]

        brave_rt = search_rt.get("brave", {})
        if "enabled" in brave_rt:
            self.enable_brave = bool(brave_rt["enabled"])
        if brave_rt.get("api_key"):
            self.brave_api_key = brave_rt["api_key"]

        gb_rt = search_rt.get("google_books", {})
        if "enabled" in gb_rt:
            self.enable_google_books = bool(gb_rt["enabled"])
        if gb_rt.get("api_key"):
            self.google_books_api_key = gb_rt["api_key"]

        # Obsidian override
        obsidian_rt = runtime.get("obsidian", {})
        if obsidian_rt.get("vault_path"):
            self.obsidian_vault_path = obsidian_rt["vault_path"]

        return self

    @model_validator(mode="after")
    def _log_provider_status(self) -> "Settings":
        disabled = []
        if not self.tavily_available:
            disabled.append("tavily")
        if not self.brave_available:
            disabled.append("brave")
        if not self.google_books_available:
            disabled.append("google_books")
        if disabled:
            logger.info("providers_disabled providers=%s", ",".join(disabled))
        if not self.obsidian_configured:
            logger.info("obsidian_not_configured export_will_fail_without_path=true")
        return self

    @field_validator("scoring_authority_weight", "scoring_relevance_weight",
                     "scoring_originality_weight", "scoring_gossip_penalty")
    @classmethod
    def _validate_weight(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Weight must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("default_search_depth")
    @classmethod
    def _validate_depth(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError(f"Search depth must be 1-10, got {v}")
        return v

    @field_validator("default_result_limit")
    @classmethod
    def _validate_limit(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError(f"Result limit must be 1-100, got {v}")
        return v


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例。业务代码统一通过此函数获取配置。"""
    return Settings()


def reset_settings() -> None:
    """清除缓存，下次调用 get_settings() 时重新从磁盘加载。"""
    get_settings.cache_clear()
