import json
import shutil
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from pytanis import PretalxClient
from src import conf, logger


class Video(BaseModel):
    id: str
    title: str
    description: str
    duration: int
    url: str
    thumbnail: str
    tags: list[str]
    speaker: str


def youtube_title(video: Video):
    # TODO Implement this function
    """ Length is limited. 
    A video title with max possible information of title, speakers and event."""
    max_length = 100
    title = video.title
    return 'https://www.youtube.com/watch?v='


def split_pycon_pydata(video: str):
    """ Assign videos to PyData or PyCon. In case this cannot be done by track, add the pretalx code in the config """
    if video['code'] in conf.pretalx.video_to_track:
        return conf.pretalx.video_to_track[video['code']]
    for snippet in conf.pretalx.track_to_channel:
        if snippet.casefold() in video['track']['en'].casefold():
            return conf.pretalx.track_to_channel[snippet]
    print(video['code'], video['track']['en'], video['title'])


def load_all_confirmed():
    pretalx_client = PretalxClient()
    subs_count, subs = pretalx_client.submissions(
        conf.pretalx.event_slug,
        params={'questions': 'all', 'state': 'confirmed'})

    (conf.dirs.work_dir / 'pretalx').mkdir(parents=True, exist_ok=True)
    for sub in subs:
        (conf.dirs.work_dir / 'pretalx' / f'{sub.code}.json').write_text(sub.model_dump_json(indent=4))


def load_all_speakers():
    pretalx_client = PretalxClient()
    subs_count, subs = pretalx_client.speakers(
        conf.pretalx.event_slug,
        params={'questions': 'all'})

    (conf.dirs.work_dir / 'pretalx_speakers').mkdir(parents=True, exist_ok=True)
    for sub in subs:
        (conf.dirs.work_dir / 'pretalx_speakers' / f'{sub.code}.json').write_text(sub.model_dump_json(indent=4))


def assign_video_to_channel():
    collect_tracks = defaultdict(list)
    collect_tracks_map = {}
    for sub in load_confirmed_map():
        track = split_pycon_pydata(sub)
        collect_tracks[track].append(sub)
        collect_tracks_map[sub['code']] = track
    with open(conf.dirs.video_dir / 'tracks.json', 'w') as f:
        json.dump(collect_tracks, f, indent=4)
    with open(conf.dirs.video_dir / 'tracks_map.json', 'w') as f:
        json.dump(collect_tracks_map, f, indent=4)
    return collect_tracks


def load_confirmed_map():
    confirmed_map = {}
    for x in conf.dirs.work_dir.glob('pretalx/*.json'):
        data = json.load(x.open())
        confirmed_map[data['code']] = data
    json.dump(confirmed_map, (conf.dirs.video_dir / 'confirmed_map.json').open('w'), indent=4)
    return confirmed_map


def load_tracks_map():
    return json.load((conf.dirs.video_dir / 'tracks_map.json').open())


def video_code_map() -> list[Path]:
    """Mapping of all downloaded videos"""
    downloaded = Path(conf.dirs.video_dir / 'downloads').rglob('*.mp4')
    return {x.stem.split('-')[0]: x for x in downloaded}


def move_videos_to_upload_channel():
    """Move all videos to the correct channel"""
    video_map = video_code_map()
    tracks_map = load_tracks_map()
    confirmed_map = load_confirmed_map()
    move_us, do_not_release, missing = set(), set(), set()
    for code, info in confirmed_map.items():
        if code not in video_map:
            if info['do_not_record']:
                # confirmed but not to be released
                logger.debug(f'Video {code} not to be released')
                do_not_release.add((code, info['title']))
                continue
            # confirmed but not downloaded
            missing.add((code, info['title']))
        if confirmed_map[code]['do_not_record']:
            logger.warning(f'Video {code} not to be released')
            do_not_release.add((code, info['title']))
            continue
        if code not in tracks_map:
            logger.warning(f'Video {code} not found in tracks')
            missing.add((code, info['title']))
            continue
        if code not in video_map:
            logger.warning(f'Video {code} recording is missing')
            missing.add((code, info['title']))
            continue
        move_us.add((video_map[code], code, tracks_map[code],))
        logger.debug(f'{code} -> {tracks_map[code]}')
        for record in move_us:
            logger.info(f'Moving {record[1]} to {record[2]}')
            src = record[0]
            dst = conf.dirs.video_dir / 'uploads' / record[2] / record[0].name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            with (conf.dirs.video_dir / 'downloads/processed.txt').open("a") as f:
                f.write_text(f'{record[1]}\n')
    a = 44


if __name__ == '__main__':
    # load_all_confirmed()
    load_all_speakers()
    # assign_video_to_channel()
    # move_videos_to_upload_channel()
    a = 44
