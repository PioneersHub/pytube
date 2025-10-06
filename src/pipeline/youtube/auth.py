"""YouTube authentication for single-channel access.

Simplified authentication focusing on single channel operations.
"""

from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import structlog

logger = structlog.get_logger()


class YouTubeAuth:
    """YouTube API authentication for a single channel."""

    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

    def __init__(self, client_secrets_file: Path, token_path: Optional[Path] = None):
        """Initialize YouTube authentication.

        Args:
            client_secrets_file: Path to OAuth2 client secrets JSON
            token_path: Path to store token (defaults to .secrets/youtube_token.json)
        """
        self.client_secrets_file = Path(client_secrets_file)

        if token_path is None:
            token_dir = self.client_secrets_file.parent / ".secrets"
            token_dir.mkdir(parents=True, exist_ok=True)
            self.token_path = token_dir / "youtube_token.json"
        else:
            self.token_path = Path(token_path)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)

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
                token_path=str(self.token_path),
            )
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.SCOPES)

        # Refresh expired tokens or initiate new OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("refreshing_token")
                creds.refresh(Request())
            else:
                logger.info(
                    "starting_oauth_flow",
                    message="Please authenticate with YouTube channel credentials in the browser window",
                )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secrets_file),
                    self.SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with self.token_path.open("w") as token_file:
                token_file.write(creds.to_json())
            logger.info("saved_token", token_path=str(self.token_path))

        # Build and return service
        service = build("youtube", "v3", credentials=creds)
        logger.info("authenticated")
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

    def get_video(self, video_id: str) -> dict:
        """Get video details.

        Args:
            video_id: YouTube video ID

        Returns:
            Video resource dict

        Raises:
            googleapiclient.errors.HttpError: On API errors
        """
        request = self.service.videos().list(
            part="snippet,status",
            id=video_id
        )
        response = request.execute()

        if response.get("items"):
            return response["items"][0]
        else:
            raise ValueError(f"Video not found: {video_id}")

    def list_playlist_videos(self, playlist_id: str, max_results: int = 50) -> list[dict]:
        """List all videos in a playlist.

        Args:
            playlist_id: YouTube playlist ID
            max_results: Maximum results per page (default 50)

        Returns:
            List of video items

        Raises:
            googleapiclient.errors.HttpError: On API errors
        """
        videos = []
        next_page_token = None

        while True:
            request = self.service.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=max_results,
                pageToken=next_page_token
            )
            response = request.execute()

            videos.extend(response.get("items", []))

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info("fetched_playlist_videos", count=len(videos), playlist_id=playlist_id)
        return videos