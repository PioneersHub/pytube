"""Vimeo API client for video operations.

Refactored from src/video_processor/vimeo_downloader.py with enhancements:
- Folder-based video listing
- Pattern-based filtering
- Robust error handling
- Best quality selection
"""

import re
import time
from datetime import datetime
from pathlib import Path

import requests
from tqdm import tqdm
from vimeo import VimeoClient as PyVimeoClient

from video_vimeo.models import PatternSelection, VimeoVideoInfo

# HTTP status codes
HTTP_OK = 200


class VimeoClient:
    """Vimeo API client with folder and pattern support."""

    def __init__(self, access_token: str, client_id: str | None = None, client_secret: str | None = None):
        """Initialize Vimeo client."""
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret

        # Initialize pyvimeo client
        if client_id and client_secret:
            self.client = PyVimeoClient(token=access_token, key=client_id, secret=client_secret)
        else:
            self.client = PyVimeoClient(token=access_token)

        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.vimeo.*+json;version=3.4",
        }
        self.api_base = "https://api.vimeo.com"

    def get_videos_in_folder(self, folder_id: str, user_id: str | None = None) -> list[VimeoVideoInfo]:
        """Get all videos in a Vimeo folder/project with pagination."""
        videos = []
        page = 1
        per_page = 100

        # Determine the URL based on whether user_id is provided
        if user_id:
            base_url = f"{self.api_base}/users/{user_id}/projects/{folder_id}/items"
        else:
            base_url = f"{self.api_base}/me/projects/{folder_id}/items"

        while True:
            params = {"page": page, "per_page": per_page}
            response = self.client.get(base_url, params=params)

            if response.status_code != HTTP_OK:
                raise RuntimeError(
                    f"Error fetching folder videos (page {page}): {response.status_code}\n{response.text}"
                )

            data = response.json()
            items = data.get("data", [])

            if not items:
                break

            # Extract video info from each item
            for item in items:
                # Items contain {"clip": {...}} for videos
                video_data = item.get("clip") or item
                if video_data:
                    try:
                        video_info = self._extract_video_info(video_data)
                        videos.append(video_info)
                    except Exception as e:
                        # Skip videos that can't be downloaded or parsed
                        video_name = video_data.get("name", "Unknown")
                        print(f"Skipping {video_name}: {e}")
                        continue

            # Check for next page
            paging = data.get("paging", {})
            if not paging.get("next"):
                break

            page += 1
            time.sleep(0.5)  # Rate limiting

        return videos

    def get_videos_by_pattern(self, pattern: PatternSelection, user_id: str | None = None) -> list[VimeoVideoInfo]:
        """Get all user videos filtered by pattern."""
        all_videos = []
        page = 1
        per_page = 100

        # Fetch all user videos
        url = f"{self.api_base}/users/{user_id}/videos" if user_id else f"{self.api_base}/me/videos"

        while True:
            params = {"page": page, "per_page": per_page}
            response = self.client.get(url, params=params)

            if response.status_code != HTTP_OK:
                raise RuntimeError(f"Error fetching videos (page {page}): {response.status_code}\n{response.text}")

            data = response.json()
            videos = data.get("data", [])

            if not videos:
                break

            all_videos.extend(videos)

            # Check for next page
            paging = data.get("paging", {})
            if not paging.get("next"):
                break

            page += 1
            time.sleep(0.5)  # Rate limiting

        # Filter by pattern
        filtered_videos = []
        for video_data in all_videos:
            video_name = video_data.get("name", "")

            # Check title_contains
            if pattern.title_contains and pattern.title_contains not in video_name:
                continue

            # Check title_regex
            if pattern.title_regex and not re.search(pattern.title_regex, video_name):
                continue

            # Extract video info
            try:
                video_info = self._extract_video_info(video_data)
                filtered_videos.append(video_info)
            except Exception as e:
                print(f"Skipping {video_name}: {e}")
                continue

        return filtered_videos

    def get_video_info(self, video_id: str, privacy_hash: str | None = None) -> VimeoVideoInfo:
        """Get detailed video metadata."""
        url = f"{self.api_base}/videos/{video_id}"
        if privacy_hash:
            url += f":{privacy_hash}"

        params = {"fields": "name,duration,download,files,created_time,modified_time,width,height"}

        response = self.client.get(url, params=params)
        if response.status_code != HTTP_OK:
            raise RuntimeError(f"Error fetching video info: {response.status_code}\n{response.text}")

        return self._extract_video_info(response.json())

    def _extract_video_info(self, video_data: dict) -> VimeoVideoInfo:
        """Extract video info from API response."""
        video_id = video_data["uri"].split("/")[-1]

        # Get download links
        if "download" not in video_data or not video_data["download"]:
            raise ValueError("No download links available. Check account permissions.")

        # Sort by quality (highest first)
        downloads = sorted(video_data["download"], key=lambda x: (x.get("height", 0), x.get("size", 0)), reverse=True)

        best = downloads[0]

        return VimeoVideoInfo(
            video_id=video_id,
            title=video_data.get("name", f"video_{video_id}"),
            duration=video_data.get("duration", 0),
            size_bytes=best.get("size"),
            quality=best.get("quality", "unknown"),
            resolution=f"{best.get('width', 0)}x{best.get('height', 0)}",
            width=best.get("width", 0),
            height=best.get("height", 0),
            fps=best.get("fps"),
            download_url=best["link"],
            created_time=datetime.fromisoformat(video_data.get("created_time", "").replace("Z", "+00:00")),
            modified_time=datetime.fromisoformat(video_data.get("modified_time", "").replace("Z", "+00:00")),
        )

    def get_download_url_by_quality(
        self, video_id: str, quality: str = "best", privacy_hash: str | None = None
    ) -> tuple[str, VimeoVideoInfo]:
        """Get download URL for specific quality."""
        url = f"{self.api_base}/videos/{video_id}"
        if privacy_hash:
            url += f":{privacy_hash}"

        params = {"fields": "name,duration,download,files,created_time,modified_time"}

        response = self.client.get(url, params=params)
        if response.status_code != HTTP_OK:
            raise RuntimeError(f"Error fetching video info: {response.status_code}\n{response.text}")

        video_data = response.json()

        if "download" not in video_data or not video_data["download"]:
            raise ValueError("No download links available")

        downloads = video_data["download"]

        # Select quality
        if quality == "best":
            selected = max(downloads, key=lambda x: (x.get("height", 0), x.get("size", 0)))
        elif quality.endswith("p"):
            # Match resolution like "1080p"
            target_height = int(quality[:-1])
            selected = min(downloads, key=lambda x: abs(x.get("height", 0) - target_height))
        else:
            # Try to match quality string
            selected = next((d for d in downloads if d.get("quality") == quality), downloads[0])

        video_info = self._extract_video_info(video_data)
        # Update with selected quality
        video_info.quality = selected.get("quality", "unknown")
        video_info.resolution = f"{selected.get('width', 0)}x{selected.get('height', 0)}"
        video_info.width = selected.get("width", 0)
        video_info.height = selected.get("height", 0)
        video_info.size_bytes = selected.get("size")
        video_info.download_url = selected["link"]

        return selected["link"], video_info

    def download_file(self, url: str, output_path: Path, expected_size: int = 0, show_progress: bool = True) -> bool:
        """Download file with progress bar and verification."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        # Get file size
        file_size = int(response.headers.get("content-length", expected_size or 0))

        # Download with progress bar
        if show_progress and file_size > 0:
            progress_bar = tqdm(total=file_size, unit="B", unit_scale=True, desc=output_path.name)

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    if show_progress and file_size > 0:
                        progress_bar.update(len(chunk))

        if show_progress and file_size > 0:
            progress_bar.close()

        # Verify size
        actual_size = output_path.stat().st_size
        return not (expected_size and actual_size != expected_size)

    def extract_video_id(self, url: str) -> tuple[str, str | None]:
        """Extract video ID and privacy hash from URL."""
        url = url.strip()

        # Remove query parameters
        if "?" in url:
            url = url.split("?")[0]

        # Extract ID and privacy hash
        if "vimeo.com/" in url:
            parts = url.split("vimeo.com/")[-1].split("/")
            video_id = parts[0]
            privacy_hash = parts[1] if len(parts) > 1 else None
            return video_id, privacy_hash

        # Assume it's already just the ID
        return url, None
