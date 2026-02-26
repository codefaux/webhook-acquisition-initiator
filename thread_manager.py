import os
import threading

import fauxlogger as _log
from aging_queue_manager import process_queue as process_aging_queue
from decision_queue_manager import process_queue as process_decision_queue
from download_queue_manager import process_queue as process_download_queue
from manual_intervention_manager import mi_thread_worker as run_mi_thread
from telegram_bot import telegram_bot_thread as run_telegram_thread

stop_event = threading.Event()
decision_queue_thread = threading.Thread()
download_queue_thread = threading.Thread()
aging_queue_thread = threading.Thread()
mi_thread = threading.Thread()
telegram_thread = threading.Thread()

RUN_DECISION_QUEUE = int(os.getenv("RUN_DECISION_QUEUE", 1)) == 1
RUN_AGING_QUEUE = int(os.getenv("RUN_AGING_QUEUE", 1)) == 1
RUN_DOWNLOAD_QUEUE = int(os.getenv("RUN_DOWNLOAD_QUEUE", 1)) == 1
RUN_MI_THREAD = int(os.getenv("RUN_MI_THREAD", 1)) == 1
RUN_TELEGRAM_BOT = RUN_MI_THREAD and (int(os.getenv("RUN_TELEGRAM_BOT", 1)) == 1)


def handle_exit_signal(signum, frame):
    _log.msg(f"\nCaught signal {signum}, shutting down gracefully...")
    stop_event.set()


def start_decision_queue_manager():
    global decision_queue_thread

    if not decision_queue_thread.ident or not decision_queue_thread.native_id:
        decision_queue_thread = threading.Thread(
            target=process_decision_queue,
            args=(stop_event,),
            daemon=True,
            name="decision_queue",
        )
        decision_queue_thread.start()

    return


def start_download_queue_manager():
    global download_queue_thread

    if not download_queue_thread.ident or not download_queue_thread.native_id:
        download_queue_thread = threading.Thread(
            target=process_download_queue,
            args=(stop_event,),
            daemon=True,
            name="download_queue",
        )
        download_queue_thread.start()

    return


def start_aging_queue_manager():
    global aging_queue_thread

    if not aging_queue_thread.ident or not aging_queue_thread.native_id:
        aging_queue_thread = threading.Thread(
            target=process_aging_queue,
            args=(stop_event,),
            daemon=True,
            name="aging_queue",
        )
        aging_queue_thread.start()

    return


def start_mi_thread():
    global mi_thread

    if not mi_thread.ident or not mi_thread.native_id:
        mi_thread = threading.Thread(
            target=run_mi_thread,
            args=(stop_event,),
            daemon=True,
            name="manual_intervention",
        )
        mi_thread.start()

    return


def start_telegram_bot():
    global telegram_thread

    if not mi_thread.ident or not mi_thread.native_id:
        return

    if not telegram_thread.ident or not telegram_thread.native_id:
        telegram_thread = threading.Thread(
            target=run_telegram_thread,
            args=(stop_event,),
            daemon=True,
            name="telegram_bot",
        )
        telegram_thread.start()

    return


def stop_decision_queue_manager():
    global decision_queue_thread

    decision_queue_thread.join()
    decision_queue_thread = threading.Thread()


def stop_aging_queue_manager():
    global aging_queue_thread

    aging_queue_thread.join()
    aging_queue_thread = threading.Thread()


def stop_download_queue_manager():
    global download_queue_thread

    download_queue_thread.join()
    download_queue_thread = threading.Thread()


def stop_telegram_bot():
    global telegram_thread

    telegram_thread.join()
    telegram_thread = threading.Thread()
    pass


def stop_mi_thread():
    global mi_thread

    stop_telegram_bot()

    mi_thread.join()
    mi_thread = threading.Thread()
    pass


def startup():
    if RUN_DECISION_QUEUE:
        start_decision_queue_manager()
    if RUN_AGING_QUEUE:
        start_aging_queue_manager()
    if RUN_DOWNLOAD_QUEUE:
        start_download_queue_manager()
    if RUN_MI_THREAD:
        start_mi_thread()

        if RUN_TELEGRAM_BOT:
            start_telegram_bot()

    _log.msg("Thread init complete")


def shutdown():
    stop_event.set()
    stop_decision_queue_manager()
    stop_aging_queue_manager()
    stop_download_queue_manager()
    stop_mi_thread()
    stop_telegram_bot()
