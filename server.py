# server.py

from fastapi import FastAPI, Request
from processor import process_message
from queue_manager import enqueue

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    text = payload.get("message")
    if not text:
        return {"error": "Missing 'message' field"}

    processed = process_message(text)
    enqueue(processed)
    return {"status": "queued"}
