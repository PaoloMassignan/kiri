from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError, field_validator, model_validator


class ConfigError(Exception):
    pass


class Settings(BaseModel):
    similarity_threshold: float = 0.75
    hard_block_threshold: float = 0.90
    action: Literal["block", "sanitize"] = "sanitize"
    proxy_port: int = 8765
    ollama_model: str = "qwen2.5:3b"
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "all-MiniLM-L6-v2"
    workspace: Path = Path()
    # Minimum symbol name length used as fallback when Ollama is unavailable.
    # When Ollama is available, filter_symbols() makes the real classification
    # and this threshold only acts as a noise gate (removes 1–3 char tokens).
    # Raise this value if the fallback produces too many false positives.
    symbol_min_length: int = 9
    openai_upstream_url: str = "https://api.openai.com"
    audit_max_bytes: int = 10 * 1024 * 1024   # 10 MB; 0 = no rotation
    audit_backup_count: int = 5               # keep up to 5 rotated files
    rate_limit_rpm: int = 0                   # requests/minute per key; 0 = disabled
    ollama_timeout_seconds: float = 10.0      # L3 classifier request timeout
    # LocalLLM backend: "ollama" (Docker distribution) or "llama_cpp" (native distribution)
    llm_backend: Literal["ollama", "llama_cpp"] = "ollama"
    # Path to the GGUF model file — required when llm_backend = "llama_cpp"
    llm_model_path: str = "/var/lib/kiri/models/qwen2.5-3b-q4.gguf"
    # llama-cpp-python tuning (only used when llm_backend = "llama_cpp")
    llm_n_ctx: int = 2048         # context window in tokens
    llm_n_threads: int = 0        # CPU threads; 0 = auto (os.cpu_count())
    llm_n_gpu_layers: int = 0     # GPU layers; 0 = CPU-only, -1 = all layers on GPU
    # When True, requests carrying an Anthropic sk-ant- token are accepted and
    # forwarded with the original token. Bypass-prevention does not apply.
    # See REQ-S-010 and US-16.
    oauth_passthrough: bool = False

    @field_validator("similarity_threshold", "hard_block_threshold")
    @classmethod
    def _threshold_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")
        return v

    @field_validator("proxy_port")
    @classmethod
    def _port_in_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return v

    @model_validator(mode="after")
    def _hard_block_gte_similarity(self) -> Settings:
        if self.hard_block_threshold < self.similarity_threshold:
            raise ValueError("hard_block_threshold must be >= similarity_threshold")
        return self

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        # WORKSPACE env var overrides the default current-directory workspace.
        # Set by docker-compose to /workspace (the volume mount); harmless when
        # running locally (env var not set → falls back to CWD).
        workspace = Path(os.environ.get("WORKSPACE", "."))

        if config_path is None:
            env = os.environ.get("KIRI_CONFIG")
            config_path = Path(env) if env else workspace / ".kiri" / "config.yaml"

        if not config_path.exists():
            # Allow key settings to be overridden via env vars when no config file exists.
            # Used by docker-compose to point the container at the internal Ollama service.
            extra: dict[str, str] = {}
            if ollama_url := os.environ.get("OLLAMA_BASE_URL"):
                extra["ollama_base_url"] = ollama_url
            return cls(workspace=workspace, **extra)  # type: ignore[arg-type]

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        raw.setdefault("workspace", str(workspace))

        try:
            return cls(**raw)
        except (ValidationError, TypeError) as exc:
            raise ConfigError(f"invalid config at {config_path}: {exc}") from exc
