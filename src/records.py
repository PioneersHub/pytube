"""
Class to create records i.e., create one record file for each session with all metadata.

This file can be used for multiple use cases like:
- Create YouTube description
- Create posts on Social Media
- etc.
"""
import json
from datetime import datetime, date
from pathlib import Path
from typing_extensions import Self

from pydantic import BaseModel, Field, model_validator, field_validator
from pydantic.networks import AnyHttpUrl
from pytanis import PretalxClient
from pytanis.pretalx.types import Submission, SubmissionSpeaker

from nlpservice import teaser_text, sized_text
from src import conf, logger


class Organization(BaseModel):
    name: str
    description: str | None = Field(None, description='Description of the organization.')
    is_sponsor: bool | None = Field(None, description='Is the organization a sponsor? "None" if unknown.')
    url: AnyHttpUrl | None = Field(None, description='Homepage of the organization.')
    linkedin: AnyHttpUrl | None = Field(None, description='LinkedIn page of the organization.')
    x_handle: str | None = Field(None, description='X handle of the organization.')


class SpeakerInfo(SubmissionSpeaker):
    linkedin: AnyHttpUrl | None = Field(None, description='LinkedIn profile page of the speaker.')
    github: AnyHttpUrl | None = Field(None, description='GitHub profile page of the speaker.')
    x_handle: str | None = Field(None, description='X handle of the speaker.')
    company: Organization | None = Field(None, description='Organization of the speaker.')
    job: str | None = Field(None, description='Job title of the speaker.')

    @model_validator(mode='after')
    def moderate_x_handle(self) -> Self:
        """Normalize the X handle"""
        if not self.x_handle:
            return self
        if "/" in self.x_handle:
            parts = [x for x in self.x_handle.split("/") if x]
            if parts:
                self.x_handle = f"@{parts[-1]}"
        elif "@" not in self.x_handle:
            self.x_handle = f"@{self.x_handle}"
        return self

    @field_validator('linkedin', mode='before')
    @classmethod
    def moderate_linkedin_url(cls, v: str) -> Self:
        """Normalize the urls"""
        if v and not str(v).startswith("http"):
            if 'linkedin.' in v:
                return f"https://{v}"
            return f"https://linkedin.com/{v}"
        return v

    @field_validator('github', mode='before')
    @classmethod
    def moderate_github_url(cls, v: str) -> Self:
        """Normalize the urls"""
        if v and not str(v).startswith("http"):
            if 'github.' in v:
                return f"https://{v}"
            return f"https://github.com/{v}"
        return v


class PretalxSession(BaseModel):
    """raw data from pretalx"""
    pretalx_id: str
    title: str
    session: Submission
    speakers: list[SpeakerInfo] | list[str]


class SessionRecord(BaseModel, validate_assignment=True):
    # raw data from pretalx
    pretalx_session: PretalxSession
    pretalx_id: str
    title: str
    abstract: str
    description: str
    speakers: list[SpeakerInfo]
    as_tweet: str = Field('', description='Short text for social media posts.')
    sm_teaser_text: str = Field('', description='Teaser text for social media posts.')
    sm_short_text: str = Field('', description='Short text for social media posts.')
    sm_long_text: str = Field('', description='Long text for social media posts.')
    youtube_channel: str = Field('', description='YouTube channel the video was uploaded to.')
    youtube_video_id: str = Field('', description='YouTube video ID.')
    youtube_description: str = Field('', description='YouTube video description.')
    youtube_title: str = Field('', description='YouTube title (max. 100 chars).')
    recorded_date: date | None = Field(None, description='Date the video was recorded.')
    youtube_online_metadata: dict | None = Field(None, description='Metadata as released on YouTube.')
    linked_in_response: dict | None = Field(None, description='Metadata as released on LinkedIn.')
    linked_in_post: str | None = Field(None, description='Post as released on LinkedIn.')


class Records:
    """
    Create and update records.
    Each session will have a record file with all metadata.
    The metadata is collected from the pretalx API (talks, speakers, etc.).
    Additional attributes are added to the record file like:
     - a teaser text
     - a short text, generated by GPT
     - a long text, generated by GPT
     - a linkable LinkedIn profile URL for tagging, if provided by the speaker
     - etc.

     The first step is to load all confirmed sessions from pretalx and store them in a JSON file:
     - load_all_confirmed_sessions(), load_all_speakers()
     This information is also used by other scripts in this module, e.g., to organize the video recordings.

     Further steps are optional and can be executed in any order. These steps will add or change the metadata on file:
        - adding teaser, short and long texts
        - extracting LinkedIn, GitHub and X profile URLs
    """

    def __init__(self, qmap: dict[str, int] | None = None, *, reload=False):
        """

        :param qmap: Some metadata can only be found in the answers to customs questions in Pretalx
        Custom questions are stored in a list of sub-documents in the pretalx session and speaker data.
        To identify the right questions, we need to map the question IDs to answer texts.
        qmap must be a dict like {attribute name to add to `SpeakerInfo` or `Organization`: ID}.
        :param reload:
        """
        self.qmap: dict[str, int] | None = qmap
        self.reload: bool = reload
        self.pretalx_client = PretalxClient()
        self._tracks_map: dict = {}
        self._confirmed_sessions_map: dict = {}
        self._speakers_map: dict = {}

        self.records: Path = conf.dirs.work_dir / 'records'
        self.records.mkdir(parents=True, exist_ok=True)

    def load_all_confirmed_sessions(self) -> None:
        """ Load all confirmed talks from pretalx and store it into a single JSON file stored in `_tmp/pretalx`"""
        logger.info('Loading all confirmed sessions')
        the_dir = conf.dirs.work_dir / 'pretalx'
        the_dir.mkdir(parents=True, exist_ok=True)
        if not self.reload and (conf.dirs.work_dir / 'confirmed_sessions_map.json').exists():
            logger.info('Confirmed sessions already loaded, skipping')
            return
        subs_count, subs = self.pretalx_client.submissions(
            conf.pretalx.event_slug,
            params={'questions': 'all', 'state': 'confirmed'})
        logger.info(f'Loaded {subs_count} confirmed sessions')

        logger.info('Writing confirmed sessions to disk')
        if self.reload:
            logger.info('Reloading confirmed sessions, deleting all existing files')
            for x in the_dir.glob('*.json'):
                x.unlink()
        for sub in subs:
            (the_dir / f'{sub.code}.json').write_text(sub.model_dump_json(indent=4))
        logger.info(f'Done: wrote {subs_count} confirmed sessions to disk')
        self.create_confirmed_sessions_map()

    def load_all_speakers(self) -> None:
        """ Load all speakers from pretalx and store it into a single JSON file stored in `_tmp/pretalx_speakers`"""
        logger.info('Loading all speakers')
        the_dir = conf.dirs.work_dir / 'pretalx_speakers'
        the_dir.mkdir(parents=True, exist_ok=True)
        if not self.reload and len(list(the_dir.glob('*.json'))):
            logger.info('Speakers already loaded, skipping')
            return
        subs_count, subs = self.pretalx_client.speakers(
            conf.pretalx.event_slug,
            params={'questions': 'all'})
        logger.info(f'Loaded {subs_count} speakers')
        logger.info('Writing speakers to disk')
        if self.reload:
            logger.info('Reloading speakers, deleting all existing files')
            for x in the_dir.glob('*.json'):
                x.unlink()
        for sub in subs:
            (conf.dirs.work_dir / 'pretalx_speakers' / f'{sub.code}.json').write_text(sub.model_dump_json(indent=4))
        logger.info(f'Done: wrote {subs_count} speakers to disk')
        self.create_speaker_map()

    @classmethod
    def create_confirmed_sessions_map(cls) -> None:
        """ Create a mapping of all confirmed sessions form the data loaded via `load_all_confirmed_sessions`"""
        the_dir = conf.dirs.work_dir / 'pretalx'
        confirmed_map = {}
        for x in the_dir.glob('*.json'):
            data = json.load(x.open())
            confirmed_map[data['code']] = data
        if not confirmed_map:
            logger.error('No confirmed sessions found, did you run `load_all_confirmed_sessions`?')
        json.dump(confirmed_map, (conf.dirs.work_dir / 'confirmed_map.json').open('w'), indent=4)
        logger.info('Created confirmed sessions map')

    @classmethod
    def create_speaker_map(cls) -> None:
        """ Create a mapping of all confirmed sessions form the data loaded via `load_all_confirmed_sessions`"""
        the_dir = conf.dirs.work_dir / 'pretalx_speakers'
        confirmed_map = {}
        for x in the_dir.glob('*.json'):
            data = json.load(x.open())
            confirmed_map[data['code']] = data
        if not confirmed_map:
            logger.error('No speakers found, did you run `load_all_speakers`?')
        json.dump(confirmed_map, (conf.dirs.work_dir / 'speaker_map.json').open('w'), indent=4)
        logger.info('Created confirmed speakers map')

    @property
    def confirmed_sessions_map(self) -> dict:
        if not self._confirmed_sessions_map:
            self._confirmed_sessions_map = json.load((conf.dirs.work_dir / 'confirmed_sessions_map.json').open())
        return self._confirmed_sessions_map

    @property
    def speakers_map(self) -> dict:
        if not self._speakers_map:
            self._speakers_map = json.load((conf.dirs.work_dir / 'speaker_map.json').open())
        return self._speakers_map

    def create_records(self) -> None:
        """ Create records for all confirmed sessions"""
        for code, data in self.confirmed_sessions_map.items():
            self.create_record(code, data)

    def create_record(self, code: str, data: dict) -> None:
        """ Create a record for a single session exclusively from pretalx data."""
        p_session = PretalxSession(
            pretalx_id=data['code'],
            title=data['title'],
            session=Submission.model_validate(data),
            speakers=[x['code'] for x in data['speakers']]
        )

        def get_answer_via_id(answers: list[dict], answer_id: int):
            # answer_id is always > 0
            rec: list[dict[str, str]] = [x for x in answers if x.get("question", {}).get("id", -1) == answer_id]
            if rec:
                answer = rec[0]["answer"]
                if isinstance(answer, str):
                    answer = answer.strip()
                return answer

        def add_attr(obj, qmap):
            for attr, qid in qmap.items():
                answer = get_answer_via_id(speaker['answers'], qid)
                if answer:
                    if attr == 'company':
                        answer = Organization(name=answer)
                    try:
                        setattr(obj, attr, answer)
                    except Exception as e:
                        pass
            return obj

        speakers = []
        for speaker in [self.speakers_map[x] for x in p_session.speakers]:
            s = SpeakerInfo.model_validate(speaker)
            s = add_attr(s, self.qmap)
            speakers.append(s)

        record = SessionRecord(
            pretalx_session=p_session,
            pretalx_id=p_session.pretalx_id,
            title=p_session.title,
            abstract=data['abstract'],
            description=data['description'],
            speakers=speakers,
            as_tweet='',
            sm_teaser_text='',
            sm_short_text='',
            sm_long_text='',
        )
        add_attr(record, self.qmap)
        (self.records / f'{code}.json').write_text(record.model_dump_json(indent=4))

    def add_descriptions(self, replace=False) -> None:
        """ Add descriptions to all confirmed sessions """
        for x in self.records.glob('*.json'):
            try:
                data = SessionRecord.model_validate_json(x.read_text())
            except Exception as e:
                jdata = json.load(x.open())
                logger.error(f'Error adding descriptions to {jdata["pretalx_id"]}: {e}')
                a = 44
            speakers = '\n'.join([f"{x.name} ({x.job}\nbiography:\n{x.biography})" for x in data.speakers])
            info = f"title:{data.title}\nspeaker(s):\n{speakers}\ndescription:\n{data.abstract}\n{data.description}"
            if not data.sm_teaser_text or replace:
                data.sm_teaser_text = teaser_text(info, max_tokens=50)
            if not data.sm_short_text or replace:
                data.sm_short_text = sized_text(info, max_tokens=100)
            if not data.sm_long_text or replace:
                data.sm_long_text = sized_text(info, max_tokens=300)
            (self.records / f'{data.pretalx_id}.json').write_text(data.model_dump_json(indent=4))
            logger.info(f'Added descriptions to {data.pretalx_id}')
            a = 44


if __name__ == '__main__':
    questions_map = {
        "company": 3012,
        "job": 3013,
        "linkedin": 3017,
        "github": 3016,
        "x_handle": 3015,
        "as_tweet": 3022,
    }
    r = Records(qmap=questions_map)
    r.load_all_confirmed_sessions()
    r.load_all_speakers()
    # r.create_records()
    r.add_descriptions(replace=False)
