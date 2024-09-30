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
from collections.abc import Mapping
from pathlib import Path

from linkedin import LinkedInPost
from models.sessions import SessionRecord
from models.video import YoutubeVideoResource
from omegaconf import OmegaConf
from pytanis.helpdesk import Mail, MailClient, Recipient
from youtube import YT, PrepareVideoMetadata

from pytube import conf, logger


class Publisher:
    def __init__(self, destination_channel: str | None, youtube_offline: bool = False):
        logger.info(f"Updating metadata for channel {destination_channel}")
        self.destination_channel = destination_channel
        self.youtube_offline = youtube_offline
        self.youtube_client = YT(youtube_offline=self.youtube_offline)
        local_credentials = OmegaConf.load(Path(__file__).parents[1] / "_secret" / "linked_in.yml")
        self.linkedin = LinkedInPost(local_credentials)
        self.video_meta = PrepareVideoMetadata(template_file="", at="")  # required for mappings
        self.pretalx_youtube_id_map = self.video_meta.pretalx_youtube_id_map
        self.pretalx_youtube_channel_map = self.video_meta.pretalx_youtube_channel_map
        self.youtube_pretalx_id_map = {v: k for k, v in self.pretalx_youtube_id_map.items()}

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

    def release_on_youtube_now(self, video_id: str, title, description, category_id):
        # Prepare the request body
        body = {
            "id": video_id,
            "snippet": {},
            "status": {}
        }

        publish_date = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=5)
        body["status"]["publishAt"] = publish_date.isoformat()
        body["status"]["privacyStatus"] = 'private'
        body["snippet"]["title"] = title
        body["snippet"]["description"] = description
        body["snippet"]["categoryId"] = category_id

        # Update video metadata
        request = self.youtube_client.youtube.videos().update(
            part="status,snippet",
            body=body
        )
        try:
            response = request.execute()
            logger.info(f"Video successfully published: {video_id}")
            return response
        except Exception as e:
            logger.error(f"Failed to update video metadata: {str(e)}")
            return

    @property
    def unpublished_videos(self) -> Mapping:
        """ Unpublished video records paths."""
        return self.youtube_client.video_records_path_updated.glob("*.json")

    @property
    def all_unpublished_video_records(self) -> dict:
        """ All unpublished video records."""
        return [YoutubeVideoResource.model_validate_json(video.read_text()) for video in self.unpublished_videos]

    @property
    def all_unpublished_video_ids(self) -> list[str]:
        """ All unpublished video IDs."""
        return [video.stem for video in self.unpublished_videos]

    @property
    def all_unpublished_videos(self) -> dict[str, str]:
        """ All unpublished videos pretalx_id: youtube_id."""
        return {video.stem: self.pretalx_youtube_channel_map.get(video.stem) for video in self.unpublished_videos}

    @property
    def all_unpublished_videos_by_channel(self) -> dict[str, list[str]]:
        """ All unpublished videos by channel {channel: [video_id]}."""
        input_dict = self.all_unpublished_videos
        output_dict = defaultdict(list)
        for key, value in input_dict.items():
            output_dict[value].append(key)
        return dict(output_dict)

    def release_random_video(self):
        # DEPRECATED
        """ Select a random video to be released on YouTube by channel."""
        logger.warn("Videos have a release schedule already assigned in preprocessing.")
        population = self.all_unpublished_videos_by_channel.get(self.destination_channel, [])
        if not population:
            logger.error(f"No videos found for channel {self.destination_channel}")
            return
        pretalx_id = random.choice(population)
        video_id = self.pretalx_youtube_id_map.get(pretalx_id)
        record_path = self.video_meta.records_path / f"{pretalx_id}.json"
        record = SessionRecord.model_validate_json(record_path.read_text())

        res = self.release_on_youtube_now(video_id, record.youtube_title, record.youtube_description, "28")

        # update record with full YouTube response
        logger.info(f"Video {pretalx_id} released on YouTube.")

        record.youtube_online_metadata = res
        record_path.write_text(record.model_dump_json(indent=4))
        logger.info(f"Updated record for video {pretalx_id}.")
        (self.youtube_client.video_records_path_updated / f"{pretalx_id}.json").rename(
            self.youtube_client.video_records_path_published / f"{pretalx_id}.json")

        self.prepare_linkedin_post(record)
        self.prepare_email_speakers(record)

    def prepare_linkedin_post(self, record: SessionRecord):
        # LinkedIn - save post to file to be posted later
        post = f"""⭐️ New video release 📺: {record.title}\n{record.sm_teaser_text}\n\n📺 Watch the video on YouTube: https://www.youtube.com/watch?v={record.youtube_video_id}\n\n{record.sm_long_text}"""
        json.dump({"pretalx_id": record.pretalx_id,
                   "post": post,
                   "title": record.title,
                   "sm_teaser_text": record.sm_teaser_text,
                   "sm_short_text": record.sm_short_text,
                   "sm_long_text": record.sm_long_text,
                   "youtube_video_id": record.youtube_video_id,
                   }, (self.linked_in_to_post / f"{record.pretalx_id}.json").open("w"), indent=4)

    def prepare_email_speakers(self, record: SessionRecord):
        agent_id = "b312fd73-b227-4664-a079-6adb2d511e93"
        team_id = "3f68251e-17e9-436f-90c3-c03b06a72472"
        recipients = [Recipient(name=x.name, email=x.email) for x in record.speakers]
        text = f"""Hi {', '.join([x.name for x in recipients])},\nYour talk {record.title} is now online. 📺🎉\n\n📺 Watch the video on YouTube: https://youtu.be/{record.youtube_video_id}\n\n{record.sm_short_text}\n\nAll the best,\nPyCon.DE & PyData Berlin Team"""
        email = Mail(
            subject=f"Your talk {record.title} is now online.",
            text=text,
            team_id=team_id,
            recipients=recipients,
            agent_id=agent_id,
            status="closed",
        )
        (self.speaker_to_email / f"{record.pretalx_id}.json").write_text(email.model_dump_json(indent=4))
        logger.info(f"Email prepared for speakers of video {record.pretalx_id}.")

    def post_on_linked_id(self):
        """ Post ONE LinkedIn update."""
        to_post = self.linked_in_to_post.glob("*.json")
        for post in to_post:
            data = json.load(post.open())
            try:
                res = self.linkedin.post(data)
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

    def email_speakers(self):
        """ Email the speaker."""
        to_mail = self.speaker_to_email.glob("*.json")
        for email in to_mail:
            mail = Mail.model_validate_json(email.read_text())
            try:
                mail_client = MailClient()
                responses, errors = mail_client.send(mail, dry_run=False)
                if not errors:
                    email.rename(self.speaker_emailed / email.name)
            except Exception as e:
                logger.error(f"Failed to email speaker: {str(e)}")

    def media_share(self, data):
        """ Boilerplate code for media sharing on LinkedIn."""
        # media share
        image_res = self.linkedin.register_image()
        if image_res is None:
            return
        asset_urn = image_res["value"]["image"]
        print(asset_urn)
        upload_url = image_res["value"]["uploadUrl"]
        # upload image
        file_path = Path(conf.session_images) / f"{data['pretalx_id']}.png"
        image_upload_res = self.linkedin.upload_media(
            url=upload_url,
            file_path=file_path,
            content_type=f"image/{file_path.suffix.replace('.', '')}",
        )
        return image_upload_res

    def unpublished_totals(self):
        unpublished = self.all_unpublished_videos_by_channel
        for channel, videos in unpublished.items():
            logger.info(f"Unpublished videos for channel {channel}: {len(videos)}")

    @property
    def scheduled_videos(self) -> list[YoutubeVideoResource]:
        """ All videos with a publishing date set"""
        all_unpublished_videos = self.all_unpublished_video_records
        return [x for x in all_unpublished_videos if x.status.publish_at]

    @property
    def recently_released(self) -> list[YoutubeVideoResource]:
        """ Recently released videos."""
        now = datetime.datetime.now(datetime.UTC)
        return [x for x in self.scheduled_videos if x.status.publish_at < now]

    def process_recent_video_releases(self):
        ids = [video.id for video in self.recently_released]
        try:
            # Switches to simpler API key authentication for searches.
            # Does not require interaction.
            # TODO: streamline workflows for API key and OAuth2 in YT class
            self.youtube_client.get_authenticated_service_via_api_key()
            status = self.youtube_client.check_video_status_by_youtube_ids(ids)
        except Exception as e:
            logger.error(f"Failed to check video status: {str(e)}")
            return

        for youtube_video_status in status["items"]:
            if youtube_video_status["status"]["privacyStatus"] != "public":
                continue
            pretalx_id = self.youtube_pretalx_id_map[youtube_video_status["id"]]
            logger.info(f"Video {pretalx_id} is now public, preparing posts and emails.")
            video_record_path = self.video_meta.video_records_path.parent / "video_records_updated" / f"{pretalx_id}.json"
            video_record = YoutubeVideoResource.model_validate_json(video_record_path.read_text())
            video_record.status.privacy_status = youtube_video_status["status"]["privacyStatus"]
            video_record_path.write_text(video_record.model_dump_json(indent=4))
            record_path = self.video_meta.records_path / f"{pretalx_id}.json"
            record = SessionRecord.model_validate_json(record_path.read_text())
            self.prepare_linkedin_post(record)
            self.prepare_email_speakers(record)
            video_record_path.rename(self.youtube_client.video_records_path_published / record_path.name)


if __name__ == "__main__":
    # TODO: Add CLI arguments
    publisher = Publisher(destination_channel=None, youtube_offline=True)
    publisher.unpublished_totals()
    publisher.process_recent_video_releases()
    publisher.post_on_linked_id()
    publisher.email_speakers()
    logger.info("Job completed successfully.")
