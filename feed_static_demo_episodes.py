#!/usr/bin/env python

import os
import requests

# Load configuration from environment variables
SONARR_URL = os.getenv("CF_SONARR_URL")
API_KEY = os.getenv("CF_SONARR_API")

if not SONARR_URL or not API_KEY:
    raise RuntimeError("Both SONARR_URL and SONARR_API environment variables must be set.")

HEADERS = {"X-Api-Key": API_KEY}
sonarr_data = []

def search_series(query):
    r = requests.get(f"{SONARR_URL}/api/v3/series/lookup", params={"term": query}, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_episodes(series_id):
    r = requests.get(f"{SONARR_URL}/api/v3/episode", params={"seriesId": series_id}, headers=HEADERS)
    r.raise_for_status()
    return r.json()

while True:
    query = input("Enter a show name to search (or leave blank to finish): ").strip()
    if not query:
        break

    try:
        results = search_series(query)
    except Exception as e:
        print(f"Error searching for series: {e}")
        continue

    if not results:
        print("No results found.")
        continue

    print("\nTop 10 search results:")
    for idx, show in enumerate(results[:10]):
        print(f"{idx}: {show['title']} ({show.get('year', 'Unknown Year')})")

    choice = input("Enter the number of the show to add (or leave blank to skip): ").strip()
    if not choice.isdigit() or int(choice) >= min(10, len(results)):
        continue

    series = results[int(choice)]
    try:
        episodes = get_episodes(series['id'])
    except Exception as e:
        print(f"Error fetching episodes: {e}")
        continue

for ep in episodes:
    sonarr_data.append({
        "series": series['title'],
        "season": ep["seasonNumber"],
        "episode": ep["episodeNumber"],
        "title": ep["title"],
        "air_date": ep["airDate"]  # or use ep["airDateUtc"] for UTC
    })
    
print("\nCollected episode data:")
for entry in sonarr_data:
    print(entry)
