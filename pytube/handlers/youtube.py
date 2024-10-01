import json
import platform
import random
import warnings
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from jinja2 import Environment, PackageLoader, select_autoescape
from models.sessions import SessionRecord
from models.video import BaseRecordingDetails, VideoSnippet, YouTubeMetadata, YoutubeVideoResource
from usr.usr import slugify

from pytube import conf, logger


class YT:
    def __init__(self, youtube_offline: bool = False):
        # Set up the necessary scopes and API service
        self.scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
        self._youtube = None

        self.youtube_offline = youtube_offline

        self.video_records_path = conf.dirs.video_dir / 'youtube/video_records'
        self.video_records_path.mkdir(parents=True, exist_ok=True)
        # data updated at YouTube
        self.video_records_path_updated = conf.dirs.video_dir / 'youtube/video_records_updated'
        self.video_records_path_updated.mkdir(parents=True, exist_ok=True)
        # videos published on YouTube
        self.video_records_path_published = conf.dirs.video_dir / 'youtube/video_published'
        self.video_records_path_published.mkdir(parents=True, exist_ok=True)

    @property
    def youtube(self):
        """ Get authenticated service on first call of API"""
        if not self._youtube:
            if self.youtube_offline:
                # API calls that work with service accounts
                self._youtube = self.get_authenticated_offline_service()
            else:
                # API calls that require 'live' user authentication
                self._youtube = self.get_authenticated_service()
        return self._youtube

    def get_authenticated_service(self):
        """ Authentication to access the channel information
        - Users need to authenticate via a web interface
        - User needs to have rights to access channel
        """
        exit_if_sequoia = self.check_macos_sequoia()
        if exit_if_sequoia:
            raise RuntimeError("macOS Sequoia detected. Exiting.")
        api_service_name = "youtube"
        api_version = "v3"
        client_secrets_file = conf.youtube.client_secrets_file

        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(client_secrets_file, self.scopes)
        credentials = flow.run_local_server(port=0)

        return googleapiclient.discovery.build(api_service_name, api_version, credentials=credentials)

    def get_authenticated_offline_service(self):
        """ Works for limited use cases only due to general restrictions by YouTube,
        >>NOT suitable for updating video metadata<<"""
        creds = None

        # The token.json stores the user's access and refresh tokens, and is created automatically
        # when the authorization flow completes for the first time.
        client_secrets_file = conf.youtube.client_secrets_file
        token_path = conf.dirs.root / conf.youtube.token_path
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)

        # If no valid credentials are available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Create a flow object, set the client secrets, and ask for offline access
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secrets_file, self.scopes)
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with token_path.open("w") as token:
                token.write(creds.to_json())

        # Create a YouTube API service
        service = build('youtube', 'v3', credentials=creds)
        return service

    def get_authenticated_service_via_api_key(self):
        self._youtube = build('youtube', 'v3', developerKey=conf.youtube.api_key)

    def get_channel_id(self):
        """ Required if channel id is unknown """
        request = self.youtube.channels().list(
            part="id",
            mine=True
        )
        response = request.execute()
        return response["items"][0]["id"]

    # Function to list all videos in the channel
    def list_all_videos(self, channel_id, max_pages=5):
        """

        :param channel_id:
        :param max_pages: Some channels have a lot of content - we ar only interested in the recent uploads
        :return:
        """
        videos = []
        request = self.youtube.search().list(
            part="snippet",
            channelId=channel_id,
            maxResults=50,
            order="date",
            forMine=True
        )
        response = request.execute()

        while request is not None and max_pages:
            videos.extend(response["items"])
            max_pages -= 1
            request = self.youtube.search().list_next(request, response)
            if request:
                response = request.execute()

        return videos

    def list_all_videos_in_playlist(self, playlist_id):
        """
        Unpublished videos cannot be accessed via the API.
        Listing all unpublished videos in the channel requires a trick:
          - put unpublished videos in a playlist
          - the playlist is accessible via the API

        :param playlist_id:
        :return:
        """
        videos = []
        request = self.youtube.playlistItems().list(
            part="snippet,contentDetails",
            maxResults=50,
            playlistId=playlist_id
        )
        response = request.execute()
        while request is not None:
            videos.extend(response['items'])
            request = self.youtube.playlistItems().list_next(request, response)
            if request:
                response = request.execute()
        return videos

    def update_video_metadata(self, video_id,  # noqa: PLR0913
                              title=None,
                              description=None,
                              tags=None,
                              category_id=None,
                              privacy_status=None,
                              publish_date=None
                              ):

        # Prepare the request body
        body = {
            "id": video_id,
            "snippet": {},
            "status": {}
        }

        if title:
            body["snippet"]["title"] = title
        if description:
            body["snippet"]["description"] = description
        if tags:
            body["snippet"]["tags"] = tags
        if category_id:
            body["snippet"]["categoryId"] = category_id
        if privacy_status:
            body["status"]["privacyStatus"] = privacy_status
        if publish_date:
            # required by YouTube
            body["status"]["privacyStatus"] = 'private'
            if isinstance(publish_date, str):
                publish_date = datetime.strptime(publish_date, '%Y-%m-%dT%H:%M:%S%z')
            elif isinstance(publish_date, datetime):
                publish_date = publish_date.strftime('%Y-%m-%dT%H:%M:%S%z')
            else:
                raise ValueError("Publish date must be a string or datetime object")
            body["status"]["publishAt"] = publish_date

        # Update video metadata
        request = self.youtube.videos().update(
            part="snippet,status",
            body=body
        )
        response = request.execute()

        print(f"Updated video metadata for video ID: {video_id}")
        return response

    def check_macos_sequoia(self):
        if self.youtube_offline:
            # does not apply when using a service account
            return False
        system = platform.system()
        version = platform.mac_ver()[0]
        if system == "Darwin" and version.startswith("15."):  # macOS Sequoia is version 15.x
            warnings.warn("Warning: macOS Sequoia (14.x) detected.", UserWarning)  # noqa: B028
            return True
        return False

    def check_video_status_by_youtube_ids(self, video_id: str | list[str]):
        if isinstance(video_id, str):
            video_id = [video_id]
        video_ids = ",".join(video_id)
        request = self.youtube.videos().list(
            part="status",
            id=video_ids
        )
        response = request.execute()
        return response

    def get_youtube_ids_for_uploads(self, youtube_channel: str):
        """ Save the YouTube video ids for the uploads to the channel to file.
        This file is required for the metadata management to map the pretalx id with the YouTube video id.
        :param youtube_channel: str, the channel name to get the video ids for, must match the name in the config
        """
        # After videos are uploaded to YouTube, we need to update the metadata
        # To update the metadata, we need the YouTube video id
        # unpublished videos data can be retrieved via an unpublished playlist only
        # youtube_pydata_playlist
        videos = self.list_all_videos_in_playlist(conf.youtube.channels[youtube_channel].playlist_id)
        json.dump(videos, (conf.dirs.video_dir / f"youtube_{youtube_channel}_playlist.json").open("w"),
                  indent=4)

    def get_channel_id_for_config(self):
        """Log the channel ID for the config.
        The channel id can be accessed via a OAuth2 login.
        """
        channel_id = self.get_channel_id()
        logger.info(f"Channel ID: {channel_id}")

    @classmethod
    def map_pretalx_id_youtube_id(cls):
        """ The pretalx id is in the video title after upload.
        We need to create a map of pretalx id to the YouTube video id
        before updating the data on YouTube. """
        videos = []
        for channel in conf.youtube.channels:
            data = json.load((conf.dirs.video_dir / f"youtube_{channel}_playlist.json").open())
            videos.extend(data)
        pretalx_yt_map = {}
        for video in videos:
            pretalx_id = video["snippet"]["title"].strip()[:6]
            youtube_id = video["snippet"]["resourceId"]["videoId"]
            pretalx_yt_map[pretalx_id] = youtube_id
        json.dump(pretalx_yt_map, (conf.dirs.video_dir / "pretalx_yt_map.json").open("w"), indent=4)


class PrepareVideoMetadata:
    # noinspection GrazieInspection
    """ This class adds YouTube specific metadata to the records created by the records.py script
        For the descriptions we use a Jinja2 template.
        Many values are hard coded, as they are not expected to change often, e.g.,
            category_id = 28 - Science & Technology
            default_language = 'en' - English
            privacy_status = 'unlisted'
            video_license = 'youtube'
            video_embeddable = True
        """

    def __init__(self, template_file: str, at):
        self.template_file = template_file
        self.at = at
        self._pretalx_youtube_channel_map = {}
        self._pretalx_youtube_id_map = {}
        self.yt_metadata = []
        self._template = None

        self.load_yt_metadata()

        self.records_path = conf.dirs.work_dir / 'records'
        self.video_records_path = conf.dirs.video_dir / 'youtube/video_records'
        self.video_records_path.mkdir(parents=True, exist_ok=True)
        # default values

    @property
    def template(self):
        """ Load template on first call """
        if not self._template:
            self.load_template()
        return self._template

    @property
    def pretalx_youtube_channel_map(self):
        """ Depends on a previously created mapping file {pretalx ID: YouTube channel} see `video_organizer.py`"""
        if not self._pretalx_youtube_channel_map:
            self._pretalx_youtube_channel_map = json.load((conf.dirs.video_dir / "tracks_map.json").open())
        return self._pretalx_youtube_channel_map

    @property
    def pretalx_youtube_id_map(self):
        """ Depends on a previously created mapping file {pretalx ID: YouTube video ID} see `video_organizer.py`"""
        if not self._pretalx_youtube_id_map:
            self._pretalx_youtube_id_map = json.load((conf.dirs.video_dir / "pretalx_yt_map.json").open())
        return self._pretalx_youtube_id_map

    @property
    def youtube_id_pretalx_map(self):
        return {v: k for k, v in self.pretalx_youtube_id_map.items()}

    def load_yt_metadata(self):
        videos = []
        for channel in conf.youtube.channels:
            data = json.load((conf.dirs.video_dir / f"youtube_{channel}_playlist.json").open())
            videos.extend(data)
        for video in videos:
            ytv = YouTubeMetadata(**video["snippet"])
            self.yt_metadata.append(ytv)

    def load_template(self):
        env = Environment(
            loader=PackageLoader("src"),
            autoescape=select_autoescape()
        )
        self._template = env.get_template(self.template_file)

    def make_all_video_metadata(self):
        manifest = json.load((conf.dirs.work_dir / "manifest.json").open())
        for video in manifest:
            self.make_video_metadata(video)

    @classmethod
    def best_youtube_title(cls, title, at):
        """ The YouTube title must have max. 100 chars, optimize the title to include the conference """
        yt_max = 100
        # remove restricted chars
        title = title.replace('>', '').replace('<', '')
        if len(title) > yt_max:
            return f"{title[:yt_max - 1]}…"
        long_title = f"{title} [{at}]"
        if len(long_title) <= yt_max:
            return long_title
        return title

    def make_video_metadata(self, video):
        """
        Collect all metadata for a video and merge it into a single document, store this document in the JSON record.
        """
        # load record
        record = SessionRecord.model_validate_json((self.records_path / f"{video['pretalx_id']}.json").read_text())
        # update record with video info if necessary
        update_record = False
        youtube_channel = self.pretalx_youtube_channel_map[video["pretalx_id"]]
        try:
            youtube_video_id = self.pretalx_youtube_id_map[video["pretalx_id"]]
        except KeyError:
            logger.warning(f'No YouTube video ID found for {video["pretalx_id"]}-{video["title"]}, skipping')
            return

        youtube_title = self.best_youtube_title(record.title, self.at)
        recorded_date = record.pretalx_session.session.slot.start

        if record.youtube_channel != youtube_channel:
            logger.info(f'Updating YouTube channel of {record.pretalx_id}')
            record.youtube_channel = youtube_channel
            update_record = True
        if record.youtube_video_id != youtube_video_id:
            logger.info(f'Updating YouTube video ID of {record.pretalx_id}')
            record.youtube_video_id = youtube_video_id
            update_record = True
        if record.youtube_title != youtube_title:
            logger.info(f'Updating YouTube title of {record.pretalx_id}')
            record.youtube_title = youtube_title
            update_record = True
        if record.recorded_date != recorded_date:
            logger.info(f'Updating YouTube recorded date of {record.pretalx_id}')
            # remove time zone info
            record.recorded_date = datetime.strptime(recorded_date.strftime("%d.%m.%Y"), "%d.%m.%Y")
            update_record = True

        def render_description(description: str = record.sm_long_text):
            text = self.template.render(
                date=record.recorded_date.strftime("%d.%m.%Y"),
                session_link=f"https://2024.pycon.de/program/{record.pretalx_id}/",
                teaser_text=record.sm_teaser_text,

                speakers=', '.join([f"{s.name}" for s in record.speakers]),
                description=description,
                tag=slugify(record.pretalx_session.session.track.en),
                pydata=record.youtube_channel == "pydata",
            )
            return text

        youtube_description = render_description()
        # <, > not allowed in YT titles, description
        youtube_description = youtube_description.replace('>', '').replace('<', '')
        if len(youtube_description) > conf.youtube.max_description_length:
            logger.info(f'YouTube description of {record.pretalx_id} is too long: {len(youtube_description)}>5000')
            render_description(description=record.sm_short_text)
        if len(youtube_description) > conf.youtube.max_description_length:
            logger.error(f'YouTube description of {record.pretalx_id} is too long: {len(youtube_description)}>5000')
            render_description(description="")

        if record.youtube_description != youtube_description:
            logger.info(f'Updating YouTube description of {record.pretalx_id}')
            record.youtube_description = youtube_description
            update_record = True

        if update_record:
            (self.records_path / f'{record.pretalx_id}.json').write_text(record.model_dump_json(indent=4))
            logger.info(f'Saved updated record of {record.pretalx_id}')

        recorded_iso: str = record.recorded_date.strftime("%d.%m.%Y")

        youtube_video_ressource = YoutubeVideoResource(
            id=youtube_video_id,
            snippet=VideoSnippet(**{
                "title": youtube_title,
                "description": youtube_description,
            }),
            recording_details=BaseRecordingDetails(**{"recording_date": recorded_iso}),
        )

        (self.video_records_path / f'{record.pretalx_id}.json').open("w").write(
            youtube_video_ressource.model_dump_json(indent=4))
        print("=" * 50)

    def send_all_video_metadata(self, destination_channel: str):
        logger.info(f"Updating metadata for channel {destination_channel}")
        ytclient = YT()
        for youtube_video in self.video_records_path.glob("*.json"):
            video = YoutubeVideoResource.model_validate_json(youtube_video.read_text())
            pretalx_id = self.youtube_id_pretalx_map.get(video.id)
            if not pretalx_id:
                # no pretalx id found, skip
                continue
            channel = self.pretalx_youtube_channel_map.get(pretalx_id)
            if not channel:
                # no channel id found, skip
                continue
            if channel != destination_channel:
                # wrong channel, skip
                continue
            try:
                ytclient.update_video_metadata(
                    video_id=video.id,
                    title=video.snippet.title,
                    description=video.snippet.description,
                    category_id=video.snippet.category_id,
                    privacy_status=video.status.privacy_status,
                    publish_date=video.status.publish_at
                )
                youtube_video.rename(ytclient.video_records_path_updated / youtube_video.name)
                logger.info(f"Updated video: {pretalx_id}, {video.id}")
            except Exception as e:
                logger.error(f"Failed to update video {video.id}: {e}")
                continue

    def update_video_metadata(self, states: str | list[str], func: callable):
        """ update record files with video metadata created already.
        :param states: str or list of str, values: 'video_records', 'video_records_updated'
        :param func: custom method to apply to the record
        """
        if isinstance(states, str):
            states = [states]
        for state in states:
            if state not in ('video_records', 'video_records_updated'):
                continue
            for record in (self.video_records_path.parent / state).glob("*.json"):
                func(record)

    @classmethod
    def update_publish_date(cls, record: Path, publish_date: datetime):
        """ Sets the publishing date at YouTube for videos"""
        with record.open("r") as f:
            record_data = json.load(f)
        record_data["status"]["publish_at"] = publish_date.isoformat()
        print("Updated publish date to", publish_date.isoformat())
        with record.open("w") as f:
            json.dump(record_data, f, indent=4)

    def update_publish_dates(self, states: str | list[str] | tuple[str] = ('video_records', 'video_records_updated'),
                             start: datetime | None = None,
                             delta: timedelta | None = None,
                             end: datetime | None = None,
                             steps: int | None = None):
        """" Update or add periodical publishing dates for videos randomly."""
        if isinstance(states, str):
            states = [states]
        if start is None:
            start = datetime.now(UTC)
        gen = self.publish_dates_generator(start, delta=delta, end=end, steps=steps)
        records = []
        for state in states:
            if state not in ('video_records', 'video_records_updated'):
                continue
            records.extend(list((self.video_records_path.parent / state).glob("*.json")))
        random.shuffle(records)
        for record, publish_at in zip(records, gen, strict=False):
            self.update_publish_date(record, publish_at)
            # move to queue for YouTube metadata updates
            record.rename(self.video_records_path / record.name)
            logger.info(f"Updated publish date for {record.name} in the video file."
                        "Please do not forget to publish the update.")

    @staticmethod
    def publish_dates_generator(start: datetime, delta: timedelta | None = None, end: datetime | None = None,
                                steps: int | None = None) -> Generator[datetime]:
        """ Create a list of publishing dates for the videos """
        if end is None and delta is None:
            raise ValueError("Either end (datetime) or delta (release every timeperiod) must be provided")
        if delta is not None:
            while True:
                yield start
                start += delta
        if not isinstance(steps, int):
            raise ValueError("Steps must be an integer")
        if steps <= 1:
            raise ValueError("Steps must be provided")
        period = (end - start) / steps
        # noinspection PyTypeChecker
        for i in range(steps):
            yield start + period * i
