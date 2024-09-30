"""
Script with functions to organize conference videos and assign them to the correct channel.
"""
import json
import shutil
from collections import defaultdict
from pathlib import Path

from handlers.records import Records

from pytube import conf, logger

records = Records()


def split_pycon_pydata(video: str):
    """ Assign videos to PyData or PyCon via the track
    In case this cannot be done by track,
    add the pretalx code in the config
    """
    if video['code'] in conf.pretalx.video_to_track:
        return conf.pretalx.video_to_track[video['code']]
    for snippet in conf.pretalx.track_to_channel:
        if snippet.casefold() in video['track']['en'].casefold():
            return conf.pretalx.track_to_channel[snippet]
    print(video['code'], video['track']['en'], video['title'])


def assign_video_to_channel():
    collect_tracks = defaultdict(list)
    collect_tracks_map = {}
    for sub in records.confirmed_sessions_map:
        track = split_pycon_pydata(sub)
        collect_tracks[track].append(sub)
        collect_tracks_map[sub['code']] = track
    with open(conf.dirs.video_dir / 'tracks.json', 'w') as f:
        json.dump(collect_tracks, f, indent=4)
    with open(conf.dirs.video_dir / 'tracks_map.json', 'w') as f:
        json.dump(collect_tracks_map, f, indent=4)
    return collect_tracks


def load_tracks_map() -> dict:
    the_file = conf.dirs.video_dir / 'tracks_map.json'
    if not the_file.exists():
        logger.error(f'File {the_file} does not exist, did you run `assign_video_to_channel`?')
    return json.load(the_file.open())


def video_code_map() -> list[Path]:
    """Mapping of all downloaded videos"""
    downloaded = Path(conf.dirs.video_dir / 'downloads').rglob('*.mp4')
    return {x.stem.split('-')[0]: x for x in downloaded}


def move_videos_to_upload_channel():
    """Move all videos to the correct channel"""
    video_map = video_code_map()
    tracks_map = load_tracks_map()
    confirmed_map = records.confirmed_sessions_map
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


if __name__ == '__main__':
    # prepare data from pretalx
    # records.load_all_confirmed_sessions()
    # records.load_all_speakers()

    # video
    # assign_video_to_channel()
    # move_videos_to_upload_channel()
    a = 44
