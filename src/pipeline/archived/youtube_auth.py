"""YouTube authentication with per-channel token storage.

Supports multiple YouTube channels with separate token files for each channel.
"""

from pathlib import Path

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = structlog.get_logger()


class YouTubeAuth:
    """YouTube API authentication with per-channel token support."""

    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

    def __init__(self, channel_name: str, client_secrets_file: Path, token_dir: Path):
        """Initialize YouTube authentication for a specific channel.

        Args:
            channel_name: Channel name (e.g., 'pycon', 'pydata')
            client_secrets_file: Path to OAuth2 client secrets JSON
            token_dir: Directory to store channel-specific tokens
        """
        self.channel_name = channel_name
        self.client_secrets_file = client_secrets_file
        self.token_dir = Path(token_dir)
        self.token_dir.mkdir(parents=True, exist_ok=True)
        self.token_path = self.token_dir / f"token_{channel_name}.json"
        self._service = None

    @property
    def service(self):
        """Get authenticated YouTube API service (lazy initialization).

        Returns:
            Authenticated YouTube API v3 service
        """
        if not self._service:
            self._service = self._get_authenticated_service()
        return self._service

    def _get_authenticated_service(self):
        """Authenticate and return YouTube API service.

        Handles token storage, refresh, and OAuth2 flow.

        Returns:
            Authenticated YouTube API v3 service
        """
        creds = None

        # Load existing token if available
        if self.token_path.exists():
            logger.info(
                "loading_token",
                channel=self.channel_name,
                token_path=str(self.token_path),
            )
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.SCOPES)

        # Refresh expired tokens or initiate new OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("refreshing_token", channel=self.channel_name)
                creds.refresh(Request())
            else:
                logger.info(
                    "starting_oauth_flow",
                    channel=self.channel_name,
                    message=f"Please authenticate with {self.channel_name} channel credentials in the browser window",
                )
                flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secrets_file), self.SCOPES)
                creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with self.token_path.open("w") as token_file:
                token_file.write(creds.to_json())
            logger.info("saved_token", channel=self.channel_name, token_path=str(self.token_path))

        # Build and return service
        service = build("youtube", "v3", credentials=creds)
        logger.info("authenticated", channel=self.channel_name)
        return service

    def update_video(self, video_body: dict) -> dict:
        """Update a video's metadata.

        Args:
            video_body: YouTube API request body (with 'id', 'snippet', 'status')

        Returns:
            API response dict

        Raises:
            googleapiclient.errors.HttpError: On API errors
        """
        request = self.service.videos().update(part="snippet,status", body=video_body)
        response = request.execute()
        return response
