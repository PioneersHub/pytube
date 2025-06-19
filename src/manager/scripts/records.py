"""
This module loads all metadata from pretalx

Make sure to put the mapping of for custom questions in config_local.yaml

"""

from manager import conf
from manager.handlers import Records

if __name__ == "__main__":
    questions_map = conf.pretalx.questions_map
    r = Records(qmap=questions_map)
    r.load_all_confirmed_sessions()
    r.load_all_speakers()
    r.create_records()
    r.add_descriptions(replace=False)
