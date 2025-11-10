#!/usr/bin/env python3
"""
Convert PyCon session JSON data to Parquet format with recording matches.

This script takes session data exported from Pretalx in JSON format and creates
a Parquet file that maps sessions to their corresponding video recordings.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import polars as pl
from omegaconf import OmegaConf


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for cross-platform compatibility"""
    invalid_chars = r'<>:"/\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    filename = filename.replace(" ", "_")
    filename = filename.strip().strip(".")
    if len(filename) > 255:
        filename = filename[:255]
    return filename


def main(json_file: Path, output_file: Path, recordings_dir: Path):
    print(f"Loading JSON data from: {json_file}")

    # Load JSON data
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} sessions")

    # Normalize data before creating DataFrame
    # Handle fields that can be either strings or dicts with 'en' key
    for record in data:
        # Normalize Session type
        if "Session type" in record and isinstance(record["Session type"], dict):
            record["Session type"] = record["Session type"].get("en", "")
        
        # Normalize Track
        if "Track" in record and isinstance(record["Track"], dict):
            record["Track"] = record["Track"].get("en", "")
        
        # Normalize Room
        if "Room" in record and isinstance(record["Room"], dict):
            record["Room"] = record["Room"].get("en", "")

    # Convert to Polars DataFrame
    df = pl.DataFrame(data)

    # Get recordings list
    recordings = []
    if recordings_dir.exists():
        recordings = [f.name for f in recordings_dir.glob("*.mp4")]
        print(f"Found {len(recordings)} recordings in {recordings_dir}")
    else:
        print(f"Warning: Recordings directory not found: {recordings_dir}")

    # Function to extract day from date string
    def date_to_day(date_str: str) -> str | None:
        try:
            if date_str:
                # Handle ISO format: "2025-04-24T16:15:00+02:00" or "2025-04-24"
                if "T" in date_str:
                    date_str = date_str.split("T")[0]
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%A")
        except Exception:
            pass
        return None

    # Function to classify time period
    def classify_time(time_str: str, start_str: str = None) -> str | None:
        try:
            # Try to extract from full datetime string first
            if start_str and "T" in start_str:
                time_part = start_str.split("T")[1].split("+")[0]
                hour = int(time_part.split(":")[0])
            elif time_str:
                hour = int(time_str.split(":")[0])
            else:
                return None

            # Classify based on 24-hour clock (lunch at 13:00)
            return "Morning" if hour < 13 else "Afternoon"  # noqa: PLR2004
        except Exception:
            return None

    # Function to find matching recording
    def find_recording(room: str, day: str, time_period: str) -> str | None:
        if not room or not day or not time_period:
            return None

        # Extract room name from dict if needed
        if isinstance(room, dict) and "en" in room:
            room = room["en"]

        # Handle special case for Zeiss Plenary
        room_for_recording = "Zeiss Plenary (Spectrum)" if "Zeiss" in str(room) else str(room)

        # Check for variation in naming convention
        prefix = (
            "PyConDE & PyData 2025"
            if str(room) in ["Dynamicum", "Ferrum", "Zeiss Plenary (Spectrum)"]
            else "PyCon DE & PyData 2025"
        )

        # Format the recording name
        recording_name = f"{prefix} - {room_for_recording} - {day} {time_period}.mp4"
        return recording_name if recording_name in recordings else None

    # Room is already extracted as a string, no need for Room

    # Add Day and TimePeriod columns
    df = df.with_columns(
        [
            pl.col("Start (date)").map_elements(date_to_day, return_dtype=pl.String).alias("Day"),
            pl.struct(["Start (time)", "Start"])
            .map_elements(lambda x: classify_time(x["Start (time)"], x["Start"]), return_dtype=pl.String)
            .alias("TimePeriod"),
        ]
    )

    # Add Recording column
    df = df.with_columns(
        [
            pl.struct(["Room", "Day", "TimePeriod"])
            .map_elements(lambda x: find_recording(x["Room"], x["Day"], x["TimePeriod"]), return_dtype=pl.String)
            .alias("Recording")
        ]
    )

    # Add sequential numbering per room/day/time group (not per recording)
    # This ensures all sessions get sequential numbers even without video matches
    df = df.with_columns([pl.int_range(pl.len()).over(["Room", "Day", "TimePeriod"]).alias("_seq")])

    # ALWAYS create Output_Folder for ALL sessions (not just matched ones)
    # Handle null values gracefully
    df = df.with_columns(
        [
            pl.when(pl.col("Day").is_not_null() & pl.col("TimePeriod").is_not_null() & pl.col("Room").is_not_null())
            .then(pl.concat_str([pl.col("Day"), pl.lit("-"), pl.col("TimePeriod"), pl.lit("-"), pl.col("Room")]))
            .otherwise(pl.lit("Unscheduled"))
            .map_elements(sanitize_filename, return_dtype=pl.String)
            .alias("Output_Folder")
        ]
    )

    # ALWAYS create Sequential_Filename for ALL sessions (not just matched ones)
    # This ensures flexible matching works with any video filename
    df = df.with_columns(
        [
            pl.when(pl.col("Proposal title").is_not_null() & pl.col("ID").is_not_null())
            .then(
                pl.concat_str(
                    [
                        (pl.col("_seq") + 1).cast(pl.String).str.pad_start(3, "0"),
                        pl.lit("_-_"),
                        pl.col("Proposal title"),
                        pl.lit("_["),
                        pl.col("ID"),
                        pl.lit("].mp4"),
                    ]
                )
            )
            .otherwise(
                pl.concat_str(
                    [
                        (pl.col("_seq") + 1).cast(pl.String).str.pad_start(3, "0"),
                        pl.lit("_-_"),
                        pl.lit("Unknown_Session"),
                        pl.lit(".mp4"),
                    ]
                )
            )
            .map_elements(sanitize_filename, return_dtype=pl.String)
            .alias("Sequential_Filename")
        ]
    )

    # Remove temporary columns
    df = df.drop(["_seq"])

    # Save as Parquet
    df.write_parquet(output_file)
    print(f"Saved parquet file to: {output_file}")

    # Save as Excel for review
    output_excel = output_file.with_suffix(".xlsx")
    df.write_excel(output_excel)
    print(f"Saved Excel file to: {output_excel}")

    # Print statistics
    matched = df.filter(pl.col("Recording").is_not_null()).height
    total = df.height
    print(f"\nMatched {matched} out of {total} sessions ({matched / total * 100:.1f}%)")

    # Show sample results
    print("\nSample results:")
    sample = df.select(["ID", "Proposal title", "Room", "Day", "TimePeriod", "Recording", "Sequential_Filename"]).head(
        5
    )
    print(sample)

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Pretalx JSON export to Parquet with video recording matches")
    parser.add_argument("json_file", type=Path, help="Path to JSON file exported from Pretalx")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default="src/video_processor/config.yaml",
        help="Config file path (default: src/video_processor/config.yaml)",
    )

    args = parser.parse_args()

    # Load config
    if not args.config.exists():
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(1)

    config = OmegaConf.load(args.config)
    base_dir = Path(config.base_dir)

    # Input JSON file
    json_file = args.json_file
    if not json_file.exists():
        print(f"ERROR: JSON file not found: {json_file}")
        sys.exit(1)

    # Output file is always in base_dir with the name from config
    output_file = base_dir / config.input.mapping_file

    # Recordings directory from config
    recordings_dir = base_dir / config.input.subfolder

    if not recordings_dir.exists():
        print(f"Warning: Recordings directory not found: {recordings_dir}")
        print("Parquet will be created without recording matches.")

    # Create output directory if needed
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"\nConfiguration from {args.config}:")
    print(f"  Base directory: {base_dir}")
    print(f"  Input JSON: {json_file}")
    print(f"  Output Parquet: {output_file}")
    print(f"  Recordings Dir: {recordings_dir}")
    print()

    main(json_file, output_file, recordings_dir)
