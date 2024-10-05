import json
from pathlib import Path

pretalx = Path("/Users/hendorf/code/pioneershub/py_tube/_tmp/pretalx")

all_talks = []
for t in Path("/Volumes/DATA/_video-TMP/pyconde-2024/transcipts").glob("*.txt"):
    data = json.loads((pretalx / f"{t.stem}.json").read_text())
    record = {
        "code": data["code"],
        "speakers": [{"name": x["name"], "biography": x["biography"]} for x in data["speakers"]],
        "title": data["title"],
        "track": data["track"]["en"],
        "description": data["description"] + data["description"],
        "transcription": t.read_text()
    }
    doc = []
    doc.append(f"Session: {data['title']}")
    try:
        spkrs = "speakers:\n" + "\n".join(
            [x.get('name', '') + "\n" + x.get('biography') if x.get('biography') else '' for x in
             data.get('speakers', [])])
    except TypeError:
        a = 44
    doc.append(spkrs)
    doc.append(f"Track: {data['track']['en']}")
    doc.append(f"Description: {data['abstract']}\n{data['description']}")
    doc.append(f"Transcription of the spoken talk: {t.read_text()}")
    doc = "\n\n".join(doc)
    with Path(f"/Volumes/DATA/_video-TMP/pyconde-2024/talks/{t.stem}.txt").open("w") as f:
        f.write(doc)
    all_talks.append(record)
    print(t.stem)
with Path("/Volumes/DATA/_video-TMP/pyconde-2024/all.json").open("w") as f:
    json.dump(all_talks, f, indent=2)
