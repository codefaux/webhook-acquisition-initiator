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

SONARR_IN_PATH = os.getenv("SONARR_IN_PATH", "")
WAI_OUT_TEMP = os.getenv("WAI_OUT_TEMP")
WAI_OUT_PATH = os.getenv("WAI_OUT_PATH", "./output")
FLIP_FLOP_QUEUE = int(os.getenv("FLIP_FLOP_QUEUE", 0)) == 1
DEBUG_PRINT = int(os.getenv("DEBUG_PRINT", 0)) != 0
DEBUG_BREAK = int(os.getenv("DEBUG_BREAK", 0)) != 0

DOWNLOAD_QUEUE_FILE = os.path.join(DATA_DIR, "download_queue.json")
DOWNLOAD_QUEUE_INTERVAL = int(os.getenv("DOWNLOAD_QUEUE_INTERVAL", 5))

dl_queue_lock = threading.Lock()
dl_queue_condition = threading.Condition(lock=dl_queue_lock)
dl_queue = []
dl_item = None


def load_queue():
    global dl_queue
    dl_queue = []
    if os.path.exists(DOWNLOAD_QUEUE_FILE):
        with open(DOWNLOAD_QUEUE_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    dl_queue.extend(data)
            except json.JSONDecodeError:
                _log.msg("Failed to decode queue JSON; starting with empty queue.")


def save_queue():
    global dl_queue
    with open(DOWNLOAD_QUEUE_FILE, "w") as f:
        json.dump(dl_queue, f, indent=2)


def enqueue(item: dict):
    with dl_queue_condition:
        dl_queue.append(item)
        save_queue()


def dequeue(item: dict) -> bool:
    with dl_queue_condition:
        for i, q_item in enumerate(dl_queue):
            if q_item == item:
                del dl_queue[i]
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
    delete_item_file("current_download.json")

    return None


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


def process_item(item: dict | None) -> tuple[bool, dict | None]:
    if not item:
        return False, None

    item = download_item(item)

    if not item:
        return False, None

    item = rename_and_move_item(item)

    if not item:
        return False, None

    item = import_item(item)

    if not item:
        return False, None

    item = close_item(
        item,
        f"Item Sonarr Import result: {item.get("import_result", {}).get('status', "")}",
        "pass.json",
        subdir="history",
    )

    return True, item


def download_item(item: dict) -> dict | None:
    from ytdlp_interface import download_video

    download_filename = download_video(
        item.get("url", ""), WAI_OUT_TEMP or WAI_OUT_PATH
    )
    item["download_filename"] = download_filename

    if not download_filename:
        _ = close_item(
            item,
            "No file at download location. Aborting download queue thread. (API will still function.)",
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


def process_queue(stop_event: threading.Event):
    global dl_item
    global dl_queue

    if dl_item is None:
        dl_item = load_item("current_download.json")
    if dl_queue == []:
        load_queue()

    while not stop_event.is_set():
        with dl_queue_condition:
            while not dl_item and not dl_queue and not stop_event.is_set():
                _log.msg(
                    f"No current item. No queue. Sleeping for at most {DOWNLOAD_QUEUE_INTERVAL} min."
                )
                dl_queue_condition.wait(timeout=DOWNLOAD_QUEUE_INTERVAL * 60)

            if dl_queue and not dl_item:
                dl_item = dl_queue.pop(0)
                if FLIP_FLOP_QUEUE:
                    _log.msg("Inverting queue")
                    dl_queue.reverse()
                save_item(dl_item, "current_download.json", True)
                save_item(dl_item, "all_processed.json", subdir="history")
                save_queue()

        if dl_item:
            wait_before_loop, dl_item = process_item(dl_item)

            if not wait_before_loop:
                continue

            _log.msg(f"Queue thread sleeping for {DOWNLOAD_QUEUE_INTERVAL} min.")
            with dl_queue_condition:
                dl_queue_condition.wait(timeout=DOWNLOAD_QUEUE_INTERVAL * 60)
