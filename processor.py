# processor.py
# stands between server and files/data

import os
import json
import re
from queue_manager import dequeue

DATA_DIR = os.getenv("DATA_DIR")


def dequeue_item(item: dict):
    return dequeue(item)

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

def get_json_item(from_file: str, name: str = None, value: str = None) -> dict:
    from_file = from_file.lower()
    if not from_file.endswith(".json"):
        from_file += ".json"

    file_path = os.path.join(DATA_DIR, from_file)

    if not os.path.exists(file_path):
        return {"error": "File not found"}

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON format"}

    if not isinstance(data, list):
        return {"error": "Expected a list of JSON objects"}

    if name is None and value is None:
        return data

    filtered = []
    for entry in data:
        if isinstance(entry, dict):
            if name and value:
                if str(entry.get(name)) == value:
                    filtered.append(entry)
            elif name:
                if name in entry:
                    filtered.append(entry)
            elif value:
                if value in map(str, entry.values()):
                    filtered.append(entry)

    return filtered

def add_json_item(to_file: str, item: dict) -> dict:
    to_file = to_file.lower()
    if not to_file.endswith(".json"):
        to_file += ".json"

    if to_file == "queue.json":
        return {"error": "Cannot operate directly on queue"}

    file_path = os.path.join(DATA_DIR, to_file)

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON format"}
        if not isinstance(data, list):
            return {"error": "Expected a list of JSON objects"}
    else:
        data = []

    data.append(item)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return {"added": item}

def remove_json_item(from_file: str, item: dict) -> dict:
    from_file = from_file.lower()
    if not from_file.endswith(".json"):
        from_file += ".json"

    if from_file == "queue.json":
        return {"error": "Cannot operate directly on queue"}

    file_path = os.path.join(DATA_DIR, from_file)
    if not os.path.exists(file_path):
        return {"error": "File not found"}

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON format"}

    if not isinstance(data, list):
        return {"error": "Expected a list of JSON objects"}

    remaining = []
    removed = []

    for entry in data:
        if not isinstance(entry, dict):
            remaining.append(entry)
            continue

        if item == entry:
            removed.append(entry)
        else:
            remaining.append(entry)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(remaining, f, indent=2)

    return {"removed": removed}
