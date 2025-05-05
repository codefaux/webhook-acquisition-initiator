# server.py

from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    from processor import process_message
    from queue_manager import enqueue
    payload = await request.json()
    text = payload.get("message")
    if not text:
        return {"error": "Missing 'message' field"}

    processed = process_message(text)
    enqueue(processed)
    return {"status": "queued"}

@app.get("/get_item")
async def get_item(datafrom: str, name: str = None, value: str = None):
    from processor import get_json_item
    result = get_json_item(datafrom, name, value)
    return result

@app.post("/dequeue_item")
async def dequeue_item(request: Request):
    item = await request.json()
    from processor import dequeue_item
    result = dequeue_item(item)
    return result

@app.post("/remove_item")
async def remove_item(from_file: str, name: str = None, value: str = None):
    from processor import remove_json_item
    result = remove_json_item(from_file, name, value)
    return result
