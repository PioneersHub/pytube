import datetime
import json

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

from pytanis.pretalx.types import Talk, Speaker, SubmissionSpeaker
from jinja2 import Environment, PackageLoader, select_autoescape

from src import conf
from src.models.video_metadata import YouTubeMetadata
from src.usr import slugify


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

    # Function to update video metadata
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


class ProcessVideoMetadata:
    def __init__(self, template_file: str):
        self.pretalx_ytchannel_map = {}
        self.yt_metadata = []
        self.template_file = template_file

        self.load_pretalx_ytchannel_map()
        self.load_yt_metadata()
        self.load_template()

    def load_pretalx_ytchannel_map(self):
        """ pretalx ID - Youtube channel """
        self.pretalx_ytchannel_map = json.load((conf.dirs.video_dir / "tracks_map.json").open())

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

    def merge_all_video_metadata(self):
        manifest = json.load((conf.dirs.work_dir / "manifest.json").open())
        for video in manifest:
            self.merge_video_metadata(video)

    def merge_video_metadata(self, video):
        """ Collect and merge video metadata from pretalx submissions & speakers and YouTube """
        pretalx_talk = self.load_pretalx_talk(video["pretalx_id"])
        pretalx_speakers = [self.load_pretalx_speaker(x.code) for x in pretalx_talk.speakers]
        youtube_channel = self.pretalx_ytchannel_map[video["pretalx_id"]]
        date = pretalx_talk.slot.start.strftime("%d.%m.%Y")
        speakers_bio = [(x.name, x.biography.replace("\n", " ").replace("\r", " ").replace("  ", " ")) if x.biography else "" for x in pretalx_talk.speakers]
        description = self.template.render(
            date= date,
            session_link=f"https://2024.pycon.de/program/{pretalx_talk.code}",
            speakers=speakers_bio,
            description=pretalx_talk.abstract,
            tag=slugify(pretalx_talk.track.en),
            pydata=self.pretalx_ytchannel_map[video["pretalx_id"]] == "pydata",
        )
        category_id = 28  # categoryId=28 - Wissenschaft
        default_language = 'en'  # 2-letter ISO-639-1-Code
        privacy_status = 'unlisted'
        video_license = 'youtube'
        video_embeddable = True
        recorded_iso = date

        # <, > not allowed in YT titles, description
        title = pretalx_talk.title.replace('>', '').replace('<', '')
        description = description.replace('>', '').replace('<', '')
        print("="*50)
        print(title)
        print()
        print(description)
        a = 44

    def load_pretalx_talk(self, pretalx_id: str):
        talk = json.load((conf.dirs.work_dir / f"pretalx/{pretalx_id}.json").open())
        return Talk(**talk)

    def load_pretalx_speaker(self, pretalx_id: str):
        speaker = json.load((conf.dirs.work_dir / f"pretalx_speakers/{pretalx_id}.json").open())
        return Speaker(**speaker)


def map_pretalx_id_youtube_id():
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

    meta = ProcessVideoMetadata(template_file="youtube_2024.txt")
    meta.merge_all_video_metadata()

    # videos = yt_client.list_all_videos(conf.youtube.channels.pycon.id)

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
