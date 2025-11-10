# Pretalx Pipeline Module

Fetch and manage conference session data from Pretalx conference management system.

## Overview

This module provides interaction with Pretalx API to fetch session records, speaker information, and event metadata. It serves as the foundation data source for the entire video processing pipeline.

## Key Features

- **Pytanis integration**: Uses the pytanis library for reliable Pretalx API access
- **Structured data models**: Pydantic models ensure type safety
- **Comprehensive records**: Combines sessions, speakers, and custom questions
- **Markdown conversion**: Converts Pretalx markdown to plain text
- **File-based output**: Individual JSON files per session for easy processing

## Prerequisites

### Configuration

In `config_local.yaml`:

```yaml
pretalx:
  event_slug: "pyconde-pydata-2025"
  questions_map:
    company: 4390
    job: 4391
    linkedin: 4394
    github: 4395
    x_handle: 4397
    python_expertise: 345536
    domain_expertise: 345535
    prerequisites: 345537

pytanis:
  PRETALX_API_TOKEN: "your_pretalx_api_token"
```

### API Token

1. Log into your Pretalx instance
2. Go to Settings → API Access
3. Generate new API token
4. Add to `config_local.yaml` under `pytanis.PRETALX_API_TOKEN`

## Directory Structure

```
.work/{event}/
└── pretalx_records/        # Session data (one JSON per session)
    ├── 7CXSPN.json        # Session record with all details
    ├── LRUKZQ.json
    └── 3CYZUH.json
```

## Usage

### Fetch All Session Records

```bash
# Fetch all sessions for the configured event
python -m src.pipeline.pretalx.fetch_records
```

This will:
1. Connect to Pretalx API using pytanis
2. Fetch all sessions for the event
3. Fetch all speakers
4. Combine session + speaker + custom question data
5. Convert markdown fields to plain text
6. Save individual JSON files to `.work/{event}/pretalx_records/`

### Output Structure

Each session creates a file `{CODE}.json` containing:

```json
{
  "code": "7CXSPN",
  "title": "AI Agents of Change: Creating, Reflecting, and Monetizing",
  "abstract": "Plain text abstract (converted from markdown)...",
  "description": "Plain text description (converted from markdown)...",
  "duration": 30,
  "slot_count": 1,
  "state": "confirmed",
  "do_not_record": false,
  "is_featured": false,
  "content_locale": "en",
  "speakers": [
    {
      "name": "Jane Doe",
      "biography": "Plain text bio (converted from markdown)...",
      "avatar": "https://pretalx.com/media/...",
      "code": "ABC123",
      "email": "jane@example.com",
      "answers": {
        "company": "Example Corp",
        "job": "Senior Engineer",
        "linkedin": "https://linkedin.com/in/janedoe",
        "github": "https://github.com/janedoe",
        "x_handle": "@janedoe",
        "python_expertise": "Advanced",
        "domain_expertise": "Machine Learning",
        "prerequisites": "Basic Python knowledge"
      }
    }
  ],
  "track": "PyData: Machine Learning, Stats",
  "submission_type": "Talk"
}
```

## Data Models

### SessionRecord

Main data structure containing:
- `code`: Pretalx session code (6 chars)
- `title`: Session title
- `abstract`: Short description (plain text)
- `description`: Full description (plain text)
- `duration`: Length in minutes
- `state`: Submission state (confirmed, accepted, etc.)
- `do_not_record`: Flag to exclude from video processing
- `speakers`: List of speaker information
- `track`: Conference track name
- `submission_type`: Talk, Workshop, Panel, etc.

### SpeakerInfo

Speaker details:
- `name`: Full name
- `biography`: Speaker bio (plain text)
- `code`: Pretalx speaker code
- `email`: Contact email
- `answers`: Custom question responses (company, social media, etc.)

## Integration with Pipeline

The Pretalx records are used by:

1. **Video Organization**: Maps video files to sessions via code
2. **YouTube Metadata**: Provides titles, descriptions for video updates
3. **Text Generation**: Source data for AI-generated summaries
4. **Notifications**: Speaker contact information

## Markdown Conversion

Pretalx stores content as markdown. This module converts to plain text for:
- `abstract`: Session abstract
- `description`: Full description
- `biography`: Speaker bios

This ensures clean, readable text for YouTube descriptions and AI processing.

## Custom Questions

The `questions_map` in config maps question IDs to friendly names:

```yaml
questions_map:
  company: 4390      # Speaker's company
  linkedin: 4394     # LinkedIn profile URL
```

Answers are stored in `speaker.answers` dictionary with friendly keys.

## Error Handling

- **API failures**: Clear error messages with retry guidance
- **Missing data**: Logs warnings for incomplete records
- **Invalid markdown**: Falls back to raw text if conversion fails

## Complete Workflow Example

```bash
# 1. Ensure config is set up
cat config_local.yaml | grep -A 5 pretalx

# 2. Fetch all records
python -m src.pipeline.pretalx.fetch_records

# 3. Verify output
ls .work/pyconde-pydata-2025/pretalx_records/
# Should show multiple {CODE}.json files

# 4. Inspect a record
cat .work/pyconde-pydata-2025/pretalx_records/7CXSPN.json | jq .

# 5. Proceed with next pipeline steps
# (video organization, metadata preparation, etc.)
```

## Troubleshooting

### No sessions found
- Verify `event_slug` matches Pretalx event
- Check API token has correct permissions
- Confirm event has confirmed sessions

### Missing speaker data
- Check speaker has completed their profile
- Verify custom questions are published

### API rate limiting
- Pytanis handles pagination automatically
- For large events, fetching may take several minutes

## Module Components

### `fetch_records.py`
- Main script for fetching Pretalx data
- Uses pytanis client for API access
- Combines sessions, speakers, questions
- Converts markdown to plain text
- Saves individual JSON files

### `models.py`
- `SessionRecord`: Complete session data structure
- `SpeakerInfo`: Speaker details with custom answers
- `Organization`: Event organization info
- Pydantic validation ensures data integrity

## See Also

- [YouTube Module](../youtube/README.md) - Uses Pretalx records for metadata
- [Text Generation Module](../text_generation/README.md) - Generates summaries from records
- [Pytanis Documentation](https://github.com/pytanis/pytanis) - Pretalx API client
