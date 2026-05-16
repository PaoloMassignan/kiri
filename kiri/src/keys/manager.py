from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

_KEY_FILE = "gateway_keys.json"
_logger = logging.getLogger(__name__)
_KEY_PREFIX = "kr-"
_DEFAULT_SECRETS_DIR = Path("/run/secrets")

_PROTOCOL_SECRET: dict[str, str] = {
    "anthropic": "anthropic_key",
    "openai": "openai_key",
}
_PROTOCOL_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


@dataclass
class KeyInfo:
    key: str
    created_at: str        # ISO 8601 UTC
    expires_at: str | None  # ISO 8601 UTC, None = never expires


class MissingUpstreamKeyError(Exception):
    pass


class KeyManager:
    def __init__(
        self,
        keys_dir: Path,
        secrets_dir: Path = _DEFAULT_SECRETS_DIR,
    ) -> None:
        self._keys_dir = keys_dir
        self._key_file = keys_dir / _KEY_FILE
        self._secrets_dir = secrets_dir
        self._lock = threading.Lock()
        keys_dir.mkdir(parents=True, exist_ok=True)
        try:
            keys_dir.chmod(0o700)  # owner-only: prevent other local users from reading keys
        except NotImplementedError:
            _logger.warning(
                "keys_manager: chmod(0o700) is not supported on this platform; "
                "key file permissions are not restricted"
            )

    def create_key(self, expires_in_days: int | None = None) -> str:
        """Create a new gateway key.

        Args:
            expires_in_days: If set, the key expires after this many days.
                             None (default) creates a non-expiring key.
        """
        key = _KEY_PREFIX + secrets.token_urlsafe(24)
        now = datetime.now(tz=UTC)
        expires_at: str | None = None
        if expires_in_days is not None and expires_in_days > 0:
            expires_at = (now + timedelta(days=expires_in_days)).isoformat(timespec="seconds")
        with self._lock:
            data = self._load_raw()
            data[key] = {
                "created_at": now.isoformat(timespec="seconds"),
                "expires_at": expires_at,
            }
            self._save_raw(data)
        return key

    def is_valid(self, key: str) -> bool:
        data = self._load_raw()
        if key not in data:
            return False
        expires_at = data[key].get("expires_at")
        if expires_at is None:
            return True
        return datetime.fromisoformat(expires_at) > datetime.now(tz=UTC)

    def is_oauth_token(self, key: str) -> bool:
        """Return True if key is an Anthropic token (sk-ant- prefix), not a kr- key."""
        return key.startswith("sk-ant-")

    def get_upstream_key(self, protocol: str = "anthropic") -> str:
        # Tier 0: explicit file path via env var — used by the native distribution.
        # The systemd/launchd/Windows service sets KIRI_UPSTREAM_KEY_FILE to
        # /var/lib/kiri/upstream.key (owned by the kiri service account, mode 600).
        if env_path := os.environ.get("KIRI_UPSTREAM_KEY_FILE"):
            p = Path(env_path)
            if p.exists():
                value = p.read_text(encoding="utf-8").strip()
                if value:
                    return value

        # Tier 1: Docker secret (not visible via `docker inspect`)
        secret_name = _PROTOCOL_SECRET.get(protocol, "anthropic_key")
        secret_file = self._secrets_dir / secret_name
        if secret_file.exists():
            value = secret_file.read_text(encoding="utf-8").strip()
            if value:
                return value

        # Local dev: read from .kiri/upstream.key (sibling of keys/ dir)
        local_key_file = self._keys_dir.parent / "upstream.key"
        if local_key_file.exists():
            value = local_key_file.read_text(encoding="utf-8").strip()
            if value:
                return value

        # Fallback: env var (local dev without Docker)
        env_var = _PROTOCOL_ENV.get(protocol, "ANTHROPIC_API_KEY")
        value = os.environ.get(env_var, "")
        if not value:
            raise MissingUpstreamKeyError(f"{env_var} is not set")
        return value

    def list_keys(self) -> list[str]:
        """Return active (non-expired) keys, sorted."""
        now = datetime.now(tz=UTC)
        return sorted(
            k
            for k, meta in self._load_raw().items()
            if meta.get("expires_at") is None
            or datetime.fromisoformat(str(meta["expires_at"])) > now
        )

    def list_key_infos(self) -> list[KeyInfo]:
        """Return KeyInfo for all keys including expired ones, sorted by key."""
        return sorted(
            [
                KeyInfo(
                    key=k,
                    created_at=meta.get("created_at") or "",
                    expires_at=meta.get("expires_at"),
                )
                for k, meta in self._load_raw().items()
            ],
            key=lambda i: i.key,
        )

    def revoke_key(self, key: str) -> bool:
        with self._lock:
            data = self._load_raw()
            if key not in data:
                return False
            del data[key]
            self._save_raw(data)
        return True

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------

    def _load_raw(self) -> dict[str, dict[str, str | None]]:
        if not self._key_file.exists():
            return {}
        content = json.loads(self._key_file.read_text(encoding="utf-8-sig"))
        # Migrate from old format (JSON array of strings)
        if isinstance(content, list):
            return {k: {"created_at": "", "expires_at": None} for k in content}
        return content  # type: ignore[no-any-return]

    def _save_raw(self, data: dict[str, dict[str, str | None]]) -> None:
        fd, tmp = tempfile.mkstemp(dir=self._keys_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise
        Path(tmp).replace(self._key_file)
