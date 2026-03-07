import threading

import fauxlogger as _log
from aging_queue_manager import process_queue as process_aging_queue
from config import Config
from decision_queue_manager import process_queue as process_decision_queue
from download_queue_manager import process_queue as process_download_queue
from manual_intervention_manager import mi_thread_worker as run_mi_thread
from telegram_bot import telegram_bot_thread as run_telegram_thread

config = Config()

stop_event = threading.Event()
decision_queue_thread = threading.Thread()
download_queue_thread = threading.Thread()
aging_queue_thread = threading.Thread()
mi_thread = threading.Thread()
telegram_thread = threading.Thread()


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
    if config.decision_queue.run:
        _log.msg("Starting Decision Queue Manager")
        start_decision_queue_manager()
    if config.aging_queue.run:
        _log.msg("Starting Aging Queue Manager")
        start_aging_queue_manager()
    if config.download_queue.run:
        _log.msg("Starting Download Queue Manager")
        start_download_queue_manager()
    if config.manual_intervention.run:
        _log.msg("Starting Manual Intervention Thread")
        start_mi_thread()

        if config.telegram.run:
            _log.msg("Starting Telegram Bot")
            start_telegram_bot()

    _log.msg("Thread init complete")


def shutdown():
    stop_event.set()
    stop_decision_queue_manager()
    stop_aging_queue_manager()
    stop_download_queue_manager()
    stop_mi_thread()
    stop_telegram_bot()
