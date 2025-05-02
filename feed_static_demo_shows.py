#!/usr/bin/env python

import os
import requests

def get_unmonitored_series():
  sonarr_url = os.getenv("CF_SONARR_URL")
  api_key = os.getenv("CF_SONARR_API")

  if not sonarr_url or not api_key:
      raise ValueError("SONARR_URL and SONARR_API_KEY environment variables must be set.")

  headers = {"X-Api-Key": api_key}
  response = requests.get(f"{sonarr_url.rstrip('/')}/api/v3/series", headers=headers)

  response.raise_for_status()
  series_list = response.json()

  # Filter only unmonitored series and return their titles
  unmonitored_titles = [s['title'] for s in series_list if s.get('monitored', True)]
  return unmonitored_titles

if __name__ == "__main__":
  print(repr(get_unmonitored_series()))