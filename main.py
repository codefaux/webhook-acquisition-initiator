# main.py

import os
import signal
import time

import fauxlogger as _log
import thread_manager
import uvicorn
from cfsonarr import validate_sonarr_config
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
        vardump: list[str] = ["Environment vars:"]
        vardump.extend(
            f"- {_log._BLUE}{varname}{_log._RESET}: {_log._GREEN}{os.getenv(varname)}{_log._RESET}"
            for varname in env_vars
        )
        _log.msg(vardump)

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
        thread_manager.startup(RUN_DECISION_QUEUE, RUN_AGING_QUEUE, RUN_DOWNLOAD_QUEUE)
        uvicorn.run(fastapi, host="0.0.0.0", port=8000)
    finally:
        thread_manager.shutdown()

        _log.msg("Shutdown complete.")
