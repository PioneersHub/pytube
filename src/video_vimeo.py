import json
import threading

import requests
from vimeo import VimeoClient

from models.talk import Talk
from src import conf, logger


def read_manifest():
    f = conf.dirs.work_dir / 'manifest.json'
    with f.open() as r:
        manifest = json.load(r)
    return manifest


client = VimeoClient(
    token=conf.vimeo.access_token,
    key=conf.vimeo.client_id,
    secret=conf.vimeo.client_secret,
)


def get_list_of__all_video_online():
    response = client.get('https://api.vimeo.com/me/videos')
    return response.json()


def save_list_of__all_video_online():
    all_videos = get_list_of__all_video_online()
    json.dump(all_videos, (conf.dirs.work_dir / 'all_videos.json').open('w'), indent=4)


def get_video_metadata(video_id: str) -> dict:
    video_metadata = client.get(f'https://api.vimeo.com/videos/{video_id}')
    return video_metadata.json()


def extract_download_link(video_metadata: dict, rendition: str = '1080p', quality: str = 'hd'):
    download_links = [x for x in video_metadata['download'] if x['quality'] == quality and x['rendition'] == rendition]
    if not download_links:
        logger.error(f"No download links found for video {video_metadata['uri'].split('/')[-1]}")
        return
    download_link = download_links[0]['link']
    return download_link


def download_videos(record, idx, total, semaphore):
    with semaphore:
        download_video(record, idx, total)


def download_video(record, idx, total):
    record = Talk(**record)
    logger.info(f'Processing {idx}/{total}: {record.pretalx_id, record.vimeo_link}')

    if not record.vimeo_id:
        return
    download = conf.dirs.video_dir / 'downloads' / f'{record.pretalx_id}' / f'{record.pretalx_id}-{record.title[:50].strip()}.mp4'

    try:
        # text file once the video is processed
        processed = (conf.dirs.video_dir / 'downloads/processed.txt').read_text().splitlines()
    except FileNotFoundError:
        processed = []
    if record.pretalx_id in processed:
        logger.info(f'Skipping {record.pretalx_id}, already processed.')
        return

    if download.exists():
        logger.info(f'Skipping {record.pretalx_id}, downloaded already.')
        return

    record.download_path = download
    vimeo_metadata_dir = conf.dirs.video_dir / 'vimeo'
    vimeo_metadata_dir.mkdir(parents=True, exist_ok=True)
    vimeo_metafile = vimeo_metadata_dir / f'{record.pretalx_id}.json'
    record.vimeo_metadata = get_video_metadata(record.vimeo_id)
    json.dump(record.vimeo_metadata, vimeo_metafile.open('w'), indent=4)
    record.vimeo_download_link = extract_download_link(record.vimeo_metadata)
    response = requests.get(record.vimeo_download_link, stream=True)
    if response.status_code != 200:  # noqa PLR2004
        logger.error(f'Failed to download video: {response.status_code}')
        return
    download.parent.mkdir(parents=True, exist_ok=True)
    with download.open('wb') as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    logger.info(f'Downloaded video to {download.name}')


def manifest_to_slowly_download_jobs(max_threads=3):
    manifest = read_manifest()
    jobs = []
    for idx, record in enumerate(manifest, 1):
        jobs.append((record, idx, len(manifest)))

    semaphore = threading.Semaphore(max_threads)
    threads = []
    for idx, record, total in jobs:
        # Create a Thread object targeting the task function
        thread = threading.Thread(target=download_videos, args=(idx, record, total, semaphore))
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()


if __name__ == '__main__':
    manifest_to_slowly_download_jobs()
