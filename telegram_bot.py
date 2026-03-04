import asyncio
import json
import os
import re
import threading
from functools import wraps
from typing import Final

import fauxlogger as _log
from manual_intervention_manager import add_notify_listener as add_mi_notify
from manual_intervention_manager import (get_mi_queue, mi_dict_type,
                                         mi_tuple_type)
from manual_intervention_manager import \
    remove_notify_listener as remove_mi_notify
# from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Message, Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

DEBUG_PRINT: Final[bool] = int(os.getenv("DEBUG_PRINT", 0)) != 0
DEBUG_BREAK: Final[bool] = int(os.getenv("DEBUG_BREAK", 0)) != 0

DATA_DIR: str = os.getenv("DATA_DIR") or "./data"

KNOWN_CHATS_FILE: Final[str] = os.path.join(DATA_DIR, "known_chats.json")
known_chats = set()

NOTIFY_CHATS_FILE: Final[str] = os.path.join(DATA_DIR, "notify_chats.json")
notify_chats = set()

RUN_TELEGRAM_BOT = int(os.getenv("RUN_TELEGRAM_BOT", 1)) == 1

TELEGRAM_BOT_TOKEN: Final = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: Final = os.getenv("TELEGRAM_CHAT_ID")

if RUN_TELEGRAM_BOT and not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable")


app: Application | None = None
loop: asyncio.AbstractEventLoop | None = None

cmd_dict: dict = {}


def register_command(name: str, help_text: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs, _cmd=f"/{name}")

        cmd_dict[name] = {
            "func": wrapper,
            "help": help_text,
        }
        return wrapper

    return decorator


def mi_data_to_detailed_message(
    mi_data: mi_tuple_type, header: str | None = None
) -> str:
    _val: str = (
        f"{header}\n"
        f"UUID: <code>{mi_data[0]}</code>\n"
        f"Creator: {mi_data[1].get("creator")}\n"
        f"Title: {mi_data[1].get("title")}\n"
        f"Datecode: {mi_data[1].get("datecode")}\n"
        f"URL: {mi_data[1].get("url")} \n\n"
    )

    _title_res = mi_data[1].get("title_result")
    if _title_res and isinstance(_title_res, dict):
        _val += (
            "Title Result:\n"
            f"- Show: {_title_res.get("matched_show")}\n"
            f"- Score: {_title_res.get("score")}\n\n"
        )
    _ep_res = mi_data[1].get("episode_result")
    if _ep_res and isinstance(_ep_res, dict):
        _val += (
            "Closest Episode Result:\n"
            f"- Input: {_ep_res.get("input")}\n"
            f"- Season: {_ep_res.get("season")}\n"
            f"- Episode: {_ep_res.get("episode")}\n"
            f"- Title: {_ep_res.get("episode_title")}\n"
            f"- Score: {_ep_res.get("score")}\n"
            f"- Reason:\n<code>\n{_ep_res.get("reason")}\n</code>\n\n"
        )

    return _val


def mi_data_to_short_message(mi_data: mi_tuple_type, header: str | None = None) -> str:
    _val: str = (
        f"{header}\n"
        f"UUID: <code>{mi_data[0]}</code>\n"
        f"URL: {mi_data[1].get("url")} \n\n"
    )

    _title_res = mi_data[1].get("title_result")
    _ep_res = mi_data[1].get("episode_result")
    if _ep_res and isinstance(_ep_res, dict):
        _val += (
            "Closest Episode Result:\n"
            f"- Input: {_ep_res.get("input")}\n"
            f"- Series: {_title_res.get("matched_show") if isinstance(_title_res, dict) else ""}\n"
            f"- Season: {_ep_res.get("season")}"
            f"  Episode: {_ep_res.get("episode")}\n"
            f"- Title: {_ep_res.get("episode_title")}\n"
        )

    return _val


def load_known_chats():
    global known_chats
    known_chats.clear()

    if os.path.exists(KNOWN_CHATS_FILE):
        with open(KNOWN_CHATS_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    known_chats.update(data)
            except json.JSONDecodeError:
                _log.msg(
                    "Failed to decode queue JSON; starting with empty known chats."
                )


def load_notify_chats():
    global notify_chats
    notify_chats.clear()

    if os.path.exists(NOTIFY_CHATS_FILE):
        with open(NOTIFY_CHATS_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    notify_chats.update(data)
            except json.JSONDecodeError:
                _log.msg(
                    "Failed to decode queue JSON; starting with empty notify chats."
                )


def save_known_chats():
    global known_chats
    with open(KNOWN_CHATS_FILE, "w") as f:
        json.dump(list(known_chats), f, indent=2)


def save_notify_chats():
    global notify_chats
    with open(NOTIFY_CHATS_FILE, "w") as f:
        json.dump(list(notify_chats), f, indent=2)


async def add_known_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        if chat.id not in known_chats:
            known_chats.add(chat.id)
            save_known_chats()
        if DEBUG_PRINT:
            _log.msg(f"Known chats: {known_chats}")


async def add_notify_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        if chat.id not in notify_chats:
            notify_chats.add(chat.id)
            save_notify_chats()
        if DEBUG_PRINT:
            _log.msg(f"Notify chats: {notify_chats}")


async def remove_known_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        known_chats.remove(chat.id)
        if DEBUG_PRINT:
            _log.msg(f"Known chats: {known_chats}")


async def remove_notify_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        notify_chats.remove(chat.id)
        if DEBUG_PRINT:
            _log.msg(f"Notify chats: {notify_chats}")


async def send_to_notify(message: str):
    for _target in notify_chats:
        await send_message(message, _target)


async def send_to_known(message: str):
    for _target in known_chats:
        await send_message(message, _target)


def get_cmd_args(
    update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str
) -> str | None:
    if context.args:
        return " ".join(context.args)
    elif (
        update.effective_message
        and update.effective_message.text
        and update.effective_message.text.startswith(_cmd)
    ):
        return update.effective_message.text.removeprefix(_cmd).strip()

    return None


def get_message(update: Update) -> Message | None:
    if update.message:
        return update.message
    elif update.channel_post:
        return update.channel_post
    else:
        return None


def extract_uuid(message_text: str | None) -> str | None:
    line_pattern = r"^UUID:\s*([0-9a-f-]{36})$"
    arg_pattern = r"([0-9a-f-]{36})"

    if message_text:
        match_line = re.search(line_pattern, message_text, re.MULTILINE | re.IGNORECASE)
        if match_line:
            return match_line.group(1)
        match_arg = re.search(arg_pattern, message_text, re.IGNORECASE)
        if match_arg:
            return match_arg.group(1)

    return None


async def _check_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        message = update.message
    elif update.channel_post:
        message = update.channel_post
    else:
        return

    if message.reply_to_message:
        if (
            message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == context.bot.id
        ):
            await message.reply_text("You replied to my message!")


async def send_message(text: str, chat_id: str | None):
    if not app:
        raise RuntimeError("Bot not running yet")

    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not target_chat_id:
        raise RuntimeError("No chat_id provided and TELEGRAM_DEFAULT_CHAT_ID not set")

    if app:
        await app.bot.send_message(chat_id=target_chat_id, text=text)


def mi_notify_callback(mi_data: mi_tuple_type) -> None:
    if loop and app:
        asyncio.run_coroutine_threadsafe(
            send_to_notify(mi_data_to_short_message(mi_data, "New item: ")), loop
        )
    return


# ========
# COMMANDS
# ========


@register_command("start", help_text="Start using the bot.")
async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):
    if update.message:
        # _keyboard = [
        #     [
        #         InlineKeyboardButton(
        #             text="List Items",
        #             switch_inline_query_current_chat="/list",
        #         )
        #     ]
        # ]

        await update.message.reply_text(
            "Hello! I'm alive.\n" "/help - Show help",
            # reply_markup=InlineKeyboardMarkup(_keyboard),
        )
    if update.channel_post:
        await update.channel_post.reply_text(
            "Hello! I'm alive.\n" "Available commands:\n" "/help - Show help"
        )


@register_command("stop", help_text="Stop using the bot and disable all notifications.")
async def _stop(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):
    await remove_known_chat(update, context)
    await remove_notify_chat(update, context)


@register_command("echo", help_text="Echo.")
async def _echo(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):
    _args = get_cmd_args(update, context, _cmd)

    if update.effective_message:
        if _args:
            await update.effective_message.reply_text(_args)
        else:
            await update.effective_message.reply_text(f"Usage: {_cmd} <text>")


@register_command("echoall", help_text="Echo to notification channels.")
async def _echo_all(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):
    _args = get_cmd_args(update, context, _cmd)

    if _args:
        await send_to_notify(_args)
    else:
        if update.effective_message:
            await update.effective_message.reply_text(f"Usage: {_cmd} <text>")


@register_command("notify", help_text="Enable notifications for new items.")
async def _notify(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):
    await add_notify_chat(update, context)


@register_command("nonotify", help_text="Stop receiving notifications.")
async def _nonotify(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):
    await remove_notify_chat(update, context)


@register_command("list", help_text="List current items.")
async def _list(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):
    _args = get_cmd_args(update, context, _cmd)

    if update.effective_message:
        if not _args:
            _queue: mi_dict_type = get_mi_queue()
            _idx = 0
            for _key, _item in _queue.items():
                _idx += 1
                _data: mi_tuple_type = (_key, _item)
                await update.effective_message.reply_text(
                    mi_data_to_short_message(_data, f"Item {_idx}:"),
                    parse_mode="HTML",
                )
        else:
            await update.effective_message.reply_text(f"Usage: {_cmd}")


@register_command("detail", help_text="Get details for current items.")
async def _detail(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):
    message = get_message(update)
    if not message:
        return

    _reply_uuid = None
    _args = get_cmd_args(update, context, _cmd)

    if message.reply_to_message:
        if (
            message.reply_to_message.author_signature
            and message.reply_to_message.author_signature == context.bot.first_name
        ):  # Need to also handle reply in direct message
            _reply_uuid = extract_uuid(message.reply_to_message.text)
    elif _args:
        if _args == "all":
            _reply_uuid = "all"
        else:
            _reply_uuid = extract_uuid(_args)

    if _reply_uuid:
        _queue: mi_dict_type = get_mi_queue()
        _idx = 0
        for _key, _item in _queue.items():
            _idx += 1
            _data: mi_tuple_type = (_key, _item)
            if _key.lower() == _reply_uuid.lower():
                await message.reply_text(
                    mi_data_to_detailed_message(_data, f"Item {_idx}:"),
                    parse_mode="HTML",
                )
    else:
        await message.reply_text(
            f"Usage: <code>{_cmd}</code> as reply to target, or <code>{_cmd} UUID</code>",
            parse_mode="HTML",
        )


@register_command("help", help_text="Command list with short descriptions.")
async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE, _cmd: str):

    for _key, _val in cmd_dict:
        pass


async def _unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Unknown command")
        await _help(update, context, "")


# ====
# CORE
# ====


async def bot_start(stop_event: threading.Event):
    global app, loop

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    loop = asyncio.get_running_loop()

    load_known_chats()
    add_mi_notify(mi_notify_callback)

    app.add_handler(MessageHandler(filters.ALL, add_known_chat), group=0)

    for _cmd, _val in cmd_dict.items():
        app.add_handler(CommandHandler(_cmd, _val["func"]), group=1)
        app.add_handler(
            MessageHandler(filters.Regex(f"^/{_cmd}"), _val["func"]), group=1
        )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _check_reply), group=2
    )

    await app.initialize()
    await app.updater.start_polling(  # pyright: ignore[reportOptionalMemberAccess]
        allowed_updates=Update.ALL_TYPES
    )
    await app.start()

    # while True:
    while not stop_event.is_set():
        # exiting from this loop will make the bot exit
        await asyncio.sleep(1)
    # dropped from the loop, shutdown

    remove_mi_notify(mi_notify_callback)

    await app.updater.stop()  # pyright: ignore[reportOptionalMemberAccess]
    await app.stop()
    await app.shutdown()


async def bot_starttask(stop_event: threading.Event):
    await asyncio.create_task(bot_start(stop_event))


def telegram_bot_thread(stop_event: threading.Event):
    asyncio.run(bot_starttask(stop_event))
