import os
import sys
import time
import yt_dlp
import logger as _log

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
    units = ['B', 'KB', 'MB', 'GB']
    
    while size >= power and n < len(units) - 1:
        size /= power
        n += 1
    
    return f"{size:.2f} {units[n]}"

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def download_video(video_url, target_folder):
    """Download a video using the yt_dlp Python API into the target folder.
    Returns the destination file path or None on failure.
    """
    ensure_dir(target_folder)
    ydl_opts = {
        'outtmpl': os.path.join(target_folder, '%(title)s.%(ext)s'),
        'progress_hooks': [download_progress_hook],
        'noplaylist': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'writeinfojson': True,
        'logger': YTDLQuietLogger(),
        'ratelimit': 5_000_000,
        'concurrent_fragments': 3
    }

    if using_ytdlpconf:
        ydl_opts['config_location'] = ytdlpconf_file
    if using_netrc:
        ydl_opts['usenetrc'] = True
        ydl_opts['netrc_location'] = netrc_file

    _log.msg(f"{_log._GREEN}Starting download of '{video_url}' - {_log._YELLOW}netrc {_log._GREEN if using_netrc else _log._RED}{using_netrc}, {_log._YELLOW}yt-dlp.conf {_log._GREEN if using_ytdlpconf else _log._RED}{using_ytdlpconf}{_log._RESET}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=True)
            output_file = ydl.prepare_filename(info_dict)
            if not os.path.isfile(output_file):
                _log.msg(f"{_log._RED}Download failed or file not found: {_log._RESET} {output_file}")
                return None
            return output_file
    except Exception as e:
        _log.msg(f"{_log._RED}yt-dlp error during download:{_log._RESET} {str(e)}")
        return None

def download_progress_hook(status):
    global last_print_time, last_print_percent

    if status['status'] == 'downloading':
        current_time = time.time()
        percent = status.get('_percent', 0)
        if (current_time - last_print_time >= 60) or (percent - last_print_percent >= 25 ):
            speed = status.get('speed', 0)
            eta = status.get('eta', 0)
            _log.msg(f"{_log._YELLOW}Downloading: {percent:.2f}% @ {format_bytes(speed)}/s, ETA: {eta}s{_log._RESET}")
            last_print_time = current_time
            last_print_percent = int(percent/25) * 25
    elif status['status'] == 'finished':
        _log.msg(f"{_log._GREEN}Download complete. Moving file...{_log._RESET}")
