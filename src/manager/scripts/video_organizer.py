"""
Script with functions to organize conference videos and assign them to the correct channel.

Video Organization Workflow:
1. Videos are downloaded to video_dir/downloads/ with filenames like: XXXXXX-title.mp4
   where XXXXXX is the 6-character Pretalx session code

2. Videos are assigned to channels based on:
   - Direct code-to-track mapping (conf.pretalx.video_to_track)
   - Track name pattern matching (conf.pretalx.track_to_channel)

3. Videos are moved to sibling directories:
   - video_dir/pycon/     - Videos for PyCon channel
   - video_dir/pydata/    - Videos for PyData channel
   - video_dir/do_not_release/ - Videos marked as do-not-record
   - video_dir/downloads/ - Unmatched videos remain here

4. The system tracks:
   - Which videos were moved where
   - Videos that couldn't be matched to a channel
   - Missing video files for confirmed sessions
"""

import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from manager import conf, logger
from manager.handlers.records import Records

records = Records()


def split_pycon_pydata(video: dict):
    """Assign videos to PyData or PyCon via the track
    In case this cannot be done by track,
    add the pretalx code in the config
    """
    if video["code"] in conf.pretalx.video_to_track:
        return conf.pretalx.video_to_track[video["code"]]
    for snippet in conf.pretalx.track_to_channel:
        if snippet.casefold() in video["track"]["en"].casefold():
            return conf.pretalx.track_to_channel[snippet]
    print(video["code"], video["track"]["en"], video["title"])


def assign_video_to_channel():
    collect_tracks = defaultdict(list)
    collect_tracks_map = {}
    for sub in records.confirmed_sessions_map:
        track = split_pycon_pydata(sub)
        collect_tracks[track].append(sub)
        collect_tracks_map[sub["code"]] = track
    with open(conf.dirs.video_dir / "tracks.json", "w") as f:
        json.dump(collect_tracks, f, indent=4)
    with open(conf.dirs.video_dir / "tracks_map.json", "w") as f:
        json.dump(collect_tracks_map, f, indent=4)
    return collect_tracks


def load_tracks_map() -> dict:
    the_file = conf.dirs.video_dir / "tracks_map.json"
    if not the_file.exists():
        logger.error(f"File {the_file} does not exist, did you run `assign_video_to_channel`?")
        return {}
    return json.load(the_file.open())


def video_code_map() -> dict[Any, Any]:
    """Mapping of all downloaded videos using first 6 characters of filename"""
    downloaded = Path(conf.dirs.video_dir / "downloads").rglob("*.mp4")
    return {x.stem[:6]: x for x in downloaded}


def move_videos_to_upload_channel(dry_run=False):
    """Move all videos to the correct channel directories

    Args:
        dry_run: If True, only simulate moves without actually moving files

    Returns:
        dict: Statistics about the operation
    """
    video_map = video_code_map()
    tracks_map = load_tracks_map()
    confirmed_map = records.confirmed_sessions_map

    # Collections for tracking
    move_to_channel = []
    move_to_dnr = []
    keep_in_downloads = []
    missing_videos = []

    if dry_run:
        logger.info("=== DRY RUN MODE - No files will be moved ===")

    logger.info(f"Processing {len(confirmed_map)} confirmed sessions")
    logger.info(f"Found {len(video_map)} video files")

    # Analyze each confirmed session
    for code, info in confirmed_map.items():
        title = info["title"]

        # Check if video should not be released
        if info.get("do_not_record", False):
            if code in video_map:
                move_to_dnr.append((video_map[code], code, title))
                logger.debug(f"Video {code} marked as do-not-record: {title}")
            else:
                logger.debug(f"Video {code} marked as do-not-record (no file): {title}")
            continue

        # Check if video file exists
        if code not in video_map:
            missing_videos.append((code, title))
            logger.warning(f"Video file missing for {code}: {title}")
            continue

        # Check if we can determine the channel
        if code not in tracks_map:
            keep_in_downloads.append((video_map[code], code, title))
            logger.warning(f"Cannot determine channel for {code}: {title}")
            continue

        # Video can be moved to channel directory
        channel = tracks_map[code]
        move_to_channel.append((video_map[code], code, channel, title))
        logger.debug(f"{code} -> {channel}: {title}")

    # Create necessary directories
    channels_needed = {item[2] for item in move_to_channel}
    for channel in channels_needed:
        channel_dir = conf.dirs.video_dir / channel
        if dry_run:
            if not channel_dir.exists():
                logger.info(f"Would create directory: {channel_dir}")
            else:
                logger.info(f"Directory exists: {channel_dir}")
        else:
            channel_dir.mkdir(exist_ok=True)
            logger.info(f"Created/verified directory: {channel_dir}")

    # Create do_not_release directory if needed
    if move_to_dnr:
        dnr_dir = conf.dirs.video_dir / "do_not_release"
        if dry_run:
            if not dnr_dir.exists():
                logger.info(f"Would create directory: {dnr_dir}")
            else:
                logger.info(f"Directory exists: {dnr_dir}")
        else:
            dnr_dir.mkdir(exist_ok=True)
            logger.info(f"Created/verified directory: {dnr_dir}")

    # Move videos to channel directories
    moved_count = 0
    for src_path, code, channel, title in move_to_channel:
        dst_path = conf.dirs.video_dir / channel / src_path.name
        if dry_run:
            logger.info(f"Would move {code} to {channel}/: {src_path.name}")
            moved_count += 1
        else:
            try:
                shutil.move(str(src_path), str(dst_path))
                moved_count += 1
                logger.info(f"Moved {code} to {channel}/: {src_path.name}")
            except Exception as e:
                logger.error(f"Failed to move {code}: {e}")

    # Move do-not-release videos
    dnr_count = 0
    for src_path, code, title in move_to_dnr:
        dst_path = conf.dirs.video_dir / "do_not_release" / src_path.name
        if dry_run:
            logger.info(f"Would move {code} to do_not_release/: {src_path.name}")
            dnr_count += 1
        else:
            try:
                shutil.move(str(src_path), str(dst_path))
                dnr_count += 1
                logger.info(f"Moved {code} to do_not_release/: {src_path.name}")
            except Exception as e:
                logger.error(f"Failed to move do-not-release video {code}: {e}")

    # Summary report
    logger.info("\n=== Video Organization Summary ===")
    logger.info(f"Moved to channel directories: {moved_count}")
    logger.info(f"Moved to do_not_release: {dnr_count}")
    logger.info(f"Kept in downloads (no channel): {len(keep_in_downloads)}")
    logger.info(f"Missing video files: {len(missing_videos)}")

    if keep_in_downloads:
        logger.info("\nVideos kept in downloads (cannot determine channel):")
        for _, code, title in keep_in_downloads:
            logger.info(f"  {code}: {title}")

    if missing_videos:
        logger.info("\nMissing video files:")
        for code, title in missing_videos:
            logger.info(f"  {code}: {title}")


def report_unassigned_videos():
    """Report videos that could not be assigned to a channel"""
    video_map = video_code_map()
    tracks_map = load_tracks_map()
    confirmed_map = records.confirmed_sessions_map

    unassigned = []
    for code, info in confirmed_map.items():
        # Skip do-not-record videos
        if info.get("do_not_record", False):
            continue

        # Check if video exists and has no channel assignment
        if code in video_map and code not in tracks_map:
            unassigned.append(
                {
                    "code": code,
                    "title": info["title"],
                    "track": info.get("track", {}).get("en", "Unknown"),
                    "video_file": video_map[code].name,
                }
            )

    if unassigned:
        logger.info("\n=== Unassigned Videos Report ===")
        logger.info(f"Found {len(unassigned)} videos without channel assignment:\n")

        for video in unassigned:
            logger.info(f"Code: {video['code']}")
            logger.info(f"  Title: {video['title']}")
            logger.info(f"  Track: {video['track']}")
            logger.info(f"  File: {video['video_file']}")
            logger.info("")

        # Save report to file
        report_file = conf.dirs.video_dir / "unassigned_videos_report.json"
        with open(report_file, "w") as f:
            json.dump(unassigned, f, indent=2)
        logger.info(f"Report saved to: {report_file}")
    else:
        logger.info("All videos have been assigned to channels!")


if __name__ == "__main__":
    # Example workflow:

    # 1. Prepare data from pretalx
    # records.load_all_confirmed_sessions()
    # records.load_all_speakers()

    # 2. Assign videos to channels based on track
    # assign_video_to_channel()

    # 3. Move videos to channel directories
    # move_videos_to_upload_channel()

    # 4. Report on any unassigned videos
    # report_unassigned_videos()

    pass
