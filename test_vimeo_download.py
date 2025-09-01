#!/usr/bin/env python3
"""
Test script for Vimeo downloader.
"""

import os
from pathlib import Path

from src.video_processor.vimeo_downloader import VimeoDownloader


def test_vimeo_download():
    """Test downloading a video from Vimeo."""
    
    # Get token from environment
    token = os.environ.get("VIMEO_ACCESS_TOKEN")
    if not token:
        print("Please set VIMEO_ACCESS_TOKEN environment variable")
        print("Example: export VIMEO_ACCESS_TOKEN='your_token_here'")
        return
    
    # Get video URL from user or use example
    video_url = input("Enter Vimeo video URL (or press Enter to skip): ").strip()
    
    if not video_url:
        print("No URL provided. Please provide a Vimeo URL when you have one.")
        return
    
    # Create downloader
    downloader = VimeoDownloader(token)
    
    try:
        # Extract video ID
        video_id = downloader.extract_video_id(video_url)
        print(f"\nVideo ID: {video_id}")
        
        # Get video info
        print("\nFetching video information...")
        video_info = downloader.get_video_info(video_id)
        print(f"Title: {video_info.get('name', 'Unknown')}")
        print(f"Duration: {video_info.get('duration', 0)} seconds")
        
        # List available qualities
        print("\nAvailable download qualities:")
        qualities = downloader.list_available_qualities(video_url)
        
        if not qualities:
            print("No download links available. Check your token permissions and account type.")
            return
        
        for i, q in enumerate(qualities, 1):
            print(f"  {i}. {q['quality']}: {q['size_mb']:.1f} MB "
                  f"({q['width']}x{q['height']} @ {q['fps']} fps)")
        
        # Download to a test directory
        output_dir = Path("test_downloads")
        output_dir.mkdir(exist_ok=True)
        
        print(f"\nDownloading best quality to {output_dir}/...")
        output_file = downloader.download_video(
            video_url, 
            output_path=output_dir,
            quality="best",
            show_progress=True
        )
        
        print(f"\n✓ Successfully downloaded to: {output_file}")
        print(f"  File size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Vimeo Video Downloader Test")
    print("=" * 40)
    test_vimeo_download()