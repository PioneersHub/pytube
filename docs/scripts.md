# Scripts

Scripts are used to run the jobs in the processing pipeline. They are located in the `scripts` directory.

## Pre-Processing Metadata to `Records`

For each video a record is created.
The record is a dictionary that contains all the metadata for a video.
The record is then used to create the video description and the video itself.

```python
from pytube.handlers import Records
from pytube import conf

# custom questions mapping
questions_map = conf.pretalx_questions_map

r = Records(qmap=questions_map)
r.load_all_confirmed_sessions()
r.load_all_speakers()
r.create_records()
r.add_descriptions(replace=False)
```

## Create Video Descriptions

The video descriptions are created from the records. This can be done in multiple steps at once or individually.
The methods update the records and their file location (status) accordingly.

```python
from datetime import UTC, datetime, timedelta

from handlers.youtube import PrepareVideoMetadata

from pytube import conf

meta = PrepareVideoMetadata("jinjs2_template.txt", "Great Conference Name")
meta.make_all_video_metadata()
meta.update_publish_dates(states=['video_records', 'video_records_updated'],
                          start=datetime.now(tz=UTC) + timedelta(minutes=5), delta=timedelta(hours=4))
for channel in conf.youtube.channels:
    meta.send_all_video_metadata(destination_channel=channel)
```

More about scheduling videos can be found [here](youtube.md#scheduling-videos).

## Notify

A script that should be run regularly until all videos are published.

1. Check for recent video releases on the YouTube channel.
2. Trigger LinkedIn posts and emails to speaker creation for all videos published since the last run.
3. Post on LinkedIn
4. Send emails to speakers

Run `scripts/notify.py`
