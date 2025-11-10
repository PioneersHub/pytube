#!/usr/bin/env python3
"""
PyCon Session Recording Matcher - Fixed Version

This script matches PyCon DE & PyData 2025 conference sessions to their corresponding
recordings based on the room and time slot.

# TODO use json to read data
Input: Export from pretalx, read in excel: pycondepydata2025_sessions.xlsx (Excel file with session information)
Output: pycondepydata2025_sessions_with_recordings.parquet (Original data with recording match and output columns)
"""

from datetime import datetime
from pathlib import Path

import polars as pl
from omegaconf import OmegaConf

import logging

# Set up logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(message)s')


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


def main(input_file: str | Path, output_file: str | Path, recordings_dir: str | Path) -> None:
    # Load the session data from JSON file
    logger.info("Loading session data...")

    # Read the JSON file
    df = pl.read_json(input_file)
    
    # Extract 'en' attribute from all struct/dict columns (Room and other multilingual fields)
    for col_name, col_type in df.schema.items():
        if isinstance(col_type, pl.Struct):
            # Check if the struct has an 'en' field
            struct_fields = {field.name for field in col_type.fields}
            if 'en' in struct_fields:
                df = df.with_columns(pl.col(col_name).struct.field("en").alias(col_name))
    
    # Cast columns to string type (skip list columns)
    for col_name, col_type in df.schema.items():
        if not isinstance(col_type, pl.List):
            df = df.with_columns(pl.col(col_name).cast(pl.String))

    # logger.info some information about the data
    logger.info(f"Loaded {df.shape[0]} sessions")

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

    # Function to handle both time and datetime objects
    def classify_time(time_obj: str | datetime | None) -> str | None:
        try:
            # Since we're reading as string, we expect strings
            if isinstance(time_obj, str):
                # Handle the Excel datetime format like "1899-12-31 16:15:00.000"
                # Extract just the time part
                time_part = time_obj.split(" ")[1]
                hour = int(time_part.split(":")[0])

                # Classify based on 24-hour clock
                if hour < cfg.event.lunch_break_cut:
                    return "Morning"
                else:
                    return "Afternoon"
            else:
                return None
        except Exception as e:
            logger.info(f"Error parsing time {time_obj}: {e}")
            return None

    # Function to find the matching recording for a session
    def find_recording(room: str, day: str, time_period: str) -> str | None:
        if not room or not day or not time_period:
            return None

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

    # Output directory
    df = df.with_columns(
        [
            pl.when(pl.col("Recording").is_not_null())
            .then(
                pl.concat_str(
                    pl.col("Day"),
                    pl.lit("-"),
                    pl.col("TimePeriod"),
                    pl.lit("-"),
                    pl.col("Room"),
                )
            )
            .otherwise(None)
            .map_elements(sanitize_filename, return_dtype=pl.String)
            .alias("Output_Folder")
        ]
    )
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


if __name__ == "__main__":
    cfg = OmegaConf.load("config.yaml")
    _input_file = "/Users/hendorf/Downloads/videos/pyconde-pydata-2025_sessions.json"
    _input_file = Path(_input_file)
    # Specify the directory containing the recordings
    _recordings_dir = "/Users/hendorf/code/pioneershub/py_tube/_data/videos/input"
    _recordings_dir = Path(_recordings_dir)
    _output_file = _recordings_dir.parent / f"{_input_file.stem}_processed{_input_file.suffix}"

    main(_input_file, _output_file, _recordings_dir)
