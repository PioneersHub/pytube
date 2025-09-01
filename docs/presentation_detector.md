# Video Presentation Detector

A tool to automatically detect and extract presentations from videos of conferences, livestreams, or lectures that contain both presentations and break screens.

![recording-cuts.png](assets/images/recording-cuts.png)

## Features

- Automatically detects transitions between break screens and presentations
- Supports batch processing of multiple videos
- Extracts presentations as separate video files
- Extracts audio from presentations as MP3 files
- Detailed output with timestamps and presentation durations
- Configurable via YAML configuration file

## Installation

1. **Create and activate a virtual environment:**

```bash
# Create a virtual environment
uv venv

# Activate it (Unix/MacOS)
source .venv/bin/activate

# Activate it (Windows)
.\.venv\Scripts\activate
```

2. **Install video processor dependencies:**

```bash
# Install with video processing dependencies
uv pip install -e ".[video_processor]"
```

3. **Install FFmpeg**: 
   FFmpeg is **required** for video and audio extraction. The tool will not work without it.

   ```bash
   # macOS (using Homebrew)
   brew install ffmpeg
   
   # Alternative for macOS (using MacPorts)
   sudo port install ffmpeg
   
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install ffmpeg
   
   # Fedora
   sudo dnf install ffmpeg
   
   # Arch Linux
   sudo pacman -S ffmpeg
   
   # Windows
   # Download from ffmpeg.org/download.html
   # Extract the files and add the bin folder to your PATH
   ```
   
   Verify installation with:
   ```bash
   ffmpeg -version
   ```

## Configuration

Configuration is stored in `src/video_processor/config.yaml`. If not present, a default one will be created automatically.

Key configuration options:

```yaml
# Base directory for all video processing
base_dir: "/path/to/videos"

input:
  # Subfolder under base_dir for input videos (relative path)
  subfolder: "input"
  # File extensions to process from input folder
  extensions: "mp4,mkv,avi,mov,webm"
  # Mapping file name (will be in base_dir)
  mapping_file: "pyconde-pydata-2025_sessions.parquet"

video:
  # Whether to resize frames for processing (speeds up detection but reduces accuracy)
  enable_resize: false
  # If resize is enabled, dimensions to use (width, height)
  processing_size: [320, 180]

break_detection:
  # Subfolder for break screen images (relative to base_dir)
  images_subfolder: "break_slides"
  # Similarity threshold for break screen detection (0-1)
  threshold: 0.95
  # Comparison method: "template" or "histogram"
  comparison_method: "template"
  # Whether to auto-detect break screens if none provided
  auto_detect: true
  # Subfolder to save detected break screens (relative to base_dir)
  detected_screens_subfolder: "break_screens_detected"

presentation_detection:
  # Minimum precision interval in seconds for binary search
  min_interval: 2
  # Size of initial search chunks in seconds
  chunk_size: 300
  # Sampling interval for break screen detection in seconds
  sampling_interval: 30
  # Maximum number of samples to take
  max_samples: 200
  # Clustering threshold for break screen detection (0-1)
  cluster_threshold: 0.90

output:
  # Subfolder for extracted presentations (relative to base_dir)
  subfolder: "output"
  # Whether to make a processing plan: detect presentations and save to JSON
  make_processing_plan: true
  # Whether to extract detected presentations as separate files
  extract_presentations: false
  # Whether to extract audio from presentations as MP3
  extract_audio: true
  # Whether to save presentation metadata as JSON
  save_metadata: true

event:
  # 24-hour format. Sessions before will be mapped to Morning, after to Afternoon
  lunch_break_cut: 13
```

## Usage

### Prerequisites

1. **Prepare the mapping file (optional):**
   If you're processing conference videos, you can create a mapping file that associates video files with session metadata:
   ```bash
   python -m src.video_processor.json_to_parquet path/to/sessions.json
   ```
   This creates a Parquet file with session information that helps organize the output.

2. **Set up your base directory:**
   Edit `src/video_processor/config.yaml` and set your `base_dir` to point to your video processing directory.

### Basic Usage

#### Batch Processing

```bash
python -m src.video_processor.presentation_detector --config src/video_processor/config.yaml
```

This will:
- Load videos from the configured input subfolder
- Generate a processing plan with detected presentations
- Save the plan to the output folder

To also extract presentations and audio:

```bash
python -m src.video_processor.presentation_detector --config src/video_processor/config.yaml --extract --audio
```

### Advanced Options

```
usage: python -m src.video_processor.presentation_detector [-h] [--config CONFIG] [--output OUTPUT]
                                                          [--break-images BREAK_IMAGES] [--extract]
                                                          [--audio] [--input-folder INPUT_FOLDER]

options:
  --config CONFIG               Path to configuration file (default: config.yaml)
  --output OUTPUT               Output subfolder for extracted presentations (overrides config)
  --break-images BREAK_IMAGES  Subfolder containing break screen images (overrides config)
  --extract                     Extract presentations as separate files (overrides config)
  --audio, -a                   Extract audio from presentations as MP3 (overrides config)
  --input-folder, -i            Process all videos in the specified subfolder
  -h, --help                    Show help message
```

### Example Commands

**Using custom break screen detection:**
```bash
python -m src.video_processor.presentation_detector --break-images break_slides_custom --extract
```

**Using custom output location:**
```bash
python -m src.video_processor.presentation_detector --output custom_output --extract
```

**Using a custom config file:**
```bash
python -m src.video_processor.presentation_detector --config path/to/custom/config.yaml
```

**Processing videos from a specific input folder:**
```bash
python -m src.video_processor.presentation_detector --input-folder conference_recordings --extract --audio
```

## Features in Detail

### Session Mapping

When a mapping file is present, the tool can:
- Match video files to conference sessions using Pretalx IDs
- Organize output by Day/Time/Room structure
- Generate sequential filenames with session titles and IDs
- Track which sessions have been processed

### Processing Plan Generation

Before extraction, the tool creates a processing plan that:
- Identifies all presentation segments in each video
- Calculates exact start/end timestamps
- Determines output paths based on mapping data
- Can be reviewed and modified before extraction

## How It Works in Detail

### 1. Frame Sampling and Analysis

The detector samples frames at regular intervals throughout the video (configurable sampling rate). For each frame:
- The frame is converted to grayscale and normalized
- Visual features are extracted using image processing techniques
- Frames are stored in memory for comparison

### 2. Break Screen Detection

Two methods are used for break screen detection:

**Method 1: Using Provided Break Images**
- If provided, the detector compares sampled frames against known break screen images
- Similarity is calculated using histogram comparison or structural similarity
- Frames that match above the similarity threshold are classified as break screens

**Method 2: Automatic Detection (when no break images are provided)**
- The detector clusters frames based on visual similarity
- Large clusters of similar frames are identified as potential break screens
- The most common frame clusters are selected as break screens

### 3. Transition Detection

Once break screens are identified, the detector:
- Uses binary search to pinpoint exact frame transitions (improves accuracy)
- Analyzes movement between adjacent frames to confirm transitions
- Handles edge cases like brief interruptions or camera shifts

### 4. Presentation Extraction

For each detected presentation segment:
- Start and end timestamps are precisely calculated
- Video is trimmed using FFmpeg with no re-encoding (when possible) for fast extraction
- Audio is extracted using FFmpeg's audio capabilities
- Metadata is generated including duration, timestamps, and filename

## Output Structure

The tool uses a base directory structure with organized subfolders:

```
base_dir/
├── input/                    # Input videos to process
│   ├── recording1.mp4
│   └── recording2.mp4
├── break_slides/            # Reference break screen images
│   └── break_screen.png
├── output/                  # Processing results
│   ├── processing_plan.json # Generated processing plan
│   ├── Day-TimePeriod-Room/ # Organized by session (if mapping file used)
│   │   ├── 001_-_Talk_Title_[CODE].mp4
│   │   ├── 001_-_Talk_Title_[CODE].mp3
│   │   └── 001_-_Talk_Title_[CODE]_metadata.json
│   └── video_name/          # Or by video name (if no mapping)
│       ├── presentations.txt
│       ├── video_name_presentation_1.mp4
│       └── video_name_presentation_1.mp3
└── sessions.parquet         # Optional mapping file
```

### Processing Plan

The tool generates a `processing_plan.json` that contains:
- Detected presentation segments with timestamps
- Output paths for each segment
- Video metadata and duration information

You can review this plan before running extraction to verify detection accuracy.

## Best Practices

### Break Slide Recommendations

The effectiveness of presentation detection depends significantly on your break slides. Here are recommendations for good break slides:

| **Type** | **Good Examples**                                                                                                                            |
|---|----------------------------------------------------------------------------------------------------------------------------------------------|
| **Static Slides** | ![break_slide_1.png](assets/images/break_slide_1.png)<br>✅ High contrast<br>✅ Consistent layout<br>✅ Solid color background                  |
| **Dynamic Slides** | ![break_slide_2.png](assets/images/break_slide_2.png)<br>✅ Consistent elements<br>✅ Distinct from presentations<br>✅ Limited animation areas |

### Tips for Optimal Results

1. **Use distinctive break slides**
   - Choose break slides that are visually very different from presentation content
   - Solid colors or simple patterns work best
   - Avoid break slides that look like presentation slides

2. **Consistent break screens**
   - Use the same break screen throughout the recording
   - If multiple break screens are used, provide examples of each in the break-images folder

3. **Processing options**
   - For large videos, enable resizing to speed up processing
   - Adjust the similarity threshold if detection is too aggressive or too lax
   - Use custom break images for best results

4. **Handling problematic videos**
   - If auto-detection fails, extract a few frames of your break screens and use them as reference
   - For videos with quick transitions, adjust sampling rate in the config
   - Process in batches when dealing with many videos

## License

MIT