# server.py

import logger as _log
from fastapi import FastAPI, Request
from nicegui import app as nicegui_app
from nicegui import ui

fastapi = FastAPI()
ui.run_with(fastapi, mount_path="/ui", storage_secret="wai_storage")


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


@ui.page("/")
def main_page():
    from processor import get_json_items_filtered

    datafiles = [
        "all_processed",
        "download_fail",
        "episode_has_file",
        "episode_score",
        "queue",
    ]

    ui.dark_mode().bind_value(nicegui_app.storage.user, "dark_mode")
    ui.checkbox("dark mode").bind_value(nicegui_app.storage.user, "dark_mode")

    with ui.column().classes("w-full items-center"):
        with ui.card().classes("max-w-screen-md w-full"):
            with ui.tabs().classes("w-full") as tabs:
                _ = [ui.tab(df) for df in datafiles]  # tab_list =

            with ui.tab_panels(tabs, value=datafiles[0]).classes("w-full"):
                tab_containers = {}

                def make_tab_panel(datafile):
                    with ui.tab_panel(datafile):
                        container = ui.column().classes("w-full")
                        tab_containers[datafile] = container
                        refresh_tab(datafile)

                def refresh_tab(datafile):
                    container = tab_containers[datafile]
                    container.clear()
                    result = get_json_items_filtered(from_file=datafile)
                    if result:
                        for item in result:
                            ui.separator()
                            with ui.expansion(
                                f"{item.get('creator', '')} :: {item.get('title', '')}",
                                icon="expand_more",
                            ):
                                ui.json_editor({"content": {"json": item}})
                                with ui.button_group():
                                    ui.button("Reprocess").on(
                                        "click",
                                        lambda e, f=datafile, i=str(item): (
                                            handle_reprocess(f, i),
                                            refresh_tab(f),
                                        ),
                                    )
                                    ui.button("Remove").on(
                                        "click",
                                        lambda e, f=datafile, i=str(item): (
                                            handle_remove(f, i),
                                            refresh_tab(f),
                                        ),
                                    )

                for datafile in datafiles:
                    make_tab_panel(datafile)


@fastapi.post("/webhook")
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
