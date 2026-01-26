# server.py

import fauxlogger as _log
import thread_manager
from fastapi import FastAPI, Query, Request

fastapi = FastAPI()


def handle_reprocess(from_file: str, item: str):
    import ast

    from decision_queue_manager import enqueue as enqueue_decision
    from processor import remove_json_item

    item = ast.literal_eval(item)

    if not isinstance(item, dict):
        _log.msg("Error: item received is not a valid item")
        return

    enqueue_decision(item)
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


@fastapi.post("/api/notify")
async def api_notify(
    creator: str = Query(...),
    title: str = Query(...),
    datecode: str = Query(...),
    url: str = Query(...),
):
    from decision_queue_manager import enqueue as enqueue_decision

    enqueue_decision(
        {
            "creator": creator.strip(),
            "title": title.strip(),
            "datecode": datecode.strip(),
            "url": url.strip(),
        }
    )
    return {"status": "queued"}


@fastapi.post("/api/stop_decision_manager")
async def api_stop_dqm():
    thread_manager.stop_decision_queue_manager()


@fastapi.post("/api/stop_aging_manager")
async def api_stop_aqm():
    thread_manager.stop_aging_queue_manager()


@fastapi.post("/api/stop_download_manager")
async def api_stop_dlqm():
    thread_manager.stop_download_queue_manager()


@fastapi.post("/api/start_decision_manager")
async def api_start_dqm():
    thread_manager.start_decision_queue_manager()


@fastapi.post("/api/start_aging_manager")
async def api_start_aqm():
    thread_manager.start_aging_queue_manager()


@fastapi.post("/api/start_download_manager")
async def api_start_dlqm():
    thread_manager.start_download_queue_manager()


@fastapi.post("/enqueue")
async def enqueue(request: Request):
    from decision_queue_manager import enqueue as enqueue_decision
    from processor import process_message

    payload = await request.json()
    text = payload.get("message")
    if not text:
        return {"error": "Missing 'message' field"}

    _log.msg(f"Message contents: {text}")

    processed = process_message(text)

    if processed == "":
        return {"error": "Unable to process message"}

    enqueue_decision(processed)
    return {"status": "queued"}


@fastapi.get("/get_item")
async def get_item(datafrom: str, name: str | None = None, value: str | None = None):
    from processor import get_json_items_filtered

    result = get_json_items_filtered(datafrom, name, value)
    return result


@fastapi.post("/dequeue_item")
async def dequeue_item(request: Request):
    item = await request.json()

    from decision_queue_manager import dequeue as dequeue_decision

    result = dequeue_decision(item)
    return result
