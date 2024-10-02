from datetime import UTC, datetime, timedelta

from handlers.youtube import YT, PrepareVideoMetadata
from usr.usr import slugify

from pytube import conf


class CustomPrepareVideoMetadata(PrepareVideoMetadata):
    """
    Patch PrepareVideoMetadata to customize attributes used in the description template.
    """
    @classmethod
    def customize_description_args(cls, description_kwargs, record):
        """Customized the description arguments."""
        description_kwargs.update({
            "tag": slugify(record.pretalx_session.session.track.en),
            "pydata": record.youtube_channel == "pydata"
        })
        return description_kwargs


def prepare_metadata(template_file: str, at: str):
    """Generate the metadata for the update on YouTube.
    Sets periodical publishing dates for the videos.
    :param template_file: The jinja2 template in `./templates` to use for the metadata.
    :param at: The event name to in the template.
    """
    meta = CustomPrepareVideoMetadata(template_file, at)
    meta.make_all_video_metadata()
    meta.update_publish_dates(states=['video_records', 'video_records_updated'],
                              start=datetime.now(tz=UTC) + timedelta(minutes=5), delta=timedelta(hours=4))
    for channel in conf.youtube.channels:
        meta.send_all_video_metadata(destination_channel=channel)


if __name__ == "__main__":
    # add functions from above here
    yt = YT()

    # get the channel id if not know via logging in
    yt.get_channel_id()

    # is a required mapping file for further processing
    yt.get_youtube_ids_for_uploads("pycon")

    # Match the pretalx id with the YouTube video id
    yt.map_pretalx_id_youtube_id()

    prepare_metadata("youtube_2024.txt", "PyCon DE & PyData Berlin 2024")
