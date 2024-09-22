import datetime
import json

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

from jinja2 import Environment, PackageLoader, select_autoescape

from records import SessionRecord
from src import conf, logger
from src.models.video_metadata import YouTubeMetadata
from src.usr import slugify

from youtube_pydantic_models import YoutubeVideoResource, VideoSnippet, VideoStatus, BaseRecordingDetails


class YT:
    def __init__(self):
        # Set up the necessary scopes and API service
        self.scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
        self.youtube = self.get_authenticated_service()

    def get_authenticated_service(self):
        """ Authentication to access the channel information
        - Users need to authenticate via a web interface
        - User needs to have rights to access channel
        """
        api_service_name = "youtube"
        api_version = "v3"
        client_secrets_file = conf.youtube.client_secrets_file

        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(client_secrets_file, self.scopes)
        credentials = flow.run_local_server(port=0)

        return googleapiclient.discovery.build(api_service_name, api_version, credentials=credentials)

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
        :param max_pages: Some channels have a lot of content - we ar only interested in the recent uplaods
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

    def update_video_metadata(self, video_id,
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
            publish_date = datetime.datetime.strptime(publish_date, '%Y-%m-%dT%H:%M:%S%z')
            body["status"]["publishAt"] = publish_date.isoformat()

        # Update video metadata
        request = self.youtube.videos().update(
            part="snippet,status",
            body=body
        )
        response = request.execute()

        print(f"Updated video metadata for video ID: {video_id}")
        return response


class PrepareVideoMetadata:
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
        self.template = None

        self.load_yt_metadata()
        self.load_template()

        self.records_path = conf.dirs.work_dir / 'records'
        self.video_records_path = conf.dirs.video_dir / 'youtube/video_records'
        self.video_records_path.mkdir(parents=True, exist_ok=True)
        # default values

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

    @classmethod
    def map_pretalx_id_youtube_id(cls):
        """ The pretalx id is in the video title after upload.
        We need to create a map of pretalx id to the YouTube video id
        before updating the data on YouTube. """
        pydata = json.load((conf.dirs.video_dir / "youtube_pydata_playlist.json").open())
        pycon = json.load((conf.dirs.video_dir / "youtube_pycon_playlist.json").open())
        pretalx_yt_map = {}
        for video in pydata + pycon:
            pretalx_id = video["snippet"]["title"].strip()[:6]
            youtube_id = video["snippet"]["resourceId"]["videoId"]
            pretalx_yt_map[pretalx_id] = youtube_id
        json.dump(pretalx_yt_map, (conf.dirs.video_dir / "pretalx_yt_map.json").open("w"), indent=4)

    def load_yt_metadata(self):
        pydata = json.load((conf.dirs.video_dir / "youtube_pydata_playlist.json").open())
        pycon = json.load((conf.dirs.video_dir / "youtube_pycon_playlist.json").open())
        for video in pydata + pycon:
            ytv = YouTubeMetadata(**video["snippet"])
            self.yt_metadata.append(ytv)

    def load_template(self):
        env = Environment(
            loader=PackageLoader("src"),
            autoescape=select_autoescape()
        )
        self.template = env.get_template(self.template_file)

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
            record.recorded_date = datetime.datetime.strptime(recorded_date.strftime("%d.%m.%Y"), "%d.%m.%Y")
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
        if len(youtube_description) > 5000:
            logger.info(f'YouTube description of {record.pretalx_id} is too long: {len(youtube_description)}>5000')
            render_description(description=record.sm_short_text)
        if len(youtube_description) > 5000:
            logger.error(f'YouTube description of {record.pretalx_id} is too long: {len(youtube_description)}>5000')
            render_description(description="")

        if record.youtube_description != youtube_description:
            logger.info(f'Updating YouTube description of {record.pretalx_id}')
            record.youtube_description = youtube_description
            update_record = True

        if update_record:
            (self.records_path / f'{record.pretalx_id}.json').write_text(record.model_dump_json(indent=4))
            logger.info(f'Saved updated record of {record.pretalx_id}')

        # YouTube static config
        category_id = "28"  # Science & Technology
        default_language = 'en'  # 2-letter ISO-639-1-Code
        privacy_status = 'unlisted'
        video_license = 'youtube'
        video_embeddable = True
        recorded_iso: str = record.recorded_date.strftime("%d.%m.%Y")

        youtube_video_ressource = YoutubeVideoResource(
            id=youtube_video_id,
            snippet=VideoSnippet(
                title=youtube_title,
                description=youtube_description,
                category_id=category_id,
                default_audio_language=default_language,
                default_language=default_language,
            ),
            status=VideoStatus(
                privacy_status=privacy_status,
                license=video_license,
                embeddable=video_embeddable,
            ),
            recording_details=BaseRecordingDetails(
                recording_date=recorded_iso
            )
        )

        (self.video_records_path / f'{record.pretalx_id}.json').write_text(
            youtube_video_ressource.model_dump_json(indent=4))
        print("=" * 50)
        a = 44

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
            res = ytclient.update_video_metadata(
                video_id=video.id,
                title=video.snippet.title,
                description=video.snippet.description,
                category_id=video.snippet.category_id,
                privacy_status=video.status.privacy_status,
            )
            a = 44


if __name__ == "__main__":
    # After videos are uploaded to YouTube, we need to update the metadata
    # To update the metadata, we need the YouTube video id
    # yt_client = YT()
    # channel_id = yt_client.get_channel_id()

    # unpublished videos data can be retrieved via an unpublished playlist only

    # videos = yt_client.list_all_videos_in_playlist(conf.youtube.channels.pycon.playlist_id)
    # json.dump(videos, (conf.dirs.video_dir/f"youtube_pycon_playlist.json").open("w"), indent=4)

    # videos = yt_client.list_all_videos_in_playlist(conf.youtube.channels.pydata.playlist_id)
    # json.dump(videos, (conf.dirs.video_dir / f"youtube_pydata_playlist.json").open("w"), indent=4)

    # Match the pretalx id with the YouTube video id
    # map_pretalx_id_youtube_id()

    # Generate the metadata for the update on YouTube

    meta = PrepareVideoMetadata(template_file="youtube_2024.txt", at="PyCon DE & PyData Berlin 2024")
    # meta.make_all_video_metadata()
    meta.send_all_video_metadata(destination_channel='pydata')
    # meta.send_all_video_metadata(destination_channel='pycon')

    a = 44
    # video_id = "YOUR_VIDEO_ID"
    # title = "New Title"
    # description = "New Description"
    # tags = ["tag1", "tag2"]
    # category_id = "22"  # Example category ID for 'People & Blogs'
    # privacy_status = "private"
    # publish_date = "2024-07-01T15:00:00+00:00"  # Example publish date in ISO 8601 format
    #
    # update_video_metadata(video_id, title, description, tags, category_id, privacy_status, publish_date)
