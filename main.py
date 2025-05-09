# main.py

import uvicorn
import threading
import signal
import os

import logger as _log
from server import fastapi
from queue_manager import process_queue, load_queue
from sonarr_api import validate_sonarr_config

DATA_DIR = os.getenv("DATA_DIR")

stop_event = threading.Event()

def handle_exit_signal(signum, frame):
    _log.msg(f"\nCaught signal {signum}, shutting down gracefully...")
    stop_event.set()

def start_background_processor():
    from queue_manager import queue_condition
    processor_thread = threading.Thread(target=process_queue, args=(stop_event,), daemon=True)
    processor_thread.start()
    return processor_thread

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)

    if not validate_sonarr_config():
        exit("Sonarr connection failed. Please check your configuration.")
        
    load_queue()

    # Register graceful shutdown signals
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, handle_exit_signal)

    processor_thread = start_background_processor()

    try:
        uvicorn.run(fastapi, host="0.0.0.0", port=8000)
    finally:
        stop_event.set()
        processor_thread.join()
        from queue_manager import save_queue
        save_queue()
        _log.msg("Shutdown complete.")
