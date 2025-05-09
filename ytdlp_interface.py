import os
import sys
import subprocess


# ANSI color codes
ANSI_BLUE = '\033[94m'
ANSI_YELLOW = '\033[93m'
ANSI_GREEN = '\033[92m'
ANSI_RED = '\033[91m'
ANSI_GREY = '\033[90m'
ANSI_RESET = '\033[0m'

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

    print(f"{ANSI_GREEN}Starting download of '{video_url}' - {ANSI_YELLOW}netrc {ANSI_GREEN if using_netrc else ANSI_RED}{using_netrc}, {ANSI_YELLOW}yt-dlp.conf {ANSI_GREEN if using_ytdlpconf else ANSI_RED}{using_ytdlpconf}{ANSI_RESET}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"{ANSI_RED}yt-dlp error during download:{ANSI_RESET} {result.stderr.strip()}")
        return None

    output = result.stdout.strip()
    if not output or not os.path.isfile(output):
        print(f"{ANSI_RED}Download failed or file not found:{ANSI_RESET} {output}")
        return None

    return output
