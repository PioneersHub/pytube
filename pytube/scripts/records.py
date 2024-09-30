from handlers import Records

from pytube import conf

if __name__ == '__main__':
    questions_map = conf.pretalx_questions_map
    r = Records(qmap=questions_map)
    r.load_all_confirmed_sessions()
    r.load_all_speakers()
    r.create_records()
    r.add_descriptions(replace=False)
