# CLI Reference

PyTube provides a comprehensive command-line interface for managing conference videos from Pretalx to YouTube publication.

## Installation

After installing PyTube, the `pytube` command will be available in your environment:

```bash
# Verify installation
pytube --version

# Get help
pytube --help
```

## Global Options

These options can be used with any command:

- `-v, --verbose`: Enable verbose output for debugging
- `-q, --quiet`: Suppress non-essential output
- `--help`: Show help for any command

## Commands Overview

```
pytube
├── assistant     # Standard interactive assistant
├── enhanced      # Enhanced interactive assistant (recommended)
├── setup         # Configuration wizard
├── records       # Manage Pretalx records
├── youtube       # YouTube operations
├── notify        # Monitor and send notifications
├── video         # Video file operations
└── status        # Show system status
```

## Interactive Assistants

### pytube assistant

Launch the standard interactive PyTube assistant for guided workflows.

```bash
pytube assistant
```

The assistant provides:
- Step-by-step guidance through common workflows
- Configuration validation
- Automated command execution
- Progress tracking

### pytube enhanced (Recommended)

Launch the enhanced interactive assistant with improved navigation and features.

```bash
pytube enhanced
```

**Enhanced Features:**
- **Named command support**: Type command names (e.g., 'setup', 'process') or numbers
- **Context-aware menus**: Shows relevant options based on system state
- **Workflow management**: Save and resume multi-step workflows
- **Better navigation**: Breadcrumbs and clear menu organization
- **Progress persistence**: Automatically resume interrupted workflows
- **Step selection**: Choose which workflow steps to execute

**Navigation Tips:**
- Use command names or numbers to navigate
- Type 'help <command>' for detailed help on any command
- Use 'back' or 'b' to go back in menus
- Workflow progress is automatically saved

### pytube setup

Run the configuration wizard to set up PyTube.

```bash
pytube setup [OPTIONS]

Options:
  --validate-only   Only validate existing configuration without setup
  --fix             Attempt to fix any validation issues found
  --json            Output results in JSON format (AI-friendly)
  --help            Show help message
```

The setup wizard will guide you through:
- Event information (name, URL, program link)
- Pretalx connection configuration
- YouTube API credentials
- AI service selection (OpenAI, Anthropic, Google, Cohere)
- Social media platform configuration
- Storage directory setup

**Context-Aware Setup:**
Each configuration section now explains:
- ✓ **What's enabled**: Features that work with this configuration
- ✗ **What's disabled**: Limitations without the configuration
- 🎯 **Required vs Optional**: Clear indicators for critical vs enhancement features

**Enhanced Reconfiguration Features:**
When running setup with an existing configuration, the wizard will:
- Display current values for each setting
- Provide options to **[K]eep**, **[C]hange**, or **[R]emove** values
- Mask sensitive information (API keys show as `sk-...XXX`)
- Preserve settings you don't modify
- Allow partial updates without losing other configuration

**Example:**
```
Event slug
  Current value: pyconde-pydata-2025
  [K]eep, [C]hange, or [R]emove? k
  ✓ Keeping existing value

OpenAI API key
  Current value: sk-p...nop
  [K]eep, [C]hange, or [R]emove? c
  New value: ****
  ✓ Changed
```

## Records Commands

### pytube records fetch

Fetch all sessions and speakers from Pretalx.

```bash
pytube records fetch [OPTIONS]

Options:
  --replace-descriptions    Replace existing AI-generated descriptions
  --skip-descriptions      Skip AI description generation
  --help                   Show help message
```

**Example:**
```bash
# Fetch all data and generate descriptions
pytube records fetch

# Fetch data but skip AI descriptions
pytube records fetch --skip-descriptions

# Re-generate all descriptions
pytube records fetch --replace-descriptions
```

### pytube records enhance

Add or update AI-generated descriptions for existing records.

```bash
pytube records enhance [OPTIONS]

Options:
  --dry-run    Show what would be updated without making changes
  --help       Show help message
```

### pytube records show

Display record details.

```bash
pytube records show [SESSION_ID]

Arguments:
  SESSION_ID    Optional session ID to show details for
```

**Example:**
```bash
# List all records
pytube records show

# Show specific record
pytube records show ABC123
```

## YouTube Commands

### pytube youtube map

Map uploaded YouTube videos to Pretalx sessions.

```bash
pytube youtube map [OPTIONS]

Options:
  --channel TEXT    YouTube channel name from config
  --help           Show help message
```

**Example:**
```bash
# Map videos for default channel
pytube youtube map

# Map videos for specific channel
pytube youtube map --channel pycon
```

### pytube youtube update

Update YouTube video metadata from records.

```bash
pytube youtube update [OPTIONS]

Options:
  --template TEXT      Jinja2 template file for descriptions [default: youtube_2024.txt]
  --event-name TEXT    Event name for the template
  --channel TEXT       Target YouTube channel
  --dry-run           Preview changes without updating YouTube
  --help              Show help message
```

**Example:**
```bash
# Update with default template
pytube youtube update

# Use custom template and event name
pytube youtube update --template custom.txt --event-name "PyCon 2024"

# Preview changes
pytube youtube update --dry-run
```

### pytube youtube schedule

Set publishing schedule for videos.

```bash
pytube youtube schedule [OPTIONS]

Options:
  --start TEXT      Start date/time (ISO format or 'now+5m')
  --interval TEXT   Publishing interval (e.g., 4h, 1d, 30m) [default: 4h]
  --preview        Show publishing schedule without applying
  --help           Show help message
```

**Example:**
```bash
# Schedule to start in 5 minutes, publish every 4 hours
pytube youtube schedule --start now+5m --interval 4h

# Schedule for specific date/time
pytube youtube schedule --start "2024-05-01T10:00:00" --interval 6h

# Preview schedule
pytube youtube schedule --preview
```

### pytube youtube channels

List configured YouTube channels.

```bash
pytube youtube channels
```

## Notify Commands

### pytube notify check

Check for recently published videos and process notifications.

```bash
pytube notify check [OPTIONS]

Options:
  --auto-post    Automatically post to social media and send emails
  --channel TEXT YouTube channel to monitor
  --offline      Use offline mode (no YouTube API calls)
  --help         Show help message
```

**Example:**
```bash
# Check and show pending notifications
pytube notify check

# Check and automatically send all notifications
pytube notify check --auto-post

# Check specific channel in offline mode
pytube notify check --channel pycon --offline
```

### pytube notify email

Send pending speaker email notifications.

```bash
pytube notify email [OPTIONS]

Options:
  --dry-run    Show what would be sent without sending
  --help       Show help message
```

### pytube notify social

Post pending social media updates.

```bash
pytube notify social [OPTIONS]

Options:
  --dry-run    Show what would be posted without posting
  --help       Show help message
```

### pytube notify run

Run the complete notification workflow (equivalent to the original notify.py script).

```bash
pytube notify run
```

## Video Commands

### pytube video download

Download videos from Vimeo.

```bash
pytube video download [OPTIONS]

Options:
  --client-id TEXT    Vimeo client ID (if using multiple)
  --limit INTEGER     Limit number of videos to download
  --help             Show help message
```

### pytube video assign-channels

Assign videos to YouTube channels based on track information.

```bash
pytube video assign-channels [OPTIONS]

Options:
  --dry-run    Show what channels would be assigned without creating files
  --help       Show help message
```

**Example:**
```bash
# Assign videos to channels
pytube video assign-channels

# Preview assignments without creating files
pytube video assign-channels --dry-run
```

This command:
- Analyzes confirmed sessions from Pretalx
- Determines which YouTube channel (PyData/PyCon) each video should be uploaded to
- Creates mapping files: `tracks.json` and `tracks_map.json`
- Uses track names and custom mappings from configuration

### pytube video move

Move videos to channel directories based on assignments.

```bash
pytube video move [OPTIONS]

Options:
  --dry-run    Show what would be moved without actually moving files
  --force      Move files even if destination already exists
  --help       Show help message
```

**Example:**
```bash
# Move videos to channel directories
pytube video move

# Preview moves without actually moving files
pytube video move --dry-run

# Force move even if files exist at destination
pytube video move --force
```

This command:
- Moves videos from `downloads/` to channel-specific directories
- Creates sibling directories: `pycon/`, `pydata/`
- Moves do-not-record videos to `do_not_release/`
- Keeps unmatched videos in `downloads/`

### pytube video report

Generate a report of unassigned videos.

```bash
pytube video report
```

This command:
- Lists all videos that could not be assigned to a channel
- Shows session codes, titles, and tracks
- Saves detailed report to `unassigned_videos_report.json`
- Helps identify videos needing manual channel assignment

### pytube video organize (Deprecated)

**[DEPRECATED]** Use `assign-channels` instead.

```bash
pytube video organize [OPTIONS]

Options:
  --dry-run    Show channel assignments without creating files
  --help       Show help message
```

This command is deprecated. Use the new workflow:
1. `pytube video assign-channels` - Assign videos to channels
2. `pytube video move` - Move videos to channel directories

### pytube video list

List video files in the configured directory.

```bash
pytube video list
```

### pytube video status

Show video processing status.

```bash
pytube video status
```

## Status Command

### pytube status

Show overall system status and statistics.

```bash
pytube status [OPTIONS]

Options:
  --detailed    Show detailed status information
  --help        Show help message
```

**Example:**
```bash
# Basic status overview
pytube status

# Detailed status with next steps
pytube status --detailed
```

## Common Workflows

### Initial Setup and First Run

```bash
# 1. Fetch data from Pretalx
pytube records fetch

# 2. Assign videos to channels based on track information
pytube video assign-channels

# 3. Move videos to channel-specific directories
pytube video move --dry-run  # Preview first
pytube video move            # Actually move files

# 4. Generate report of any unassigned videos
pytube video report

# 5. Upload videos to YouTube manually from channel directories
# Upload from pycon/ directory to PyCon channel
# Upload from pydata/ directory to PyData channel

# 6. Map videos to sessions
pytube youtube map

# 7. Update video metadata
pytube youtube update

# 8. Schedule publishing
pytube youtube schedule --start "2024-05-01T10:00:00" --interval 6h

# 9. Monitor and notify
pytube notify check --auto-post
```

### Video Organization Workflow

```bash
# Check current status
pytube video status

# Assign videos to channels (dry-run first)
pytube video assign-channels --dry-run
pytube video assign-channels

# Preview what files will be moved
pytube video move --dry-run

# Move videos to channel directories
pytube video move

# Check for any unassigned videos
pytube video report
```

### Daily Monitoring

```bash
# Check system status
pytube status

# Process new publications and send notifications
pytube notify check --auto-post
```

### Troubleshooting

```bash
# Check detailed status
pytube status --detailed

# Preview operations without making changes
pytube youtube update --dry-run
pytube notify email --dry-run

# Use verbose mode for debugging
pytube -v records fetch
```

## Environment Variables

The CLI respects these environment variables:

- `PYTUBE_CONFIG`: Path to alternative config file
- `PYTUBE_VERBOSE`: Set to "1" for verbose output by default
- `NO_COLOR`: Disable colored output

## Exit Codes

- `0`: Success
- `1`: General error
- `2`: Configuration error
- `3`: API error
- `4`: File not found