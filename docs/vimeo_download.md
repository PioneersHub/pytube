# Vimeo Bulk Download

Download raw conference livestream recordings from Vimeo using the
`pytube video bulk-download` command. This is **Stage 1** of the auto-cut
pipeline — for the full walkthrough (download → session mapping → break-image
setup → auto-cutting), see the
[Auto-Cut Pipeline guide](auto-cut-pipeline.md).

## What it does

- Lists videos from one or more Vimeo source accounts (via `folder_id`,
  `title_contains`, or `title_regex`).
- Picks the best-quality progressive download link per video.
- Streams each video to `{target}.mp4.part` and atomic-renames on success.
- Writes `_metadata/{vimeo_id}.json` sidecars for audit.
- Preserves the sanitized Vimeo title as the filename so downstream tooling
  (`process_talk_list.py`) can match recordings to Pretalx sessions.
- Honours a `removed/` subdirectory as a permanent skip-list.

## Configuration

All settings live under `vimeo.raw_sources` in `config_local.yaml`:

| Key | Meaning |
| --- | --- |
| `accounts[].name` | Label shown in logs and CLI output |
| `accounts[].client_id` / `client_secret` / `access_token` | Vimeo API credentials |
| `accounts[].user_id` | Required only when `selection.folder_id` is set |
| `accounts[].selection.folder_id` | Fetch every video from a Vimeo project/folder |
| `accounts[].selection.title_contains` | Substring match on `/me/videos` titles |
| `accounts[].selection.title_regex` | Regex match on `/me/videos` titles |
| `download.output_dir` | **Must equal** the auto-cutter's `input.folder` |
| `download.quality` | `best` \| `1080p` \| `720p` \| `480p` |
| `download.max_concurrent` | Per-account parallel downloads (default `2`) |
| `download.max_accounts_concurrent` | Accounts in parallel (default `1` = serial) |
| `download.retry_max_attempts` | Exponential-backoff retries on transient errors (default `3`) |
| `download.skip_existing` | Skip files already present on disk (default `true`) |

Each account must set **exactly one** of `folder_id`, `title_contains`, or
`title_regex`. The validator at
[src/manager/config.py](../src/manager/config.py) rejects configs that
violate this.

### Example

```yaml
vimeo:
  raw_sources:
    accounts:
      - name: "main-stage"
        client_id: "..."
        client_secret: "..."
        access_token: "..."
        user_id: "12345678"
        selection:
          folder_id: "98765432"
    download:
      output_dir: "/Volumes/DATA/_pyconde2026/videos/input"
      quality: "best"
      max_concurrent: 2
      skip_existing: true
```

## CLI

```bash
# Print the rename plan; no HTTP downloads happen
pytube video bulk-download --dry-run

# Download everything configured
pytube video bulk-download

# Restrict to one account
pytube video bulk-download --account main-stage

# Smoke-test with a budget
pytube video bulk-download --account main-stage --limit 2
```

## Blocklist — `{output_dir}/removed/`

Move unwanted recordings (break-only streams, test uploads, re-renders) into
the `removed/` subdirectory and they will be skipped on every subsequent run.
Match is by sanitized filename or by trailing `_{vimeo_id}` suffix.

## Getting Vimeo credentials

1. Create a Vimeo developer account at <https://developer.vimeo.com/>.
2. Register an app per source account.
3. Generate an access token with the `private` scope and download permissions.

Also see [API Credentials](api-credentials.md).

## Next step

Continue with the
[Auto-Cut Pipeline guide, Stage 2](auto-cut-pipeline.md#stage-2-build-the-sessionrecording-mapping-parquet).
