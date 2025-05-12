import os
import time

import logger as _log
import yt_dlp
import yt_dlp.options

DATA_DIR = os.getenv("DATA_DIR")
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


def format_bytes(size):
    power = 1024
    n = 0
    units = ["B", "KB", "MB", "GB"]

    while size >= power and n < len(units) - 1:
        size /= power
        n += 1

    return f"{size:.2f} {units[n]}"


def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


create_parser = yt_dlp.options.create_parser


def parse_patched_options(opts):
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


def cli_to_api(opts, cli_defaults=False):
    opts = (yt_dlp.parse_options if cli_defaults else parse_patched_options)(
        opts
    ).ydl_opts

    diff = {k: v for k, v in opts.items() if default_ytdlp_opts[k] != v}
    if "postprocessors" in diff:
        diff["postprocessors"] = [
            pp
            for pp in diff["postprocessors"]
            if pp not in default_ytdlp_opts["postprocessors"]
        ]
    return diff


def download_video(video_url, target_folder):
    """Download a video using the yt_dlp Python API into the target folder.
    Returns the destination file path or None on failure.
    """
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


def download_progress_hook(status):
    global last_print_time, last_print_percent

    if status["status"] == "downloading":
        current_time = time.time()
        percent = status.get("_percent", 0)
        time_diff = current_time - last_print_time
        pct_diff = percent - last_print_percent
        if (time_diff >= 60) or (pct_diff >= 25):
            midstr = (
                f" @ {format_bytes(status.get('speed', 0) or 0)}/s, ETA: {status.get('eta', 0) or 0}s{_log._RESET}"
                if last_print_time > 5
                else ""
            )
            use_total = (
                status.get("total_bytes_estimate", None)
                or status.get("total_bytes", None)
                or 0
            )
            _log.msg(
                f"{_log._YELLOW}Downloading: {percent:.2f}% of {format_bytes(use_total)}"
                f"{midstr}\n{_log._BLUE}filename:{_log._RESET} {status.get('filename', '')}"
            )
            last_print_time = current_time
            last_print_percent = int(percent / 25) * 25
    elif status["status"] == "finished":
        last_print_time = 0
        last_print_percent = 0
        _log.msg(
            f"{_log._GREEN}Download complete. "
            f"{format_bytes(status.get('total_bytes', 0) or 0)} "
            f"in {int(status.get('elapsed', 0)+0.4999) or 0}s "
            f"({format_bytes(status.get('speed', 0) or 0)}/s). "
            f"Finalizing file...{_log._RESET}\n"
            f"{_log._BLUE}filename:{_log._RESET} {status.get('filename', '')}"
        )
    elif status["status"] == "error":
        _log.msg(
            f"status: {_log._RED}error{_log._RESET}\n"
            f"\t{_log._YELLOW}{status}{_log._RESET}"
        )
    # else:
    #     _log.msg(f"status: {status}")
