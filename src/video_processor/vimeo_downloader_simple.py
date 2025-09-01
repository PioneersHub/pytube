#!/usr/bin/env python3
"""
Simple Vimeo downloader that works without API authentication.
Uses the player config endpoint to get video URLs.
"""

import json
import re
from pathlib import Path
from typing import Optional

import requests
from tqdm import tqdm


class SimpleVimeoDownloader:
    """Download Vimeo videos without API authentication."""
    
    def extract_video_id(self, url: str) -> str:
        """Extract video ID from Vimeo URL."""
        # Remove query parameters
        if "?" in url:
            url = url.split("?")[0]
        
        # Extract ID from URL
        if "vimeo.com/" in url:
            parts = url.split("vimeo.com/")[-1].split("/")
            return parts[0]
        
        return url
    
    def get_video_config(self, video_url: str) -> dict:
        """
        Get video configuration from player endpoint.
        
        Args:
            video_url: Full Vimeo URL including privacy hash if needed
        
        Returns:
            Video configuration dict
        """
        video_id = self.extract_video_id(video_url)
        
        # First, try to get the page to extract config
        page_response = requests.get(video_url)
        page_response.raise_for_status()
        
        # Look for config URL in the page
        config_match = re.search(r'"config_url":"([^"]+)"', page_response.text)
        if config_match:
            config_url = config_match.group(1).replace("\\", "")
            print(f"Found config URL: {config_url}")
            
            # Get the config
            config_response = requests.get(config_url)
            config_response.raise_for_status()
            return config_response.json()
        
        # Fallback: try direct player config endpoint
        config_url = f"https://player.vimeo.com/video/{video_id}/config"
        config_response = requests.get(config_url)
        config_response.raise_for_status()
        return config_response.json()
    
    def get_download_links(self, video_url: str) -> list[dict]:
        """
        Get available download links for a video.
        
        Args:
            video_url: Vimeo video URL
        
        Returns:
            List of download options
        """
        config = self.get_video_config(video_url)
        
        downloads = []
        
        # Check for progressive downloads (direct MP4 files)
        if "request" in config and "files" in config["request"]:
            files = config["request"]["files"]
            
            if "progressive" in files:
                for file_info in files["progressive"]:
                    downloads.append({
                        "url": file_info["url"],
                        "quality": file_info.get("quality", "unknown"),
                        "width": file_info.get("width"),
                        "height": file_info.get("height"),
                        "fps": file_info.get("fps"),
                        "mime": file_info.get("mime", "video/mp4"),
                        "size": None  # Size not provided in config
                    })
        
        # Get video title
        title = "Unknown"
        if "video" in config:
            title = config["video"].get("title", "Unknown")
        
        # Sort by quality (resolution)
        downloads.sort(key=lambda x: (x.get("width", 0), x.get("height", 0)), reverse=True)
        
        return downloads, title
    
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
            video_url: Vimeo video URL
            output_path: Where to save the video
            quality: Quality preference ("best", "worst", or specific resolution like "1080p")
            show_progress: Show download progress
        
        Returns:
            Path to downloaded file
        """
        print(f"Fetching video info from: {video_url}")
        
        # Get download links
        downloads, title = self.get_download_links(video_url)
        
        if not downloads:
            raise ValueError("No download links found for this video")
        
        # Select quality
        if quality == "best":
            selected = downloads[0]  # Already sorted by quality
        elif quality == "worst":
            selected = downloads[-1]
        else:
            # Try to match specific quality
            for dl in downloads:
                if dl["quality"] == quality or f"{dl['height']}p" == quality:
                    selected = dl
                    break
            else:
                selected = downloads[0]  # Default to best
        
        # Sanitize filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:200]
        
        # Determine output path
        if output_path is None:
            output_path = Path(f"{safe_title}.mp4")
        elif output_path.is_dir():
            output_path = output_path / f"{safe_title}.mp4"
        
        print(f"Downloading {selected['quality']} ({selected['width']}x{selected['height']}) to {output_path}")
        
        # Download the file
        response = requests.get(selected["url"], stream=True)
        response.raise_for_status()
        
        # Get file size from headers
        file_size = int(response.headers.get("content-length", 0))
        
        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download with progress bar
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
        
        print(f"✓ Downloaded successfully: {output_path}")
        return output_path
    
    def list_qualities(self, video_url: str) -> list[dict]:
        """List available qualities for a video."""
        downloads, title = self.get_download_links(video_url)
        
        print(f"Video: {title}")
        print("Available qualities:")
        
        qualities = []
        for dl in downloads:
            qualities.append({
                "quality": dl["quality"],
                "resolution": f"{dl['width']}x{dl['height']}",
                "fps": dl.get("fps", "?")
            })
        
        return qualities


def main():
    """Example usage."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python vimeo_downloader_simple.py <vimeo_url>")
        sys.exit(1)
    
    video_url = sys.argv[1]
    
    downloader = SimpleVimeoDownloader()
    
    try:
        # List qualities
        qualities = downloader.list_qualities(video_url)
        for q in qualities:
            print(f"  - {q['quality']}: {q['resolution']} @ {q['fps']} fps")
        
        # Download best quality
        print("\nDownloading best quality...")
        output_file = downloader.download_video(video_url)
        print(f"Downloaded to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()