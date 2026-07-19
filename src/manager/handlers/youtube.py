import random
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

from manager import conf, logger
from manager.config import get_event_dir
from manager.handlers.records import Records, load_session_record
from manager.models.sessions import SessionRecord
from manager.models.video import (
    BaseRecordingDetails,
    VideoSnippet,
    YouTubeMetadata,
    YoutubeVideoResource,
)
from manager.utils.common import SafeConfig, ensure_directory, load_json, save_json


class YT:
    def __init__(self, youtube_offline: bool = False):
        # Set up the necessary scopes and API service
        self.scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
        self._youtube = None

        self.youtube_offline = youtube_offline

        # Use event-specific directory structure
        self.event_dir = get_event_dir(conf)
        self.video_records_path = self.event_dir / "videos" / "youtube" / "video_records"
        ensure_directory(self.video_records_path)
        # data updated at YouTube
        self.video_records_path_updated = self.event_dir / "videos" / "youtube" / "video_records_updated"
        ensure_directory(self.video_records_path_updated)
        # videos published on YouTube
        self.video_records_path_published = self.event_dir / "videos" / "youtube" / "video_published"
        ensure_directory(self.video_records_path_published)

    @property
    def youtube(self):
        """Get authenticated service on first call of API"""
        if not self._youtube:
            if self.youtube_offline:
                # API calls that work with service accounts
                self._youtube = self.get_authenticated_offline_service()
            else:
                # API calls that require 'live' user authentication
                self._youtube = self.get_authenticated_service()
        return self._youtube

    def get_authenticated_service(self):
        """Authentication to access the channel information
        - Users need to authenticate via a web interface
        - User needs to have rights to access channel
        """
        exit_if_sequoia = self.check_macos_sequoia()
        if exit_if_sequoia:
            raise RuntimeError("macOS Sequoia detected. Exiting.")
        api_service_name = "youtube"
        api_version = "v3"
        safe_conf = SafeConfig(conf)
        client_secrets_file = conf.dirs["root"] / safe_conf.get("youtube.client_secrets_file")
        if not client_secrets_file:
            raise ValueError("YouTube client secrets file not configured")

        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(client_secrets_file, self.scopes)
        credentials = flow.run_local_server(port=0)

        return googleapiclient.discovery.build(api_service_name, api_version, credentials=credentials)

    def get_authenticated_offline_service(self):
        """Works for limited use cases only due to general restrictions by YouTube,
        >>NOT suitable for updating video metadata<<"""
        creds = None

        # The token.json stores the user's access and refresh tokens, and is created automatically
        # when the authorization flow completes for the first time.
        safe_conf = SafeConfig(conf)
        client_secrets_file = safe_conf.get("youtube.client_secrets_file")
        if not client_secrets_file:
            raise ValueError("YouTube client secrets file not configured")
        root_dir = Path(safe_conf.get("dirs.root", "."))
        token_path_str = safe_conf.get("youtube.token_path", "token.json")
        token_path = root_dir / token_path_str
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)

        # If no valid credentials are available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Create a flow object, set the client secrets, and ask for offline access
                flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, self.scopes)
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with token_path.open("w") as token:
                token.write(creds.to_json())

        # Create a YouTube API service
        service = build("youtube", "v3", credentials=creds)
        return service

    def get_authenticated_service_via_api_key(self):
        safe_conf = SafeConfig(conf)
        api_key = safe_conf.get("youtube.api_key")
        if not api_key:
            raise ValueError("YouTube API key not configured")
        self._youtube = build("youtube", "v3", developerKey=api_key)

    def get_channel_id(self):
        """Required if channel id is unknown"""
        request = self.youtube.channels().list(part="id", mine=True)
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
            part="snippet", channelId=channel_id, maxResults=50, order="date", forMine=True
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
            part="snippet,contentDetails", maxResults=50, playlistId=playlist_id
        )
        response = request.execute()
        while request is not None:
            videos.extend(response["items"])
            request = self.youtube.playlistItems().list_next(request, response)
            if request:
                response = request.execute()
        return videos

    def update_video_metadata(
        self,
        video_id,  # noqa: PLR0913
        title=None,
        description=None,
        tags=None,
        category_id=None,
        privacy_status=None,
        publish_date=None,
    ):
        # Prepare the request body
        body = {"id": video_id, "snippet": {}, "status": {}}

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
            body["status"]["privacyStatus"] = "private"
            if isinstance(publish_date, str):
                publish_date = datetime.strptime(publish_date, "%Y-%m-%dT%H:%M:%S%z")
            elif isinstance(publish_date, datetime):
                publish_date = publish_date.strftime("%Y-%m-%dT%H:%M:%S%z")
            else:
                raise ValueError("Publish date must be a string or datetime object")
            body["status"]["publishAt"] = publish_date

        # Update video metadata
        request = self.youtube.videos().update(part="snippet,status", body=body)
        response = request.execute()

        print(f"Updated video metadata for video ID: {video_id}")
        return response

    def check_macos_sequoia(self):
        if self.youtube_offline:
            # does not apply when using a service account
            return False
        # system = platform.system()
        # version = platform.mac_ver()[0]
        # if system == "Darwin" and version.startswith("15."):  # macOS Sequoia is version 15.x
        #     warnings.warn("Warning: macOS Sequoia (14.x) detected.", UserWarning)  # noqa: B028
        #     return True
        return False

    def check_video_status_by_youtube_ids(self, video_id: str | list[str]):
        if isinstance(video_id, str):
            video_id = [video_id]
        video_ids = ",".join(video_id)
        request = self.youtube.videos().list(part="status", id=video_ids)
        response = request.execute()
        return response

    def get_youtube_ids_for_uploads(self, youtube_channel: str):
        """Save the YouTube video ids for the uploads to the channel to file.
        This file is required for the metadata management to map the pretalx id with the YouTube video id.
        :param youtube_channel: str, the channel name to get the video ids for, must match the name in the config
        :return: int, number of videos found in the playlist
        """
        # After videos are uploaded to YouTube, we need to update the metadata
        # To update the metadata, we need the YouTube video id
        # unpublished videos data can be retrieved via an unpublished playlist only
        # youtube_pydata_playlist
        safe_conf = SafeConfig(conf)
        channels = safe_conf.get("youtube.channels", {})
        if youtube_channel not in channels:
            raise ValueError(f"YouTube channel '{youtube_channel}' not configured in config")
        playlist_id = channels[youtube_channel].get("playlist_id")
        if not playlist_id:
            raise ValueError(f"Playlist ID not configured for channel '{youtube_channel}'")

        try:
            videos = self.list_all_videos_in_playlist(playlist_id)
        except Exception as e:
            err_str = str(e)
            if "404" in str(e) or "playlistNotFound" in err_str:
                msg = f"Playlist '{playlist_id}' not found or not accessible. The playlist may be private or the ID is incorrect."
            elif "403" in err_str:
                msg = f"Access denied to playlist '{playlist_id}'. This playlist may require OAuth authentication instead of API key."
            else:
                msg = f"Unable to access playlist '{playlist_id}': {err_str}"
            raise ValueError(msg) from e

        save_json(videos, self.event_dir / "videos" / f"youtube_{youtube_channel}_playlist.json")
        return len(videos)

    def get_channel_id_for_config(self):
        """Log the channel ID for the config.
        The channel id can be accessed via a OAuth2 login.
        """
        channel_id = self.get_channel_id()
        logger.info(f"Channel ID: {channel_id}")

    @classmethod
    def map_pretalx_id_youtube_id(cls, filter_by_channel=None):
        """Map Pretalx IDs to YouTube video IDs, respecting channel assignments.

        The pretalx id is extracted from the video title after upload.
        This method now respects channel assignments and do_not_record flags.

        Args:
            filter_by_channel: If specified, only process videos assigned to this channel

        Returns:
            tuple: (pretalx_yt_map, warnings) where warnings is a list of issues found
        """

        # Determine event directory for current context
        event_dir = get_event_dir(conf)
        safe_conf = SafeConfig(conf)
        video_dir = Path(safe_conf.get("dirs.video_dir", "."))

        # Load channel assignments if they exist
        tracks_map_file = video_dir / "tracks_map.json"
        channel_assignments = {}
        if tracks_map_file.exists():
            try:
                channel_assignments = load_json(tracks_map_file)
                logger.info(f"Loaded channel assignments for {len(channel_assignments)} videos")
            except Exception as e:
                logger.warning(f"Could not load channel assignments: {e}")

        # Load confirmed sessions to check do_not_record flag
        records = Records()
        session_data = records.confirmed_sessions_map

        # Process videos from YouTube playlists
        videos = []
        warnings = []

        safe_conf = SafeConfig(conf)
        channels = safe_conf.get("youtube.channels", {})
        for channel in channels:
            playlist_file = event_dir / "videos" / f"youtube_{channel}_playlist.json"
            if not playlist_file.exists():
                logger.warning(f"Playlist file not found: {playlist_file}")
                continue

            data = load_json(playlist_file)

            # Add channel info to each video
            for video in data:
                video["_channel"] = channel
            videos.extend(data)

        # Create the mapping with safety checks
        pretalx_yt_map = {}
        skipped_videos = []

        for video in videos:
            pretalx_id = video["snippet"]["title"].strip()[:6]
            youtube_id = video["snippet"]["resourceId"]["videoId"]
            video_channel = video.get("_channel", "unknown")

            # Check if we have session data for this video
            if pretalx_id not in session_data:
                warnings.append(f"Video {pretalx_id} not found in Pretalx data (YouTube ID: {youtube_id})")
                continue

            session = session_data[pretalx_id]

            # Check do_not_record flag
            if session.get("do_not_record", False):
                warnings.append(
                    f"WARNING: Video {pretalx_id} is marked as do_not_record but found in YouTube playlist! "
                    f"(YouTube ID: {youtube_id}, Channel: {video_channel})"
                )
                skipped_videos.append(
                    {
                        "pretalx_id": pretalx_id,
                        "youtube_id": youtube_id,
                        "title": session.get("title", "Unknown"),
                        "channel": video_channel,
                        "reason": "do_not_record",
                    }
                )
                continue

            # Check channel assignment
            if channel_assignments:
                assigned_channel = channel_assignments.get(pretalx_id)

                # Skip if assigned to no_publishing
                if assigned_channel == "no_publishing":
                    warnings.append(
                        f"WARNING: Video {pretalx_id} assigned to 'no_publishing' but found in YouTube! "
                        f"(YouTube ID: {youtube_id}, Channel: {video_channel})"
                    )
                    skipped_videos.append(
                        {
                            "pretalx_id": pretalx_id,
                            "youtube_id": youtube_id,
                            "title": session.get("title", "Unknown"),
                            "channel": video_channel,
                            "reason": "no_publishing",
                        }
                    )
                    continue

                # If filtering by channel, skip videos not assigned to that channel
                if filter_by_channel and assigned_channel != filter_by_channel:
                    logger.debug(
                        f"Skipping {pretalx_id} - assigned to {assigned_channel}, filtering for {filter_by_channel}"
                    )
                    continue

            # Add to mapping
            pretalx_yt_map[pretalx_id] = youtube_id
            logger.debug(f"Mapped {pretalx_id} -> {youtube_id} (Channel: {video_channel})")

        # Save the mapping
        output_file = event_dir / "videos" / "pretalx_yt_map.json"
        save_json(pretalx_yt_map, output_file)
        logger.info(f"Created YouTube mapping with {len(pretalx_yt_map)} videos")

        # Save skipped videos report if any were skipped
        if skipped_videos:
            skipped_file = event_dir / "videos" / "skipped_videos_report.json"
            save_json(
                {
                    "timestamp": datetime.now(tz=UTC).isoformat(),
                    "total_skipped": len(skipped_videos),
                    "videos": skipped_videos,
                },
                skipped_file,
            )
            logger.warning(f"Skipped {len(skipped_videos)} videos - see {skipped_file}")

        # Log warnings
        for warning in warnings:
            logger.warning(warning)

        return pretalx_yt_map, warnings


class PrepareVideoMetadata:
    # noinspection GrazieInspection
    """This class adds YouTube specific metadata to the records created by the records.py script
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

        # Use event-specific directory structure
        self.event_dir = get_event_dir(conf)
        self.records_path = self.event_dir / "records"
        self.video_records_path = self.event_dir / "videos" / "youtube" / "video_records"
        ensure_directory(self.video_records_path)
        # default values

    @property
    def template(self):
        """Load template on first call"""
        if not self._template:
            self.load_template()
        return self._template

    @property
    def pretalx_youtube_channel_map(self):
        """Depends on a previously created mapping file {pretalx ID: YouTube channel} see `video_organizer.py`"""
        if not self._pretalx_youtube_channel_map:
            self._pretalx_youtube_channel_map = load_json(self.event_dir / "videos" / "tracks_map.json")
        return self._pretalx_youtube_channel_map

    @property
    def pretalx_youtube_id_map(self):
        """Depends on a previously created mapping file {pretalx ID: YouTube video ID} see `video_organizer.py`"""
        if not self._pretalx_youtube_id_map:
            self._pretalx_youtube_id_map = load_json(self.event_dir / "videos" / "pretalx_yt_map.json")
        return self._pretalx_youtube_id_map

    @property
    def youtube_id_pretalx_map(self):
        return {v: k for k, v in self.pretalx_youtube_id_map.items()}

    def load_yt_metadata(self):
        videos = []
        safe_conf = SafeConfig(conf)
        channels = safe_conf.get("youtube.channels", {})
        for channel in channels:
            data = load_json(self.event_dir / "videos" / f"youtube_{channel}_playlist.json")
            videos.extend(data)
        for video in videos:
            ytv = YouTubeMetadata(**video["snippet"])
            self.yt_metadata.append(ytv)

    def load_template(self):
        env = Environment(loader=PackageLoader("src"), autoescape=select_autoescape())
        self._template = env.get_template(self.template_file)

    def make_all_video_metadata(self):
        manifest = load_json(self.event_dir / "manifest.json")
        for video in manifest:
            self.make_video_metadata(video)

    @classmethod
    def best_youtube_title(cls, title, at):
        """The YouTube title must have max. 100 chars, optimize the title to include the conference"""
        yt_max = 100
        # remove restricted chars
        title = title.replace(">", "").replace("<", "")
        if len(title) > yt_max:
            return f"{title[: yt_max - 1]}…"
        long_title = f"{title} [{at}]"
        if len(long_title) <= yt_max:
            return long_title
        return title

    def make_video_metadata(self, video):
        """
        Collect all metadata for a video and merge it into a single document, store this document in the JSON record.
        """
        # load record
        record = load_session_record(self.records_path / f"{video['pretalx_id']}.json")
        # update record with video info if necessary
        update_record = False
        youtube_channel = self.pretalx_youtube_channel_map[video["pretalx_id"]]
        try:
            youtube_video_id = self.pretalx_youtube_id_map[video["pretalx_id"]]
        except KeyError:
            logger.warning(f"No YouTube video ID found for {video['pretalx_id']}-{video['title']}, skipping")
            return

        youtube_title = self.best_youtube_title(record.title, self.at)
        recorded_date = record.pretalx_session.session.slot.start

        if record.youtube_channel != youtube_channel:
            logger.info(f"Updating YouTube channel of {record.pretalx_id}")
            record.youtube_channel = youtube_channel
            update_record = True
        if record.youtube_video_id != youtube_video_id:
            logger.info(f"Updating YouTube video ID of {record.pretalx_id}")
            record.youtube_video_id = youtube_video_id
            update_record = True
        if record.youtube_title != youtube_title:
            logger.info(f"Updating YouTube title of {record.pretalx_id}")
            record.youtube_title = youtube_title
            update_record = True
        if record.recorded_date != recorded_date:
            logger.info(f"Updating YouTube recorded date of {record.pretalx_id}")
            # remove time zone info
            record.recorded_date = datetime.strptime(recorded_date.strftime("%d.%m.%Y"), "%d.%m.%Y")
            update_record = True

        youtube_description = self.render_description(record.sm_long_text, record)
        # <, > not allowed in YT titles, description
        youtube_description = youtube_description.replace(">", "").replace("<", "")
        # Make sure the length is not too long
        safe_conf = SafeConfig(conf)
        yt_max = safe_conf.get("youtube.max_description_length", 5000)
        if len(youtube_description) > yt_max:
            logger.info(f"YouTube description of {record.pretalx_id} is too long: {len(youtube_description)}>{yt_max}")
            youtube_description = self.render_description(record.sm_short_text, record)
        if len(youtube_description) > yt_max:
            logger.error(f"YouTube description of {record.pretalx_id} is too long: {len(youtube_description)}>{yt_max}")
            youtube_description = self.render_description("", record)

        if record.youtube_description != youtube_description:
            logger.info(f"Updating YouTube description of {record.pretalx_id}")
            record.youtube_description = youtube_description
            update_record = True

        if update_record:
            (self.records_path / f"{record.pretalx_id}.json").write_text(record.model_dump_json(indent=4))
            logger.info(f"Saved updated record of {record.pretalx_id}")

        recorded_iso: str = record.recorded_date.strftime("%d.%m.%Y")

        youtube_video_ressource = YoutubeVideoResource(
            id=youtube_video_id,
            snippet=VideoSnippet(
                **{
                    "title": youtube_title,
                    "description": youtube_description,
                }
            ),
            recording_details=BaseRecordingDetails(**{"recording_date": recorded_iso}),
        )

        (self.video_records_path / f"{record.pretalx_id}.json").open("w").write(
            youtube_video_ressource.model_dump_json(indent=4)
        )
        print("=" * 50)

    def render_description(self, description: str, record: SessionRecord):
        """Provides commonly used values for rendering the description"""
        safe_conf = SafeConfig(conf)
        description_kwargs = {
            "date": record.recorded_date.strftime("%d.%m.%Y"),
            "session_link": f"{safe_conf.get('event.program_url', '')}{record.pretalx_id}/",
            "teaser_text": record.sm_teaser_text,
            "speakers": ", ".join([f"{s.name}" for s in record.speakers]),
            "description": description,
        }
        description_kwargs = self.customize_description_args(description_kwargs, record)
        text = self.template.render(**description_kwargs)
        return text

    @classmethod
    def customize_description_args(cls, description_kwargs: dict, record: SessionRecord):  # noqa: ARG003
        """Customize this method to fit your description needs: add or alter attributes used in the template"""
        return description_kwargs

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
                    publish_date=video.status.publish_at,
                )
                youtube_video.rename(ytclient.video_records_path_updated / youtube_video.name)
                logger.info(f"Updated video: {pretalx_id}, {video.id}")
            except Exception as e:
                logger.error(f"Failed to update video {video.id}: {e}")
                continue

    def update_video_metadata(self, states: str | list[str], func: callable):
        """update record files with video metadata created already.
        :param states: str or list of str, values: 'video_records', 'video_records_updated'
        :param func: custom method to apply to the record
        """
        if isinstance(states, str):
            states = [states]
        for state in states:
            if state not in ("video_records", "video_records_updated"):
                continue
            for record in (self.video_records_path.parent / state).glob("*.json"):
                func(record)

    @classmethod
    def update_publish_date(cls, record: Path, publish_date: datetime):
        """Sets the publishing date at YouTube for videos"""
        record_data = load_json(record)
        record_data["status"]["publish_at"] = publish_date.isoformat()
        print("Updated publish date to", publish_date.isoformat())
        save_json(record_data, record)

    def update_publish_dates(
        self,
        states: str | list[str] | tuple[str] = ("video_records", "video_records_updated"),
        start: datetime | None = None,
        delta: timedelta | None = None,
        end: datetime | None = None,
        steps: int | None = None,
    ):
        """ " Update or add periodical publishing dates for videos randomly."""
        if isinstance(states, str):
            states = [states]
        if start is None:
            start = datetime.now(UTC)
        gen = self.publish_dates_generator(start, delta=delta, end=end, steps=steps)
        records = []
        for state in states:
            if state not in ("video_records", "video_records_updated"):
                continue
            records.extend(list((self.video_records_path.parent / state).glob("*.json")))
        random.shuffle(records)
        for record, publish_at in zip(records, gen, strict=False):
            self.update_publish_date(record, publish_at)
            # move to queue for YouTube metadata updates
            record.rename(self.video_records_path / record.name)
            logger.info(
                f"Updated publish date for {record.name} in the video file.Please do not forget to publish the update."
            )

    @staticmethod
    def publish_dates_generator(
        start: datetime,
        delta: timedelta | None = None,
        end: datetime | None = None,
        steps: int | None = None,
    ) -> Generator[datetime]:
        """Create a list of publishing dates for the videos"""
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
