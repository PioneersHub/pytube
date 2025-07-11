# Map Videos Debugging Scripts

These scripts allow you to debug the YouTube video mapping process independently from the CLI framework. Three versions are provided for different debugging scenarios:

1. **map_videos_debug.py** - Uses existing codebase with debug output
2. **map_videos_standalone.py** - Full featured standalone version
3. **map_videos_standalone_simple.py** - Minimal dependencies version

## Features

- **Independent execution**: Run directly without CLI framework
- **Debugger-friendly**: Clear function boundaries for setting breakpoints
- **Authentication options**: Switch between OAuth and API key authentication
- **Channel filtering**: Test individual channels or all channels
- **Debug output**: Saves intermediate results to JSON files
- **Step-by-step execution**: Each major step is clearly separated

## Quick Start

### Using map_videos_debug.py (Recommended)

This version uses the existing codebase and provides detailed debug output:

```bash
# Run with OAuth (default)
python scripts/map_videos_debug.py

# Run with API key
python scripts/map_videos_debug.py --auth apikey

# Filter to specific channel
python scripts/map_videos_debug.py --channel pycon
```

### Using map_videos_standalone_simple.py (Minimal Dependencies)

Use this if you have import issues:

```bash
# Install minimal dependencies
uv pip install google-auth-oauthlib google-api-python-client pyyaml

# Run the script
python scripts/map_videos_standalone_simple.py
```

### Using map_videos_standalone.py (Full Featured)

```bash
# Run with OAuth authentication (default)
python scripts/map_videos_standalone.py

# Run with API key authentication
python scripts/map_videos_standalone.py --auth apikey

# Filter to specific channel
python scripts/map_videos_standalone.py --channel pycon
python scripts/map_videos_standalone.py --channel pydata

# Test a specific channel only
python scripts/map_videos_standalone.py --test-channel pycon
```

### Debugging in VS Code

Add this configuration to your `.vscode/launch.json`:

```json
{
    "name": "Debug Map Videos",
    "type": "python",
    "request": "launch",
    "program": "${workspaceFolder}/scripts/map_videos_standalone.py",
    "args": ["--auth", "oauth"],
    "console": "integratedTerminal",
    "justMyCode": false
}
```

### Debugging in PyCharm

1. Right-click on `map_videos_standalone.py`
2. Select "Debug 'map_videos_standalone'"
3. Or create a Run Configuration:
   - Script path: `scripts/map_videos_standalone.py`
   - Parameters: `--auth oauth`
   - Working directory: Project root

## Key Breakpoint Locations

1. **Authentication**: Set breakpoint in `authenticate()` method
   - Line checking `if self.use_oauth:`
   - OAuth flow: `self.youtube_client.get_authenticated_service()`
   - API key flow: `self.youtube_client.get_authenticated_service_via_api_key()`

2. **Playlist Retrieval**: Set breakpoint in `retrieve_videos_from_playlists()`
   - Before the channel loop
   - Inside `self.youtube_client.get_youtube_ids_for_uploads(channel)`

3. **Video Mapping**: Set breakpoint in `map_pretalx_to_youtube()`
   - Before calling `self.youtube_client.map_pretalx_id_youtube_id()`

4. **Error Handling**: Set breakpoints in all except blocks

## Output Files

The script creates a `debug_map_videos/` directory with:

- `mapping_results.json`: Complete results including errors and warnings
- `playlist_pycon.json`: Copy of PyConDE playlist data (if available)
- `playlist_pydata.json`: Copy of PyData playlist data (if available)

## Common Issues to Debug

### Authentication Issues

1. **OAuth Token Expired**
   - Check token file: `_secret/youtube_token.json`
   - Delete token file to force re-authentication

2. **Wrong Client Secrets File**
   - Verify `config_local.yaml` points to correct file
   - Should be: `client_secrets_file: ./_secret/client_secrets.json`

3. **API Key Issues**
   - API key can't access private videos
   - Will show "Private video" for all titles

### Playlist Access Issues

1. **404 Errors**
   - Playlist ID is incorrect
   - Playlist was deleted

2. **403 Errors**
   - Playlist is private
   - Requires OAuth authentication

3. **Empty Playlists**
   - No videos uploaded yet
   - Videos not added to playlist

## Debugging Tips

1. **Start with test-channel**:
   ```bash
   python scripts/map_videos_standalone.py --test-channel pycon
   ```
   This tests authentication and basic playlist access.

2. **Check intermediate files**:
   - Look in `_tmp/{event_slug}/videos/` for:
     - `youtube_pycon_playlist.json`
     - `youtube_pydata_playlist.json`
     - `pretalx_yt_map.json`

3. **Enable detailed logging**:
   Add this to the script for more verbose output:
   ```python
   logging.getLogger('googleapiclient.discovery').setLevel(logging.DEBUG)
   ```

4. **Test API directly**:
   Use the YouTube API Explorer to test your playlist IDs:
   https://developers.google.com/youtube/v3/docs/playlistItems/list
