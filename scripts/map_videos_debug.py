#!/usr/bin/env python3
"""Debug version of map_videos that can be run standalone.

This script replicates the pytube youtube map command functionality
but can be run directly for debugging purposes.
"""

import logging
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

# Add paths for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Set up logging before imports to catch import issues
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Now import what we need with error handling
try:
    from manager import conf
    from manager.config import get_event_dir
    from manager.utils.common import SafeConfig, load_json, save_json

    logger.info("Successfully imported manager modules")
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("Make sure you run this from the project root or have installed the package")
    sys.exit(1)


def debug_map_videos(use_oauth: bool = True, filter_channel: str | None = None):
    """Debug version of the map_videos functionality.

    Args:
        use_oauth: If True, use OAuth. If False, use API key.
        filter_channel: Optional channel filter.
    """
    print("\n" + "=" * 80)
    print("DEBUG MAP VIDEOS")
    print("=" * 80)

    # Step 1: Show configuration
    print("\n1. CONFIGURATION:")
    print("-" * 40)
    safe_conf = SafeConfig(conf)

    # Show event config
    event_slug = safe_conf.get("pretalx.event_slug", "unknown")
    print(f"Event slug: {event_slug}")

    # Show YouTube config
    channels = safe_conf.get("youtube.channels", {})
    print(f"\nConfigured channels: {list(channels.keys())}")
    for name, config in channels.items():
        print(f"  {name}:")
        print(f"    Channel ID: {config.get('id', 'NOT SET')}")
        print(f"    Playlist ID: {config.get('playlist_id', 'NOT SET')}")

    # Show auth config
    print("\nAuthentication:")
    if use_oauth:
        client_secrets = conf.dirs["root"] / safe_conf.get("youtube.client_secrets_file", "NOT SET")
        print("  Method: OAuth")
        print(f"  Client secrets: {client_secrets}")
        if client_secrets.exists():
            print("  ✓ Client secrets file exists")
        else:
            print("  ✗ Client secrets file NOT FOUND")
    else:
        api_key = safe_conf.get("youtube.api_key", "")
        print("  Method: API Key")
        print(f"  API Key: {'SET' if api_key else 'NOT SET'}")

    # Step 2: Import and initialize YouTube handler
    print("\n2. YOUTUBE CLIENT INITIALIZATION:")
    print("-" * 40)

    try:
        # Import here to avoid issues if not all dependencies are installed
        from manager.handlers.youtube import YT

        print("✓ Successfully imported YT class")

        # Initialize client
        if use_oauth:
            print("Initializing with OAuth...")
            yt_client = YT(youtube_offline=True)
            yt_client.get_authenticated_service()
        else:
            print("Initializing with API key...")
            yt_client = YT()
            yt_client.get_authenticated_service_via_api_key()

        print("✓ YouTube client initialized")

    except Exception as e:
        print(f"\n✗ FAILED to initialize YouTube client: {e}")
        import traceback

        traceback.print_exc()
        return

    # Step 3: Retrieve videos from playlists
    print("\n3. RETRIEVING VIDEOS FROM PLAYLISTS:")
    print("-" * 40)

    channel_results = {}
    total_videos = 0

    for channel_name in channels:
        print(f"\nProcessing {channel_name}...")
        try:
            video_count = yt_client.get_youtube_ids_for_uploads(channel_name)
            channel_results[channel_name] = {"status": "success", "count": video_count, "error": None}
            total_videos += video_count
            print(f"✓ Retrieved {video_count} videos")

        except Exception as e:
            channel_results[channel_name] = {"status": "error", "count": 0, "error": str(e)}
            print(f"✗ Error: {e}")

    print(f"\nTotal videos found: {total_videos}")

    # Step 4: Show playlist data
    print("\n4. PLAYLIST DATA:")
    print("-" * 40)

    event_dir = get_event_dir(conf)
    for channel_name in channels:
        playlist_file = event_dir / "videos" / f"youtube_{channel_name}_playlist.json"
        if playlist_file.exists():
            print(f"\n{channel_name} playlist file: {playlist_file}")
            try:
                data = load_json(playlist_file)
                print(f"  Videos in file: {len(data)}")
                # Show first few videos
                for i, video in enumerate(data[:3]):
                    snippet = video.get("snippet", {})
                    title = snippet.get("title", "NO TITLE")
                    video_id = snippet.get("resourceId", {}).get("videoId", "NO ID")
                    print(f"  {i + 1}. {title} (ID: {video_id})")
                if len(data) > 3:
                    print(f"  ... and {len(data) - 3} more")
            except Exception as e:
                print(f"  Error reading file: {e}")
        else:
            print(f"\n{channel_name}: No playlist file found")

    # Step 5: Map videos
    print("\n5. MAPPING PRETALX IDs TO YOUTUBE IDs:")
    print("-" * 40)

    if filter_channel:
        print(f"Filtering by channel: {filter_channel}")

    try:
        mapping, warnings = yt_client.map_pretalx_id_youtube_id(filter_by_channel=filter_channel)
        print(f"\n✓ Created mapping with {len(mapping)} entries")

        # Show some mapping examples
        if mapping:
            print("\nExample mappings:")
            for i, (pretalx_id, youtube_id) in enumerate(list(mapping.items())[:5]):
                print(f"  {pretalx_id} -> {youtube_id}")
            if len(mapping) > 5:
                print(f"  ... and {len(mapping) - 5} more")

        # Show warnings
        if warnings:
            print(f"\n⚠️  {len(warnings)} warnings:")
            for warning in warnings[:5]:
                print(f"  - {warning}")
            if len(warnings) > 5:
                print(f"  ... and {len(warnings) - 5} more")

    except Exception as e:
        print(f"\n✗ Mapping failed: {e}")
        import traceback

        traceback.print_exc()
        return

    # Step 6: Check output files
    print("\n6. OUTPUT FILES:")
    print("-" * 40)

    mapping_file = event_dir / "videos" / "pretalx_yt_map.json"
    if mapping_file.exists():
        print(f"✓ Mapping file created: {mapping_file}")
        print(f"  Size: {mapping_file.stat().st_size} bytes")
        print(f"  Modified: {datetime.fromtimestamp(mapping_file.stat().st_mtime)}")
    else:
        print(f"✗ Mapping file not found: {mapping_file}")

    # Check for skipped videos report
    skipped_file = event_dir / "videos" / "skipped_videos_report.json"
    if skipped_file.exists():
        print(f"\n⚠️  Skipped videos report: {skipped_file}")
        try:
            skipped_data = load_json(skipped_file)
            print(f"  Total skipped: {skipped_data.get('total_skipped', 0)}")
        except Exception as e:
            print(f"  Error reading report: {e}")

    # Save debug summary
    print("\n7. SAVING DEBUG SUMMARY:")
    print("-" * 40)

    debug_dir = Path("debug_map_videos")
    debug_dir.mkdir(exist_ok=True)

    debug_summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "config": {
            "event_slug": event_slug,
            "auth_method": "OAuth" if use_oauth else "API Key",
            "filter_channel": filter_channel,
            "channels": list(channels.keys()),
        },
        "results": {
            "channels": channel_results,
            "total_videos": total_videos,
            "mapped_videos": len(mapping),
            "warnings": len(warnings),
        },
        "files": {
            "mapping_file": str(mapping_file),
            "mapping_exists": mapping_file.exists(),
            "skipped_file": str(skipped_file),
            "skipped_exists": skipped_file.exists(),
        },
    }

    summary_file = debug_dir / "debug_summary.json"
    save_json(debug_summary, summary_file)
    print(f"✓ Debug summary saved to: {summary_file}")

    print("\n" + "=" * 80)
    print("DEBUG COMPLETE")
    print("=" * 80)


def main(use_oauth=False):
    try:
        debug_map_videos(use_oauth)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
