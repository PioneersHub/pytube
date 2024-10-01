# YouTube

!!! note
    In general, the YouTube API is sometimes oddly limited for users that are not a content network.
    Some workarounds are necessary.

!!! warning
    The Google-API wrapper currently does not work for macOS Sequoia, yet (22.09.2024).

## Preparations / Prerequisites

👉A Google user account is required.  
👉This user account needs to have access to the YouTube channel.
👉A Google Cloud Project with YouTube API V3 enabled. [See the required API access below.](#api).

👉Add the YouTube channel id to the local configuration file `config_local.yaml. 
```yaml
youtube:
  channels:
    my_channel:
      id: "MYCHANNELID"
```
If unknown, one can retrieve the YouTube channel id via running:

```python
from pytube.handlers.youtube import YT

yt = YT()
yt.get_channel_id()
```

## Uploading Videos

👉Videos need to be uploaded via the 🖥 **[YouTube studio web interface](https://studio.youtube.com/)**️.  
By the way, API Uploads is not an option as they make videos 'private' by default, 
and there is no way to change this setting afterward.

Uploading is easy: one can upload 15 videos at a time by drag and drop.

👉All following steps are required:

1. Include **Pretix-Session-ID in file names**, e.g., *{PreTix-Session-ID}-{Title}.mp4*.
2. Make sure in YouTube Studio in **Settings/Upload defaults** the title is **empty**.  
   YouTube will use the filename as title then, we need this to match the descriptions' metadata to the video uploads.
3. Add all videos uploaded to a **hidden playlist** (workaround)

### YouTube Video IDs via a Hidden Playlist

After videos are uploaded to YouTube, we need to update the metadata.  
To update the metadata, we need the YouTube video ids.  

Metadata of unpublished videos is not available via the YouTube API but
can be retrieved via an **unpublished playlist** (workaround).

Add the playlist id in the `local_config.yaml` file:

```yaml
youtube:
  channels:
    my_channel:
      playlist_id: "playlist_id_ADD_HERE"
```

### Mapping YouTube Video IDs to Pretalx IDs

You need to **prepare mapping files** for the processing pipeline.
These files are expected by the handler (`Publisher`) by convention. 

The methods below create mappings of the pretalx id and the YouTube id and store them in JSON files.

```python
from pytube.handlers.youtube import YT

yt = YT()
yt.get_youtube_ids_for_uploads("my_channel")

# Match the pretalx id with the YouTube video id
yt.map_pretalx_id_youtube_id()
```

### Caveats

👉 It's impossible to get the filename used for the upload via the API, although the information is
  available via the web interface. Do follow the steps above, step 2.  
👉 API limits: Queries are limited per day, use them wisely.

## Scheduling Videos

The `PrepareVideoMetadata` handler class provides a method to set the publishing date of the videos in the video metadata.

```python
from datetime import datetime, timedelta, UTC
from pytube.handlers.youtube import PrepareVideoMetadata

meta = PrepareVideoMetadata("template_file", "great conference name")
...
# when to start and how often to publish
in_five_minutes = datetime.now(UTC) + timedelta(minutes=5)
every_four_hours = timedelta(hours=4)

meta.update_publish_dates(start=in_five_minutes, delta=every_four_hours)
```

## API

Access to the YouTube API V3 is required to update the metadata of the videos.
To access the YouTube API V3 a Google Cloud project is required.

### How to Get a YouTube API Key

1. Log in to Google Developers Console.
2. Create a new project.
3. On the new project dashboard, click Explore & Enable APIs.
4. In the library, navigate to YouTube Data API v3 under YouTube APIs.
5. Enable the YouTube API V3.
6. Create credentials:  
    a. API key  
    b. OAuth2.0 client ID

There are plenty of detailed tutorials available on the web.

### Caveats

👉 Metadata updates require OAuth2.0 authentication. API keys or service accounts are not sufficient.  
👉 Status updates can be requested with a simple API key.
