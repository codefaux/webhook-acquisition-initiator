# queue_manager.py

import errno
import json
import os
import shutil
import sys
import threading
import uuid

import fauxlogger as _log
from util import delete_item_file, load_item, save_item

DATA_DIR = os.getenv("DATA_DIR", "./data")

AGING_RIPENESS_PER_DAY = int(os.getenv("AGING_RIPENESS_PER_DAY", 4))
SONARR_IN_PATH = os.getenv("SONARR_IN_PATH", "")
WAI_OUT_TEMP = os.getenv("WAI_OUT_TEMP")
WAI_OUT_PATH = os.getenv("WAI_OUT_PATH", "./output")
HONOR_UNMON_SERIES = int(os.getenv("HONOR_UNMON_SERIES", 1)) == 1
HONOR_UNMON_EPS = int(os.getenv("HONOR_UNMON_EPS", 1)) == 1
OVERWRITE_EPS = int(os.getenv("OVERWRITE_EPS", 0)) == 1
FLIP_FLOP_QUEUE = int(os.getenv("FLIP_FLOP_QUEUE", 0)) == 1
DEBUG_PRINT = int(os.getenv("DEBUG_PRINT", 0)) != 0
DEBUG_BREAK = int(os.getenv("DEBUG_BREAK", 0)) != 0
DEBUG_DECISIONS = int(os.getenv("DEBUG_DECISIONS", 0))

QUEUE_FILE = os.path.join(DATA_DIR, "queue.json")
QUEUE_INTERVAL = int(os.getenv("QUEUE_INTERVAL", 5))
queue_lock = threading.Lock()
queue_condition = threading.Condition(lock=queue_lock)
queue = []
item = None


def load_queue():
    global queue
    queue = []
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    queue.extend(data)
            except json.JSONDecodeError:
                _log.msg("Failed to decode queue JSON; starting with empty queue.")


def save_queue():
    global queue
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def enqueue(item: dict):
    with queue_condition:
        queue.append(item)
        save_queue()
        # queue_condition.notify()
        # TODO : VERIFY : Disable immediate queue dispatch bypassing queue timer!


def dequeue(item: dict) -> bool:
    with queue_condition:
        for i, q_item in enumerate(queue):
            if q_item == item:
                del queue[i]
                save_queue()

                return True
        return False


def close_item(
    item: dict,
    message: str,
    filename: str | None,
    stack_offset: int = 2,
    subdir: str = "",
) -> dict | None:
    if DEBUG_BREAK:
        breakpoint()
    _log.msg(message, stack_offset)
    if filename:
        save_item(item, filename, subdir=subdir)
    delete_item_file("current.json")

    return None


def diagnose_show_score(item: dict) -> dict | None:
    # ...? resolution: manual intervention queue
    if DEBUG_BREAK:
        breakpoint()

    return close_item(
        item,
        f"Series match score not high enough. ({item["title_result"]["score"]} < 70)  Aborting.",
        "series_score.json",
        subdir="history",
    )


def diagnose_episode_score(item: dict) -> dict | None:
    from aging_queue_manager import aging_enqueue
    from util import get_new_ripeness

    # airdate; issue: too new, Sonarr metadata not updated?
    #          resolution: refresh Sonarr series data, requeue?
    # tokens too generic? resolution: manual intervention queue
    _log.msg(
        f"Episode match score not high enough. ({item["episode_result"]["score"]} < 70)\n\tDiagnosing.",
        2,
    )

    ripeness = get_new_ripeness(item)
    if DEBUG_BREAK:
        breakpoint()

    if ripeness < AGING_RIPENESS_PER_DAY * 3:
        aging_enqueue(item)
        return close_item(item, f"Ripeness {ripeness}: Requeue to aging queue", None)

    else:
        _log.msg(f"Ripeness {ripeness}: Item should be old enough for data")

    return close_item(
        item,
        "Moving to manual intervention queue.",
        "manual_intervention.json",
        subdir="history",
    )


def match_and_check(item: dict) -> dict | None:
    from cfsonarrmatcher import (extract_episode_hint,
                                 match_title_to_sonarr_episode,
                                 match_title_to_sonarr_show)
    from pyarr import SonarrAPI

    sonarr = SonarrAPI(os.getenv("SONARR_URL"), os.getenv("SONARR_API"))

    _log.msg(
        f"Processing item:\n"
        f"\t{_log._GREEN}creator:{_log._RESET} {item.get('creator', '')}"
        f"\t{_log._GREEN}title:{_log._RESET} {item.get('title', '')}\n"
        f"\t{_log._GREEN}datecode:{_log._RESET} {item.get('datecode', '')}"
        f"\t{_log._GREEN}url:{_log._RESET} {item.get('url', '')}"
    )

    show_titles = []
    id_is_monitored = {}

    for _s in sonarr.get_series():
        show_titles.append((_s["title"], _s["id"]))
        id_is_monitored[_s["id"]] = _s["monitored"]

    candidate_series_ids = []
    matched_id = 0

    main_title = f"{item.get('creator', '')} :: {item.get('title', '')}"

    s_hint, e_hint, substr = extract_episode_hint(main_title)
    _log.msg(f"s_hint: {s_hint}\ne_hint: {e_hint}\nsubstr: {substr}")

    title_result = match_title_to_sonarr_show(main_title, show_titles)
    item["title_result"] = title_result
    _log.msg(
        f"Match result: title -> show\n"
        f"\t{_log._YELLOW}input:{_log._RESET} '{main_title}'\n"
        f"\t{_log._BLUE if title_result.get('score', 0) >= 70 else _log._RED}score:{_log._RESET} {title_result.get('score', 0)}"
        f"\t{_log._GREEN}matched show:{_log._RESET} '{title_result.get('matched_show')}'"
        f" {_log._YELLOW}(id:{title_result.get('matched_id')}){_log._RESET}\n"
        f"\t{_log._YELLOW}reasons:{_log._RESET} {title_result.get('reason', '')}"
    )

    if title_result["score"] >= 80:
        candidate_series_ids.append(title_result["matched_id"])
        matched_id = title_result.get("matched_id")
    else:
        _log.msg(f"Series title match {_log._RED}not good enough.{_log._RESET}")

    sonarr_relevant_tags = [
        sonarr.get_tag_detail(_tag.get("id"))
        for _tag in sonarr.get_tag()
        if _tag.get("label").startswith("wai-")
    ]
    sonarr_relevant_tags = {
        _tag["label"].removeprefix("wai-"): _tag["seriesIds"]
        for _tag in sonarr_relevant_tags
        if _tag["label"] == f"wai-{item.get("creator", "").lower()}"
    }

    for series_ids in sonarr_relevant_tags.values():
        for series_id in series_ids:
            if not HONOR_UNMON_SERIES or (
                HONOR_UNMON_SERIES and id_is_monitored.get(title_result["matched_id"])
            ):
                if series_id != matched_id:
                    _log.msg(f"Add candidate series ID by tag: {series_id}")
                    candidate_series_ids.append(series_id)

    if len(candidate_series_ids) < 1:
        return diagnose_show_score(item)

    show_data = []
    episode_result = {}

    for candidate_series_id in candidate_series_ids:
        _series_name = sonarr.get_series(candidate_series_id, {}).get("title", "")
        _log.msg(
            f"Scan episodes of candidate series: {candidate_series_id} ({_series_name})"
        )

        for _ep in sonarr.get_episode(candidate_series_id, True):
            if HONOR_UNMON_EPS and not _ep["monitored"]:
                continue

            _ep["series"] = _series_name
            show_data.append(
                {
                    "has_file": _ep["hasFile"],
                    "series": _ep["series"],
                    "series_id": _ep["seriesId"],
                    "season": _ep["seasonNumber"],
                    "episode": _ep["episodeNumber"],
                    "episode_id": _ep["id"],
                    "title": _ep["title"],
                    "air_date": _ep.get("airDate", ""),
                    "air_date_utc": _ep.get("airDateUtc", ""),
                }
            )

    episode_result = match_title_to_sonarr_episode(
        main_title,
        item.get("datecode", ""),
        show_data,
        None,
        title_result.get("matched_show", ""),
    )
    item["episode_result"] = episode_result
    _log.msg(
        f"Match result: title -> episode:\n"
        f"\t{_log._YELLOW}input:{_log._RESET} '{main_title}'\n"
        f"\t{_log._BLUE}series:{_log._RESET} {episode_result.get('matched_show', '')}\n"
        f"\t{_log._GREEN}season:{_log._RESET} {episode_result.get('season', 0)}"
        f"\t{_log._GREEN}episode:{_log._RESET} {episode_result.get('episode')}"
        f"\t{_log._GREEN}title:{_log._RESET} '{episode_result.get('episode_orig_title', '')}'\n"
        f"\t{_log._BLUE if episode_result.get('score', 0) >= 70 else _log._RED}score:{_log._RESET} {episode_result.get('score', 0)}\n"
        f"\t{_log._YELLOW}reasons:{_log._RESET} {episode_result.get('reason', '')}"
    )

    if episode_result["score"] < 70:
        return diagnose_episode_score(item)

    if not OVERWRITE_EPS and episode_result["full_match"].get("has_file"):
        if episode_result["score"] < DEBUG_DECISIONS:
            breakpoint()

        return close_item(
            item,
            "Episode already has file. Aborting.",
            "episode_has_file.json",
            subdir="history",
        )

    if episode_result["score"] < DEBUG_DECISIONS:
        breakpoint()

    return item


def safe_move(src, dst):
    """Rename a file from ``src`` to ``dst``.

    *   Moves must be atomic.  ``shutil.move()`` is not atomic.
        Note that multiple threads may try to write to the cache at once,
        so atomicity is required to ensure the serving on one thread doesn't
        pick up a partially saved image from another thread.

    *   Moves must work across filesystems.  Often temp directories and the
        cache directories live on different filesystems.  ``os.rename()`` can
        throw errors if run across filesystems.

    So we try ``os.rename()``, but if we detect a cross-filesystem copy, we
    switch to ``shutil.move()`` with some wrappers to make it atomic.
    """
    try:
        os.rename(src, dst)
    except OSError as err:

        if err.errno == errno.EXDEV:
            # Generate a unique ID, and copy `<src>` to the target directory
            # with a temporary name `<dst>.<ID>.tmp`.  Because we're copying
            # across a filesystem boundary, this initial copy may not be
            # atomic.  We intersperse a random UUID so if different processes
            # are copying into `<dst>`, they don't overlap in their tmp copies.
            copy_id = uuid.uuid4()
            tmp_dst = "%s.%s.tmp" % (dst, copy_id)
            shutil.copyfile(src, tmp_dst)

            # Then do an atomic rename onto the new name, and clean up the
            # source image.
            os.rename(tmp_dst, dst)
            os.unlink(src)
        else:
            raise


def download_item(item: dict) -> dict | None:
    from ytdlp_interface import download_video

    download_filename = download_video(
        item.get("url", ""), WAI_OUT_TEMP or WAI_OUT_PATH
    )
    item["download_filename"] = download_filename

    if not download_filename:
        _ = close_item(
            item,
            "No file at download location. Aborting main queue thread. (API will still function.)",
            "download_fail.json",
            subdir="history",
        )
        sys.exit(1)  # error condition

    _log.msg(f"Download returned: {download_filename}")

    return item


def rename_and_move_item(item: dict) -> dict | None:
    from util import tag_filename

    tag_filepath = tag_filename(item.get("download_filename", ""))
    file_name = os.path.basename(tag_filepath)

    if WAI_OUT_TEMP:  # NOT WORKING ?
        safe_move(
            tag_filepath,
            os.path.join(os.path.abspath(WAI_OUT_PATH), file_name),
        )
        _log.msg(f"Moved: {tag_filepath} \n\t-> To: {os.path.abspath(WAI_OUT_PATH)}")
        safe_move(
            tag_filepath.replace(".mkv", ".info.json"),
            os.path.join(
                os.path.abspath(WAI_OUT_PATH), file_name.replace(".mkv", ".info.json")
            ),
        )
        _log.msg(
            f"Moved: {tag_filepath.replace(".mkv", ".info.json")} \n\t-> To: {os.path.abspath(WAI_OUT_PATH)}"
        )

    item["file_name"] = file_name

    return item


def import_item(item: dict) -> dict | None:
    from cfsonarr import import_downloaded_episode

    _id = item["episode_result"].get("matched_series_id")
    _season = item["episode_result"].get("season")
    _episode = item["episode_result"].get("episode")
    _filename = item["file_name"]
    _folder = SONARR_IN_PATH

    import_result = import_downloaded_episode(
        _id, _season, _episode, _filename, _folder
    )

    item["import_result"] = import_result

    return item


def process_item(item: dict | None) -> tuple[bool, dict | None]:
    from download_queue_manager import enqueue as enqueue_download

    if not item:
        return False, None

    item = match_and_check(item)

    if not item:
        return False, None

    if DEBUG_BREAK:
        breakpoint()

    enqueue_download(item)

    item = close_item(
        item, "Item queued for download.", "download_enqueue.json", subdir="history"
    )

    return False, item


def process_queue(stop_event: threading.Event):
    global item
    global queue

    if item is None:
        item = load_item("current.json")
    if queue == []:
        load_queue()

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
                save_item(item, "all_processed.json", subdir="history")
                save_queue()

        if item:
            wait_before_loop, item = process_item(item)

            if not wait_before_loop:
                continue

            _log.msg(f"Queue thread sleeping for {QUEUE_INTERVAL} min.")
            with queue_condition:
                queue_condition.wait(timeout=QUEUE_INTERVAL * 60)
