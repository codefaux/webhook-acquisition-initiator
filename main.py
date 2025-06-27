# main.py

import os
import signal
import threading
import time

import logger as _log
import uvicorn
from aging_queue_manager import process_aging_queue
from queue_manager import process_queue
from server import fastapi
from sonarr_api import validate_sonarr_config

# Load configuration from environment variables
DATA_DIR = os.getenv("DATA_DIR") or "./data"
SONARR_URL = os.getenv("SONARR_URL")
API_KEY = os.getenv("SONARR_API")
SONARR_IN_PATH = os.getenv("SONARR_IN_PATH")
RUN_DOWNLOAD_QUEUE = int(os.getenv("RUN_DOWNLOAD_QUEUE", 1)) == 1
RUN_AGING_QUEUE = int(os.getenv("RUN_AGING_QUEUE", 1)) == 1

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


def start_queue_processor():
    queue_thread = threading.Thread(
        target=process_queue, args=(stop_event,), daemon=True
    )
    queue_thread.start()
    return queue_thread


def start_aging_queue_processor():
    aging_queue_thread = threading.Thread(
        target=process_aging_queue, args=(stop_event,), daemon=True
    )
    aging_queue_thread.start()
    return aging_queue_thread


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)

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

    aging_queue_thread = (
        start_aging_queue_processor() if RUN_AGING_QUEUE else threading.Thread()
    )
    queue_thread = start_queue_processor() if RUN_DOWNLOAD_QUEUE else threading.Thread()

    try:
        uvicorn.run(fastapi, host="0.0.0.0", port=8000)
    finally:
        stop_event.set()
        if RUN_AGING_QUEUE:
            queue_thread.join()
        if RUN_DOWNLOAD_QUEUE:
            aging_queue_thread.join()

        _log.msg("Shutdown complete.")
