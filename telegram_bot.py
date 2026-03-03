import asyncio
import json
import os
import threading
from typing import Final

import fauxlogger as _log
from manual_intervention_manager import add_notify_listener as add_mi_notify
from manual_intervention_manager import (get_mi_queue, mi_dict_type,
                                         mi_tuple_type)
from manual_intervention_manager import \
    remove_notify_listener as remove_mi_notify
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

DEBUG_PRINT: Final[bool] = int(os.getenv("DEBUG_PRINT", 0)) != 0
DEBUG_BREAK: Final[bool] = int(os.getenv("DEBUG_BREAK", 0)) != 0

DATA_DIR: str = os.getenv("DATA_DIR") or "./data"

KNOWN_CHATS_FILE: Final[str] = os.path.join(DATA_DIR, "known_chats.json")
known_chats = set()

RUN_TELEGRAM_BOT = int(os.getenv("RUN_TELEGRAM_BOT", 1)) == 1

TELEGRAM_BOT_TOKEN: Final = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: Final = os.getenv("TELEGRAM_CHAT_ID")

app: Application | None = None
loop: asyncio.AbstractEventLoop | None = None

if RUN_TELEGRAM_BOT and not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable")


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


def mi_data_to_message(mi_data: mi_tuple_type, header: str | None = None) -> str:
    _val: str = (
        f"{header}\n"
        f"UUID: {mi_data[0]}\n"
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
            "Episode Result:\n"
            f"- Input: {_ep_res.get("input")}\n"
            f"- Season: {_ep_res.get("season")}\n"
            f"- Episode: {_ep_res.get("episode]")}\n"
            f"- Title: {_ep_res.get("episode_title")}\n"
            f"- Score: {_ep_res.get("score")}\n"
            f"- Reason:\n<code>\n{_ep_res.get("reason")}\n</code>\n\n"
        )

    return _val


def save_known_chats():
    global known_chats
    with open(KNOWN_CHATS_FILE, "w") as f:
        json.dump(list(known_chats), f, indent=2)


async def track_known_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        if chat.id not in known_chats:
            known_chats.add(chat.id)
            save_known_chats()
        if DEBUG_PRINT:
            _log.msg(f"Known chats: {known_chats}")


async def remove_known_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        known_chats.remove(chat.id)
        if DEBUG_PRINT:
            _log.msg(f"Known chats: {known_chats}")


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "Hello! I'm alive.\n"
            "Available commands:\n"
            "/echo <text> - Echo back text\n"
            "/list - List items for intervention\n"
            "/help - Show help"
        )
    if update.channel_post:
        await update.channel_post.reply_text(
            "Hello! I'm alive.\n"
            "Available commands:\n"
            "/echo <text> - Echo back text\n"
            "/list - List items for intervention\n"
            "/help - Show help"
        )


async def _echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _cmd = "/echo"
    _args = None
    if context.args:
        _args = " ".join(context.args)
    elif (
        update.effective_message
        and update.effective_message.text
        and update.effective_message.text.startswith(_cmd)
    ):
        _args = update.effective_message.text.removeprefix(_cmd).strip()

    if update.effective_message:
        if _args:
            await update.effective_message.reply_text(_args)
        else:
            await update.effective_message.reply_text(f"Usage: {_cmd} <text>")


async def _list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _cmd = "/list"
    _args = None
    if context.args:
        _args = " ".join(context.args)
    elif (
        update.effective_message
        and update.effective_message.text
        and update.effective_message.text.startswith(_cmd)
    ):
        _args = update.effective_message.text.removeprefix(_cmd).strip()

    if update.effective_message:
        if not _args:
            _queue: mi_dict_type = get_mi_queue()
            _idx = 0
            for _key, _item in _queue.items():
                _idx += 1
                _data: mi_tuple_type = (_key, _item)
                await update.effective_message.reply_text(
                    mi_data_to_message(_data, f"Item {_idx}:"), parse_mode="HTML"
                )
        else:
            await update.effective_message.reply_text(f"Usage: {_cmd}")


async def _echo_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _cmd = "/echoall"
    _args = None
    if context.args:
        _args = " ".join(context.args)
    elif (
        update.effective_message
        and update.effective_message.text
        and update.effective_message.text.startswith(_cmd)
    ):
        _args = update.effective_message.text.removeprefix(_cmd).strip()

    if _args:
        await send_to_known(_args)
    else:
        if update.effective_message:
            await update.effective_message.reply_text(f"Usage: {_cmd} <text>")


async def _unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Unknown command")


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


async def send_to_known(message: str):
    for _target in known_chats:
        await send_message(message, _target)


def mi_notify_callback(mi_data: mi_tuple_type) -> None:
    _uuid = mi_data[0]
    _message = mi_data_to_message(mi_data, "New item: ")

    if loop and app:
        asyncio.run_coroutine_threadsafe(
            send_to_known(f"uuid: {_uuid}\ndata: {_message}"),
            loop,
        )
    return


async def bot_start(stop_event: threading.Event):
    global app, loop

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    loop = asyncio.get_running_loop()

    load_known_chats()
    add_mi_notify(mi_notify_callback)

    app.add_handler(MessageHandler(filters.ALL, track_known_chats), group=0)

    app.add_handler(CommandHandler("echoall", _echo_all), group=1)
    app.add_handler(MessageHandler(filters.Regex("^/echoall"), _echo_all), group=1)

    app.add_handler(CommandHandler("echo", _echo), group=1)
    app.add_handler(MessageHandler(filters.Regex("^/echo"), _echo), group=1)

    app.add_handler(CommandHandler("start", _start), group=1)
    app.add_handler(MessageHandler(filters.Regex("^/start"), _start), group=1)

    app.add_handler(CommandHandler("stop", remove_known_chat), group=1)
    app.add_handler(MessageHandler(filters.Regex("^/stop"), remove_known_chat), group=1)

    app.add_handler(CommandHandler("list", _list), group=1)
    app.add_handler(MessageHandler(filters.Regex("^/list"), _list), group=1)

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


# class TelegramBotModule:

#     def __init__(self):
#         self._loop: Optional[asyncio.AbstractEventLoop] = None
#         self._application: Optional[Application] = None
#         self._ready_event = threading.Event()

#     def send_message(self, text: str, chat_id: Optional[str] = None):
#         if not self._application or not self._loop:
#             raise RuntimeError("Bot not running yet")

#         target_chat_id = chat_id or TELEGRAM_CHAT_ID
#         if not target_chat_id:
#             raise RuntimeError(
#                 "No chat_id provided and TELEGRAM_DEFAULT_CHAT_ID not set"
#             )

#         async def _send():
#             if self._application:
#                 await self._application.bot.send_message(
#                     chat_id=target_chat_id,
#                     text=text,
#                 )

#         asyncio.run_coroutine_threadsafe(_send(), self._loop)

#     async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
#         if update.message:
#             await update.message.reply_text(
#                 "Hello! I'm alive.\n"
#                 "Available commands:\n"
#                 "/echo <text> - Echo back text\n"
#                 "/help - Show help"
#             )

#     async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
#         if update.message:
#             await update.message.reply_text(
#                 "Commands:\n" "/echo <text> - Echo back your text"
#             )

#     async def _echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
#         if context.args:
#             text = " ".join(context.args)
#         else:
#             text = "Usage: /echo <text>"

#         if update.message:
#             await update.message.reply_text(text)

#     async def _unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
#         if update.message:
#             await update.message.reply_text("Unknown command")

#     async def _shutdown(self):
#         _log.msg("Shutting down Telegram bot...")
#         await self._application.updater.stop()  # pyright: ignore[reportOptionalMemberAccess]
#         await self._application.stop()  # pyright: ignore[reportOptionalMemberAccess]
#         await self._application.shutdown()  # pyright: ignore[reportOptionalMemberAccess]

#     def run(self, stop_event: threading.Event):
#         self._loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(self._loop)

#         async def _main():
#             if not TELEGRAM_BOT_TOKEN:
#                 raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable")

#             self._application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

#             self._application.add_handler(CommandHandler("start", self._start))
#             self._application.add_handler(CommandHandler("help", self._help))
#             self._application.add_handler(CommandHandler("echo", self._echo))
#             self._application.add_handler(MessageHandler(None, self._unknown))

#             await self._application.initialize()
#             await self._application.start()

#             self._application.run_polling()

#             # _log.msg("Telegram bot started.")
#             # self._ready_event.set()

#             # await asyncio.to_thread(self._ready_event.wait)

#             # _log.msg("Bot reports ready.")

#             # self.send_message("Bot online")

#             await asyncio.to_thread(stop_event.wait)

#             _log.msg("Bot stopped")

#             if self._application:
#                 await self._shutdown()

#             if self._loop:
#                 self._loop.stop()

#         try:
#             self._loop.create_task(_main())
#             self._loop.run_forever()
#         except KeyboardInterrupt:
#             pass
#         finally:
#             self._loop.close()
