#!/usr/bin/env python3
"""
Script to separate videos between PyCon and PyData channels.

This script demonstrates the video organization workflow using PyTube's
existing commands.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str]) -> int:
    """Run a command and return its exit code."""
    print(f"\n🚀 Running: {' '.join(cmd)}")
    print("-" * 60)
    result = subprocess.run(cmd)
    return result.returncode


def main():
    """Run the video separation workflow."""
    print("=" * 60)
    print("PyTube Video Separation Script")
    print("=" * 60)
    
    # Check if pytube is available
    if subprocess.run(["which", "pytube"], capture_output=True).returncode != 0:
        print("❌ Error: pytube command not found!")
        print("Please ensure you have activated your virtual environment.")
        sys.exit(1)
    
    print("\nThis script will:")
    print("1. Assign videos to channels based on track information")
    print("2. Move videos to channel-specific directories")
    print("3. Generate a report of any unassigned videos")
    
    response = input("\nContinue? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    # Step 1: Check current status
    print("\n📊 Checking current status...")
    run_command(["pytube", "status", "--detailed"])
    
    # Step 2: Assign videos to channels
    print("\n📝 Assigning videos to channels...")
    if run_command(["pytube", "video", "assign-channels"]) != 0:
        print("❌ Failed to assign channels!")
        return
    
    # Step 3: Show what will be moved (dry run)
    print("\n👀 Preview of video movements (dry run)...")
    run_command(["pytube", "video", "move", "--dry-run"])
    
    response = input("\nProceed with moving videos? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    # Step 4: Actually move the videos
    print("\n📦 Moving videos to channel directories...")
    if run_command(["pytube", "video", "move"]) != 0:
        print("❌ Failed to move videos!")
        return
    
    # Step 5: Generate report of unassigned videos
    print("\n📋 Generating report...")
    run_command(["pytube", "video", "report"])
    
    print("\n✅ Video separation completed!")
    print("\nDirectory structure:")
    print("  video_dir/")
    print("  ├── downloads/      # Unmatched videos")
    print("  ├── pyconde/        # PyCon channel videos")
    print("  ├── pydata/         # PyData channel videos")
    print("  └── do_not_release/ # Do-not-record videos")


if __name__ == "__main__":
    main()