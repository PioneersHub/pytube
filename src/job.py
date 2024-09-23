"""
Run jobs:
- Release on YouTube
- Publish LinkedIn post
- Email speaker to inform about the release
"""
import datetime
import json
import random
from collections import defaultdict
from pathlib import Path

from omegaconf import OmegaConf

from linkedin_company_post import LinkedIn
from records import SessionRecord
from src import logger, conf
from youtube_videos import YT, PrepareVideoMetadata


class Publisher:
    def __init__(self, destination_channel: str):
        logger.info(f"Updating metadata for channel {destination_channel}")
        self.destination_channel = destination_channel
        self.yt_client = YT()
        local_credentials = OmegaConf.load(Path(__file__).parents[1] / "_secret" / "linked_in.yml")
        self.linkedin = LinkedIn(local_credentials)
        self.video_meta = PrepareVideoMetadata(template_file="", at="")  # required for mappings
        self.pretalx_youtube_id_map = self.video_meta.pretalx_youtube_id_map
        self.pretalx_youtube_channel_map = self.video_meta.pretalx_youtube_channel_map

        self.linked_in_to_post = conf.dirs.work_dir / 'linked_in_to_post'
        self.linked_in_to_post.mkdir(exist_ok=True, parents=True)

        self.linked_in_posted = conf.dirs.work_dir / 'linked_in_posted'
        self.linked_in_posted.mkdir(exist_ok=True, parents=True)

        self.x_to_post = conf.dirs.work_dir / 'x_to_post'
        self.x_to_post.mkdir(exist_ok=True, parents=True)

        self.x_posted = conf.dirs.work_dir / 'x_posted'
        self.x_posted.mkdir(exist_ok=True, parents=True)

        self.speaker_to_email = conf.dirs.work_dir / 'speaker_to_email'
        self.speaker_to_email.mkdir(exist_ok=True, parents=True)

        self.speaker_emailed = conf.dirs.work_dir / 'speaker_emailed'
        self.speaker_emailed.mkdir(exist_ok=True, parents=True)

    def release_on_youtube_now(self, video_id: str):
        # Prepare the request body
        body = {
            "id": video_id,
            "snippet": {},
            "status": {}
        }

        publish_date = datetime.datetime.now()
        body["status"]["publishAt"] = publish_date.isoformat()

        # Update video metadata
        request = self.yt_client.youtube.videos().update(
            part="snippet,status",
            body=body
        )
        response = request.execute()
        data = response.json()
        if response.status_code != 200:
            logger.error(f"Failed to update video metadata: {data}")
            return response
        logger.info(f"Video successfully published: {video_id}")
        return response

    @property
    def all_unpublished_videos_by_channel(self):
        """ Get all unpublished videos by channel."""
        all_unpublished_videos = self.yt_client.video_records_path_updated.glob("*.json")
        input_dict = {video.stem: self.pretalx_youtube_channel_map.get(video.stem) for video in all_unpublished_videos}
        output_dict = defaultdict(list)
        for key, value in input_dict.items():
            output_dict[value].append(key)
        return dict(output_dict)

    def release_random_video(self):
        """ Select a random video to be released on YouTube by channel."""
        population = self.all_unpublished_videos_by_channel.get(self.destination_channel, [])
        if not population:
            logger.error(f"No videos found for channel {self.destination_channel}")
            return
        pretalx_id = random.choice(population)
        video_id = self.pretalx_youtube_id_map.get(pretalx_id)

        res = self.release_on_youtube_now(video_id)

        # update record with full YouTube response
        logger.info(f"Video {pretalx_id} released on YouTube.")
        record_path = self.video_meta.records_path / f"{pretalx_id}.json"
        record = SessionRecord.model_validate_json(record_path.read_text())
        record["youtube_online_metadata"] = res
        record_path.write_text(record.model_dump_json(indent=4))
        logger.info(f"Updated record for video {pretalx_id}.")

        # LinkedIn - save post to file to be posted later
        post = f"""⭐️ New video release 📺\n{record.sm_teaser_text}\n\n📺 Watch the video on YouTube: https://youtu.be/{record.youtube_video_id}\n{record.sm_short_text}"""
        (self.linked_in_to_post / f"{pretalx_id}.json").write_text(
            {
                "pretalx_id": pretalx_id,
                "post": post,
                "sm_teaser_text": record.sm_teaser_text,
                "sm_short_text": record.sm_short_text,
                "youtube_video_id": record.youtube_video_id,
            }
        )

    def post_on_linked_id(self):
        """ Post ONE LinkedIn update."""
        to_post = self.linked_in_to_post.glob("*.json")
        for post in to_post:
            data = json.load(post.open())
            try:
                res = self.linkedin.post(data["post"])
                if res is None:
                    return
                data["linked_in_response"] = res
                post.rename(self.linked_in_posted / post.name)
                return
            except Exception as e:
                data["linked_in_response"] = str(e)

    def post_on_x(self, record: SessionRecord):
        """ Post on X."""
        pass

    def email_speaker(self, record: SessionRecord):
        """ Email the speaker."""
        pass


if __name__ == "__main__":
    for channel in (
            'pycon',
            # 'pydata'
    ):
        publisher = Publisher(destination_channel=channel)
        publisher.release_random_video()
        publisher.post_on_linked_id()
        logger.info("Job completed successfully.")
