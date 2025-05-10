# Vimeo Pattern Downloader

A tool to download Vimeo videos that match a specific pattern in their names using the Vimeo API.

## Features

- Search Vimeo for videos using a search query
- Filter videos by regex pattern in their names
- Download videos in the highest available quality
- Display download progress with progress bars
- Configure all settings through a YAML configuration file

## Prerequisites

1. Python 3.6 or higher
2. Vimeo API credentials (access token, client ID, client secret)

## Installation

1. Clone or download this repository
2. Install the required packages:

```bash
pip install requests tqdm omegaconf
```

## Getting Vimeo API Credentials

Before using this script, you'll need to:

1. Create a Vimeo Developer account at https://developer.vimeo.com/
2. Register a new app
3. Generate an access token with the "private" scope and download permissions

## Configuration

Create a YAML configuration file (see `config.yaml` example) with the following structure:

```yaml
# API credentials
api:
  access_token: "YOUR_ACCESS_TOKEN"
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"

# Search parameters
search:
  query: "optional initial search query"  # Optional
  pattern: "Conference 2025"  # Required
  max_videos: 10  # Optional

# Output settings
output:
  directory: "./downloads"
```

## Usage

Run the script with your configuration file:

```bash
python vimeo_downloader.py --config config.yaml
```

You can override some config options via command line:

```bash
python vimeo_downloader.py --config config.yaml --output-dir "./custom-dir" --max-videos 5
```

## Examples

### Example 1: Download all tutorial videos

**config.yaml**:
```yaml
api:
  access_token: "abc123"
  client_id: "def456"
  client_secret: "ghi789"

search:
  query: "tutorials"
  pattern: "Tutorial.*2025"
  max_videos: 20

output:
  directory: "./tutorials"
```

**Command**:
```bash
python vimeo_downloader.py --config config.yaml
```

### Example 2: Download specific project videos with a custom output directory

**config.yaml**:
```yaml
api:
  access_token: "abc123"
  client_id: "def456"
  client_secret: "ghi789"

search:
  pattern: "Project XYZ"

output:
  directory: "./project-videos"
```

**Command**:
```bash
python vimeo_downloader.py --config config.yaml --output-dir "./custom-location"
```

## Notes

- The script downloads videos in the highest available quality
- File names will be sanitized to remove illegal characters
- A progress bar will show download progress for each video
- After all downloads are complete, a summary will be displayed