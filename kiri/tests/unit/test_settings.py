from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# --- helpers ------------------------------------------------------------------


def write_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data), encoding="utf-8")


# --- defaults -----------------------------------------------------------------


def test_settings_missing_file_returns_defaults(tmp_path: Path) -> None:
    from src.config.settings import Settings

    s = Settings.load(config_path=tmp_path / ".kiri" / "config.yaml")

    assert s.similarity_threshold == 0.75
    assert s.hard_block_threshold == 0.90
    assert s.action == "sanitize"
    assert s.proxy_port == 8765
    assert s.ollama_model == "qwen2.5:3b"
    assert s.embedding_model == "all-MiniLM-L6-v2"


def test_settings_loads_values_from_file(tmp_path: Path) -> None:
    from src.config.settings import Settings

    config_path = tmp_path / ".kiri" / "config.yaml"
    write_config(config_path, {
        "similarity_threshold": 0.80,
        "hard_block_threshold": 0.95,
        "action": "sanitize",
        "proxy_port": 9000,
        "ollama_model": "llama3.2:3b",
        "embedding_model": "all-mpnet-base-v2",
    })

    s = Settings.load(config_path=config_path)

    assert s.similarity_threshold == 0.80
    assert s.hard_block_threshold == 0.95
    assert s.action == "sanitize"
    assert s.proxy_port == 9000
    assert s.ollama_model == "llama3.2:3b"
    assert s.embedding_model == "all-mpnet-base-v2"


def test_settings_partial_file_fills_missing_with_defaults(tmp_path: Path) -> None:
    from src.config.settings import Settings

    config_path = tmp_path / ".kiri" / "config.yaml"
    write_config(config_path, {"proxy_port": 9999})

    s = Settings.load(config_path=config_path)

    assert s.proxy_port == 9999
    assert s.similarity_threshold == 0.75  # default
    assert s.action == "sanitize"          # default


# --- validation ---------------------------------------------------------------


def test_settings_invalid_action_raises_config_error(tmp_path: Path) -> None:
    from src.config.settings import ConfigError, Settings

    config_path = tmp_path / ".kiri" / "config.yaml"
    write_config(config_path, {"action": "explode"})

    with pytest.raises(ConfigError):
        Settings.load(config_path=config_path)


def test_settings_similarity_threshold_above_1_raises_config_error(tmp_path: Path) -> None:
    from src.config.settings import ConfigError, Settings

    config_path = tmp_path / ".kiri" / "config.yaml"
    write_config(config_path, {"similarity_threshold": 1.5})

    with pytest.raises(ConfigError):
        Settings.load(config_path=config_path)


def test_settings_hard_block_below_similarity_raises_config_error(tmp_path: Path) -> None:
    # hard_block must be >= similarity_threshold
    from src.config.settings import ConfigError, Settings

    config_path = tmp_path / ".kiri" / "config.yaml"
    write_config(config_path, {"similarity_threshold": 0.80, "hard_block_threshold": 0.70})

    with pytest.raises(ConfigError):
        Settings.load(config_path=config_path)


def test_settings_proxy_port_out_of_range_raises_config_error(tmp_path: Path) -> None:
    from src.config.settings import ConfigError, Settings

    config_path = tmp_path / ".kiri" / "config.yaml"
    write_config(config_path, {"proxy_port": 99999})

    with pytest.raises(ConfigError):
        Settings.load(config_path=config_path)


# --- env var override ---------------------------------------------------------


def test_settings_env_var_overrides_default_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.config.settings import Settings

    config_path = tmp_path / "custom_config.yaml"
    write_config(config_path, {"proxy_port": 1234})
    monkeypatch.setenv("KIRI_CONFIG", str(config_path))

    s = Settings.load()

    assert s.proxy_port == 1234
