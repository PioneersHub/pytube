"""Vimeo video downloader module.

This module provides robust Vimeo video downloading capabilities with:
- Folder-based or pattern-based video selection
- Smart download tracking and skip logic
- Best quality selection
- Concurrent downloads
- Complete verification

Uses existing pipeline infrastructure for config, logging, and paths.
"""

from video_vimeo.client import VimeoClient  # noqa: F401
from video_vimeo.downloader import download_all_videos  # noqa: F401
from video_vimeo.models import (  # noqa: F401
    DownloadRecord,
    DownloadTracking,
    VimeoSelection,
    VimeoVideoInfo,
)

__all__ = [
    "VimeoClient",
    "download_all_videos",
    "VimeoVideoInfo",
    "DownloadRecord",
    "DownloadTracking",
    "VimeoSelection",
]
