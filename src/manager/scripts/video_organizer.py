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
import random
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
import yaml

from manager import conf, logger
from manager.handlers.records import Records

records = Records()


def call_claude_api(title: str, abstract: str) -> str | None:
    """Call Claude API to determine channel assignment.

    Returns 'pycon' or 'pydata', or None on error.
    """
    api_key = conf.get("anthropic", {}).get("api_key", "")
    if not api_key:
        logger.warning("No Anthropic API key configured")
        return None

    prompt = conf.claude.prompt.format(title=title, abstract=abstract)

    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": conf.get("anthropic", {}).get("model", "claude-3-haiku-20240307"),
                "max_tokens": 10,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=10.0,
        )
        response.raise_for_status()

        content = response.json()["content"][0]["text"].strip()

        # Map response to channel names
        if content == "PyCon DE":
            return "pycon"
        elif content == "PyData":
            return "pydata"
        else:
            logger.warning(f"Unexpected Claude response: {content}")
            return None

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return None


def call_openai_api(title: str, abstract: str) -> str | None:
    """Call OpenAI API to determine channel assignment.

    Returns 'pycon' or 'pydata', or None on error.
    """
    api_key = conf.get("openai", {}).get("api_key", "")
    if not api_key:
        logger.warning("No OpenAI API key configured")
        return None

    prompt = conf.claude.prompt.format(title=title, abstract=abstract)

    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": conf.get("openai", {}).get("model", "gpt-4-turbo"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 10,
                "temperature": 0,
            },
            timeout=10.0,
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"].strip()

        # Map response to channel names
        if content == "PyCon DE":
            return "pycon"
        elif content == "PyData":
            return "pydata"
        else:
            logger.warning(f"Unexpected OpenAI response: {content}")
            return None

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return None


def match_video_heuristically(video: dict) -> tuple[str | None, str]:
    """Use AI APIs to determine channel based on title and abstract.

    Tries both Claude and OpenAI. If they agree, returns the result.
    If they disagree, returns a random choice between them.
    If both fail, returns None.

    Returns:
        Tuple of (channel, method) where method is one of:
        'claude', 'openai', 'consensus', 'random', or 'failed'
    """
    title = video.get("title", "")
    abstract = video.get("abstract", "") or video.get("description", "")
    code = video.get("code", "UNKNOWN")

    if not title or not abstract:
        return None, "failed"

    # Log that we're making API calls
    logger.info(f"🤖 Calling AI APIs for {code}: {title[:50]}...")

    # Get predictions from both models
    claude_result = call_claude_api(title, abstract)
    openai_result = call_openai_api(title, abstract)

    # Log the results for debugging
    logger.debug(f"Heuristic matching for {code}: Claude={claude_result}, OpenAI={openai_result}")

    # If both failed, return None
    if claude_result is None and openai_result is None:
        logger.warning(f"Both AI APIs failed for {code}")
        return None, "failed"

    # If only one succeeded, use it
    if claude_result is None:
        return openai_result, "openai"
    if openai_result is None:
        return claude_result, "claude"

    # If both succeeded and agree, use the consensus
    if claude_result == openai_result:
        logger.debug(f"AI consensus for {code}: {claude_result}")
        return claude_result, "consensus"

    # If they disagree, pick randomly
    result = random.choice([claude_result, openai_result])
    chosen_model = "claude" if result == claude_result else "openai"
    logger.info(
        f"AI disagreement for {code}: Claude={claude_result}, OpenAI={openai_result}, chose {result} (from {chosen_model})"
    )
    return result, "random"


def split_pycon_pydata(video: dict) -> str | None:
    """Assign videos to PyData or PyCon via the track.

    In case this cannot be done by track,
    add the pretalx code in the config.
    """
    code = video["code"]

    # Check direct mapping first
    if code in conf.pretalx.video_to_track:
        return conf.pretalx.video_to_track[code]

    # Handle missing or null track
    if not video.get("track"):
        logger.debug(f"No track for {code}")
        return None

    # Get track name - it's in track.name.en
    track_name = video["track"]["name"]["en"]

    # Check track patterns
    if track_name:
        for snippet in conf.pretalx.track_to_channel:
            if snippet.casefold() in track_name.casefold():
                return conf.pretalx.track_to_channel[snippet]

    # Log unmatched video
    title = video.get("title", "Unknown")
    logger.debug(f"No channel match for {code}: track='{track_name}', title='{title}'")
    return None


def assign_video_to_channel(
    dry_run: bool = False, use_heuristics: bool = True, progress_callback=None
) -> tuple[dict[str | None, list[dict]], dict[str, str]]:
    """Analyze sessions and determine YouTube channel assignments.

    Args:
        dry_run: If True, don't save files
        use_heuristics: If True, use AI for unmatched videos
        progress_callback: Optional callback(current, total, message) for progress updates

    Returns tuple of:
    - dict mapping channel names to lists of session data
    - dict mapping code to assignment method ("track", "claude", "openai", "consensus", "random", "single_channel")
    """
    collect_tracks = defaultdict(list)
    collect_tracks_map = {}
    assignment_methods = {}

    # Load confirmed sessions
    records.load_all_confirmed_sessions()
    total_sessions = len(records.confirmed_sessions_map)

    # Check if only one channel is configured
    youtube_channels = conf.get("youtube", {}).get("channels", {})
    channel_names = [name for name in youtube_channels if name != "do_not_release"]

    if len(channel_names) == 1:
        # Single channel mode - assign all videos to this channel
        single_channel = channel_names[0]
        logger.info(f"Single channel mode detected: '{single_channel}' - skipping all heuristics")

    # Process each session
    for idx, (code, session_data) in enumerate(records.confirmed_sessions_map.items()):
        title = session_data.get("title", "Unknown")[:60]  # Truncate long titles

        # Update progress
        if progress_callback:
            progress_callback(idx + 1, total_sessions, f"Processing: {code} - {title}")

        # Check do_not_record first - these go to no_publishing channel
        if session_data.get("do_not_record", False):
            track = "no_publishing"
            assignment_methods[code] = "do_not_record"
        elif len(channel_names) == 1:
            # Single channel mode - assign to the only channel
            track = single_channel
            assignment_methods[code] = "single_channel"
        else:
            # Try track-based matching first
            track = split_pycon_pydata(session_data)

            if track:
                assignment_methods[code] = "track"
            elif use_heuristics:
                # Update progress for API call
                if progress_callback:
                    progress_callback(idx + 1, total_sessions, f"🤖 AI matching: {code} - {title}")

                # Try heuristic matching
                track, method = match_video_heuristically(session_data)
                if track:
                    assignment_methods[code] = method

        collect_tracks[track].append(session_data)
        if track:
            collect_tracks_map[code] = track

    # Save mapping files only if not dry run
    if not dry_run:
        video_dir = Path(conf.dirs.video_dir)
        video_dir.mkdir(parents=True, exist_ok=True)

        (video_dir / "tracks.json").write_text(json.dumps(collect_tracks, indent=4))
        (video_dir / "tracks_map.json").write_text(json.dumps(collect_tracks_map, indent=4))

    return collect_tracks, assignment_methods


def generate_assignment_report(collect_tracks: dict, assignment_methods: dict, video_map: dict | None = None) -> None:
    """Generate YAML report of channel assignments.

    Args:
        collect_tracks: Channel assignments from assign_video_to_channel
        assignment_methods: How each video was matched
        video_map: Optional mapping of codes to video files
    """
    report = {"pyconde": [], "pydata": [], "no_publishing": [], "unmatched": []}

    # Build report structure
    for channel, videos in collect_tracks.items():
        for video in videos:
            code = video["code"]
            # Get track name safely
            track_name = None
            if video.get("track") and video["track"].get("name") and video["track"]["name"].get("en"):
                track_name = video["track"]["name"]["en"]

            entry = {
                "talk": video.get("title", "Unknown"),
                "code": code,
                "track": track_name,
                "filename": video_map.get(code).name if video_map and code in video_map else None,
                "matched_via": assignment_methods.get(code, "none"),
            }

            if channel == "pycon":
                report["pyconde"].append(entry)
            elif channel == "pydata":
                report["pydata"].append(entry)
            elif channel == "no_publishing":
                report["no_publishing"].append(entry)
            else:
                report["unmatched"].append(entry)

    # Save YAML report
    event_dir = Path(conf.dirs.work_dir) / conf.pretalx.event_slug
    event_dir.mkdir(parents=True, exist_ok=True)

    report_file = event_dir / "channel_assignments.yaml"
    report_file.write_text(yaml.dump(report, default_flow_style=False, sort_keys=False))

    logger.info(f"Saved channel assignment report to {report_file}")

    # Log statistics
    track_count = sum(1 for v in assignment_methods.values() if v == "track")
    single_channel_count = sum(1 for v in assignment_methods.values() if v == "single_channel")
    claude_count = sum(1 for v in assignment_methods.values() if v == "claude")
    openai_count = sum(1 for v in assignment_methods.values() if v == "openai")
    consensus_count = sum(1 for v in assignment_methods.values() if v == "consensus")
    random_count = sum(1 for v in assignment_methods.values() if v == "random")
    unmatched_count = len(report["unmatched"])

    logger.info("Assignment statistics:")
    if single_channel_count > 0:
        logger.info(f"  Single channel: {single_channel_count}")
    logger.info(f"  Track-based: {track_count}")
    logger.info(f"  AI Consensus: {consensus_count}")
    logger.info(f"  Claude only: {claude_count}")
    logger.info(f"  OpenAI only: {openai_count}")
    logger.info(f"  Random (disagreement): {random_count}")
    logger.info(f"  Unmatched: {unmatched_count}")


def load_tracks_map() -> dict:
    the_file = conf.dirs.video_dir / "tracks_map.json"
    if not the_file.exists():
        logger.error(f"File {the_file} does not exist, did you run `assign_video_to_channel`?")
        return {}
    return json.load(the_file.open())


def video_code_map() -> dict[Any, Any]:
    """Mapping of all downloaded videos using first 6 characters of filename"""
    downloads_dir = Path(conf.dirs.video_dir / "downloads")
    video_extensions = ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm", "*.m4v"]

    downloaded = []
    for pattern in video_extensions:
        downloaded.extend(downloads_dir.glob(pattern))

    return {x.stem[:6]: x for x in downloaded}


def move_videos_to_upload_channel(dry_run=False, progress_callback=None):
    """Move all videos to the correct channel directories

    Args:
        dry_run: If True, only simulate moves without actually moving files
        progress_callback: Optional callback(current, total, message) for progress updates

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
    for idx, (code, info) in enumerate(confirmed_map.items()):
        title = info["title"]

        # Update progress
        if progress_callback:
            progress_callback(idx + 1, len(confirmed_map), f"Analyzing: {code} - {title[:50]}...")

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
            logger.debug(f"Video file missing for {code}: {title}")
            continue

        # Check if we can determine the channel
        if code not in tracks_map:
            keep_in_downloads.append((video_map[code], code, title))
            logger.debug(f"Cannot determine channel for {code}: {title}")
            continue

        # Video can be moved to channel directory
        channel = tracks_map[code]

        # Handle no_publishing channel - these go to do_not_release
        if channel == "no_publishing":
            move_to_dnr.append((video_map[code], code, title))
            logger.debug(f"{code} -> do_not_release (no_publishing): {title}")
        else:
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
    total_moves = len(move_to_channel) + len(move_to_dnr)
    current_move = 0

    for src_path, code, channel, _ in move_to_channel:
        current_move += 1
        if progress_callback:
            progress_callback(current_move, total_moves, f"Moving to {channel}: {code} - {src_path.name}")

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
    for src_path, code, _ in move_to_dnr:
        current_move += 1
        if progress_callback:
            progress_callback(current_move, total_moves, f"Moving to do_not_release: {code} - {src_path.name}")

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

    # Return statistics for CLI to display
    return {
        "moved": moved_count,
        "dnr": dnr_count,
        "kept": len(keep_in_downloads),
        "missing": missing_videos,
        "dry_run": dry_run,
    }


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
