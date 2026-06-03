"""Direct X API client for OAuth-backed timeline reads."""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from kodiak.errors import ConfigurationError
from kodiak.signals.models import SourceItem
from kodiak.signals.x_auth import XOAuthCredentials, save_x_oauth_credentials

HOME_TIMELINE_URL = "https://api.x.com/2/users/{user_id}/timelines/reverse_chronological"
TOKEN_URL = "https://api.x.com/2/oauth2/token"


class XApiClient:
    """Minimal X API client for reading the authenticated user's home timeline."""

    def __init__(self, credentials: XOAuthCredentials) -> None:
        self.credentials = credentials

    def refresh_if_needed(self) -> XOAuthCredentials:
        if not self.credentials.expires_soon():
            return self.credentials
        if not self.credentials.refresh_token:
            return self.credentials
        self.credentials = self.refresh_access_token()
        return self.credentials

    def fetch_home_timeline(self, max_results: int = 20) -> list[SourceItem]:
        credentials = self.refresh_if_needed()
        response = requests.get(
            HOME_TIMELINE_URL.format(user_id=credentials.x_user_id),
            headers={"Authorization": f"Bearer {credentials.access_token}"},
            params={
                "max_results": max_results,
                "expansions": "author_id",
                "tweet.fields": "created_at",
                "user.fields": "username,name",
            },
            timeout=20,
        )
        if response.status_code == 401 and credentials.refresh_token:
            credentials = self.refresh_access_token()
            response = requests.get(
                HOME_TIMELINE_URL.format(user_id=credentials.x_user_id),
                headers={"Authorization": f"Bearer {credentials.access_token}"},
                params={
                    "max_results": max_results,
                    "expansions": "author_id",
                    "tweet.fields": "created_at",
                    "user.fields": "username,name",
                },
                timeout=20,
            )
        response.raise_for_status()
        payload = response.json()
        authors = {
            user["id"]: user
            for user in payload.get("includes", {}).get("users", [])
            if isinstance(user, dict) and user.get("id")
        }

        items: list[SourceItem] = []
        for post in payload.get("data", []):
            author = authors.get(post.get("author_id"), {})
            created_at = datetime.fromisoformat(
                str(post.get("created_at")).replace("Z", "+00:00")
            ).astimezone(UTC)
            username = str(author.get("username") or credentials.username)
            post_id = str(post["id"])
            items.append(
                SourceItem(
                    external_id=post_id,
                    url=f"https://x.com/{username}/status/{post_id}",
                    published_at=created_at,
                    author=username,
                    text=str(post.get("text") or ""),
                )
            )
        return items

    def refresh_access_token(self) -> XOAuthCredentials:
        if not self.credentials.refresh_token:
            raise ConfigurationError(
                message="No X refresh token is available",
                code="X_REFRESH_TOKEN_MISSING",
            )

        form = {
            "refresh_token": self.credentials.refresh_token,
            "grant_type": "refresh_token",
            "client_id": self.client_id(),
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        if self.client_secret():
            headers["Authorization"] = self.basic_auth_header()
        response = requests.post(TOKEN_URL, data=form, headers=headers, timeout=20)
        response.raise_for_status()
        payload = response.json()
        credentials = save_x_oauth_credentials(
            x_user_id=self.credentials.x_user_id,
            username=self.credentials.username,
            access_token=str(payload["access_token"]),
            refresh_token=str(payload.get("refresh_token") or self.credentials.refresh_token),
            token_type=str(payload.get("token_type") or self.credentials.token_type),
            scope=str(payload.get("scope") or self.credentials.scope),
            expires_in=payload.get("expires_in"),
        )
        return credentials

    @staticmethod
    def client_id() -> str:
        value = os.getenv("X_CLIENT_ID", "").strip()
        if not value:
            raise ConfigurationError(
                message="X_CLIENT_ID is not configured on Kodiak",
                code="X_CLIENT_ID_MISSING",
            )
        return value

    @staticmethod
    def client_secret() -> str:
        return os.getenv("X_CLIENT_SECRET", "").strip()

    @classmethod
    def basic_auth_header(cls) -> str:
        encoded = base64.b64encode(f"{cls.client_id()}:{cls.client_secret()}".encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"

