# main.py

import os
import signal
import threading
import time

import fauxlogger as _log
import uvicorn
from aging_queue_manager import process_queue as process_aging_queue
from cfsonarr import validate_sonarr_config
from decision_queue_manager import process_queue as process_decision_queue
from download_queue_manager import process_queue as process_download_queue
from server import fastapi

# Load configuration from environment variables
DATA_DIR = os.getenv("DATA_DIR") or "./data"
CONF_DIR = os.getenv("CONF_DIR") or "./conf"
SONARR_URL = os.getenv("SONARR_URL")
API_KEY = os.getenv("SONARR_API")
SONARR_IN_PATH = os.getenv("SONARR_IN_PATH")
RUN_DECISION_QUEUE = int(os.getenv("RUN_DECISION_QUEUE", 1)) == 1
RUN_AGING_QUEUE = int(os.getenv("RUN_AGING_QUEUE", 1)) == 1
RUN_DOWNLOAD_QUEUE = int(os.getenv("RUN_DOWNLOAD_QUEUE", 1)) == 1
DEBUG_PRINT = int(os.getenv("DEBUG_PRINT", 0)) == 1

if not SONARR_URL or not API_KEY:
    raise RuntimeError(
        "Both SONARR_URL and SONARR_API environment variables must be set."
    )

if not SONARR_IN_PATH:
    raise RuntimeError("SONARR_IN_PATH must be set.")

stop_event = threading.Event()


def handle_exit_signal(signum, frame):
    _log.msg(f"\nCaught signal {signum}, shutting down gracefully...")
    stop_event.set()


def start_decision_queue_processor():
    queue_thread = threading.Thread(
        target=process_decision_queue, args=(stop_event,), daemon=True
    )
    queue_thread.start()
    return queue_thread


def start_download_queue_processor():
    dl_queue_thread = threading.Thread(
        target=process_download_queue, args=(stop_event,), daemon=True
    )
    dl_queue_thread.start()
    return dl_queue_thread


def start_aging_queue_processor():
    aging_queue_thread = threading.Thread(
        target=process_aging_queue, args=(stop_event,), daemon=True
    )
    aging_queue_thread.start()
    return aging_queue_thread


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CONF_DIR, exist_ok=True)

    if DEBUG_PRINT:
        env_vars = [
            "SONARR_API",
            "RADARR_API",
            "SONARR_URL",
            "RADARR_URL",
            "SONARR_IN_PATH",
            "WAI_OUT_PATH",
            "WAI_OUT_TEMP",
            "DATA_DIR",
            "CONF_DIR",
            "FLIP_FLOP_QUEUE",
            "AGING_RIPENESS_PER_DAY",
            "DOWNLOAD_QUEUE_INTERVAL",
            "AGING_QUEUE_INTERVAL",
            "DECISION_QUEUE_INTERVAL",
            "OVERWRITE_EPS",
            "HONOR_UNMON_EPS",
            "HONOR_UNMON_SERIES",
            "RUN_AGING_QUEUE",
            "RUN_DOWNLOAD_QUEUE",
            "RUN_DECISION_QUEUE",
            "DEBUG_PRINT",
            "DEBUG_BREAK",
            "DEBUG_DECISIONS",
        ]
        for varname in env_vars:
            _log.msg(f"{varname}: {os.getenv(varname)} \n")

    retries = 0
    while retries < 5:
        if validate_sonarr_config():
            retries = 0
            break
        else:
            retries += 1
            _log.msg("Error: Sonarr connection failed. Retrying in 10 sec..")
            time.sleep(10)

    if retries:
        exit("Sonarr connection failed. Please check your configuration.")

    # Register graceful shutdown signals
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, handle_exit_signal)

    decision_queue_thread = (
        start_decision_queue_processor() if RUN_DECISION_QUEUE else threading.Thread()
    )
    aging_queue_thread = (
        start_aging_queue_processor() if RUN_AGING_QUEUE else threading.Thread()
    )
    download_queue_thread = (
        start_download_queue_processor() if RUN_DOWNLOAD_QUEUE else threading.Thread()
    )

    try:
        uvicorn.run(fastapi, host="0.0.0.0", port=8000)
    finally:
        stop_event.set()
        decision_queue_thread.join()
        aging_queue_thread.join()
        download_queue_thread.join()

        _log.msg("Shutdown complete.")
