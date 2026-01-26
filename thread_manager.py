import threading

import fauxlogger as _log
from aging_queue_manager import process_queue as process_aging_queue
from decision_queue_manager import process_queue as process_decision_queue
from download_queue_manager import process_queue as process_download_queue

stop_event = threading.Event()
decision_queue_thread = threading.Thread()
download_queue_thread = threading.Thread()
aging_queue_thread = threading.Thread()


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


def startup(run_decision_queue: bool, run_aging_queue: bool, run_download_queue: bool):
    global decision_queue_thread
    global aging_queue_thread
    global download_queue_thread

    if run_decision_queue:
        start_decision_queue_manager()
    if run_aging_queue:
        start_aging_queue_manager()
    if run_download_queue:
        start_download_queue_manager()

    _log.msg("Thread init complete")


def shutdown():
    stop_event.set()
    stop_decision_queue_manager()
    stop_aging_queue_manager()
    stop_download_queue_manager()
