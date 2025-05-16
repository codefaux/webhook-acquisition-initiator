import os
import time

import logger as _log
import yt_dlp
import yt_dlp.options

DATA_DIR = os.getenv("DATA_DIR") or "./data"
netrc_file = os.path.join(DATA_DIR, "netrc")
ytdlpconf_file = os.path.join(DATA_DIR, "yt-dlp.conf")
using_netrc = os.path.exists(netrc_file)
using_ytdlpconf = os.path.exists(ytdlpconf_file)

last_print_time = 0
last_print_percent = 0


class YTDLQuietLogger:
    def debug(self, msg):
        pass  # Suppress all debug messages (includes status prints)

    def info(self, msg):
        pass  # Suppress all info messages

    def warning(self, msg):
        pass  # Suppress all warning messages

    def error(self, msg):
        print(msg)  # Allow errors to pass through


def format_bytes(size: int | float) -> str:
    power = 1024
    n = 0
    units = ["B", "KB", "MB", "GB"]

    while size >= power and n < len(units) - 1:
        size /= power
        n += 1

    return f"{size:.2f} {units[n]}"


create_parser = yt_dlp.options.create_parser


def parse_patched_options(opts: list) -> yt_dlp.ParsedOptions:
    patched_parser = create_parser()
    patched_parser.defaults.update(
        {
            "ignoreerrors": False,
        }
    )
    yt_dlp.options.create_parser = lambda: patched_parser
    try:
        return yt_dlp.parse_options(opts)
    finally:
        yt_dlp.options.create_parser = create_parser


default_ytdlp_opts = parse_patched_options([]).ydl_opts


def cli_to_api(opts: list, cli_defaults: bool = False):
    new_opts = (yt_dlp.parse_options if cli_defaults else parse_patched_options)(
        opts
    ).ydl_opts

    diff = {k: v for k, v in new_opts.items() if default_ytdlp_opts[k] != v}
    if "postprocessors" in diff:
        diff["postprocessors"] = [
            pp
            for pp in diff["postprocessors"]
            if pp not in default_ytdlp_opts["postprocessors"]
        ]
    return diff


def download_video(video_url: str, target_folder: str) -> str | None:
    """Download a video using the yt_dlp Python API into the target folder.
    Returns the destination file path or None on failure.
    """
    from util import ensure_dir

    ensure_dir(target_folder)

    ydl_opts = {
        "progress_hooks": [download_progress_hook],
        "noplaylist": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "writeinfojson": True,
        "logger": YTDLQuietLogger(),
        "ratelimit": 5_000_000,
        "concurrent_fragments": 3,
    }

    if using_ytdlpconf:
        ydl_opts.update(cli_to_api(["--config-locations", f"{DATA_DIR}"]))
    if using_netrc:
        ydl_opts["usenetrc"] = True
        ydl_opts["netrc_location"] = netrc_file

    ydl_opts["outtmpl"] = os.path.join(target_folder, "%(title)s.%(ext)s")

    _log.msg(
        f"{_log._GREEN}Starting download of '{video_url}' "
        f"- {_log._YELLOW}netrc {_log._GREEN if using_netrc else _log._RED}{using_netrc}"
        f", {_log._YELLOW}yt-dlp.conf {_log._GREEN if using_ytdlpconf else _log._RED}{using_ytdlpconf}{_log._RESET}"
    )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=True)
            output_file = ydl.prepare_filename(info_dict)
            if not os.path.isfile(output_file):
                _log.msg(
                    f"{_log._RED}Download failed or file not found: {_log._RESET} {output_file}"
                )
                return None
            return output_file
    except Exception as e:
        _log.msg(f"{_log._RED}yt-dlp error during download:{_log._RESET} {str(e)}")
        return None


def handle_downloading(status: dict):
    global last_print_time, last_print_percent
    current_time = time.time()
    percent = status.get("_percent", 0)
    time_diff = current_time - last_print_time
    pct_diff = percent - last_print_percent

    if (time_diff >= 60) or (pct_diff >= 25):
        midstr = ""
        if last_print_time > 5:
            speed = format_bytes(status.get("speed", 0) or 0)
            eta = status.get("eta", 0) or 0
            midstr = f" @ {speed}/s, ETA: {eta}s{_log._RESET}"

        total_bytes = (
            status.get("total_bytes_estimate") or status.get("total_bytes") or 0
        )
        _log.msg(
            f"{_log._YELLOW}Downloading: {percent:.2f}% of {format_bytes(total_bytes)}"
            f"{midstr}\n{_log._BLUE}filename:{_log._RESET} {status.get('filename', '')}",
            2,
        )

        # Update global state
        last_print_time = current_time
        last_print_percent = int(percent / 25) * 25


def handle_finished(status: dict):
    global last_print_time, last_print_percent
    last_print_time = 0
    last_print_percent = 0
    total_bytes = format_bytes(status.get("total_bytes", 0) or 0)
    elapsed = int(status.get("elapsed", 0) + 0.4999) or 0
    speed = format_bytes(status.get("speed", 0) or 0)

    _log.msg(
        f"{_log._GREEN}Download complete. {total_bytes} in {elapsed}s ({speed}/s). "
        f"Finalizing file...{_log._RESET}\n"
        f"{_log._BLUE}filename:{_log._RESET} {status.get('filename', '')}",
        2,
    )


def handle_error(status: dict):
    _log.msg(
        f"status: {_log._RED}error{_log._RESET}\n"
        f"\t{_log._YELLOW}{status}{_log._RESET}",
        2,
    )


def download_progress_hook(status: dict):
    handlers = {
        "downloading": handle_downloading,
        "finished": handle_finished,
        "error": handle_error,
    }
    handler = handlers.get(status["status"])
    if handler:
        handler(status)
