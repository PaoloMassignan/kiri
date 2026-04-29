from __future__ import annotations

from pathlib import Path

import pytest


def make_store(tmp_path: Path):
    from src.store.secrets_store import SecretsStore

    workspace = tmp_path / "project"
    workspace.mkdir()
    gateway_dir = workspace / ".kiri"
    gateway_dir.mkdir()
    secrets_file = gateway_dir / "secrets"
    secrets_file.write_text("", encoding="utf-8")
    return SecretsStore(secrets_path=secrets_file, workspace=workspace)


def test_path_traversal_dotdot_raises(tmp_path: Path) -> None:
    from src.store.secrets_store import PathTraversalError

    store = make_store(tmp_path)
    evil = tmp_path / "project" / ".." / ".." / "etc" / "passwd"

    with pytest.raises(PathTraversalError):
        store.add_path(evil)


def test_path_traversal_absolute_outside_workspace_raises(tmp_path: Path) -> None:
    from src.store.secrets_store import PathTraversalError

    store = make_store(tmp_path)
    evil = Path("/etc/passwd")

    with pytest.raises(PathTraversalError):
        store.add_path(evil)


def test_path_traversal_symlink_outside_workspace_raises(tmp_path: Path) -> None:
    from src.store.secrets_store import PathTraversalError

    store = make_store(tmp_path)

    # create a file outside the workspace
    outside = tmp_path / "outside.py"
    outside.touch()

    # create a symlink inside the workspace pointing outside
    link = tmp_path / "project" / "src" / "evil_link.py"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)

    with pytest.raises(PathTraversalError):
        store.add_path(link)


def test_path_inside_workspace_does_not_raise(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    safe = tmp_path / "project" / "src" / "engine.py"
    safe.parent.mkdir(parents=True, exist_ok=True)
    safe.touch()

    store.add_path(safe)  # must not raise

    assert safe in store.list_paths()


def test_path_traversal_in_secrets_file_is_rejected_on_load(tmp_path: Path) -> None:
    from src.store.secrets_store import PathTraversalError, SecretsStore

    workspace = tmp_path / "project"
    workspace.mkdir()
    gateway_dir = workspace / ".kiri"
    gateway_dir.mkdir()
    secrets_file = gateway_dir / "secrets"
    # manually write a traversal path into secrets
    secrets_file.write_text("../../etc/passwd\n", encoding="utf-8")

    store = SecretsStore(secrets_path=secrets_file, workspace=workspace)

    with pytest.raises(PathTraversalError):
        store.list_paths()
