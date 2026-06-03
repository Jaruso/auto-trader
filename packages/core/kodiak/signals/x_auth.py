"""Encrypted storage for X OAuth credentials used by the signal monitor."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from kodiak.errors import ConfigurationError
from kodiak.signals.store import get_signals_data_dir

X_AUTH_FILENAME = "x_oauth.json"


@dataclass
class XOAuthCredentials:
    """Persisted X OAuth credentials."""

    x_user_id: str
    username: str
    access_token: str
    refresh_token: str | None
    token_type: str
    scope: str
    expires_at: datetime | None
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "x_user_id": self.x_user_id,
            "username": self.username,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "scope": self.scope,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "XOAuthCredentials":
        return cls(
            x_user_id=str(payload["x_user_id"]),
            username=str(payload["username"]),
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token"),
            token_type=str(payload.get("token_type") or "bearer"),
            scope=str(payload.get("scope") or ""),
            expires_at=_parse_dt(payload.get("expires_at")),
            updated_at=_parse_dt(payload.get("updated_at")) or datetime.now(UTC),
        )

    def expires_soon(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= datetime.now(UTC) + timedelta(minutes=2)


def save_x_oauth_credentials(
    *,
    x_user_id: str,
    username: str,
    access_token: str,
    refresh_token: str | None,
    token_type: str,
    scope: str,
    expires_in: int | None,
    data_dir: Path | None = None,
) -> XOAuthCredentials:
    """Encrypt and persist X OAuth credentials."""
    credentials = XOAuthCredentials(
        x_user_id=x_user_id,
        username=username,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type or "bearer",
        scope=scope or "",
        expires_at=(
            datetime.now(UTC) + timedelta(seconds=int(expires_in))
            if expires_in not in (None, "", 0)
            else None
        ),
        updated_at=datetime.now(UTC),
    )
    path = _path(data_dir)
    payload = _fernet().encrypt(json.dumps(credentials.to_dict()).encode("utf-8"))
    path.write_bytes(payload)
    return credentials


def load_x_oauth_credentials(data_dir: Path | None = None) -> XOAuthCredentials | None:
    """Load and decrypt stored X OAuth credentials."""
    path = _path(data_dir)
    if not path.is_file():
        return None
    try:
        payload = _fernet().decrypt(path.read_bytes())
    except InvalidToken as exc:
        raise ConfigurationError(
            message="Stored X OAuth credentials could not be decrypted",
            code="X_OAUTH_DECRYPT_FAILED",
            suggestion=(
                "Reconnect X or restore the previous KODIAK_SIGNAL_ENCRYPTION_SECRET / "
                "KODIAK_API_TOKEN used to encrypt the stored credentials."
            ),
        ) from exc
    data = json.loads(payload.decode("utf-8"))
    return XOAuthCredentials.from_dict(data)


def delete_x_oauth_credentials(data_dir: Path | None = None) -> bool:
    """Delete persisted X OAuth credentials."""
    path = _path(data_dir)
    if not path.exists():
        return False
    path.unlink()
    return True


def x_oauth_status(data_dir: Path | None = None) -> dict[str, Any]:
    """Return non-secret X OAuth connection status."""
    credentials = load_x_oauth_credentials(data_dir)
    if credentials is None:
        return {"connected": False}
    return {
        "connected": True,
        "x_user_id": credentials.x_user_id,
        "username": credentials.username,
        "scope": credentials.scope,
        "expires_at": credentials.expires_at.isoformat() if credentials.expires_at else None,
        "updated_at": credentials.updated_at.isoformat(),
    }


def _path(data_dir: Path | None = None) -> Path:
    return get_signals_data_dir(data_dir) / X_AUTH_FILENAME


def _fernet() -> Fernet:
    secret = (
        os.getenv("KODIAK_SIGNAL_ENCRYPTION_SECRET", "").strip()
        or os.getenv("KODIAK_API_TOKEN", "").strip()
    )
    if not secret:
        raise ConfigurationError(
            message="KODIAK_SIGNAL_ENCRYPTION_SECRET or KODIAK_API_TOKEN is required to store X OAuth credentials",
            code="X_OAUTH_ENCRYPTION_KEY_MISSING",
        )
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
