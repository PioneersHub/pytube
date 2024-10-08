"""
Read Google Sheet with videos
"""
import time

import gspread
import pandas as pd
from models.talk import Talk
from pytanis import GSheetsClient

from pytube import conf, logger

# noinspection SpellCheckingInspection
SPREADSHEET_ID = conf.spreadsheets.ids
WORKSHEET_NAMES = conf.spreadsheets.sheets


def load_sheets() -> dict[tuple[str, str], pd.DataFrame]:
    """ Load Google Sheets into DataFrames
    If the file exists, read it, otherwise read from Google Sheets.
    There is a limit on the number of reads for the Google Sheets API.
    """
    data = {}
    gsheets_client = GSheetsClient()
    logger.info("Reading Google Sheets")
    for room, spreadsheet_id in SPREADSHEET_ID.items():
        for day in WORKSHEET_NAMES:
            f = conf.dirs.work_dir / f"sheets/{day}_{room}.xlsx"
            tries = 0
            if f.exists():
                data[(day, room)] = pd.read_excel(f)
                logger.info(f"Skipping {room} {day}, file exists")
                continue

            logger.info(f"Reading {room} {day}")
            while True:
                try:
                    sheet_data = gsheets_client.gsheet_as_df(spreadsheet_id, day)
                    data[(day, room)] = sheet_data
                    try:
                        sheet_data.to_excel(f, index=False)
                        logger.info(f"Saved {room} {day}")
                    except Exception as e:
                        logger.error(f"Error saving {room} {day} {e}")
                    try:
                        sheet_data.to_excel(f, index=False)
                        logger.info(f"Saved {room} {day}")
                    except Exception as e:
                        logger.error(f"Error saving {room} {day} {e}")
                    break
                except gspread.exceptions.APIError as e:
                    if tries > 3:  # noqa PLR2004
                        logger.error(f"Too many tries: giving up {room} {day} {e}")
                        break
                    logger.error(f"APIError reading {room} {day} {e}")
                    logger.info("Retrying in 60 seconds")
                    tries += 1
                    time.sleep(60)
                except Exception as e:
                    logger.error(f"Error reading {room} {day} {e}")
    return data


def process_sheets():
    """
    Process the Google Sheets to a list of Talks for further processing
    Produced a manifest.xlsx and manifest_skipped.xlsx
    Manifest.xlsx contains the list of talks to process.
    Skipped_manifest.xlsx contains the list of lines that were skipped to doublecheck.
    :return:
    """
    data_collected = load_sheets()
    talks = []
    skipped = []
    for (day, room), df in data_collected.items():
        logger.info(f"Processing {room} {day}")
        # the same columns are expected for all sheets
        df.columns = ["talk", "speakers", "pretalx_id", "vimeo_link"]
        df = df.fillna("")  # noqa PLW2901
        for i, row in df.iterrows():
            try:
                t = Talk(
                    title=row["talk"],
                    speaker=row["speakers"],
                    pretalx_id=row["pretalx_id"],
                    room=room,
                    day=day,
                    vimeo_link=row["vimeo_link"],
                )
            except Exception as e:
                logger.error(f"Error processing {room} {day} {i} {e}")
                skipped.append(row)
                continue
            if not t.pretalx_id or len(t.pretalx_id.strip()) != 6 or "vimeo.com" not in t.vimeo_link:  # noqa PLR2004
                # heuristic to skip empty or opt-out comments
                logger.error(f"Missing pretalx_id {t.title} {t.speaker}")
                skipped.append(t)
                continue
            talks.append(t)
            logger.debug(f"Processed {t.title} {t.speaker} {t.pretalx_id} {t.vimeo_link}")
        logger.info(f"Processed {len(talks)} talks for {room} {day}")
    manifest = pd.DataFrame([t.model_dump() for t in talks])
    manifest.to_excel(conf.dirs.work_dir / "manifest.xlsx", index=False)
    manifest.to_json(conf.dirs.work_dir / "manifest.json", orient="records")
    manifest_skipped = pd.DataFrame([t.model_dump() for t in skipped])
    manifest_skipped.to_excel(conf.dirs.work_dir / "manifest_skipped.xlsx", index=False)
    logger.info("Done")
    return manifest.to_dict(orient="records")


if __name__ == "__main__":
    process_sheets()
    logger.info("Finished processing sheets.")
