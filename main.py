# main.py

import os
import signal
import time

import fauxlogger as _log
import thread_manager
import uvicorn
from cfsonarr import validate_sonarr_config
from config import Config
from server import fastapi

CONFIG_FILE = os.getenv("WAI_CONFIG_FILE", "./conf/wai.toml")

config = Config()


if __name__ == "__main__":
    os.makedirs(config.wai.conf_dir, exist_ok=True)
    os.makedirs(config.wai.data_dir, exist_ok=True)

    _log.msg(f"Config: {CONFIG_FILE}")

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
        signal.signal(sig, thread_manager.handle_exit_signal)

    try:
        thread_manager.startup()
        uvicorn.run(fastapi, host="0.0.0.0", port=8000)
    finally:
        thread_manager.shutdown()

        _log.msg("Shutdown complete.")
