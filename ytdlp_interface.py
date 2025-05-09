import os
import subprocess

import logger as _log

DATA_DIR = os.getenv("DATA_DIR")
netrc_file = os.path.join(DATA_DIR, "netrc")
ytdlpconf_file = os.path.join(DATA_DIR, "yt-dlp.conf")
using_netrc = os.path.exists(netrc_file)
using_ytdlpconf = os.path.exists(ytdlpconf_file)

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def download_video(video_url, target_folder):
    """Download a video using yt-dlp into the target folder.
    Returns the destination file path or None on failure.
    """
    ensure_dir(target_folder)
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--no-check-certificate",
        "--write-info-json",
        "--print", "after_move:filepath",
        "-P", target_folder,
        video_url
    ]

    if using_ytdlpconf:
        cmd[1:1] = ["--config-location", ytdlpconf_file]
    if using_netrc:
        cmd[1:1] = ["--netrc", "--netrc-location", netrc_file]

    _log.msg(f"{_log._GREEN}Starting download of '{video_url}' - {_log._YELLOW}netrc {_log._GREEN if using_netrc else _log._RED}{using_netrc}, {_log._YELLOW}yt-dlp.conf {_log._GREEN if using_ytdlpconf else _log._RED}{using_ytdlpconf}{_log._RESET}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        _log.msg(f"{_log._RED}yt-dlp error during download:{_log._RESET} {result.stderr.strip()}")
        return None

    output = result.stdout.strip()
    if not output or not os.path.isfile(output):
        _log.msg(f"{_log._RED}Download failed or file not found:{_log._RESET} {output}")
        return None

    return output
