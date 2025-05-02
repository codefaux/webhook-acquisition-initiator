#/usr/bin/env python

import os
from matcher import match_title_to_sonarr_episode, match_title_to_sonarr_show
import requests
from collections import defaultdict


# Static titles array
titles = [
    ("4/27/25 1:01 PM", "Jet Lag: The Game :: Ep 4 — Schengen Showdown"),
    ("4/27/25 1:01 PM", "Jet Lag: The Game :: Ep 5 — Schengen Showdown"),
    ("4/27/25 1:01 PM", "Jet Lag: The Game :: Ep 6 — Schengen Showdown"),
    ("4/27/25 1:01 PM", "Jet Lag: The Game :: We Played Hide And Seek Across NYC"),
    ("4/27/25 1:01 PM", "First We Feast :: Saquon Barkley Hurdles Over Spicy Wings | Hot Ones"),
    ("4/27/25 1:01 PM", "First We Feast :: Will Forte Goes For a High Score While Eating Spicy Wings | Hot Ones"),
    ("4/27/25 1:01 PM", "GLITCH :: THE GASLIGHT DISTRICT: PILOT"),
    ("4/28/25 11:30 AM", "17 Pages :: 17 Pages — Official Trailer"),
    ("4/28/25 1:23 PM", "Vivziepop :: HELLUVA BOSS - MASTERMIND // S2: Episode 11"),
    ("4/28/25 1:23 PM", "Vivziepop :: HELLUVA BOSS - SINSMAS // S2: Episode 12 -FINALE"),
    ("4/28/25 1:31 PM", "Distractible Podcast :: Even More Broken News"),
    ("4/28/25 1:31 PM", "Distractible Podcast :: Wade Screws Up At 47 Minutes"),
    ("4/28/25 1:31 PM", "Distractible Podcast :: The Perfecter Crime"),
    ("4/28/25 1:31 PM", "Distractible Podcast :: Dippy Dawg Does Dunkirk"),
    ("4/28/25 1:31 PM", "Distractible Podcast :: The Even More Perfecter Crime"),
    ("4/30/25 8:29 AM", "Jet Lag: The Game :: Ep 2 — We Played Hide And Seek Across NYC"),
]


# Configuration
SONARR_URL = os.getenv("SONARR_URL")
API_KEY = os.getenv("SONARR_API")
HEADERS = {"X-Api-Key": API_KEY}

if not SONARR_URL or not API_KEY:
    raise RuntimeError("Both SONARR_URL and SONARR_API environment variables must be set.")

# Load shows
def get_all_monitored_shows():
    r = requests.get(f"{SONARR_URL}/api/v3/series", headers=HEADERS)
    r.raise_for_status()
    series_list = r.json()
    return [s['title'] for s in series_list if s.get('monitored', True)]

# Load episodes for a specific show
def get_episodes_for_series_title(title):
    r = requests.get(f"{SONARR_URL}/api/v3/series/lookup", params={"term": title}, headers=HEADERS)
    r.raise_for_status()
    results = r.json()
    if not results:
        return []

    best_match = results[0]
    series_id = best_match['id']

    r = requests.get(f"{SONARR_URL}/api/v3/episode", params={"seriesId": series_id}, headers=HEADERS)
    r.raise_for_status()
    episodes = r.json()

    return [{
        "series": best_match["title"],
        "season": ep["seasonNumber"],
        "episode": ep["episodeNumber"],
        "title": ep["title"],
        "air_date": ep.get("airDate", -1)
    } for ep in episodes]

# Begin matching logic
if __name__ == "__main__":
    all_shows = get_all_monitored_shows()
    grouped_titles = defaultdict(list)

    # Step 1: Match titles to shows and group
    title_to_show = {}
    for timestamp, title in titles:
        show_match = match_title_to_sonarr_show(title, all_shows)
        matched_show = show_match["matched_show"]
        print(f"\nMatched Show: {show_match['input']}")
        print(f"→ Series: {matched_show}")
        print(f"→ Score: {show_match['score']}")
        print(f"→ Why: {show_match['reason']}")

        if matched_show:
            grouped_titles[matched_show].append((timestamp, title))
            title_to_show[title] = matched_show
        else:
            print("→ No show match; skipping.")

    print("\n\n\n\nPHASE TWO\n\n\n\n")

    # Step 2: For each group, match to episodes
    for show, grouped in grouped_titles.items():
        print(f"\n=== Matching Episodes for Show: {show} ===")
        episodes = get_episodes_for_series_title(show)

        for timestamp, title in grouped:
            episode_match = match_title_to_sonarr_episode(title, timestamp, episodes)
            print(f"\n[{timestamp}] Title: {title}")
            print(f"→ Matched Episode → Series: {episode_match['matched_show']}")
            print(f"  Season {episode_match['season']} Episode {episode_match['episode']}: {episode_match['episode_title']}")
            print(f"  Score: {episode_match['score']}")
            print(f"  Why: {episode_match['reason']}")
