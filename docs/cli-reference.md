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
- `--version`: Show the installed version
- `--help`: Show help for any command

## Commands Overview

Every command, with its options. Details follow in the sections below.

| Command | Options | Purpose |
|---|---|---|
| `pytube assistant` | — | Interactive, guided workflows |
| `pytube setup` | `--validate-only` `--fix` `--json` | Configuration wizard |
| `pytube validate` | `--fix` | Validate config; `--fix` creates missing directories |
| `pytube status` | `--detailed` | Overall pipeline status |
| **Records** | | |
| `pytube records fetch` | — | Download sessions + speakers from Pretalx |
| `pytube records generate-descriptions` | `--replace` `--dry-run` | Generate teaser/short/long texts |
| `pytube records show [SESSION_ID]` | — | List records or show one |
| **Video files** | | |
| `pytube video bulk-download` | `--account` (repeatable) `--limit` `--dry-run` | Download raw streams from Vimeo accounts |
| `pytube video map-recordings` | `--dry-run` `--force` | Write the filename → room/day/period mapping |
| `pytube video map-to-channels` | `--dry-run` | Assign sessions to channels → `tracks_map.json` |
| `pytube video move-to-channel-dirs` | `--dry-run` `--force` | Move files into the channel upload folders |
| `pytube video report` | — | List videos without a channel assignment |
| `pytube video list` | — | List video files found |
| `pytube video status` | — | Video processing status |
| `pytube video organize` | `--dry-run` | **Deprecated** — use `map-to-channels` |
| `pytube video download` | `--client-id` `--limit` | **Not implemented** — use `bulk-download` |
| **YouTube** | | |
| `pytube youtube map` | `--channel` `--filter-channel` | Match uploaded videos to sessions |
| `pytube youtube update` | `--template` `--event-name` `--channel` `--dry-run` `--show-body` `--limit` `--yes` `--force` | Write titles/descriptions to YouTube |
| `pytube youtube schedule` | `--start` `--interval` `--preview` | Set publishing schedule |
| `pytube youtube channels` | — | List configured channels |
| **Notifications** | | |
| `pytube notify check` | `--auto-post` `--channel` `--offline` | Detect published videos, queue notifications |
| `pytube notify email` | `--dry-run` | Send queued speaker emails |
| `pytube notify social` | `--dry-run` | Post queued social media updates |
| `pytube notify run` | — | Full notification workflow |

Commands that need network access: `records fetch` (Pretalx), `video bulk-download`
(Vimeo), `youtube map` / `youtube update`, and `notify` (unless `--offline`).
`youtube map` opens a browser for OAuth on first use and caches the token at
`youtube.channels.<name>.token_path`, falling back to `youtube.token_path`; see
[One OAuth token per channel](#one-oauth-token-per-channel) for how the other
commands authenticate.

### One OAuth token per channel

PyCon DE and PyData are separate YouTube channels owned by **different Google
accounts**. Give each channel its own `token_path` in `config_local.yaml`:

```yaml
youtube:
  channels:
    pyconde:
      token_path: ".secrets/token_pyconde.json"
    pydata:
      token_path: ".secrets/token_pydata.json"
```

Without a per-channel path both channels share `youtube.token_path`, and
authorizing the second channel **overwrites the first channel's token** — the
first channel then needs a fresh browser authorization on its next command.

`youtube map` creates one client per channel, so `--channel pyconde` only ever
touches the pyconde token — provided that key is set; without it, `map` silently
falls back to the shared `youtube.token_path`. A run **without** `--channel` walks
every configured channel and authenticates each against its own token file,
opening a browser only for channels whose token is missing or no longer
refreshable; authorize each with the matching Google account.

> **Note — tokens expire about every 7 days, and that is accepted.**
> While the Google Cloud OAuth consent screen is in publishing status
> **Testing**, Google expires refresh tokens after roughly seven days. Moving the
> app to **In production** would stop that, but it requires going through Google's
> app verification — deliberately **not** done here, because the effort outweighs
> re-authorizing occasionally.
>
> This only affects `youtube map`, the one command that reuses a cached token.
> Roughly weekly it will open a browser and ask for authorization again. That is
> expected, not a misconfiguration: the refresh failure is caught and turned
> into a browser prompt automatically, so the command continues once you have
> signed in — with the Google account **belonging to that channel**.

Which commands authenticate, and how:

| Command | Authentication | Browser prompt |
|---|---|---|
| `youtube map` | Cached token, per channel | Only when the token is missing or can no longer be refreshed |
| `youtube update` | Interactive OAuth, no token cache | **Every run**, once per channel |
| `youtube schedule` | None — rewrites local record files only | Never |
| `notify *` | API key (`youtube.api_key`) | Never |

So `youtube update` ignores `token_path` entirely and re-prompts on every
invocation regardless of token expiry; sign in with the account owning the channel
you are targeting.

Each channel's playlist snapshot under
`{work_dir}/{event_slug}/videos/youtube_<channel>_playlist.json` is only rewritten
by a run covering that channel. After changing a playlist on YouTube, re-run
`youtube map` for that channel before reading the file — otherwise it still shows
the state of the previous run.

## Interactive Assistant

### pytube assistant

Launch the interactive PyTube assistant for guided workflows.

```bash
pytube assistant
```

**Features:**
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
- AI service selection (OpenAI, Anthropic)
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

Fetch all sessions and speakers from Pretalx. This command only downloads and
stores records; AI descriptions are generated by a separate command (see
`generate-descriptions` below).

```bash
pytube records fetch [OPTIONS]

Options:
  --help    Show help message
```

**Example:**
```bash
# Fetch all sessions and speakers
pytube records fetch
```

### pytube records generate-descriptions

Generate AI teaser/description texts for the fetched records.

```bash
pytube records generate-descriptions [OPTIONS]

Options:
  --replace    Replace existing AI-generated descriptions
  --dry-run    Show what would be updated without making changes
  --help       Show help message
```

**Example:**
```bash
# Generate descriptions for records that don't have them yet
pytube records generate-descriptions

# Re-generate and overwrite all descriptions
pytube records generate-descriptions --replace

# Preview without writing
pytube records generate-descriptions --dry-run
```

**Progress output.** Generation takes tens of seconds per talk (a local model needs
roughly 70 s for the three texts), so the command prints one line per session plus
a live bar showing which session is currently running:

```
Found 145 records to process
[1/145] ✓ 333HDN From Hard Problems to Proven Solutions… (34s)
[2/145] ✓ 37AESH In Praise of Documentation: Tools, Tips… (37s)
[3/145] • BQPEUG Opening Session — already had texts
⠹ 39MHWT From Ticket to Draft… ━━━━━━━━━╸────────── 3/145 0:01:52
```

`✓` generated, `•` skipped because the fields were already filled, `✗` record
could not be read. The run is safe to interrupt with `Ctrl-C`: each record is
written immediately after it is generated, and a later run continues with the
remaining ones.

**Transcript-based summaries (optional):** if `transcripts.dir` is set in config,
each talk that has a transcript (`<transcripts.dir>/<CODE…>/transcript.md`) gets
its short/long description summarized from the transcript via the
`ai_service.prompts.description_from_transcript` prompt (recommended provider: Anthropic
Claude). Talks without a transcript keep the abstract-based description; the
teaser always uses the abstract-based prompt. A configured-but-missing
`transcripts.dir` is treated as a configuration error.

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
  --channel TEXT             YouTube channel name from config
  --filter-channel TEXT      Only map videos assigned to this channel
  --help                     Show help message
```

**Example:**
```bash
# Map videos (automatically skips do_not_record)
pytube youtube map

# Map videos for specific YouTube channel
pytube youtube map --channel pycon

# Only map videos assigned to pydata channel
pytube youtube map --filter-channel pydata

```

This command:
- Retrieves video IDs from YouTube playlists
- Matches videos to Pretalx sessions by filename
- **Automatically skips videos marked as do_not_record**
- **Respects channel assignments from video organization**
- **Warns about videos that shouldn't be on YouTube**
- Creates mapping files for further processing

### pytube youtube update

Update YouTube video metadata from records.

```bash
pytube youtube update [OPTIONS]

Options:
  --template TEXT      Jinja2 template file for descriptions [default: youtube_2026.txt]
                       Looked up in projects/<slug>/ first, then the bundled
                       templates in src/manager/templates/.
  --event-name TEXT    Event name for the template
  --channel TEXT       Only build and send videos on this channel
  --dry-run            Show what would be sent; writes nothing, sends nothing
  --show-body N        With --dry-run: dump the full request body for the first
                       N videos [default: 1]
  --limit N            Send at most N videos per channel (quota safety)
  --yes                Skip the confirmation prompt (for scripted runs)
  --force              Send even if the estimated quota exceeds the daily budget
  --help               Show help message
```

Which videos are processed is driven by `pretalx_yt_map.json` — the talks that
are both uploaded to YouTube and resolved to a Pretalx code. A talk with a
channel assignment but no uploaded video is skipped.

**Example:**
```bash
# Read the generated descriptions before spending any API quota
pytube youtube update --dry-run

# Inspect the exact request body for the first three videos
pytube youtube update --dry-run --show-body 3

# Pilot: send a small sample first and check it on YouTube
pytube youtube update --channel pyconde --limit 5

# Send the rest, one channel at a time
pytube youtube update --channel pyconde
```

#### The live send

Each `videos.update` costs 50 quota units against a daily budget of 10000
(`youtube.quota` in config). Before sending, the command prints the estimate
(`N videos → N×50 of 10000 units`), refuses to start a run that would exceed the
budget unless `--force` is given, and asks for confirmation unless `--yes` is
passed. `--limit N` caps how many are sent per channel — the safe way to pilot a
handful before committing quota to all of them.

The body sent is exactly the one `--dry-run` prints. Authentication uses the
channel's own cached OAuth token (from `youtube map`), so a live send does not
open a browser as long as the token is valid.

Failures are reported, not swallowed: a per-channel results table shows
updated/failed counts, a quota error stops the run rather than burning the rest
of the budget, a failed video stays queued for a retry, and the command exits
non-zero if anything failed. After sending, each video is read back from YouTube
to confirm its privacy status landed.

#### What --dry-run guarantees

Nothing is written to disk and nothing is sent: no records are rewritten, no
video records are created, and no OAuth flow is started. The metadata is built
in memory and printed as a table (code, video id, channel, privacy, publish
date, description length, tag count, title), followed by the request body for
the first `--show-body` videos.

That body is exactly what a real run sends. Every field of `snippet` and
`status` is always included, because YouTube **deletes any property it does not
receive** within a part that is being updated — sending a partial `snippet`
would silently wipe the video's tags and language settings. The values come from
`youtube.video_defaults` (see [Projects & Configuration](projects.md)).

Setting a publish date forces `privacyStatus` to `private`, which is the only
state in which YouTube accepts `publishAt`; the video becomes public when that
time passes.

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
pytube youtube schedule --start "2026-05-01T10:00:00" --interval 6h

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

**Not implemented.** The per-video download loop was never written; the command
used to print a success message without fetching anything and now exits with an
error instead. Use [`pytube video bulk-download`](#pytube-video-bulk-download).

```bash
pytube video download [OPTIONS]

Options:
  --client-id TEXT    Vimeo client ID (if using multiple)
  --limit INTEGER     Limit number of videos to download
  --help             Show help message
```

### pytube video bulk-download

Download raw long-stream sources from the Vimeo accounts configured under
`vimeo.raw_sources` in `config_local.yaml` (stage 1 of the auto-cut pipeline).

```bash
pytube video bulk-download [OPTIONS]

Options:
  --account TEXT      Restrict to named account(s); default = all configured (repeatable)
  --limit INTEGER     Max videos per account (for smoke tests)
  --dry-run           Print the download plan; don't fetch anything
  --help              Show help message
```

> Not needed for editions where finished cuts are provided directly (e.g. from a
> Google Drive release folder). Use only for the raw → auto-cut workflow.

### pytube video map-recordings

Scan raw recording filenames and write the room/day/period mapping YAML (path
from `pretalx.recording_mapping_yaml`). Hand-edit the result to fix typos or
classify filenames the scanner skipped.

```bash
pytube video map-recordings [OPTIONS]

Options:
  --dry-run    Print the mapping without writing the YAML
  --force      Overwrite existing mapping YAML (hand edits will be lost)
  --help       Show help message
```

### pytube video map-to-channels

Assign videos to YouTube channels based on track information.

```bash
pytube video map-to-channels [OPTIONS]

Options:
  --dry-run    Show what channels would be assigned without creating files
  --help       Show help message
```

**Example:**
```bash
# Assign videos to channels
pytube video map-to-channels

# Preview assignments without creating files
pytube video map-to-channels --dry-run
```

This command:
- Analyzes confirmed sessions from Pretalx
- Determines which YouTube channel (PyData/PyCon) each video should be uploaded to
- Creates mapping files: `tracks.json` and `tracks_map.json`
- Uses track names and custom mappings from configuration
- Optionally uses AI (Claude/OpenAI) to analyze unmatched videos
- Handles `do_not_record` sessions → `no_publishing` channel

### pytube video move-to-channel-dirs

Move videos to channel directories based on assignments.

```bash
pytube video move-to-channel-dirs [OPTIONS]

Options:
  --dry-run    Show what would be moved without actually moving files
  --force      Move files even if destination already exists
  --help       Show help message
```

**Example:**
```bash
# Move videos to channel directories
pytube video move-to-channel-dirs

# Preview moves without actually moving files
pytube video move-to-channel-dirs --dry-run

# Force move even if files exist at destination
pytube video move-to-channel-dirs --force
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

**[DEPRECATED]** Use `map-to-channels` instead.

```bash
pytube video organize [OPTIONS]

Options:
  --dry-run    Show channel assignments without creating files
  --help       Show help message
```

This command is deprecated. Use the new workflow:
1. `pytube video map-to-channels` - Assign videos to channels
2. `pytube video move-to-channel-dirs` - Move videos to channel directories

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

## Validate Command

### pytube validate

Validate the configuration without running the setup wizard.

```bash
pytube validate [OPTIONS]

Options:
  --fix     Attempt to fix issues (creates missing directories)
  --help    Show help message
```

Not to be confused with `pytube setup --validate-only`, which runs the wizard's
validation and can emit JSON. `pytube validate` is the quick standalone check.

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
pytube video map-to-channels

# 3. Move videos to channel-specific directories
pytube video move-to-channel-dirs --dry-run  # Preview first
pytube video move-to-channel-dirs            # Actually move files

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
pytube youtube schedule --start "2026-05-01T10:00:00" --interval 6h

# 9. Monitor and notify
pytube notify check --auto-post
```

### Video Organization Workflow

```bash
# Check current status
pytube video status

# Assign videos to channels (dry-run first)
pytube video map-to-channels --dry-run
pytube video map-to-channels

# Preview what files will be moved
pytube video move-to-channel-dirs --dry-run

# Move videos to channel directories
pytube video move-to-channel-dirs

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

The CLI itself reads no environment variables. `NO_COLOR` works because the
underlying `rich` console honours it. Verbosity is controlled with `-v/--verbose`
and `-q/--quiet`, the config file with `config_local.yaml` — there is no
`PYTUBE_CONFIG` override.

## Exit Codes

- `0`: Success
- `1`: Any error (configuration, API, missing file — all use the same code)
