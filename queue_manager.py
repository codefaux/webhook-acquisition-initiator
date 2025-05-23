# queue_manager.py

import json
import os
import shutil
import sys
import threading
from pathlib import Path

import logger as _log
import pycountry
from matcher import match_title_to_sonarr_episode, match_title_to_sonarr_show
from sonarr_api import (get_all_series, get_episode_data_for_shows,
                        import_downloaded_episode, is_episode_file,
                        is_monitored_episode, is_monitored_series)
from ytdlp_interface import download_video

DATA_DIR = os.getenv("DATA_DIR")
item = None

QUEUE_FILE = os.path.join(DATA_DIR, "queue.json")
queue_lock = threading.Lock()
queue_condition = threading.Condition(lock=queue_lock)
queue = []

SONARR_IN_PATH = os.getenv("SONARR_IN_PATH", None)
WAI_OUT_TEMP = os.getenv("WAI_OUT_TEMP", None)
WAI_OUT_PATH = os.getenv("WAI_OUT_PATH", "./output")
HONOR_UNMON_SERIES = int(os.getenv("HONOR_UNMON_SERIES", 1)) == 1
HONOR_UNMON_EPS = int(os.getenv("HONOR_UNMON_EPS", 1)) == 1
OVERWRITE_EPS = int(os.getenv("OVERWRITE_EPS", 0)) == 1
QUEUE_INTERVAL = int(os.getenv("QUEUE_INTERVAL", 5))
FLIP_FLOP_QUEUE = int(os.getenv("FLIP_FLOP_QUEUE", 0)) == 1
DEBUG_MODE = os.getenv("DEBUG_MODE", 0) != 0


def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    queue.extend(data)
            except json.JSONDecodeError:
                _log.msg("Failed to decode queue JSON; starting with empty queue.")


def save_queue():
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def load_item(file: str, remove_after: bool = False):
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


def enqueue(item: dict):
    with queue_condition:
        queue.append(item)
        save_queue()
        queue_condition.notify()


def round_to_nearest_hd(width, height):
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


def tag_filename(file_filepath):
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
        file_lang = pycountry.languages.get(alpha_2=file_lang)

    file_tags = f".WEB-DL.{file_width}x{file_height}.{file_lang.alpha_3}-cfwai"

    file_path = Path(file_filepath)
    new_name = file_path.stem + file_tags + file_path.suffix
    new_filepath = file_path.with_name(new_name)
    file_path.rename(new_filepath)

    _log.msg(f"File renamed: {new_filepath}")

    return new_filepath or file_filepath


def dequeue(item: dict):
    with queue_condition:
        for i, q_item in enumerate(queue):
            if q_item == item:
                del queue[i]
                save_queue()

                return {"status": "removed"}

        return {"error": "Item not found in queue"}


def close_item(item, message, filename):
    if DEBUG_MODE:
        breakpoint()
    _log.msg(message)
    save_item(item, filename)
    delete_item_file("current.json")

    return None


def match_and_check(item):
    _log.msg(
        f"Processing item:\n"
        f"\t{_log._GREEN}creator:{_log._RESET} {item.get('creator', '')}"
        f"\t{_log._GREEN}title:{_log._RESET} {item.get('title', '')}\n"
        f"\t{_log._GREEN}datecode:{_log._RESET} {item.get('datecode', '')}"
        f"\t{_log._GREEN}url:{_log._RESET} {item.get('url', '')}"
    )

    show_titles = get_all_series()

    main_title = f"{item.get('creator', '')} :: {item.get('title', '')}"
    title_result = match_title_to_sonarr_show(main_title, show_titles)
    item["title_result"] = title_result
    _log.msg(
        f"Match result: title -> show\n"
        f"\t{_log._YELLOW}input:{_log._RESET} '{main_title}'\n"
        f"\t{_log._BLUE}score:{_log._RESET} {title_result.get('score')}"
        f"\t{_log._GREEN}matched show:{_log._RESET} '{title_result.get('matched_show')}'"
        f" {_log._YELLOW}(id:{title_result.get('matched_id')}){_log._RESET}"
    )

    if title_result["score"] < 70:
        return close_item(
            item,
            f"Series match score not high enough. ({title_result['score']} < 70)  Aborting.",
            "series_score.json",
        )

    if HONOR_UNMON_SERIES:
        if not is_monitored_series(title_result["matched_id"]):
            return close_item(
                item,
                "Series NOT monitored. Aborting.",
                "unmonitored_series.json",
            )

    show_data = get_episode_data_for_shows(
        title_result.get("matched_show"), title_result.get("matched_id")
    )
    episode_result = match_title_to_sonarr_episode(
        main_title, item.get("datecode", -1), show_data
    )
    item["episode_result"] = episode_result
    _log.msg(
        f"Match result: title -> episode:\n"
        f"\t{_log._YELLOW}input:{_log._RESET} '{main_title}'\n"
        f"\t{_log._BLUE}score:{_log._RESET} {episode_result.get('score', 0)}"
        f"\t{_log._GREEN}season:{_log._RESET} {episode_result.get('season', 0)}"
        f"\t{_log._GREEN}episode:{_log._RESET} {episode_result.get('episode')}\n"
        f"{_log._GREEN}title:{_log._RESET} '{episode_result.get('episode_orig_title', '')}'\n"
        f"\t{_log._GREEN}reasons:{_log._RESET} {episode_result.get('reason', '')}"
    )

    if episode_result["score"] < 70:
        return close_item(
            item,
            f"Episode match score not high enough. ({episode_result['score']} < 70)  Aborting.",
            "episode_score.json",
        )

    if HONOR_UNMON_EPS:
        if not is_monitored_episode(
            title_result.get("matched_id"),
            episode_result.get("season"),
            episode_result.get("episode"),
        ):
            return close_item(
                item,
                "Episode NOT monitored. Aborting.",
                "unmonitored_episode.json",
            )

    if not OVERWRITE_EPS:
        if is_episode_file(
            title_result.get("matched_id"),
            episode_result.get("season"),
            episode_result.get("episode"),
        ):
            return close_item(
                item,
                "Episode already has file. Aborting.",
                "episode_has_file.json",
            )

    return item


def download_item(item):
    download_filename = download_video(item.get("url"), WAI_OUT_TEMP or WAI_OUT_PATH)
    item["download_filename"] = download_filename

    if not download_filename:
        item = close_item(
            item,
            "No file at download location. Aborting thread. (API will still function.)",
            "download_fail.json",
        )
        sys.exit(1)  # error condition

    _log.msg(f"Download returned: {download_filename}")

    return item


def rename_and_move_item(item):
    tag_filepath = tag_filename(item.get("download_filename"))
    file_name = os.path.basename(tag_filepath)

    if WAI_OUT_TEMP:  # NOT WORKING
        shutil.copy(tag_filepath, os.path.abspath(WAI_OUT_PATH))
        os.remove(tag_filepath)
        _log.msg(f"Moved: {tag_filepath} \n\t-> To: {os.path.abspath(WAI_OUT_PATH)}")

    item["file_name"] = file_name

    return item


def import_item(item):
    import_result = import_downloaded_episode(
        item["title_result"].get("matched_id"),
        item["episode_result"].get("season"),
        item["episode_result"].get("episode"),
        item["file_name"],
        SONARR_IN_PATH,
    )

    item["import_result"] = import_result

    return item


def process_item(item):
    item = match_and_check(item)

    if not item:
        return False

    if DEBUG_MODE:
        breakpoint()

    item = download_item(item)

    item = rename_and_move_item(item)

    item = import_item(item)

    item = close_item(
        item,
        f"Item Sonarr Import result: {item.get("import_result").get('status')}",
        "pass.json",
    )

    return True


def process_queue(stop_event: threading.Event):
    item = load_item("current.json")

    while not stop_event.is_set():
        with queue_condition:
            while not item and not queue and not stop_event.is_set():
                _log.msg(
                    f"No current item. No queue. Sleeping for at most {QUEUE_INTERVAL} min."
                )
                queue_condition.wait(timeout=QUEUE_INTERVAL * 60)

            if queue and not item:
                item = queue.pop(0)
                if FLIP_FLOP_QUEUE:
                    _log.msg("Inverting queue")
                    queue.reverse()
                save_item(item, "current.json", True)
                save_item(item, "all_processed.json")
                save_queue()

        if item:
            wait_before_loop = process_item(item)

            item = None

            if not wait_before_loop:
                continue

            _log.msg(f"Queue thread sleeping for {QUEUE_INTERVAL} min.")
            with queue_condition:
                queue_condition.wait(timeout=QUEUE_INTERVAL * 60)
