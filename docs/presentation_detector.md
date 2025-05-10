# Video Presentation Detector

A tool to automatically detect and extract presentations from videos of conferences, livestreams, or lectures that contain both presentations and break screens.

## Features

- Automatically detects transitions between break screens and presentations
- Supports batch processing of multiple videos
- Extracts presentations as separate video files
- Extracts audio from presentations as MP3 files
- Detailed output with timestamps and presentation durations
- Configurable via YAML configuration file

## Requirements

- Python 3.6+
- OpenCV
- NumPy
- OmegaConf
- FFmpeg (for video and audio extraction)

Install required Python packages:

```bash
pip install -r requirements.txt
```

## Quick Start

1. Process a single video:

```bash
python presentation_detector.py path/to/video.mp4 --extract --audio
```

2. Batch process all videos in a folder:

```bash
python presentation_detector.py --input-folder path/to/videos --extract --audio
```

## Configuration

Configuration is stored in `config.yaml`. If not present, a default one will be created automatically.

Key configuration options:

```yaml
input:
  # Single video file path (leave empty to use folder)
  video_path: ""
  # Folder containing videos to batch process
  folder: "input_videos"
  # File extensions to process from input folder
  extensions: "mp4,mkv,avi,mov,webm"

video:
  # Whether to resize frames for processing (speeds up detection but reduces accuracy)
  enable_resize: false
  # If resize is enabled, dimensions to use (width, height)
  processing_size: [320, 180]

break_detection:
  # Directory for break screen images (leave empty for auto-detection)
  images_dir: ""
  # Similarity threshold for break screen detection (0-1)
  threshold: 0.92
  # Whether to auto-detect break screens if none provided
  auto_detect: true

output:
  # Base output folder for extracted presentations
  folder: "extracted_presentations"
  # Whether to extract detected presentations as separate files
  extract_presentations: true
  # Whether to extract audio from presentations as MP3
  extract_audio: true
  # Whether to save presentation metadata as JSON
  save_metadata: true
```

## Command-Line Options

```
usage: presentation_detector.py [-h] [--config CONFIG] [--output OUTPUT]
                              [--break-images BREAK_IMAGES] [--extract]
                              [--audio] [--input-folder INPUT_FOLDER]
                              [video_path]

positional arguments:
  video_path            Path to the video file (optional if specified in config)

optional arguments:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
                        Path to config file
  --output OUTPUT, -o OUTPUT
                        Override output folder for extracted presentations
  --break-images BREAK_IMAGES, -b BREAK_IMAGES
                        Override directory containing break screen images
  --extract, -e         Extract detected presentations as separate files
  --audio, -a           Extract audio from presentations as MP3
  --input-folder INPUT_FOLDER, -i INPUT_FOLDER
                        Process all videos in the specified folder
```

## How It Works

1. The script samples frames throughout the video
2. It clusters similar frames to detect potential break screens
3. Using binary search, it finds precise transitions between break screens and presentations
4. It outputs time ranges for each detected presentation
5. Optionally extracts presentations as video files and audio files

## Output Structure

For each processed video, a subdirectory is created in the output folder:

```
output_folder/
├── video1_name/
│   ├── presentations.txt       # Text file with presentation times
│   ├── video1_name_metadata.json   # JSON with detailed metadata
│   ├── video1_name_presentation_1.mp4  # First presentation video
│   ├── video1_name_presentation_1.mp3  # First presentation audio
│   ├── video1_name_presentation_2.mp4  # Second presentation video
│   └── video1_name_presentation_2.mp3  # Second presentation audio
├── video2_name/
│   └── ...
└── ...
```

## License

MIT