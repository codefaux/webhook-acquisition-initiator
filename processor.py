# processor.py

import re

def process_message(raw_text: str) -> dict:
    # Pattern to match the format: CREATOR :: DATECODE :: TITLE\n\nURL
    pattern = re.compile(r'^(.*?)\s*::\s*(\d{8})\s*::\s*(.*?)\s*\n+(\S+)', re.DOTALL)

    match = pattern.match(raw_text.strip())
    if not match:
        return {}  # or raise an error / return None depending on context

    creator, datecode, title, url = match.groups()

    return {
        "creator": creator.strip(),
        "title": title.strip(),
        "datecode": datecode.strip(),
        "url": url.strip()
    }
