# manual_intervention_manager.py

import json
import os
import threading
from typing import Callable, Final
from uuid import UUID, uuid4

import fauxlogger as _log

DATA_DIR: str = os.getenv("DATA_DIR") or "./data"

DEBUG_PRINT: Final[bool] = int(os.getenv("DEBUG_PRINT", 0)) != 0
DEBUG_BREAK: Final[bool] = int(os.getenv("DEBUG_BREAK", 0)) != 0

MI_QUEUE_FILE: Final[str] = os.path.join(DATA_DIR, "manual_intervention.json")

mi_queue_lock: Final = threading.Lock()
mi_queue_notify_event: Final = threading.Event()

type mi_dict_type = dict[UUID, dict[str, int | str]]
type mi_tuple_type = tuple[UUID, dict[str, int | str]]
type mi_tuple_type_n = mi_tuple_type | None

mi_queue: mi_dict_type = {}
mi_current: mi_tuple_type_n = None
mi_notify_listeners: list[Callable[[mi_tuple_type], None]] = []


def load_mi_queue():
    global mi_queue
    mi_queue = {}
    if os.path.exists(MI_QUEUE_FILE):
        with open(MI_QUEUE_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    mi_queue.update(data)
            except json.JSONDecodeError:
                _log.msg(
                    "Failed to decode queue JSON; starting with empty manual intervention queue."
                )


def save_mi_queue():
    global mi_queue
    with open(MI_QUEUE_FILE, "w") as f:
        json.dump(mi_queue, f, indent=2)


def enqueue(mi_data: dict[str, int | str]) -> None:
    global mi_current
    if len(mi_queue) == 0:
        load_mi_queue()

    _uuid = uuid4()

    with mi_queue_lock:
        mi_queue[_uuid] = mi_data
        save_mi_queue()
    mi_current = (_uuid, mi_data)
    mi_queue_notify_event.set()

    return None


def add_notify_listener(callback: Callable[[mi_tuple_type], None]) -> None:
    if callback not in mi_notify_listeners:
        mi_notify_listeners.append(callback)


def remove_notify_listener(callback: Callable[[mi_tuple_type], None]) -> None:
    try:
        mi_notify_listeners.remove(callback)
    except ValueError:
        pass


def get_mi_queue():
    return mi_queue


def mi_thread_worker(stop_event: threading.Event):
    while not stop_event.is_set():
        if len(mi_queue) == 0:
            load_mi_queue()

        if mi_queue_notify_event.wait(timeout=5):
            mi_queue_notify_event.clear()

            for _listener in mi_notify_listeners:
                try:
                    if mi_current:
                        _listener(mi_current)
                except Exception:
                    pass
