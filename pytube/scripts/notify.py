"""
Check for recent video releases on the YouTube channel.
Trigger LinkedIn post and email to speaker creation.
Post LinkedIn and send emails.
"""
from handlers import Publisher

from pytube import logger

if __name__ == "__main__":
    logger.info("Starting the job.")
    publisher = Publisher(destination_channel=None, youtube_offline=True)
    publisher.unpublished_totals()
    publisher.process_recent_video_releases()
    publisher.post_on_linked_id()
    publisher.email_speakers()
    logger.info("Job completed successfully.")
