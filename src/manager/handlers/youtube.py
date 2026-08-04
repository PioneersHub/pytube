from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from jinja2 import Environment, FileSystemLoader, select_autoescape

from manager import conf, logger
from manager.config import get_event_dir
from manager.handlers.records import Records, load_session_record
from manager.models.sessions import SessionRecord
from manager.models.video import (
    BaseRecordingDetails,
    VideoSnippet,
    VideoStatus,
    YoutubeVideoResource,
    trim_tags,
)
from manager.utils.common import SafeConfig, ensure_directory, load_json, save_json


def _http_error_reason(exc: googleapiclient.errors.HttpError) -> str:
    """The machine-readable reason of a YouTube API error, e.g. 'quotaExceeded'.

    Mirrors src/pipeline/youtube/send_updates.py: the reason lives in
    error_details, falling back to the string form when the API sends none.
    """
    details = getattr(exc, "error_details", None) or []
    if details and isinstance(details[0], dict):
        return details[0].get("reason", "")
    return ""


class YT:
    def __init__(self, youtube_offline: bool = False, channel: str | None = None):
        """
        :param youtube_offline: authenticate from the cached token instead of a browser flow
        :param channel: channel name from `youtube.channels`. Channels usually belong to
            different Google accounts and therefore need their own OAuth token; passing the
            channel selects `youtube.channels.<name>.token_path`. One YT instance serves
            exactly one channel — authorizing a second channel through the same instance
            would overwrite the first channel's token.
        """
        # Set up the necessary scopes and API service
        self.scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
        self._youtube = None

        self.youtube_offline = youtube_offline
        self.channel = channel

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

    def _token_path_str(self, safe_conf) -> str:
        """Token file for this instance: per channel if configured, else the global one.

        Channels typically live in different Google accounts, so a single shared token
        file means authorizing one channel destroys the other channel's credentials.
        """
        if self.channel:
            per_channel = safe_conf.get(f"youtube.channels.{self.channel}.token_path")
            if per_channel:
                return per_channel
        return safe_conf.get("youtube.token_path", "token.json")

    def get_authenticated_offline_service(self):
        """Works for limited use cases only due to general restrictions by YouTube,
        >>NOT suitable for updating video metadata<<"""
        creds = None

        # The token.json stores the user's access and refresh tokens, and is created automatically
        # when the authorization flow completes for the first time.
        safe_conf = SafeConfig(conf)
        root_dir = Path(safe_conf.get("dirs.root", "."))
        client_secrets_file = safe_conf.get("youtube.client_secrets_file")
        if not client_secrets_file:
            raise ValueError("YouTube client secrets file not configured")
        # Anchor to the repo root like get_authenticated_service does, so a relative
        # path (.secrets/client_secrets.json) resolves regardless of the cwd. Only
        # reached on the browser fallback below, but a wrong cwd there surfaced as a
        # misleading "playlist may be private" error.
        client_secrets_file = str(root_dir / client_secrets_file)
        token_path = root_dir / self._token_path_str(safe_conf)
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)

        # If no valid credentials are available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as exc:
                    # Refresh tokens expire (inactivity, password change, revoked access).
                    # Without this fallback the command fails permanently and reports a
                    # misleading "playlist may be private/deleted" error instead of
                    # simply asking for authorization again.
                    logger.warning(f"Cached YouTube token could not be refreshed ({exc}); re-authorizing in browser")
                    creds = None

            if not creds or not creds.valid:
                # Create a flow object, set the client secrets, and ask for offline access
                flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, self.scopes)
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            token_path.parent.mkdir(parents=True, exist_ok=True)
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

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> dict:
        """Add one video to a playlist (playlistItems.insert, 50 quota units).

        The playlist and the video may belong to different channels — any public
        video can be added to a playlist the authenticated account owns.
        """
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        }
        response = self.youtube.playlistItems().insert(part="snippet", body=body).execute()
        logger.info(f"Added {video_id} to playlist {playlist_id}")
        return response

    def send_video_update(self, resource: YoutubeVideoResource) -> dict:
        """Send one video's metadata to YouTube.

        Posts exactly what `resource.to_update_body()` returns — the same body
        `youtube update --dry-run` prints — so the preview and the real request
        cannot diverge. That matters because YouTube deletes any property it does
        not receive within a part it is updating; a partial body silently wipes
        tags and resets the status fields.

        The `part` is derived from the body's top-level keys, so a part is only
        ever updated when the body carries it (e.g. recordingDetails is included
        only when a recording date is present).
        """
        body = resource.to_update_body()
        part = ",".join(k for k in ("snippet", "status", "recordingDetails") if k in body)
        request = self.youtube.videos().update(part=part, body=body)
        response = request.execute()
        logger.info(f"Updated video metadata for {resource.id}")
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

    def check_video_status_by_youtube_ids(self, video_id: str | list[str], part: str = "status") -> dict:
        """Read back video status/snippet from YouTube, in chunks of 50.

        `videos.list` accepts at most 50 ids per call, so a single joined string
        of 65 ids fails. Chunking keeps the cost at 1 unit per 50 videos and
        merges the results into one response-shaped dict.
        """
        if isinstance(video_id, str):
            video_id = [video_id]
        items = []
        for start in range(0, len(video_id), 50):
            chunk = video_id[start : start + 50]
            response = self.youtube.videos().list(part=part, id=",".join(chunk)).execute()
            items.extend(response.get("items", []))
        return {"items": items}

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

    def __init__(self, template_file: str, at, dry_run: bool = False):
        """
        :param template_file: Jinja2 template for the video description
        :param at: event name appended to the video title
        :param dry_run: build metadata without writing anything to disk
        """
        self.template_file = template_file
        self.at = at
        self.dry_run = dry_run
        self._pretalx_youtube_channel_map = {}
        self._pretalx_youtube_id_map = {}
        self._template = None

        # Use event-specific directory structure
        self.event_dir = get_event_dir(conf)
        self.records_path = self.event_dir / "records"
        self.video_records_path = self.event_dir / "videos" / "youtube" / "video_records"
        ensure_directory(self.video_records_path)

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

    def load_template(self):
        """Load the description template, preferring the event's own copy.

        Descriptions are event-specific (year, links, sponsor wording), so each
        project may ship its own template in projects/<slug>/. The packaged
        templates are the fallback for events that don't need a custom one.

        `PackageLoader("src")` used to be passed here, which resolves to
        `src/templates/` — a directory that does not exist. Any call raised
        before rendering a single description.
        """
        search_path = [self.event_dir, Path(__file__).parent.parent / "templates"]
        env = Environment(loader=FileSystemLoader(search_path), autoescape=select_autoescape())
        self._template = env.get_template(self.template_file)

    def make_all_video_metadata(
        self, channel: str | None = None, only: set[str] | None = None
    ) -> list[YoutubeVideoResource]:
        """Build YouTube metadata for every talk that has an uploaded video.

        Driven by pretalx_yt_map.json — the only artifact that means "uploaded to
        YouTube AND resolved to a Pretalx code", which is exactly the set of
        videos `videos.update` can act on. It used to read manifest.json, which
        is the Vimeo *download* manifest (see scripts/vimeo_download.py) and does
        not exist here; the command failed before touching a single video.

        Sorted so that partial runs are deterministic and repeatable.

        :param channel: only build videos assigned to this channel
        :param only: if given, restrict to these Pretalx codes (targeted re-runs)
        :return: the resources that were built, in order
        """
        built = []
        for pretalx_id in sorted(self.pretalx_youtube_id_map):
            if channel and self.pretalx_youtube_channel_map.get(pretalx_id) != channel:
                continue
            if only is not None and pretalx_id not in only:
                continue
            resource = self.make_video_metadata(pretalx_id)
            if resource is not None:
                built.append(resource)
        return built

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

    def make_video_metadata(self, pretalx_id: str) -> YoutubeVideoResource | None:
        """Collect all metadata for one talk and store it as a video record.

        :param pretalx_id: the talk's Pretalx code
        :return: the built resource, or None if the talk has to be skipped
        """
        youtube_channel = self.pretalx_youtube_channel_map.get(pretalx_id)
        if not youtube_channel:
            logger.warning(f"No channel assigned to {pretalx_id}, skipping")
            return None
        youtube_video_id = self.pretalx_youtube_id_map.get(pretalx_id)
        if not youtube_video_id:
            logger.warning(f"No YouTube video ID found for {pretalx_id}, skipping")
            return None

        record = load_session_record(self.records_path / f"{pretalx_id}.json")
        update_record = False

        youtube_title = self.best_youtube_title(record.title, self.at)
        # `slots` is when the talk was given — Pretalx models it as a list and has
        # no `slot` attribute, so reading `.slot.start` raised on every video.
        slots = record.pretalx_session.session.slots
        if not slots:
            logger.warning(f"No schedule slot for {pretalx_id}, skipping")
            return None
        recorded_date = slots[0].start

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

        if update_record and not self.dry_run:
            (self.records_path / f"{record.pretalx_id}.json").write_text(record.model_dump_json(indent=4))
            logger.info(f"Saved updated record of {record.pretalx_id}")

        # Store the recording date as an ISO date ("2026-04-14") so to_update_body
        # can widen it to the RFC 3339 form YouTube's recordingDate requires. The
        # German-format date shown inside the description is rendered separately.
        recorded_iso: str = record.recorded_date.isoformat()
        target, status = self.video_record_target(record.pretalx_id, youtube_channel)

        youtube_video_ressource = YoutubeVideoResource(
            id=youtube_video_id,
            snippet=VideoSnippet(
                title=youtube_title,
                description=youtube_description,
                tags=self.channel_tags(youtube_channel),
                # Only override what config actually sets — passing None would send
                # `categoryId: null`, which YouTube rejects.
                **self.configured(("category_id", "default_language", "default_audio_language")),
            ),
            recording_details=BaseRecordingDetails(recording_date=recorded_iso),
            status=status,
        )

        if not self.dry_run:
            target.write_text(youtube_video_ressource.model_dump_json(indent=4))
        return youtube_video_ressource

    def video_record_target(self, pretalx_id: str, channel: str) -> tuple[Path, VideoStatus]:
        """Where this talk's video record lives, and the status it should carry.

        A record moves between video_records/, _updated/ and _published/ as it
        progresses. Rebuilding metadata must update it where it currently is —
        writing unconditionally to video_records/ leaves a second copy behind,
        and `update_publish_dates` globs both directories and would then hand the
        same talk two different publish dates.

        Only `publish_at` is carried over from an existing record; everything
        else comes from config, so a config change still propagates. Without
        this, `youtube update` silently discarded the schedule set by
        `youtube schedule`.
        """
        status = VideoStatus(
            **self.configured(
                (
                    "privacy_status",
                    "license",
                    "embeddable",
                    "public_stats_viewable",
                    "self_declared_made_for_kids",
                )
            )
        )
        target = self.video_records_path / f"{pretalx_id}.json"
        youtube_dir = self.video_records_path.parent
        for state in ("video_records", "video_records_updated", "video_published"):
            candidate = youtube_dir / state / f"{pretalx_id}.json"
            if candidate.exists():
                existing = YoutubeVideoResource.model_validate_json(candidate.read_text()).status
                if existing.publish_at:
                    status.publish_at = existing.publish_at
                    status.privacy_status = "private"
                target = candidate
                break
        return target, status

    @staticmethod
    def video_defaults() -> dict:
        """Single source for the fields written on every videos.update call."""
        return dict(SafeConfig(conf).get("youtube.video_defaults", {}) or {})

    @classmethod
    def configured(cls, keys: tuple[str, ...]) -> dict:
        """Those of `keys` that config actually sets.

        Keys the config omits are left out entirely so the model's own default
        applies. Passing them through as None would override a valid default with
        an empty value and produce a request body YouTube refuses.
        """
        defaults = cls.video_defaults()
        return {key: defaults[key] for key in keys if defaults.get(key) is not None}

    @classmethod
    def channel_tags(cls, channel: str | None) -> list[str]:
        """Tags for a channel: the shared set plus that channel's own."""
        defaults = cls.video_defaults()
        tags = list(defaults.get("tags") or [])
        tags += list((defaults.get("channel_tags") or {}).get(channel) or [])
        kept, dropped = trim_tags(tags)
        if dropped:
            logger.warning(f"Dropped {len(dropped)} tag(s) over YouTube's 500-character limit: {dropped}")
        return kept

    def render_description(self, description: str, record: SessionRecord):
        """Provides commonly used values for rendering the description.

        Exposes the video's channel so templates can branch per channel with
        ``{% if pydata %}…{% endif %}`` / ``{% if pyconde %}…{% endif %}``.
        `record.youtube_channel` is set by make_video_metadata before this runs.
        """
        safe_conf = SafeConfig(conf)
        channel = record.youtube_channel
        description_kwargs = {
            "date": record.recorded_date.strftime("%d.%m.%Y"),
            "session_link": f"{safe_conf.get('event.program_url', '')}{record.pretalx_id}/",
            "teaser_text": record.sm_teaser_text,
            "speakers": ", ".join([f"{s.name}" for s in record.speakers]),
            "description": description,
            "channel": channel,
            "pydata": channel == "pydata",
            "pyconde": channel == "pyconde",
        }
        description_kwargs = self.customize_description_args(description_kwargs, record)
        text = self.template.render(**description_kwargs)
        return text

    @classmethod
    def customize_description_args(cls, description_kwargs: dict, record: SessionRecord):  # noqa: ARG003
        """Customize this method to fit your description needs: add or alter attributes used in the template"""
        return description_kwargs

    _QUOTA_REASONS = ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded")

    def videos_to_send(self, destination_channel: str, only: set[str] | None = None) -> list[Path]:
        """Queued video records for one channel, in deterministic order.

        Sorted so that a `--limit`ed run always picks the same videos and a
        resumed run continues predictably. Only reads video_records/; a record is
        moved out on success, so re-running sends what is left.

        :param only: if given, restrict to these Pretalx codes (targeted re-runs)
        """
        queued = []
        for path in sorted(self.video_records_path.glob("*.json")):
            video = YoutubeVideoResource.model_validate_json(path.read_text())
            pretalx_id = self.youtube_id_pretalx_map.get(video.id)
            if not pretalx_id or self.pretalx_youtube_channel_map.get(pretalx_id) != destination_channel:
                continue
            if only is not None and pretalx_id not in only:
                continue
            queued.append(path)
        return queued

    def send_all_video_metadata(
        self, destination_channel: str, limit: int | None = None, only: set[str] | None = None
    ) -> dict:
        """Send queued video metadata for one channel to YouTube.

        Returns a result summary instead of swallowing failures, so the caller
        can report honestly and set a non-zero exit code. On a quota error it
        stops rather than burning the remaining budget on doomed calls.
        """
        if self.dry_run:
            # Constructing YT here would run the interactive OAuth flow and pop a
            # browser window — the opposite of what a dry run is for.
            raise RuntimeError("send_all_video_metadata must not be called on a dry run")

        result = {
            "channel": destination_channel,
            "total": 0,
            "updated": 0,
            "failed": 0,
            "quota_exhausted": False,
            "sent_ids": [],
            "errors": [],
        }
        queued = self.videos_to_send(destination_channel, only=only)
        if limit is not None:
            queued = queued[:limit]
        result["total"] = len(queued)
        if not queued:
            return result

        logger.info(f"Updating metadata for {len(queued)} videos on channel {destination_channel}")
        ytclient = YT(youtube_offline=True, channel=destination_channel)
        for path in queued:
            video = YoutubeVideoResource.model_validate_json(path.read_text())
            try:
                ytclient.send_video_update(video)
            except googleapiclient.errors.HttpError as exc:
                reason = _http_error_reason(exc)
                if reason in self._QUOTA_REASONS:
                    result["quota_exhausted"] = True
                    result["errors"].append((video.id, f"quota: {reason}"))
                    logger.error(f"Quota exhausted ({reason}); stopping before the remaining videos")
                    break
                result["failed"] += 1
                result["errors"].append((video.id, str(exc)))
                logger.error(f"Failed to update video {video.id}: {exc}")
                continue
            except Exception as exc:
                result["failed"] += 1
                result["errors"].append((video.id, str(exc)))
                logger.error(f"Failed to update video {video.id}: {exc}")
                continue
            # Only move on success, so a failed video stays queued for a retry.
            path.rename(ytclient.video_records_path_updated / path.name)
            result["updated"] += 1
            result["sent_ids"].append(video.id)
        return result

    def fill_playlist(self, channel: str, video_ids: list[str]) -> dict:
        """Ensure the channel's playlist contains all of `video_ids`.

        Reads the current membership and inserts only the missing videos, so it
        creates no duplicates and is safe to re-run — a run stopped by a quota
        error finishes on the next run (e.g. after the daily reset). Uses the
        owning channel's token; the videos may belong to the other channel.
        """
        if self.dry_run:
            raise RuntimeError("fill_playlist must not be called on a dry run")

        playlist_id = SafeConfig(conf).get(f"youtube.channels.{channel}.playlist_id")
        result = {
            "channel": channel,
            "target": playlist_id,
            "present": 0,
            "added": 0,
            "failed": 0,
            "quota_exhausted": False,
            "errors": [],
        }
        if not playlist_id:
            result["errors"].append(("-", f"no playlist_id configured for channel {channel}"))
            result["failed"] = 1
            return result

        ytclient = YT(youtube_offline=True, channel=channel)
        present = {item["contentDetails"]["videoId"] for item in ytclient.list_all_videos_in_playlist(playlist_id)}
        result["present"] = len(present)
        missing = [vid for vid in video_ids if vid not in present]
        logger.info(f"Playlist {channel}: {len(present)} present, {len(missing)} to add")

        for video_id in missing:
            try:
                ytclient.add_video_to_playlist(playlist_id, video_id)
            except googleapiclient.errors.HttpError as exc:
                reason = _http_error_reason(exc)
                if reason in self._QUOTA_REASONS:
                    result["quota_exhausted"] = True
                    result["errors"].append((video_id, f"quota: {reason}"))
                    logger.error(f"Quota exhausted ({reason}); stopping — re-run after the reset to finish")
                    break
                result["failed"] += 1
                result["errors"].append((video_id, str(exc)))
                logger.error(f"Failed to add {video_id} to {channel} playlist: {exc}")
                continue
            except Exception as exc:
                result["failed"] += 1
                result["errors"].append((video_id, str(exc)))
                logger.error(f"Failed to add {video_id} to {channel} playlist: {exc}")
                continue
            result["added"] += 1
        return result

    @classmethod
    def update_publish_date(cls, record: Path, publish_date: datetime):
        """Sets the publishing date at YouTube for videos"""
        record_data = load_json(record)
        record_data["status"]["publish_at"] = publish_date.isoformat()
        print("Updated publish date to", publish_date.isoformat())
        save_json(record_data, record)

    def plan_publish_dates(
        self,
        states: str | list[str] | tuple[str] = ("video_records", "video_records_updated"),
        start: datetime | None = None,
        delta: timedelta | None = None,
        end: datetime | None = None,
        steps: int | None = None,
    ) -> list[tuple[Path, datetime]]:
        """Assign a publish datetime to each queued record, deterministically.

        Records are ordered alphabetically by Pretalx code (the filename stem) so
        that `--preview` matches the applied run and re-runs are reproducible; the
        previous `random.shuffle` made both impossible. With `delta=timedelta(0)`
        every record gets the same datetime (one coordinated release).
        """
        if isinstance(states, str):
            states = [states]
        if start is None:
            start = datetime.now(UTC)
        records = []
        for state in states:
            if state not in ("video_records", "video_records_updated"):
                continue
            records.extend((self.video_records_path.parent / state).glob("*.json"))
        records = sorted(records, key=lambda p: p.stem)
        gen = self.publish_dates_generator(start, delta=delta, end=end, steps=steps)
        return list(zip(records, gen, strict=False))

    def update_publish_dates(
        self,
        states: str | list[str] | tuple[str] = ("video_records", "video_records_updated"),
        start: datetime | None = None,
        delta: timedelta | None = None,
        end: datetime | None = None,
        steps: int | None = None,
    ):
        """Write the planned publish date to each record and re-queue it to send."""
        for record, publish_at in self.plan_publish_dates(states, start, delta=delta, end=end, steps=steps):
            self.update_publish_date(record, publish_at)
            # move back to the send queue so `youtube update` transmits the date
            record.rename(self.video_records_path / record.name)
            logger.info(f"Set publish date {publish_at.isoformat()} for {record.stem}")

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
