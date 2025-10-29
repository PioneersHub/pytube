"""Fetch YouTube playlist data for mapping."""

import sys
from datetime import UTC, datetime
from pathlib import Path

from ..config import load_config
from ..logger import setup_logging
from ..paths import WorkPaths
from ..youtube.auth import YouTubeAuth
from .models import PlaylistVideo


def fetch_playlist_videos(
    youtube_auth: YouTubeAuth, playlist_id: str, channel_name: str, logger
) -> list[PlaylistVideo]:
    """Fetch all videos from a YouTube playlist."""
    logger.info(f"Fetching playlist videos for {channel_name}", playlist_id=playlist_id)

    videos = []
    next_page_token = None

    while True:
        try:
            request = youtube_auth.service.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token,
            )
            response = request.execute()

            for item in response.get("items", []):
                snippet = item["snippet"]
                video = PlaylistVideo(
                    youtube_id=snippet["resourceId"]["videoId"],
                    title=snippet["title"],
                    published_at=datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00")),
                    channel_id=snippet["channelId"],
                )
                videos.append(video)

            logger.info(
                f"Fetched {len(response.get('items', []))} videos",
                channel=channel_name,
                total_so_far=len(videos),
            )

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        except Exception as e:
            logger.error(f"Error fetching playlist {channel_name}", error=str(e), playlist_id=playlist_id)
            raise

    logger.info(f"Completed fetching {channel_name} playlist", total_videos=len(videos))
    return videos


def fetch_all_playlists():
    """Fetch playlist data for all configured YouTube channels."""
    # Setup
    config = load_config()
    logger = setup_logging(module_name="pretalx_youtube_map.fetch_playlists")
    paths = WorkPaths(config)
    paths.ensure_directories()

    # Create output directory
    playlist_dir = paths.get_path("pretalx_youtube_map")

    logger.info("Starting YouTube playlist fetch", event_slug=config.pretalx.event_slug)

    # Initialize YouTube auth
    try:
        client_secrets_path = Path(config.youtube.client_secrets_file)
        youtube_auth = YouTubeAuth(client_secrets_file=client_secrets_path)
        logger.info("YouTube authentication successful")
    except Exception as e:
        logger.error("Failed to authenticate with YouTube", error=str(e))
        sys.exit(1)

    # Get configured channels
    if not hasattr(config, "youtube") or not hasattr(config.youtube, "channels"):
        logger.error("No YouTube channels configured in config")
        sys.exit(1)

    channels = config.youtube.channels
    total_videos = 0
    channels_processed = []

    # Fetch each channel's playlist
    for channel_name in channels:
        channel_config = channels[channel_name]

        if not hasattr(channel_config, "playlist_id"):
            logger.warning(f"No playlist_id for channel {channel_name}, skipping")
            continue

        playlist_id = channel_config.playlist_id
        logger.info(f"Processing channel: {channel_name}", playlist_id=playlist_id)

        try:
            videos = fetch_playlist_videos(youtube_auth, playlist_id, channel_name, logger)
            total_videos += len(videos)
            channels_processed.append(channel_name)

            # Save playlist data
            playlist_data = {
                "channel": channel_name,
                "playlist_id": playlist_id,
                "fetched_at": datetime.now(UTC).isoformat(),
                "video_count": len(videos),
                "videos": [v.model_dump(mode="json") for v in videos],
            }

            filename = f"playlist_{channel_name}.json"
            paths.save_json(playlist_data, "pretalx_youtube_map", filename)
            logger.info(f"Saved {channel_name} playlist data", filename=filename, video_count=len(videos))

        except Exception as e:
            logger.error(f"Failed to fetch playlist for {channel_name}", error=str(e))
            continue

    # Save summary
    summary = {
        "event_slug": config.pretalx.event_slug,
        "fetched_at": datetime.now(UTC).isoformat(),
        "channels_processed": channels_processed,
        "total_videos": total_videos,
    }
    paths.save_yaml(summary, "pretalx_youtube_map", "_fetch_summary.yaml")

    logger.info(
        "Playlist fetch complete",
        channels_processed=len(channels_processed),
        total_videos=total_videos,
    )

    return total_videos


if __name__ == "__main__":
    fetch_all_playlists()
