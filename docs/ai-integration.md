# AI Integration Guide for PyTube

This guide explains how AI agents can interact with PyTube to automate conference video management workflows.

## Overview

PyTube provides AI-friendly interfaces with structured responses that make it easy for AI agents to:
- Validate configurations
- Set up new installations
- Monitor processing pipelines
- Troubleshoot issues

## Key Commands for AI Automation

### 1. Setup and Configuration

```bash
# Get current configuration status as JSON
pytube setup --validate-only --json

# Run setup with JSON output
pytube setup --json

# Fix configuration issues automatically
pytube setup --fix --json
```

**Response Structure:**
```json
{
  "success": true,
  "config": {
    "pretalx": {...},
    "youtube": {...},
    "dirs": {...}
  },
  "validation": {
    "pretalx": {
      "valid": true,
      "message": "Configuration looks valid",
      "details": {},
      "fix_suggestions": []
    }
  },
  "errors": []
}
```

### 2. Processing Pipeline Status

```bash
# Check system status
pytube status --detailed

# Get pipeline counts
pytube status | grep "Stage"
```

### 3. Automated Workflows

#### Complete Conference Processing
```python
# Example Python script for AI automation
import subprocess
import json

def process_conference():
    # 1. Validate setup
    result = subprocess.run(
        ["pytube", "setup", "--validate-only", "--json"],
        capture_output=True,
        text=True
    )
    validation = json.loads(result.stdout)
    
    if not all(v["valid"] for v in validation.values()):
        # Fix issues
        subprocess.run(["pytube", "setup", "--fix"])
    
    # 2. Fetch records
    subprocess.run(["pytube", "records", "fetch"])
    
    # 3. Map videos (after manual upload)
    subprocess.run(["pytube", "youtube", "map"])
    
    # 4. Update metadata
    subprocess.run(["pytube", "youtube", "update"])
    
    # 5. Schedule releases
    subprocess.run(["pytube", "youtube", "schedule"])
    
    # 6. Monitor and notify
    subprocess.run(["pytube", "notify", "check", "--auto-post"])
```

## Structured Data Locations

AI agents can directly read JSON files from these directories:

```
projects/<event-slug>/
├── records/                     # Session data from Pretalx
│   └── *.json                   # One file per session
├── videos/
│   ├── tracks_map.json          # Pretalx code -> channel
│   ├── pretalx_yt_map.json      # Pretalx code -> YouTube video id
│   └── youtube/
│       ├── video_records/         # Videos mapped to sessions
│       ├── video_records_updated/ # Metadata sent to YouTube
│       └── video_published/       # Live on YouTube
└── speaker_to_email/            # Email queue
    └── *.json                   # Pending notifications
```

The root comes from `dirs.work_dir` and the event from `pretalx.event_slug`.
See [Projects & Configuration](projects.md) for the full layout.

## API-Style Interactions

### SetupWizard Class (Python)
```python
from manager.cli.setup import SetupWizard
from rich.console import Console

wizard = SetupWizard(Console())

# Validate all services
results = wizard.validate_all()
# Returns: Dict[str, Dict[str, Any]] with validation details

# Fix specific issues
failed_services = ["pretalx", "youtube"]
fix_results = wizard.fix_issues(failed_services)
# Returns: Dict[str, Dict[str, Any]] with fix status

# Run complete setup
setup_result = wizard.run()
# Returns structured result with success status and config
```

## Error Handling

All commands provide structured error information:

```json
{
  "valid": false,
  "message": "Client secrets file not found",
  "details": {
    "path": "./client_secrets.json"
  },
  "fix_suggestions": [
    "Check file path",
    "Download from Google Cloud Console"
  ]
}
```

## Monitoring and Alerts

AI agents can monitor the pipeline by:

1. Checking directory counts:
```bash
ls projects/pyconde-pydata-2026/videos/youtube/video_records/*.json | wc -l
```

2. Parsing status output:
```bash
pytube status --detailed | grep "Total Videos in Pipeline"
```

3. Watching for new files in specific directories

## Configuration Templates

The setup wizard provides configuration templates with metadata:

```python
{
    "pretalx": {
        "_description": "Pretalx event management system configuration",
        "event_slug": {
            "_type": "string",
            "_required": True,
            "_example": "pycon-2024",
            "_description": "Event identifier in Pretalx"
        }
    }
}
```

## Best Practices for AI Agents

1. **Always validate before processing**
   ```bash
   pytube setup --validate-only --json
   ```

2. **Use JSON output for parsing**
   - Add `--json` flag where available
   - Parse structured responses for decision making

3. **Handle rate limits**
   - YouTube API has quotas
   - Implement exponential backoff

4. **Monitor file system changes**
   - Watch directories for new JSON files
   - React to pipeline state changes

5. **Error recovery**
   - Use fix_suggestions from validation errors
   - Retry failed operations with backoff

## Example: Automated Setup Validation

```python
#!/usr/bin/env python3
import subprocess
import json
import sys

def check_pytube_health():
    """Check PyTube configuration and provide actionable feedback."""
    
    # Run validation
    result = subprocess.run(
        ["pytube", "setup", "--validate-only", "--json"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error running validation: {result.stderr}")
        return False
    
    validation = json.loads(result.stdout)
    
    # Check each service
    all_valid = True
    for service, status in validation.items():
        if not status["valid"]:
            all_valid = False
            print(f"\n❌ {service}: {status['message']}")
            
            # Show fix suggestions
            if status.get("fix_suggestions"):
                print("   Suggested fixes:")
                for fix in status["fix_suggestions"]:
                    print(f"   - {fix}")
    
    if all_valid:
        print("✅ All services configured correctly")
    
    return all_valid

if __name__ == "__main__":
    if not check_pytube_health():
        sys.exit(1)
```

## Integration with CI/CD

PyTube commands can be integrated into CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Validate PyTube Configuration
  run: |
    pytube setup --validate-only --json > validation.json
    python -c "import json; exit(0 if all(v['valid'] for v in json.load(open('validation.json')).values()) else 1)"

- name: Process Conference Videos
  run: |
    pytube records fetch
    pytube youtube map
    pytube youtube update
```

## Support

For AI-specific features or integration questions:
- Check structured error messages and fix_suggestions
- Review JSON output for detailed context
- File issues with "ai-integration" label