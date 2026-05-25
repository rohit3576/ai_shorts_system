"""Google/YouTube OAuth helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


class YouTubeAuth:
    """Lazy OAuth credential loader for YouTube APIs."""

    def credentials(self) -> Any:
        """Return authorized Google credentials, creating a token when needed."""

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        token_file = settings.resolve_path(settings.youtube_token_file)
        client_secret_file = settings.resolve_path(settings.youtube_client_secret_file)
        creds = None

        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds or not creds.valid:
            if not client_secret_file.exists():
                raise FileNotFoundError(
                    f"YouTube client secret file not found at {client_secret_file}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), SCOPES)
            creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def build(self, service_name: str, version: str) -> Any:
        """Build a Google API service client."""

        from googleapiclient.discovery import build

        return build(service_name, version, credentials=self.credentials(), cache_discovery=False)

