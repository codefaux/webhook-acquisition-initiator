#!/usr/bin/env python

import os

import logger as _log
import requests

# Load configuration from environment variables
SONARR_URL = os.getenv("SONARR_URL")
API_KEY = os.getenv("SONARR_API")

if not SONARR_URL or not API_KEY:
    raise RuntimeError(
        "Both SONARR_URL and SONARR_API environment variables must be set."
    )

HEADERS = {"X-Api-Key": API_KEY}


def validate_sonarr_config() -> bool:
    """
    Validates the Sonarr URL and API key by checking the /api/v3/health endpoint.

    Args:
        sonarr_url (str): The base URL of the Sonarr instance.
        api_key (str): The API key for Sonarr.

    Returns:
        bool: True if configuration is valid, False otherwise.
    """
    url = f"{SONARR_URL.rstrip('/')}/api/v3/health"
    headers = {"X-Api-Key": API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            _log.msg("Sonarr configuration is valid.")
            return True
        else:
            _log.msg(
                f"Unexpected response status: {response.status_code}. Check URL and API key."
            )
            return False
    except requests.exceptions.RequestException as e:
        _log.msg(f"Failed to connect to Sonarr: {e}")
        return False


def get_all_series():
    """Returns a list of monitored show titles from Sonarr."""
    response = requests.get(f"{SONARR_URL.rstrip('/')}/api/v3/series", headers=HEADERS)
    response.raise_for_status()
    series_list = response.json()
    return [(s["title"], s["id"]) for s in series_list]


def get_monitored_series():
    """Returns a list of monitored show titles from Sonarr."""
    response = requests.get(f"{SONARR_URL.rstrip('/')}/api/v3/series", headers=HEADERS)
    response.raise_for_status()
    series_list = response.json()
    return [s["title"] for s in series_list if s.get("monitored", False)]


def is_monitored_series(series_id):
    """Returns a list of monitored show titles from Sonarr."""
    response = requests.get(f"{SONARR_URL.rstrip('/')}/api/v3/series", headers=HEADERS)
    response.raise_for_status()
    series_list = response.json()
    return any(s["id"] == series_id and s.get("monitored", True) for s in series_list)


def search_local_series(query):
    """Search for a show by title from locally added series only."""
    response = requests.get(f"{SONARR_URL}/api/v3/series", headers=HEADERS)
    response.raise_for_status()
    series_list = response.json()

    query_lower = query.lower()
    return [s for s in series_list if query_lower in s["title"].lower()]


def search_series(query):
    """Search for a show by title and return results."""
    response = requests.get(
        f"{SONARR_URL}/api/v3/series/lookup", params={"term": query}, headers=HEADERS
    )
    response.raise_for_status()
    return response.json()


def get_episodes(series_id):
    """Retrieve episodes for a given series ID."""
    response = requests.get(
        f"{SONARR_URL}/api/v3/episode", params={"seriesId": series_id}, headers=HEADERS
    )
    response.raise_for_status()
    return response.json()


def get_episode_data_for_shows(show_title, show_ids):
    """
    Accepts a list of show titles, queries Sonarr for their episodes,
    and returns structured episode data.
    """
    sonarr_data = []

    if isinstance(show_ids, int):
        show_ids = [show_ids]

    for show_id in show_ids:
        try:
            episodes = get_episodes(show_id)
        except Exception as e:
            _log.msg(f"Error fetching episodes for '{show_id}':\n\t{e}")
            continue

        for ep in episodes:
            sonarr_data.append(
                {
                    "series": show_title,
                    "season": ep["seasonNumber"],
                    "episode": ep["episodeNumber"],
                    "episode_id": ep["id"],
                    "title": ep["title"],
                    "air_date": ep.get("airDate", -1),
                }
            )

    return sonarr_data


def get_file_quality_and_language(file_path):
    """
    Fetches quality and language info for a specific file using Sonarr's ManualImport endpoint.

    Parameters:
        file_path (str): Full path to the file to match.

    Returns:
        dict: A dictionary with 'quality' and 'languages' keys from the matched file info.

    Raises:
        ValueError: If no matching file is found in the manual import results.
    """
    folder = os.path.dirname(file_path)

    response = requests.get(
        f"{SONARR_URL.rstrip('/')}/api/v3/manualimport",
        params={"folder": folder, "filterExistingFiles": "false"},
        headers=HEADERS,
    )
    response.raise_for_status()
    files = response.json()
    ret_quality = {}
    ret_languages = []

    for file_entry in files:
        if file_entry.get("path") == file_path:
            ret_quality = file_entry["quality"]
            ret_languages = file_entry["languages"]
            return ret_quality, ret_languages

    raise ValueError(f"No matching file found for path: {file_path}")


def get_sonarr_episode(series_id, season_number, episode_number):
    episodes = get_episodes(series_id)
    matching_ep = next(
        (
            ep
            for ep in episodes
            if ep["seasonNumber"] == season_number
            and ep["episodeNumber"] == episode_number
        ),
        None,
    )

    return matching_ep


def is_monitored_episode(series_id, season_number, episode_number):
    sonarr_episode = get_sonarr_episode(series_id, season_number, episode_number)
    return sonarr_episode.get("monitored", True)


def is_episode_file(series_id, season_number, episode_number):
    sonarr_episode = get_sonarr_episode(series_id, season_number, episode_number)
    return not sonarr_episode.get("episodeFileId", 0) == 0


def import_downloaded_episode(
    series_id, season_number, episode_number, file_name, sonarr_folder
):
    """
    Uses Sonarr's ManualImport API to import a downloaded episode.

    Parameters:
        show_title (str): Title of the series (must already exist in Sonarr).
        season_number (int): Season number.
        episode_number (int): Episode number.
        file_path (str): Full path to the downloaded video file.
        download_folder (str): Parent folder containing the downloaded file.
                               If not provided, it will be inferred from file_path.
    """

    if not sonarr_folder:
        return None

    matching_ep = get_sonarr_episode(series_id, season_number, episode_number)

    if not matching_ep:
        raise ValueError(
            f"Episode S{season_number:02}E{episode_number:02} not found for '{series_id}'"
        )

    file_path = os.path.join(sonarr_folder, file_name)

    quality_result, language_result = get_file_quality_and_language(file_path)

    payload = {
        "name": "manualImport",
        "files": [
            {
                "path": file_path,
                "seriesId": series_id,
                "episodeIds": [matching_ep["id"]],
                "releaseGroup": "cfwai",
                "quality": quality_result,
                "languages": language_result,
                "releaseType": "singleEpisode",
            }
        ],
        "importMode": "Move",  # Options: Move, Copy, HardLink
    }

    response = requests.post(
        f"{SONARR_URL.rstrip('/')}/api/v3/command", headers=HEADERS, json=payload
    )
    response.raise_for_status()
    return response.json()
