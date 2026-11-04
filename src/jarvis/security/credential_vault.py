"""Credentials are encrypted for the current Windows user, never kept in memory DBs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


class CredentialVault:
    def __init__(self, directory: Path | None = None) -> None:
        self.path = directory / "connections.dpapi" if directory else None
        self._lock = RLock()
        self._memory: dict[str, Any] = {}

    def _read(self) -> dict[str, Any]:
        if self.path is None:
            return dict(self._memory)
        if not self.path.exists():
            return {}
        if os.name != "nt":
            raise RuntimeError("Persistent connection storage currently requires Windows.")
        import win32crypt
        try:
            raw = win32crypt.CryptUnprotectData(self.path.read_bytes(), None, None, None, 1)[1]
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise TypeError("Invalid connection storage")
            return value
        except Exception as exc:
            raise RuntimeError("Saved connections could not be unlocked by this Windows account.") from exc

    def get(self, name: str) -> dict[str, Any]:
        with self._lock:
            return self._read().get(name, {}).copy()

    def set(self, name: str, value: dict[str, Any]) -> None:
        with self._lock:
            data = self._read()
            data[name] = value
            if self.path is None:
                self._memory = data
                return
            if os.name != "nt":
                raise RuntimeError("Persistent connection storage currently requires Windows.")
            import win32crypt
            self.path.parent.mkdir(parents=True, exist_ok=True)
            encrypted = win32crypt.CryptProtectData(json.dumps(data).encode(), "JARVIS connections", None, None, None, 1)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_bytes(encrypted)
            os.replace(temporary, self.path)
