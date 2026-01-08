# server.py

import fauxlogger as _log
from fastapi import FastAPI, Request

fastapi = FastAPI()


def handle_reprocess(from_file: str, item: str):
    import ast

    from processor import remove_json_item
    from queue_manager import enqueue

    item = ast.literal_eval(item)

    if not isinstance(item, dict):
        _log.msg("Error: item received is not a valid item")
        return

    enqueue(item)
    remove_json_item(from_file, item)
    # add_json_item("queue", item)


def handle_remove(from_file: str, item: str):
    import ast

    from processor import remove_json_item

    item = ast.literal_eval(item)

    if not isinstance(item, dict):
        _log.msg("Error: item received is not a valid item")
        return

    remove_json_item(from_file, item)


@fastapi.post("/enqueue")
async def enqueue(request: Request):
    from processor import process_message
    from queue_manager import enqueue

    payload = await request.json()
    text = payload.get("message")
    if not text:
        return {"error": "Missing 'message' field"}

    _log.msg(f"Message contents: {text}")

    processed = process_message(text)

    if processed == "":
        return {"error": "Unable to process message"}

    enqueue(processed)
    return {"status": "queued"}


@fastapi.get("/get_item")
async def get_item(datafrom: str, name: str | None = None, value: str | None = None):
    from processor import get_json_items_filtered

    result = get_json_items_filtered(datafrom, name, value)
    return result


@fastapi.post("/dequeue_item")
async def dequeue_item(request: Request):
    item = await request.json()
    from processor import dequeue_item

    result = dequeue_item(item)
    return result
