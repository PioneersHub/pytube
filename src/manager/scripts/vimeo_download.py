import http
import json
import re
import threading

import requests
from vimeo import VimeoClient

from manager import conf, logger
from manager.models.talk import Talk


def read_manifest():
    f = conf.dirs.work_dir / "manifest.json"
    with f.open() as r:
        manifest = json.load(r)
    return manifest


def make_vimeo_client(client_id=None):
    vimeo_credentials = conf.vimeo.get(f"vimeo_{client_id}") if client_id else conf.vimeo
    _client = VimeoClient(
        token=vimeo_credentials.access_token,
        key=vimeo_credentials.client_id,
        secret=vimeo_credentials.client_secret,
    )
    return _client


def get_list_of__all_video_online() -> list:
    all_videos = []
    page = 1
    per_page = 100  # Vimeo's maximum per page

    while True:
        params = {"page": page, "per_page": per_page}
        response = client.get("https://api.vimeo.com/me/videos", params=params)

        if response.status_code != 200:
            print(f"Error fetching page {page}: {response.status_code}")
            print(response.text)
            break

        data = response.json()
        videos = data.get("data", [])

        if not videos:
            break

        all_videos.extend(videos)

        # Check if there's a next page
        paging = data.get("paging", {})
        if not paging.get("next"):
            break

        page += 1

    return all_videos


def save_list_of__all_video_online() -> None:
    all_videos = get_list_of__all_video_online()
    json.dump(all_videos, (conf.dirs.work_dir / "all_videos.json").open("w"), indent=4)
    return all_videos


def get_video_metadata(video_id: str) -> dict:
    video_metadata = client.get(f"https://api.vimeo.com/videos/{video_id}")
    return video_metadata.json()


def extract_download_link(video_metadata: dict, rendition: str = "1080p", quality: str = "hd"):
    download_links = [x for x in video_metadata["download"] if x["quality"] == quality and x["rendition"] == rendition]
    if not download_links:
        logger.error(f"No download links found for video {video_metadata['uri'].split('/')[-1]}")
        return
    download_link = download_links[0]["link"]
    return download_link


def download_videos(record, idx, total, semaphore):
    with semaphore:
        download_video(record, idx, total)


def download_video(record, idx, total):
    record = Talk(**record)
    logger.info(f"Processing {idx}/{total}: {record.pretalx_id, record.vimeo_link}")

    if not record.vimeo_id:
        return
    download = (
        conf.dirs.video_dir
        / "downloads"
        / f"{record.pretalx_id}"
        / f"{record.pretalx_id}-{record.title[:50].strip()}.mp4"
    )

    try:
        # text file once the video is processed
        processed = (conf.dirs.video_dir / "downloads/processed.txt").read_text().splitlines()
    except FileNotFoundError:
        processed = []
    if record.pretalx_id in processed:
        logger.info(f"Skipping {record.pretalx_id}, already processed.")
        return

    if download.exists():
        logger.info(f"Skipping {record.pretalx_id}, downloaded already.")
        return

    record.download_path = download
    vimeo_metadata_dir = conf.dirs.video_dir / "vimeo"
    vimeo_metadata_dir.mkdir(parents=True, exist_ok=True)
    vimeo_metafile = vimeo_metadata_dir / f"{record.pretalx_id}.json"
    record.vimeo_metadata = get_video_metadata(record.vimeo_id)
    json.dump(record.vimeo_metadata, vimeo_metafile.open("w"), indent=4)
    record.vimeo_download_link = extract_download_link(record.vimeo_metadata)
    response = requests.get(record.vimeo_download_link, stream=True)
    if response.status_code != 200:  # noqa PLR2004
        logger.error(f"Failed to download video: {response.status_code}")
        return
    download.parent.mkdir(parents=True, exist_ok=True)
    with download.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    logger.info(f"Downloaded video to {download.name}")


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


def download_videos_via_pattern(search_term):
    """Download all videos with '2025' in the title in 1080p quality"""
    all_videos = save_list_of__all_video_online()

    # Filter videos with 2025 in the title
    _videos = [v for v in all_videos if search_term in v.get("name", "")]

    print(f"Found {len(_videos)} videos with '{search_term}' in the title")

    for i, video in enumerate(_videos, 1):
        video_id = video["uri"].split("/")[-1]
        video_name = video.get("name", "")

        print(f"\nProcessing video {i}/{len(_videos)}: {video_name}")
        if not video.get("download"):
            print(f"Video {video_name} is not downloadable, this is likely the entry for a live event.")
            continue

        # Get video metadata to get download links
        metadata = get_video_metadata(video_id)

        # Find the 1080p download link
        download_links = [
            dl for dl in metadata.get("download", []) if dl.get("quality") == "hd" and dl.get("height") == 1080
        ]

        if not download_links:
            print(f"No 1080p download link found for {video_name}")
            continue

        download_link = download_links[0].get("link")

        # Create safe filename
        safe_name = re.sub(r'[\\/*?"<>|]', "_", video_name)
        output_path = conf.dirs.video_dir / f"{safe_name}.mp4"

        # Download the video
        response = requests.get(download_link, stream=True)

        if response.status_code != http.HTTPStatus.OK:
            print(f"Failed to download {video_name}: {response.status_code}")
            continue

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        print(f"Downloaded {video_name}")


if __name__ == "__main__":
    for i in [2, 3, 4]:
        client = make_vimeo_client(i)
        download_videos_via_pattern(search_term="2025")
    # manifest_to_slowly_download_jobs()
