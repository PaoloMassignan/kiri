from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest

# --- construction -------------------------------------------------------------


def test_key_manager_constructs_without_error(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    assert km is not None


def test_key_manager_creates_keys_dir_if_missing(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    keys_dir = tmp_path / "nested" / "keys"
    KeyManager(keys_dir=keys_dir)

    assert keys_dir.exists()


# --- create_key ---------------------------------------------------------------


def test_create_key_returns_string(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    key = km.create_key()

    assert isinstance(key, str)


def test_create_key_has_gw_prefix(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    key = km.create_key()

    assert key.startswith("kr-")


def test_create_key_has_sufficient_length(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    key = km.create_key()

    # "kr-" + 32 chars from token_urlsafe(24)
    assert len(key) >= 35


def test_create_key_is_unique(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    keys = {km.create_key() for _ in range(10)}

    assert len(keys) == 10


def test_create_key_persists_to_disk(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key()

    km2 = KeyManager(keys_dir=tmp_path)

    assert km2.is_valid(key)


# --- is_valid -----------------------------------------------------------------


def test_is_valid_returns_true_for_created_key(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key()

    assert km.is_valid(key) is True


def test_is_valid_returns_false_for_unknown_key(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    assert km.is_valid("kr-nonexistent") is False


def test_is_valid_returns_false_before_any_keys_created(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    assert km.is_valid("kr-anything") is False


# --- list_keys ----------------------------------------------------------------


def test_list_keys_empty_initially(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    assert km.list_keys() == []


def test_list_keys_returns_created_key(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key()

    assert key in km.list_keys()


def test_list_keys_returns_all_keys(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    keys = [km.create_key() for _ in range(3)]

    listed = km.list_keys()

    assert sorted(listed) == sorted(keys)


def test_list_keys_is_sorted(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    for _ in range(5):
        km.create_key()

    listed = km.list_keys()

    assert listed == sorted(listed)


# --- revoke_key ---------------------------------------------------------------


def test_revoke_key_returns_true_for_existing_key(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key()

    assert km.revoke_key(key) is True


def test_revoke_key_returns_false_for_unknown_key(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    assert km.revoke_key("kr-nonexistent") is False


def test_revoke_key_removes_from_store(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key()
    km.revoke_key(key)

    assert km.is_valid(key) is False


def test_revoke_key_persists_removal(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key()
    km.revoke_key(key)

    km2 = KeyManager(keys_dir=tmp_path)

    assert km2.is_valid(key) is False


def test_revoke_key_leaves_other_keys_intact(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    k1 = km.create_key()
    k2 = km.create_key()
    km.revoke_key(k1)

    assert km.is_valid(k2) is True


# --- get_upstream_key ---------------------------------------------------------


def test_get_upstream_key_returns_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.keys.manager import KeyManager

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
    km = KeyManager(keys_dir=tmp_path)

    assert km.get_upstream_key() == "sk-ant-test123"


def test_get_upstream_key_raises_when_env_var_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.keys.manager import KeyManager, MissingUpstreamKeyError

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    km = KeyManager(keys_dir=tmp_path)

    with pytest.raises(MissingUpstreamKeyError):
        km.get_upstream_key()


def test_get_upstream_key_raises_when_env_var_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.keys.manager import KeyManager, MissingUpstreamKeyError

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    km = KeyManager(keys_dir=tmp_path)

    with pytest.raises(MissingUpstreamKeyError):
        km.get_upstream_key()


def test_get_upstream_key_reads_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.keys.manager import KeyManager

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-first")
    km = KeyManager(keys_dir=tmp_path)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-second")

    assert km.get_upstream_key() == "sk-ant-second"


# --- Docker secret file -------------------------------------------------------


def test_get_upstream_key_reads_from_secret_file(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "anthropic_key").write_text("sk-ant-fromsecret\n", encoding="utf-8")

    km = KeyManager(keys_dir=tmp_path, secrets_dir=secrets_dir)

    assert km.get_upstream_key() == "sk-ant-fromsecret"


def test_get_upstream_key_secret_takes_priority_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.keys.manager import KeyManager

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fromenv")
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "anthropic_key").write_text("sk-ant-fromsecret", encoding="utf-8")

    km = KeyManager(keys_dir=tmp_path, secrets_dir=secrets_dir)

    assert km.get_upstream_key() == "sk-ant-fromsecret"


def test_get_upstream_key_falls_back_to_env_when_no_secret_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.keys.manager import KeyManager

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fromenv")
    km = KeyManager(keys_dir=tmp_path, secrets_dir=tmp_path / "nosecrets")

    assert km.get_upstream_key() == "sk-ant-fromenv"


def test_get_upstream_key_empty_secret_file_falls_back_to_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.keys.manager import KeyManager

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fromenv")
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "anthropic_key").write_text("   \n", encoding="utf-8")

    km = KeyManager(keys_dir=tmp_path, secrets_dir=secrets_dir)

    assert km.get_upstream_key() == "sk-ant-fromenv"


def test_get_upstream_key_openai_reads_correct_secret_file(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "openai_key").write_text("sk-openai-fromsecret", encoding="utf-8")

    km = KeyManager(keys_dir=tmp_path, secrets_dir=secrets_dir)

    assert km.get_upstream_key(protocol="openai") == "sk-openai-fromsecret"


# --- key expiry ---------------------------------------------------------------


def test_create_key_without_expiry_is_valid(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key()

    assert km.is_valid(key) is True


def test_create_key_with_future_expiry_is_valid(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key(expires_in_days=30)

    assert km.is_valid(key) is True


def test_create_key_with_past_expiry_is_invalid(tmp_path: Path) -> None:
    from datetime import datetime, timedelta
    from unittest.mock import patch

    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)

    # Create key with 1-day expiry, but advance clock by 2 days
    past = datetime.now(tz=UTC) - timedelta(days=2)
    with patch("src.keys.manager.datetime") as mock_dt:
        mock_dt.now.return_value = past
        mock_dt.fromisoformat = datetime.fromisoformat
        key = km.create_key(expires_in_days=1)

    assert km.is_valid(key) is False


def test_expired_key_not_in_list_keys(tmp_path: Path) -> None:
    from datetime import datetime, timedelta
    from unittest.mock import patch

    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    past = datetime.now(tz=UTC) - timedelta(days=2)

    with patch("src.keys.manager.datetime") as mock_dt:
        mock_dt.now.return_value = past
        mock_dt.fromisoformat = datetime.fromisoformat
        expired_key = km.create_key(expires_in_days=1)

    active_key = km.create_key()

    assert expired_key not in km.list_keys()
    assert active_key in km.list_keys()


def test_list_key_infos_includes_expired_keys(tmp_path: Path) -> None:
    from datetime import datetime, timedelta
    from unittest.mock import patch

    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    past = datetime.now(tz=UTC) - timedelta(days=2)

    with patch("src.keys.manager.datetime") as mock_dt:
        mock_dt.now.return_value = past
        mock_dt.fromisoformat = datetime.fromisoformat
        expired_key = km.create_key(expires_in_days=1)

    infos = km.list_key_infos()
    assert any(i.key == expired_key for i in infos)


def test_key_info_has_expires_at_when_set(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    km.create_key(expires_in_days=90)

    infos = km.list_key_infos()
    assert len(infos) == 1
    assert infos[0].expires_at is not None


def test_key_info_expires_at_none_when_not_set(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    km.create_key()

    infos = km.list_key_infos()
    assert infos[0].expires_at is None


def test_migration_from_old_list_format(tmp_path: Path) -> None:
    """Old gateway_keys.json (JSON array) must be migrated transparently."""
    import json

    from src.keys.manager import _KEY_FILE, KeyManager

    key_file = tmp_path / _KEY_FILE
    key_file.write_text(json.dumps(["kr-old1", "kr-old2"]), encoding="utf-8")

    km = KeyManager(keys_dir=tmp_path)

    assert km.is_valid("kr-old1") is True
    assert km.is_valid("kr-old2") is True
    assert "kr-old1" in km.list_keys()


def test_zero_expires_in_days_creates_non_expiring_key(tmp_path: Path) -> None:
    from src.keys.manager import KeyManager

    km = KeyManager(keys_dir=tmp_path)
    key = km.create_key(expires_in_days=0)

    assert km.is_valid(key) is True
    infos = km.list_key_infos()
    assert infos[0].expires_at is None
