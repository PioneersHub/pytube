#!/usr/bin/env python3
"""
Download videos from Vimeo using API access token.

This module provides functionality to download videos from Vimeo
when you have the appropriate access token and permissions.
"""

import logging
from pathlib import Path
from typing import Optional

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)


class VimeoDownloader:
    """Download videos from Vimeo using API access."""
    
    def __init__(self, access_token: str):
        """
        Initialize Vimeo downloader.
        
        Args:
            access_token: Vimeo API access token with video_files scope
        """
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.vimeo.*+json;version=3.4"
        }
        self.api_base = "https://api.vimeo.com"
    
    def extract_video_id(self, url: str) -> tuple[str, Optional[str]]:
        """
        Extract video ID and privacy hash from Vimeo URL.
        
        Args:
            url: Vimeo video URL (e.g., https://vimeo.com/123456789 or https://vimeo.com/123456789/abcd1234)
        
        Returns:
            Tuple of (video_id, privacy_hash)
        """
        # Handle various URL formats
        url = url.strip()
        
        # Remove query parameters
        if "?" in url:
            url = url.split("?")[0]
        
        # Extract ID and privacy hash from URL
        if "vimeo.com/" in url:
            parts = url.split("vimeo.com/")[-1].split("/")
            video_id = parts[0]
            privacy_hash = parts[1] if len(parts) > 1 else None
            return video_id, privacy_hash
        
        # Assume it's already just the ID
        return url, None
    
    def get_video_info(self, video_id: str, privacy_hash: Optional[str] = None) -> dict:
        """
        Get video metadata from Vimeo API.
        
        Args:
            video_id: Vimeo video ID
            privacy_hash: Optional privacy hash for private videos
        
        Returns:
            Video metadata dict
        """
        url = f"{self.api_base}/videos/{video_id}"
        if privacy_hash:
            url += f":{privacy_hash}"
        
        params = {
            "fields": "name,duration,download,files,created_time,modified_time"
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_best_download_link(self, video_info: dict) -> tuple[str, int, str]:
        """
        Get the highest quality download link from video info.
        
        Args:
            video_info: Video metadata from API
        
        Returns:
            Tuple of (download_url, size_bytes, quality)
        """
        if "download" not in video_info or not video_info["download"]:
            raise ValueError("No download links available. Check account permissions.")
        
        # Sort by size (highest quality first)
        downloads = sorted(
            video_info["download"], 
            key=lambda x: x.get("size", 0), 
            reverse=True
        )
        
        best = downloads[0]
        return best["link"], best.get("size", 0), best.get("quality", "unknown")
    
    def download_video(
        self, 
        video_url: str, 
        output_path: Optional[Path] = None,
        quality: str = "best",
        show_progress: bool = True
    ) -> Path:
        """
        Download a video from Vimeo.
        
        Args:
            video_url: Vimeo video URL or ID
            output_path: Where to save the video (optional)
            quality: Quality preference ("best", "worst", or specific like "hd")
            show_progress: Show download progress bar
        
        Returns:
            Path to downloaded file
        """
        # Extract video ID and privacy hash
        video_id, privacy_hash = self.extract_video_id(video_url)
        logger.info(f"Downloading video ID: {video_id}" + (f" with privacy hash: {privacy_hash}" if privacy_hash else ""))
        
        # Get video info
        video_info = self.get_video_info(video_id, privacy_hash)
        video_name = video_info.get("name", f"video_{video_id}")
        
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in video_name)
        safe_name = safe_name[:200]  # Limit length
        
        # Get download link
        if "download" not in video_info or not video_info["download"]:
            raise ValueError(
                "No download links available. Ensure your token has 'video_files' scope "
                "and you have a Vimeo PRO or Business account."
            )
        
        # Select quality
        downloads = video_info["download"]
        
        if quality == "best":
            selected = max(downloads, key=lambda x: x.get("size", 0))
        elif quality == "worst":
            selected = min(downloads, key=lambda x: x.get("size", 0))
        else:
            # Try to find specific quality
            selected = next(
                (d for d in downloads if d.get("quality") == quality),
                max(downloads, key=lambda x: x.get("size", 0))  # Default to best
            )
        
        download_url = selected["link"]
        file_size = selected.get("size", 0)
        quality_name = selected.get("quality", "unknown")
        
        # Determine output path
        if output_path is None:
            output_path = Path(f"{safe_name}.mp4")
        elif output_path.is_dir():
            output_path = output_path / f"{safe_name}.mp4"
        
        logger.info(f"Downloading {quality_name} quality ({file_size / 1024 / 1024:.1f} MB) to {output_path}")
        
        # Download file
        response = requests.get(download_url, stream=True)
        response.raise_for_status()
        
        # Get actual file size from headers if not in metadata
        if file_size == 0:
            file_size = int(response.headers.get("content-length", 0))
        
        # Write to file with progress bar
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if show_progress and file_size > 0:
            progress_bar = tqdm(
                total=file_size,
                unit="B",
                unit_scale=True,
                desc=output_path.name
            )
        
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    if show_progress and file_size > 0:
                        progress_bar.update(len(chunk))
        
        if show_progress and file_size > 0:
            progress_bar.close()
        
        logger.info(f"Downloaded successfully: {output_path}")
        return output_path
    
    def list_available_qualities(self, video_url: str) -> list[dict]:
        """
        List all available download qualities for a video.
        
        Args:
            video_url: Vimeo video URL or ID
        
        Returns:
            List of dicts with quality information
        """
        video_id, privacy_hash = self.extract_video_id(video_url)
        video_info = self.get_video_info(video_id, privacy_hash)
        
        if "download" not in video_info or not video_info["download"]:
            return []
        
        qualities = []
        for dl in video_info["download"]:
            qualities.append({
                "quality": dl.get("quality", "unknown"),
                "size_mb": dl.get("size", 0) / 1024 / 1024,
                "width": dl.get("width"),
                "height": dl.get("height"),
                "fps": dl.get("fps"),
                "type": dl.get("type", "video/mp4")
            })
        
        return sorted(qualities, key=lambda x: x["size_mb"], reverse=True)


def main():
    """Example usage."""
    import os
    import sys
    
    # Get token from environment or command line
    token = os.environ.get("VIMEO_ACCESS_TOKEN")
    
    if not token:
        print("Please set VIMEO_ACCESS_TOKEN environment variable")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print("Usage: python vimeo_downloader.py <vimeo_url>")
        sys.exit(1)
    
    video_url = sys.argv[1]
    
    # Create downloader
    downloader = VimeoDownloader(token)
    
    try:
        # List available qualities
        print("\nAvailable qualities:")
        qualities = downloader.list_available_qualities(video_url)
        for q in qualities:
            print(f"  {q['quality']}: {q['size_mb']:.1f} MB ({q['width']}x{q['height']} @ {q['fps']} fps)")
        
        # Download best quality
        print("\nDownloading best quality...")
        output_file = downloader.download_video(video_url)
        print(f"✓ Downloaded to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()