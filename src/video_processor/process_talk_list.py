#!/usr/bin/env python3
"""
PyCon Session Recording Matcher - Fixed Version

This script matches PyCon DE & PyData 2025 conference sessions to their corresponding
recordings based on the room and time slot.

# TODO use json to read data
Input: Export from pretalx, read in excel: pycondepydata2025_sessions.xlsx (Excel file with session information)
Output: pycondepydata2025_sessions_with_recordings.parquet (Original data with recording match and output columns)
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import polars as pl
import yaml
from omegaconf import OmegaConf

from manager import logger
from video_processor import map_recordings, room_mapping

# Matches a bracketed annotation at the end of a room name, e.g. " [3rd Floor]".
_ROOM_ANNOTATION_RE = re.compile(r"\s*\[[^\]]*\]\s*")

def _load_recording_mapping(mapping_yaml: Path) -> dict[tuple[str, str, str], str]:
    """Invert the filename->classification YAML into a (room, day, period) -> filename lookup."""
    if not mapping_yaml.exists():
        raise FileNotFoundError(
            f"pretalx.recording_mapping_yaml points to a missing file: {mapping_yaml}. "
            "Run `pytube video map-recordings` (or `python src/video_processor/map_recordings.py`) first."
        )
    with mapping_yaml.open() as f:
        data = yaml.safe_load(f) or {}
    recordings = data.get("recordings") or {}
    inverted: dict[tuple[str, str, str], str] = {}
    for filename, meta in recordings.items():
        key = (str(meta["room"]), str(meta["day"]), str(meta["period"]))
        if key in inverted and inverted[key] != filename:
            logger.info(
                f"Duplicate mapping for {key}: {inverted[key]!r} and {filename!r}; keeping first"
            )
            continue
        inverted[key] = filename
    return inverted


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for cross-platform compatibility

    Removes invalid characters and replaces spaces with underscores
    """
    # Remove invalid characters for Windows/Mac/Linux
    invalid_chars = r'<>:"/\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Replace spaces with underscores
    filename = filename.replace(" ", "_")

    # Remove leading/trailing spaces and dots
    filename = filename.strip().strip(".")

    # Limit length to 255 characters (Windows limit)
    if len(filename) > 255:
        filename = filename[:255]

    return filename


def main(
    input_file: str | Path,
    output_file: str | Path,
    recordings_dir: str | Path,
    cfg: OmegaConf | None = None,
) -> None:
    if cfg is None:
        cfg = _load_config()
    mapping_yaml = OmegaConf.select(cfg, "pretalx.recording_mapping_yaml", default="")
    if not mapping_yaml:
        raise ValueError(
            "pretalx.recording_mapping_yaml is not set. "
            "Add it to config.yaml / config_local.yaml."
        )
    mapping_path = Path(mapping_yaml)
    if not mapping_path.exists():
        logger.info(f"Step 1/2: No mapping YAML at {mapping_path} — generating from filenames.")
        map_recordings.run(dry_run=False, force=False)
        logger.info(
            f"Mapping written to {mapping_path}. Review and hand-edit for typos / unclassified "
            "entries, then re-run this script to produce the session Parquet."
        )
        return
    if sys.stdin.isatty():
        answer = input(
            f"Step 1/2: Mapping YAML already exists at {mapping_path}.\n"
            "Regenerate? Hand edits WILL be lost. [y/N]: "
        ).strip().lower()
        if answer in ("y", "yes"):
            map_recordings.run(dry_run=False, force=True)
            logger.info(
                f"Mapping regenerated at {mapping_path}. Review and hand-edit, then re-run."
            )
            return
        logger.info("Step 1/2: Keeping existing mapping.")
    else:
        logger.info(
            f"Step 1/2: Using existing mapping at {mapping_path}. "
            "Run `pytube video map-recordings --force` to regenerate."
        )
    logger.info("Step 2/2: Matching sessions against mapping and writing Parquet.")
    recording_by_triple = _load_recording_mapping(mapping_path)

    logger.info("Loading session data...")

    df = pl.read_csv(input_file, infer_schema_length=0)

    # Cast all columns to string type
    df = df.with_columns([pl.col(col).cast(pl.String) for col in df.columns])

    # logger.info some information about the data
    logger.info(f"Loaded {df.shape[0]} sessions")

    # Ensure the Pretalx Room -> short-form mapping YAML exists (prompt before replace).
    unique_rooms = [r for r in df["Room"].drop_nulls().unique().to_list() if r]
    room_mapping.generate(unique_rooms)

    # Read recordings from directory
    recordings_path = Path(recordings_dir)
    if not recordings_path.exists():
        raise FileNotFoundError(f"Recordings directory not found: {recordings_path}")

    # Get all MP4 files in the recordings directory
    recordings = [file.name for file in recordings_path.glob("*.mp4")]

    if not recordings:
        logger.info(f"Warning: No MP4 files found in {recordings_path}")
    else:
        logger.info(f"Found {len(recordings)} recordings in {recordings_path}")

    # logger.info first few recordings for verification
    for rec in sorted(recordings)[:5]:
        logger.info(f"{rec}")
    if len(recordings) > 5:
        logger.info(f"... and {len(recordings) - 5} more")

    logger.info(f"Columns in the data: {df.columns}")

    # Function to handle both date and datetime objects
    def date_to_day(date_obj: str | datetime | None) -> str | None:
        try:
            # Since we're reading as string, we expect strings
            if isinstance(date_obj, str):
                # Handle different date formats
                if "/" in date_obj:
                    # Format: MM/DD/YY
                    parts = date_obj.split("/")
                    if len(parts) == 3 and len(parts[2]) == 2:
                        date_obj = datetime.strptime(date_obj, "%m/%d/%y")
                    else:
                        date_obj = datetime.strptime(date_obj, "%m/%d/%Y")
                elif "-" in date_obj:
                    # Format: YYYY-MM-DD
                    date_obj = datetime.strptime(date_obj, "%Y-%m-%d")
                else:
                    return None
                return date_obj.strftime("%A")
            else:
                return None
        except Exception as e:
            logger.info(f"Error parsing date {date_obj}: {e}")
            return None

    def classify_time(time_obj: str | None) -> str | None:
        if not isinstance(time_obj, str) or not time_obj.strip():
            return None
        try:
            # Accept "HH:MM[:SS]" and Excel-style "1899-12-31 HH:MM:SS.000".
            hour = int(time_obj.split(" ")[-1].split(":")[0])
            return "Morning" if hour < cfg.event.lunch_break_cut else "Afternoon"
        except Exception as e:
            logger.info(f"Error parsing time {time_obj}: {e}")
            return None

    def find_recording(room: str, day: str, time_period: str) -> str | None:
        if not room or not day or not time_period:
            return None
        # Strip bracketed annotations from room names, e.g. "Europium [3rd Floor]" -> "Europium".
        room_clean = _ROOM_ANNOTATION_RE.sub("", str(room)).strip()
        return recording_by_triple.get((room_clean, day, time_period))

    logger.info("Processing session data...")

    # Add columns for day of week and time period
    df = df.with_columns(
        [
            pl.col("Start (date)")
            .map_elements(lambda x: date_to_day(x) if x is not None else None, return_dtype=pl.String)
            .alias("Day"),
            pl.col("Start (time)")
            .map_elements(lambda x: classify_time(x) if x is not None else None, return_dtype=pl.String)
            .alias("TimePeriod"),
        ]
    )

    # Add column for recording name
    df = df.with_columns(
        [
            pl.struct(["Room", "Day", "TimePeriod"])
            .map_elements(
                lambda x: find_recording(
                    x.get("Room") if x and "Room" in x else None,
                    x.get("Day") if x and "Day" in x else None,
                    x.get("TimePeriod") if x and "TimePeriod" in x else None,
                ),
                return_dtype=pl.String,
            )
            .alias("Recording")
        ]
    )

    # Add column for sequential filename
    # Group by recording and add sequential numbers
    df = df.with_columns([pl.int_range(pl.len()).over("Recording").alias("_seq")])

    # Room without bracket annotations for folder names (e.g. "Europium [3rd Floor]" -> "Europium")
    df = df.with_columns(
        [
            pl.col("Room")
            .map_elements(
                lambda r: _ROOM_ANNOTATION_RE.sub("", str(r)).strip() if r is not None else None,
                return_dtype=pl.String,
            )
            .alias("_room_clean"),
        ]
    )

    # Output directory: Room-Day-TimePeriod (sanitized)
    df = df.with_columns(
        [
            pl.when(pl.col("Recording").is_not_null())
            .then(
                pl.concat_str(
                    pl.col("_room_clean"),
                    pl.lit("-"),
                    pl.col("Day"),
                    pl.lit("-"),
                    pl.col("TimePeriod"),
                )
            )
            .otherwise(None)
            .map_elements(sanitize_filename, return_dtype=pl.String)
            .alias("Output_Folder")
        ]
    )
    df = df.drop("_room_clean")
    # Create sequential filenames
    df = df.with_columns(
        [
            pl.when(pl.col("Recording").is_not_null())
            .then(
                pl.concat_str(
                    [
                        # Remove the conference prefix and .mp4 extension
                        (pl.col("_seq") + 1).cast(pl.String).str.pad_start(3, "0"),  # Add 3-digit number
                        pl.lit(" - "),
                        pl.col("Proposal title"),
                        pl.lit(" ["),
                        pl.col("ID"),
                        pl.lit("]"),
                        pl.lit(".mp4"),
                    ]
                )
            )
            .otherwise(None)
            .map_elements(sanitize_filename, return_dtype=pl.String)
            .alias("Sequential_Filename")
        ]
    )

    # Remove the temporary sequence column
    df = df.drop("_seq")

    # Save as Parquet, this is the main exchange file
    parquet_file = output_file.with_suffix(".parquet")
    df.write_parquet(parquet_file)
    logger.info(f"Results also saved as Parquet to {parquet_file}")

    # Write a human-readable YAML of sessions that couldn't be matched to a recording.
    # Each entry lists what (Room, Day, TimePeriod) the matcher looked for — use this
    # to find the entry to add/fix in recording_mapping_yaml.
    missing_df = (
        df.filter(pl.col("Recording").is_null())
        .select(["ID", "Proposal title", "Room", "Day", "TimePeriod", "Start (date)", "Start (time)"])
        .sort(["Day", "TimePeriod", "Room", "Start (time)"])
    )
    missing_entries = [
        {
            "id": row["ID"],
            "title": row["Proposal title"],
            "room": row["Room"],
            "day": row["Day"],
            "period": row["TimePeriod"],
            "start_date": row["Start (date)"],
            "start_time": row["Start (time)"],
        }
        for row in missing_df.iter_rows(named=True)
    ]
    missing_yaml = output_file.with_name(f"{output_file.stem}_missing.yaml")
    with missing_yaml.open("w") as f:
        f.write(
            f"# {len(missing_entries)} sessions without a matching recording.\n"
            "# Hand-edit recording_mapping_yaml to fix (typos, unclassified entries),\n"
            "# then re-run process_talk_list.py.\n\n"
        )
        yaml.safe_dump(
            {"missing": missing_entries}, f, sort_keys=False, allow_unicode=True, default_flow_style=False
        )
    logger.info(f"Unmatched sessions written to {missing_yaml} ({len(missing_entries)} rows)")

    # logger.info some stats
    matched = df.filter(pl.col("Recording").is_not_null()).height
    total = df.height
    logger.info(f"Matched {matched} out of {total} sessions ({matched / total * 100:.1f}%)")

    # logger.info unique rooms found
    unique_rooms = df["Room"].unique().to_list()
    logger.info(f"Unique rooms found: {sorted([str(r) for r in unique_rooms if r])}")

    # logger.info sample matching results
    logger.info("\nSample matching results:")
    sample_df = df.select(["Proposal title", "Room", "Day", "TimePeriod", "Recording", "Sequential_Filename"]).head(10)
    logger.info(sample_df)


def _load_config() -> OmegaConf:
    """Load config.yaml, merging config_local.yaml on top if it exists."""
    cfg = OmegaConf.load("config.yaml")
    local_path = Path("config_local.yaml")
    if local_path.exists():
        cfg = OmegaConf.merge(cfg, OmegaConf.load(local_path))
    return cfg


if __name__ == "__main__":
    cfg = _load_config()

    sessions_csv = OmegaConf.select(cfg, "pretalx.sessions_csv", default="")
    if not sessions_csv:
        raise ValueError(
            "pretalx.sessions_csv is not set. "
            "Add it to config_local.yaml — path to the Pretalx confirmed-sessions CSV export."
        )
    _input_file = Path(sessions_csv)
    if not _input_file.exists():
        raise FileNotFoundError(f"pretalx.sessions_csv points to a missing file: {_input_file}")

    recordings_dir = OmegaConf.select(cfg, "vimeo.raw_sources.download.output_dir", default="")
    if not recordings_dir:
        raise ValueError(
            "vimeo.raw_sources.download.output_dir is not set. "
            "Add it to config_local.yaml — must equal the folder Stage 1 (bulk-download) writes into."
        )
    _recordings_dir = Path(recordings_dir)

    _output_file = _input_file.parent / f"{_input_file.stem}_processed{_input_file.suffix}"

    main(_input_file, _output_file, _recordings_dir, cfg)
