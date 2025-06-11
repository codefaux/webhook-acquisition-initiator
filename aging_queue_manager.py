# queue_manager.py

import json
import os
import threading
from datetime import datetime

import logger as _log
from util import delete_item_file, load_item, save_item

# from matcher import match_title_to_sonarr_episode
# from queue_manager import enqueue
# from sonarr_api import get_episode_data_for_shows, refresh_series
# from util import delete_item_file, get_new_ripeness, load_item, save_item

DATA_DIR = os.getenv("DATA_DIR") or "./data"

AGING_RIPENESS_PER_DAY = int(os.getenv("AGING_RIPENESS_PER_DAY", 4))
SONARR_IN_PATH = os.getenv("SONARR_IN_PATH", None)
WAI_OUT_TEMP = os.getenv("WAI_OUT_TEMP", None)
WAI_OUT_PATH = os.getenv("WAI_OUT_PATH", "./output")
HONOR_UNMON_SERIES = int(os.getenv("HONOR_UNMON_SERIES", 1)) == 1
HONOR_UNMON_EPS = int(os.getenv("HONOR_UNMON_EPS", 1)) == 1
OVERWRITE_EPS = int(os.getenv("OVERWRITE_EPS", 0)) == 1
FLIP_FLOP_QUEUE = int(os.getenv("FLIP_FLOP_QUEUE", 0)) == 1
DEBUG_PRINT = os.getenv("DEBUG_PRINT", 0) != 0
DEBUG_BREAK = os.getenv("DEBUG_BREAK", 0) != 0

AGING_QUEUE_FILE = os.path.join(DATA_DIR, "aging_queue.json")
AGING_QUEUE_INTERVAL = int(os.getenv("AGING_QUEUE_INTERVAL", 5))
aging_queue_lock = threading.Lock()
aging_queue_condition = threading.Condition(lock=aging_queue_lock)
aging_queue = []
aging_item = None


def load_aging_queue():
    global aging_queue
    aging_queue = []
    if os.path.exists(AGING_QUEUE_FILE):
        with open(AGING_QUEUE_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    aging_queue.extend(data)
            except json.JSONDecodeError:
                _log.msg(
                    "Failed to decode queue JSON; starting with empty aging queue."
                )


def save_aging_queue():
    global aging_queue
    with open(AGING_QUEUE_FILE, "w") as f:
        json.dump(aging_queue, f, indent=2)


def aging_enqueue(aging_item: dict) -> None:
    from util import get_new_ripeness, get_next_aging_time

    if aging_item.get("ripeness", -1) == -1:
        aging_item["ripeness"] = get_new_ripeness(aging_item)
        aging_item["next_aging"] = get_next_aging_time()

    with aging_queue_condition:
        aging_queue.append(aging_item)
        save_aging_queue()
        aging_queue_condition.notify()  # does this cause immediate action?

    return None


def close_aging_item(
    aging_item: dict, message: str, filename: str | None, stack_offset: int = 2
) -> None:
    # if DEBUG_BREAK:
    #     breakpoint()
    _log.msg(message, stack_offset)
    if filename:
        save_item(aging_item, filename)
    delete_item_file("current_aging.json")

    return None


def recheck_episode_match(item: dict) -> dict | None:
    from matcher import match_title_to_sonarr_episode
    from sonarr_api import get_episode_data_for_shows

    show_data = get_episode_data_for_shows(
        item["title_result"].get("matched_show"), item["title_result"].get("matched_id")
    )
    main_title = f"{item.get('creator', '')} :: {item.get('title', '')}"
    episode_result = match_title_to_sonarr_episode(
        main_title, item.get("datecode", -1), show_data
    )

    if episode_result["score"] < 70:
        return None

    item["episode_result"] = episode_result

    return item


def process_aging_item(aging_item: dict) -> tuple[bool, dict | None]:
    from queue_manager import enqueue
    from sonarr_api import refresh_series
    from util import get_new_ripeness, get_next_aging_time

    if aging_item.get("ripeness", -1) == -1:
        aging_item["ripeness"] = get_new_ripeness(aging_item)

    if aging_item["ripeness"] < AGING_RIPENESS_PER_DAY * 3:
        checked_item = recheck_episode_match(aging_item)

        if checked_item:
            enqueue(checked_item)
            return True, close_aging_item(
                aging_item,
                f"{_log._GREEN}Episode found.{_log._RESET} Returning item to main queue.",
                "requeued.json",
            )
        else:
            now = int(datetime.now().timestamp())

            if now - aging_item.get("last_scan", 0) > 120:
                aging_item["last_scan"] = now

                refresh_series(aging_item["title_result"]["matched_id"])
                _ = close_aging_item(
                    aging_item,
                    "Requesting Sonarr refresh for '"
                    f"{_log._YELLOW}{aging_item["title_result"]["matched_show"]}{_log._RESET}"
                    "' and returning to aging queue.",
                    None,
                )
            else:
                aging_item["ripeness"] += 1
                aging_item["next_aging"] = get_next_aging_time()

            return True, aging_item

    else:
        _log.msg(
            f"Ripeness {aging_item["ripeness"]}: Item should be old enough for data."
        )
        return True, close_aging_item(
            aging_item,
            "Moving to manual intervention queue.",
            "manual_intervention.json",
        )


def process_aging_queue(stop_event: threading.Event):
    global aging_item
    global aging_queue

    if aging_item is None:
        aging_item = load_item("current_aging.json")
    if aging_queue == []:
        load_aging_queue()

    while not stop_event.is_set():
        with aging_queue_condition:
            while not aging_item and not aging_queue and not stop_event.is_set():
                _log.msg(
                    f"No current aging item. No aging queue. Sleeping for at most {AGING_QUEUE_INTERVAL} min."
                )
                aging_queue_condition.wait(timeout=AGING_QUEUE_INTERVAL * 60)

            if not aging_item and aging_queue:
                now = int(datetime.now().timestamp())
                eligible_aging_items = [
                    n_item
                    for n_item in aging_queue
                    if n_item.get("next_aging", 0) <= now
                ]
                if eligible_aging_items:
                    # Sort by next_aging to pick the most overdue item
                    if DEBUG_PRINT:
                        _log.msg("Sorting eligible items..")
                    eligible_aging_items.sort(
                        key=lambda item: item.get("next_aging", 0)
                    )
                    aging_item = eligible_aging_items[0]
                    aging_queue.remove(aging_item)
                    save_item(aging_item, "current_aging.json", True)
                    save_aging_queue()
                elif DEBUG_PRINT:
                    _log.msg("Queue present but no eligible items.")

        if aging_item:
            _log.msg(f"Processing aging item\n{aging_item}")

            wait_before_loop, aging_item = process_aging_item(aging_item)

            if aging_item:
                aging_item = aging_enqueue(aging_item)
            if not wait_before_loop:
                continue

        if DEBUG_PRINT:
            _log.msg(f"Aging queue thread sleeping for {AGING_QUEUE_INTERVAL} min.")
        with aging_queue_condition:
            aging_queue_condition.wait(timeout=AGING_QUEUE_INTERVAL * 60)
