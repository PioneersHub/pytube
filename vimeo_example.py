#!/usr/bin/env python3
"""
Simple example of using the Vimeo downloader.

Set your access token as an environment variable:
export VIMEO_ACCESS_TOKEN='your_token_here'

Then run:
python vimeo_example.py https://vimeo.com/VIDEO_ID
"""

import os
import sys
from pathlib import Path

from src.video_processor.vimeo_downloader import VimeoDownloader


# Example 1: Basic download
def basic_download(video_url: str, token: str):
    """Download a video with default settings."""
    downloader = VimeoDownloader(token)
    output_file = downloader.download_video(video_url)
    print(f"Downloaded to: {output_file}")


# Example 2: Download to specific directory
def download_to_directory(video_url: str, token: str):
    """Download to a specific directory."""
    downloader = VimeoDownloader(token)
    output_dir = Path("downloads")
    output_file = downloader.download_video(video_url, output_path=output_dir)
    print(f"Downloaded to: {output_file}")


# Example 3: Check available qualities first
def download_with_quality_check(video_url: str, token: str):
    """List qualities before downloading."""
    downloader = VimeoDownloader(token)

    # List available qualities
    qualities = downloader.list_available_qualities(video_url)
    print("Available qualities:")
    for q in qualities:
        print(f"  - {q['quality']}: {q['size_mb']:.1f} MB")

    # Download best quality
    output_file = downloader.download_video(video_url, quality="best")
    print(f"Downloaded best quality to: {output_file}")


if __name__ == "__main__":
    # Get token from environment
    token = os.environ.get("VIMEO_ACCESS_TOKEN")
    secret = "VIMEO_SECRET"
    if not token:
        print("Error: Please set VIMEO_ACCESS_TOKEN environment variable")
        print("Example: export VIMEO_ACCESS_TOKEN='your_token_here'")
        sys.exit(1)

    # Get video URL from command line
    # if len(sys.argv) < 2:
    #     print("Usage: python vimeo_example.py <vimeo_url>")
    #     print("Example: python vimeo_example.py https://vimeo.com/123456789")
    #     sys.exit(1)

    video_urls = [
        "https://vimeo.com/1114324749/4173f48870",  # B09
        "https://vimeo.com/1114331829/453cb98d4e",  # B0506
        "https://vimeo.com/1114330801/f565cf073b",  # B0708
        "https://vimeo.com/1114768778/ca10511f29",  # C01
    ]
    # video_url = sys.argv[1]
    for video_url in video_urls:
        try:
            # Run the example
            print(f"Downloading video from: {video_url}\n")
            download_with_quality_check(video_url, token)

        except Exception as e:
            print(f"Error: {e}")
