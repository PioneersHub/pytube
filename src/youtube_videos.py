import datetime
import json

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

from src import conf


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


if __name__ == "__main__":
    yt_client = YT()
    # channel_id = yt_client.get_channel_id()

    # videos = yt_client.list_all_videos_in_playlist(conf.youtube.channels.pycon.playlist_id)
    # json.dump(videos, (conf.dirs.video_dir/f"youtube_pycon_playlist.json").open("w"), indent=4)

    videos = yt_client.list_all_videos_in_playlist(conf.youtube.channels.pydata.playlist_id)
    json.dump(videos, (conf.dirs.video_dir / f"youtube_pydata_playlist.json").open("w"), indent=4)

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
