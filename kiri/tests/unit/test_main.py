from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.config.settings import Settings


def make_settings(tmp_path: Path) -> Settings:
    return Settings(workspace=tmp_path)


# --- construction -------------------------------------------------------------


def test_create_gateway_app_returns_fastapi(tmp_path: Path) -> None:
    from fastapi import FastAPI

    from src.main import create_gateway_app

    with patch("src.indexer.watcher.Watcher.start"):
        app = create_gateway_app(make_settings(tmp_path))

    assert isinstance(app, FastAPI)


def test_create_gateway_app_registers_messages_route(tmp_path: Path) -> None:
    from src.main import create_gateway_app

    with patch("src.indexer.watcher.Watcher.start"):
        app = create_gateway_app(make_settings(tmp_path))

    routes = [r.path for r in app.routes]  # type: ignore[attr-defined]
    assert "/v1/messages" in routes


def test_create_gateway_app_starts_watcher(tmp_path: Path) -> None:
    from src.main import create_gateway_app

    started: list[bool] = []

    with patch("src.indexer.watcher.Watcher.start", side_effect=lambda: started.append(True)):
        create_gateway_app(make_settings(tmp_path))

    assert started == [True]


def test_create_gateway_app_creates_secrets_file_if_missing(tmp_path: Path) -> None:
    from src.main import create_gateway_app

    secrets_path = tmp_path / ".kiri" / "secrets"
    assert not secrets_path.exists()

    with patch("src.indexer.watcher.Watcher.start"):
        create_gateway_app(make_settings(tmp_path))

    assert secrets_path.exists()


def test_create_gateway_app_uses_default_settings_when_none(tmp_path: Path) -> None:
    from fastapi import FastAPI

    from src.main import create_gateway_app

    with (
        patch("src.config.settings.Settings.load", return_value=make_settings(tmp_path)),
        patch("src.indexer.watcher.Watcher.start"),
    ):
        app = create_gateway_app()

    assert isinstance(app, FastAPI)


def test_create_gateway_app_idempotent(tmp_path: Path) -> None:
    """Two calls with same settings both return a FastAPI app."""
    from fastapi import FastAPI

    from src.main import create_gateway_app

    settings = make_settings(tmp_path)

    with patch("src.indexer.watcher.Watcher.start"):
        app1 = create_gateway_app(settings)
        app2 = create_gateway_app(settings)

    assert isinstance(app1, FastAPI)
    assert isinstance(app2, FastAPI)
