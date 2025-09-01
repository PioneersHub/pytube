# Video Processor Module

The `video_processor` module provides tools for automatically processing conference video recordings, detecting individual presentations, and organizing them for publication.

## Overview

This module handles two main tasks:
1. **Session Matching**: Maps conference sessions from Pretalx to their corresponding video recordings
2. **Presentation Detection**: Automatically detects and extracts individual talks from long conference recordings

## Components

### 1. video_splitter.py (Recommended)

Streamlined video splitter that processes conference videos one at a time with immediate extraction and automatic skip logic for already processed videos.

#### Features
- **Single-video processing**: Process one video, extract immediately
- **Skip processed videos**: Maintains `.processed_videos.json` to avoid reprocessing
- **Skip existing files**: Won't re-extract segments that already exist
- **Simple and clean**: No complex plan generation, just detect and extract
- **Progress tracking**: Shows real-time progress with tqdm
- **Immediate extraction**: Cuts are made as soon as transitions are found

#### Usage
```bash
# Process all videos in input folder
python -m src.video_processor.video_splitter --config config.yaml

# Process a single video
python -m src.video_processor.video_splitter --config config.yaml --video /path/to/video.mp4

# Reset processed list and start fresh
python -m src.video_processor.video_splitter --config config.yaml --reset
```

### 2. presentation_detector.py (Legacy)

Automatically detects and extracts individual presentations from long conference recordings by finding transitions between break screens and presentations.

#### Features
- **Auto-detection of break screens**: Automatically identifies recurring break/pause screens in videos
- **Binary search for precision**: Uses binary search to find exact transition points between segments
- **Batch processing**: Process multiple videos in a single run
- **Multiple output formats**: Extract as video files and/or MP3 audio
- **Metadata generation**: Creates JSON metadata for all detected presentations

#### Usage
```bash
python -m src.video_processor.presentation_detector --config config.yaml
```

#### Command-line Options
- `--config`: Path to configuration file (default: config.yaml)
- `--output`: Override output folder from config
- `--break-images`: Directory containing break screen images (overrides config)
- `--extract`: Force extraction of presentations
- `--audio` or `-a`: Extract audio as MP3
- `--input-folder` or `-i`: Process all videos in specified folder

### 2. json_to_parquet.py

Converts Pretalx JSON export to Parquet format with video recording matches.

#### Features
- Reads session data from JSON export (recommended format)
- Matches sessions to recordings by room, day, and time period
- Generates sequential filenames for organization
- Creates mapping for video processing pipeline
- Fully configurable via command-line arguments

#### Usage
```bash
# Convert JSON to Parquet (output location is defined in config.yaml)
python -m src.video_processor.json_to_parquet sessions.json

# Use custom config file if needed
python -m src.video_processor.json_to_parquet sessions.json -c custom_config.yaml
```

### 3. process_talk_list.py

Legacy script that matches conference sessions from Excel export to video recordings.

#### Features
- Reads session data from Excel export (legacy format)
- Matches sessions to recordings by room, day, and time period
- Generates sequential filenames for organization
- Creates folder structure for output
- Exports mapping as Parquet file for further processing

#### Usage
```python
python -m src.video_processor.process_talk_list
```

**Note**: For new projects, use `json_to_parquet.py` with JSON exports instead.

### 4. config.yaml

Central configuration file controlling all tools. Uses a base directory to avoid path redundancy.

#### Key Configuration Sections

##### Base Configuration
```yaml
# All paths are relative to this base directory
base_dir: "/Users/hendorf/Downloads/videos"

input:
  subfolder: "input"                      # Videos are in base_dir/input
  extensions: "mp4,mkv,avi,mov,webm"      # Video formats to process
  mapping_file: "sessions_processed.parquet" # Mapping file in base_dir
```

##### Break Detection
```yaml
break_detection:
  images_dir: "/path/to/break/screens"    # Pre-defined break screen images (optional)
  threshold: 0.95                         # Similarity threshold (0-1)
  comparison_method: "template"           # "template" or "histogram"
  auto_detect: true                       # Auto-detect if no images provided
  detected_screens_dir: "/path/to/save"   # Where to save detected screens
```

##### Presentation Detection
```yaml
presentation_detection:
  min_interval: 2                         # Minimum precision in seconds
  chunk_size: 300                         # Initial search chunks (seconds)
  sampling_interval: 30                   # Frame sampling interval
  max_samples: 200                        # Max samples for break detection
  cluster_threshold: 0.90                 # Clustering threshold for breaks
```

##### Output Settings
```yaml
output:
  folder: "/path/to/output"               # Base output directory
  make_processing_plan: false             # Detect without extracting
  extract_presentations: true              # Extract detected segments
  extract_audio: true                     # Also extract as MP3
  save_metadata: true                     # Save detection metadata
```

##### Event Settings
```yaml
event:
  lunch_break_cut: 13                     # Hour dividing morning/afternoon (24hr)
```

## Streamlined Workflow (Recommended)

### Step 1: Export and Convert Session Data
```bash
# Export from Pretalx as JSON and create parquet with mappings
python -m src.video_processor.json_to_parquet /path/to/sessions.json \
    -r "/path/to/video/recordings" \
    -o /path/to/output.parquet
```

### Step 2: Configure
Edit `config.yaml`:
- Set `input.folder` to your video recordings directory  
- Set `input.mapping_file` to the parquet file from Step 1
- Set `output.folder` for extracted presentations
- Set `break_detection.images_dir` to your break screens

### Step 3: Process Videos
```bash
# Process all videos (will skip already processed)
python -m src.video_processor.video_splitter --config config.yaml

# The splitter will:
# 1. Process each video one at a time
# 2. Detect transitions and extract immediately  
# 3. Skip videos already in .processed_videos.json
# 4. Skip segments that already exist on disk
# 5. Save progress automatically
```

## Legacy Workflow

### Step 1: Export Session Data from Pretalx

Export your conference sessions from Pretalx in JSON format. This should include:
- Session ID, title, and metadata
- Speaker information
- Room assignments
- Start date and time
- Track information

### Step 2: Prepare Session Mapping

Convert the JSON export to a Parquet file with video recording matches:

```bash
# Basic usage - will auto-detect recordings directory from config or common locations
python -m src.video_processor.json_to_parquet /path/to/sessions.json

# Or specify recordings directory explicitly
python -m src.video_processor.json_to_parquet /path/to/sessions.json \
    -r /path/to/video/recordings \
    -o /path/to/output.parquet
```

This creates a Parquet file that:
- Maps each session to its corresponding video recording
- Generates sequential filenames for extracted presentations
- Creates folder structure based on day/time/room

### Step 3: Configure Processing
Edit `config.yaml`:
- Set `input.folder` to your video directory
- Set `input.mapping_file` to the Parquet file from Step 2
- Set `output.folder` for extracted presentations
- Configure break detection settings

### Step 4: Detect Presentations (Dry Run)
```bash
# First, detect presentations without extracting
# Set in config.yaml:
#   make_processing_plan: true
#   extract_presentations: false

python -m src.video_processor.presentation_detector --config config.yaml
```
This creates `processing_plan.json` with detected presentation timestamps.

### Step 5: Review Detection Results
- Check `processing_plan.json` for detected presentations
- Review break screens saved in `detected_screens_dir`
- Adjust detection thresholds if needed

### Step 6: Extract Presentations
```bash
# Set in config.yaml:
#   make_processing_plan: false
#   extract_presentations: true

python -m src.video_processor.presentation_detector --config config.yaml
```
This extracts all detected presentations as separate files.

## Output Structure

```
output_folder/
├── processing_plan.json                  # Detection results for all videos
├── Monday-Morning-Room1/
│   ├── 001_-_Talk_Title_[ID].mp4        # Extracted presentation
│   ├── 001_-_Talk_Title_[ID].mp3        # Audio version (if enabled)
│   ├── presentations.txt                 # List of presentations
│   └── metadata.json                     # Detailed metadata
├── Monday-Afternoon-Room2/
│   └── ...
└── detected_break_screens/
    ├── break_screen_1.jpg                # Auto-detected break screens
    └── break_screen_2.jpg
```

## How Break Detection Works

1. **Sampling**: The detector samples frames throughout the video at regular intervals
2. **Clustering**: Similar frames are grouped together to identify recurring screens
3. **Break Screen Identification**: Clusters with high frequency and duration are identified as break screens
4. **Binary Search**: For each transition, binary search finds the exact frame where the change occurs
5. **Extraction**: Video segments between transitions are extracted as individual presentations

## Tips for Best Results

1. **Break Screen Quality**: Ensure break screens are static and visually distinct from presentations
2. **Threshold Tuning**: Adjust `break_detection.threshold` if detection is too sensitive or not sensitive enough
3. **Processing Size**: Enable `video.enable_resize` for faster processing of high-resolution videos
4. **Manual Break Screens**: Provide known break screen images in `break_detection.images_dir` for more reliable detection
5. **Chunk Size**: Adjust `presentation_detection.chunk_size` based on typical presentation length

## Troubleshooting

### No presentations detected
- Check if break screens are being detected correctly (review `detected_screens_dir`)
- Lower the `break_detection.threshold` value
- Ensure videos have clear transitions between breaks and presentations

### Wrong transition points
- Decrease `presentation_detection.min_interval` for more precision
- Adjust `break_detection.threshold` for better break screen matching

### Processing too slow
- Enable `video.enable_resize` to process at lower resolution
- Increase `presentation_detection.sampling_interval`
- Reduce `presentation_detection.max_samples`

## Complete Example

Here's a complete example workflow for PyCon DE & PyData 2025:

```bash
# 1. Export sessions from Pretalx as JSON
# Download: pyconde-pydata-2025_sessions.json

# 2. Create Parquet mapping file
python -m src.video_processor.json_to_parquet \
    /Users/hendorf/Downloads/videos/pyconde-pydata-2025_sessions.json \
    -r "/Volumes/DATA-STUFF/Video-Aufzeichnungen/PyConDE & PyData 2025 Raw Video Cut/videos/input" \
    -o /Users/hendorf/Downloads/videos/pyconde-pydata-2025_sessions_processed.parquet

# 3. Update config.yaml with the parquet file path
# input:
#   mapping_file: "/Users/hendorf/Downloads/videos/pyconde-pydata-2025_sessions_processed.parquet"

# 4. Run presentation detection
python -m src.video_processor.presentation_detector --config config.yaml

# Output will be organized as:
# output/
# ├── Thursday-Morning-Europium2/
# │   ├── 001_-_Building_a_Self-Hosted_MLOps_Platform_[3CYZUH].mp4
# │   ├── 002_-_Next_Talk_Title_[ID].mp4
# │   └── ...
# └── Friday-Afternoon-Platinum3/
#     └── ...
```

## Requirements

- Python 3.8+
- OpenCV (cv2)
- Polars
- NumPy
- OmegaConf
- FFmpeg (system installation required for video extraction)