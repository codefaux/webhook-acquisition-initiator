import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import logger as _log
import pycountry
from dateutil import parser as dateparser

DATA_DIR = os.getenv("DATA_DIR") or "./data"
AGING_RIPENESS_PER_DAY = int(os.getenv("AGING_RIPENESS_PER_DAY", 4))


def parse_date(date_input: str | date) -> datetime | None:
    if isinstance(date_input, date):
        date_input = str(date_input)

    try:
        return dateparser.parse(date_input, fuzzy=True)
    except (ValueError, TypeError):
        return None


def date_distance_days(date1_input: str | date, date2_input: str | date) -> int:
    date1 = parse_date(date1_input)
    date2 = parse_date(date2_input)
    if date1 is None or date2 is None:
        return -1
    return abs((date1.date() - date2.date()).days)


def get_next_aging_time() -> int:
    return int(
        (datetime.now() + timedelta(hours=(24 / AGING_RIPENESS_PER_DAY))).timestamp()
    )


def get_new_ripeness(item: dict) -> int:
    return (
        date_distance_days(item["datecode"], date.today().strftime("%Y-%m-%d"))
        * AGING_RIPENESS_PER_DAY
    )


def ensure_dir(directory: str):
    if not os.path.exists(directory):
        os.makedirs(directory)


def load_item(file: str, remove_after: bool = False) -> dict | None:
    file_path = os.path.join(DATA_DIR, file)

    if os.path.exists(file_path):
        item = None
        with open(file_path, "r") as f:
            try:
                item = json.load(f)
            except json.JSONDecodeError:
                _log.msg(f"Failed to decode JSON '{file_path}' ; returning None.")
        if remove_after:
            os.remove(file_path)

        return item


def delete_item_file(file: str):
    file_path = os.path.join(DATA_DIR, file)

    if os.path.exists(file_path):
        os.remove(file_path)


def save_item(item, file: str, replace: bool = False):
    file_path = os.path.join(DATA_DIR, file)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    if not replace:
        existing_items = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    existing_items = json.load(f)
                    if not isinstance(existing_items, list):
                        _log.msg(
                            f"Warning: Expected list in {file}, got {type(existing_items)}. Overwriting."
                        )
                        existing_items = []
            except json.JSONDecodeError:
                _log.msg(f"Warning: Failed to decode {file}. Overwriting.")

        existing_items.append(item)
    else:
        existing_items = item

    with open(file_path, "w") as f:
        json.dump(existing_items, f, indent=2)


def round_to_nearest_hd(width: int, height: int) -> tuple[int, int]:
    resolutions = [
        (426, 240),
        (640, 360),
        (854, 480),
        (1280, 720),
        (1920, 1080),
        (2560, 1440),
        (3840, 2160),
        (7680, 4320),
    ]
    for w, h in resolutions:
        if width <= w and height <= h:
            return (w, h)

    return (7680, 4320)


def tag_filename(file_filepath: str) -> str:
    data_name = str(Path(file_filepath).with_suffix(".info.json"))
    file_data = {}

    if os.path.exists(data_name):
        with open(data_name, "r") as f:
            try:
                file_data = json.load(f)
            except json.JSONDecodeError:
                _log.msg("Failed to decode file JSON; skipping retag.")

                return file_filepath

    file_width, file_height = round_to_nearest_hd(
        file_data["width"], file_data["height"]
    )

    file_lang = file_data.get("language", None)
    if not file_lang:
        # import langid
        from langid.langid import LanguageIdentifier, model

        identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)
        classify_string = file_data.get("description", None)
        if not classify_string:
            classify_string = file_data.get("title", None)

        lang_id, lang_prob = identifier.classify(classify_string)

        _log.msg(f"lang_id: {lang_id}\tlang_condifence: {lang_prob}")
        file_lang = pycountry.languages.get(alpha_2=lang_id)
    else:
        new_lang = dict(pycountry.languages.get(alpha_2=file_lang) or {})
        file_lang = new_lang.get("alpha_3", "unk")

    file_tags = f".WEB-DL.{file_width}x{file_height}.{file_lang}-cfwai"

    file_path = Path(file_filepath)
    new_name = file_path.stem + file_tags + file_path.suffix
    new_filepath = str(file_path.with_name(new_name))
    file_path.rename(new_filepath)

    _log.msg(f"File renamed: {new_filepath}")

    return new_filepath or file_filepath
