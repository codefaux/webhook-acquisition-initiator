import asyncio
import inspect
import json
import os
import re
import threading
from enum import Enum
from functools import wraps
from typing import Final, get_args, get_origin

import fauxlogger as _log
from decision_queue_manager import enqueue as decision_enqueue
from manual_intervention_manager import add_notify_listener as add_mi_notify
from manual_intervention_manager import (drop_mi_queue_item, get_mi_queue,
                                         get_mi_queue_item, load_mi_queue,
                                         mi_dict_type, mi_tuple_type)
from manual_intervention_manager import \
    remove_notify_listener as remove_mi_notify
from manual_intervention_manager import save_mi_queue, set_mi_queue_item
# from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
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

USAGE_TARGET_BASIC: Final[str] = "`{self}` as reply to target, or `{self} UUID`"

app: Application | None = None
loop: asyncio.AbstractEventLoop | None = None

cmd_dict: dict[str, dict] = {}


class RaiseCondition(Enum):
    RAISE_ON_ARG = True
    RAISE_NO_ARG = False
    RAISE_NONE = None


class ArgsExpect(Enum):
    ARGS_ARE_LIST = True
    ARGS_NOT_LIST = False
    ARGS_NONE = None


def scan_args_signature(func) -> ArgsExpect:
    _signature = inspect.signature(func)
    _params = list(_signature.parameters.values())

    if len(_params) == 3:
        return ArgsExpect.ARGS_NONE

    _annotation = _params[3].annotation

    if _annotation is str:
        return ArgsExpect.ARGS_NOT_LIST
    elif get_origin(_annotation) is list and get_args(_annotation) == (str,):
        return ArgsExpect.ARGS_ARE_LIST

    return ArgsExpect.ARGS_NONE


def register_command(
    name: str | list[str],
    help_text: str | list[str],
    usage_text: str | list[str] | None = "`{self}`",
    detail_text: str | list[str] | None = None,
    raise_on_args: RaiseCondition = RaiseCondition.RAISE_NONE,
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            _called_as = get_called_as(args[0])
            try:
                match cmd_dict[_called_as].get("args_expect"):
                    case ArgsExpect.ARGS_ARE_LIST:
                        _args = get_args_list_from(
                            args[0], args[1], _called_as, raise_on_args
                        )
                        return await func(*args, _called_as, _args, **kwargs)
                    case ArgsExpect.ARGS_NOT_LIST:
                        _arg = get_single_arg_from(
                            args[0], args[1], _called_as, raise_on_args
                        )
                        return await func(*args, _called_as, _arg, **kwargs)
                    case ArgsExpect.ARGS_NONE:
                        if raise_on_args:
                            get_single_arg_from(
                                args[0],
                                args[1],
                                _called_as,
                                RaiseCondition.RAISE_ON_ARG,
                            )
                        return await func(*args, _called_as, **kwargs)

            except UsageError:
                await send_usage(args[0], _called_as)

        for _idx, _name in enumerate(name if isinstance(name, list) else [name]):
            _entry: dict = {"func": wrapper}

            if isinstance(help_text, str):
                _entry["help"] = help_text
            elif isinstance(help_text, list):
                _entry["help"] = help_text[_idx]

            if not usage_text:
                pass
            elif isinstance(usage_text, str):
                _entry["usage"] = usage_text.format(self=f"/{_name}")
            elif isinstance(usage_text, list):
                _entry["usage"] = usage_text[_idx].format(self=f"/{_name}")

            if not detail_text:
                pass
            elif isinstance(detail_text, str):
                _entry["detail_text"] = detail_text
            elif isinstance(detail_text, list):
                _entry["detail_text"] = detail_text[_idx]

            _entry["args_expect"] = scan_args_signature(func)

            cmd_dict[_name] = _entry
        return wrapper

    return decorator


class UsageError(Exception):
    pass


def mi_data_to_detailed_message(
    mi_data: mi_tuple_type, header: str | None = None
) -> str:
    _val: str = (
        f"{header or ""}\n"
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
        f"{header or ""}\n"
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

    if os.path.exists(KNOWN_CHATS_FILE):
        with open(KNOWN_CHATS_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    known_chats.clear()
                    known_chats.update(data)
            except json.JSONDecodeError:
                _log.msg(
                    "Failed to decode queue JSON; starting with empty known chats."
                )


def load_notify_chats():
    global notify_chats

    if os.path.exists(NOTIFY_CHATS_FILE):
        with open(NOTIFY_CHATS_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    notify_chats.clear()
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
    if update.effective_chat and update.effective_chat.id not in known_chats:
        known_chats.add(update.effective_chat.id)
        save_known_chats()
        if DEBUG_PRINT:
            _log.msg(f"Known chats: {known_chats}")


async def add_notify_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.id not in notify_chats:
        notify_chats.add(update.effective_chat.id)
        save_notify_chats()
        if DEBUG_PRINT:
            _log.msg(f"Notify chats: {notify_chats}")


async def remove_known_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.id in known_chats:
        known_chats.remove(update.effective_chat.id)
        if DEBUG_PRINT:
            _log.msg(f"Known chats: {known_chats}")


async def remove_notify_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.id in notify_chats:
        notify_chats.remove(update.effective_chat.id)
        if DEBUG_PRINT:
            _log.msg(f"Notify chats: {notify_chats}")


async def send_to_notify(message: str):
    await asyncio.gather(*(send_message(message, _target) for _target in notify_chats))


async def send_to_known(message: str):
    await asyncio.gather(*(send_message(message, _target) for _target in known_chats))


def get_called_as(update: Update) -> str:
    _val = ""
    if update.effective_message and update.effective_message.text:
        _val = update.effective_message.text.removeprefix("/").split()[0].lower()
    return _val


def get_single_arg_from(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    called_as: str,
    raiseOnArg: RaiseCondition = RaiseCondition.RAISE_NONE,
) -> str:
    _arg = ""

    if context.args:
        _arg = " ".join(context.args)
    elif (
        update.effective_message
        and update.effective_message.text
        and update.effective_message.text.startswith(f"/{called_as}")
    ):
        _arg = update.effective_message.text.removeprefix(f"/{called_as}").strip()

    if _arg and len(_arg) > 0 and raiseOnArg is RaiseCondition.RAISE_ON_ARG:
        raise UsageError()
    if (not _arg or len(_arg) == 0) and raiseOnArg is RaiseCondition.RAISE_NO_ARG:
        raise UsageError()

    return _arg


def get_args_list_from(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    called_as: str,
    raiseOnArg: RaiseCondition = RaiseCondition.RAISE_NONE,
) -> list[str]:
    _args = []

    if context.args:
        _args = context.args
    elif (
        update.effective_message
        and update.effective_message.text
        and update.effective_message.text.startswith(f"/{called_as}")
    ):
        _args = (
            update.effective_message.text.removeprefix(f"/{called_as}").strip().split()
        )

    if _args and raiseOnArg is RaiseCondition.RAISE_ON_ARG:
        raise UsageError()
    if not _args and raiseOnArg is RaiseCondition.RAISE_NO_ARG:
        raise UsageError()

    return _args


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


def get_uuid_from(update: Update, text: str | None) -> str | None:
    if update.effective_message and update.effective_message.reply_to_message:
        return extract_uuid(update.effective_message.reply_to_message.text)
    elif text:
        if text == "all":
            return "all"
        else:
            return extract_uuid(text)

    return None


async def send_message(text: str, chat_id: str | None):
    if not app:
        raise RuntimeError("Bot not running yet")

    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not target_chat_id:
        raise RuntimeError("No chat_id provided and TELEGRAM_DEFAULT_CHAT_ID not set")

    if app:
        await app.bot.send_message(chat_id=target_chat_id, text=text)


async def send_usage(update: Update, called_as: str):
    if not app:
        raise RuntimeError("Bot not running yet")

    if update.effective_message:
        _target = cmd_dict.get(called_as)
        if _target:
            _usage = _target.get("usage")
            if _usage:
                await update.effective_message.reply_text(
                    f"Usage:\n{_usage}", parse_mode="Markdown"
                )


# ========
# COMMANDS
# ========


@register_command("start", help_text="Start using the bot.")
async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str):
    if update.effective_message:
        # _keyboard = [
        #     [
        #         InlineKeyboardButton(
        #             text="List Items",
        #             switch_inline_query_current_chat="/list",
        #         )
        #     ]
        # ]

        await update.effective_message.reply_text(
            "Hello! I'm alive.\n"
            "You will receive broadcast messages.\n"
            "/help - Show help\n"
            "/stop - Stop receiving broadcast messages and discontinue using this bot.",
            # reply_markup=InlineKeyboardMarkup(_keyboard),
        )


@register_command(
    "stop",
    help_text="Stop using the bot and disable all notifications.",
)
async def _stop(update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str):
    await remove_known_chat(update, context)
    await remove_notify_chat(update, context)

    if update.effective_message:
        await update.effective_message.reply_text(
            "This chat has been removed, there will be no further unprompted messages."
        )


@register_command(
    "echoall",
    help_text="Echo to notification channels.",
    usage_text="`{self} text`",
    raise_on_args=RaiseCondition.RAISE_NO_ARG,
)
async def _echo_all(
    update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str, _arg: str
):
    await send_to_notify(_arg)


@register_command(
    "echo",
    help_text="Echo.",
    usage_text="`{self} <text>`",
    raise_on_args=RaiseCondition.RAISE_NO_ARG,
)
async def _echo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str, _arg: str
):
    if update.effective_message:
        await update.effective_message.reply_text(_arg)


@register_command(
    "notify",
    help_text="Enable notifications for new items.",
)
async def _notify(update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str):
    if update.effective_message:
        await update.effective_message.reply_text(
            "You have been added to notifications.\n Use /nonotify to stop."
        )
    await add_notify_chat(update, context)


@register_command(
    ["nonotify", "stopnotify"],
    help_text="Stop receiving notifications.",
)
async def _nonotify(update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str):
    await remove_notify_chat(update, context)
    if update.effective_message:
        await update.effective_message.reply_text(
            "You have been removed from notifications.\n Use /notify to restart."
        )


@register_command("list", help_text="List current items.")
async def _list(update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str):
    if update.effective_message:
        _queue: mi_dict_type = get_mi_queue()
        _idx = 0
        for _key, _item in _queue.items():
            _idx += 1
            _data: mi_tuple_type = (_key, _item)
            await update.effective_message.reply_text(
                mi_data_to_short_message(_data, f"Item {_idx}:"),
                parse_mode="HTML",
            )


@register_command(
    "detail",
    help_text="Get details for target item.",
    usage_text=USAGE_TARGET_BASIC,
)
async def _detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str, _arg: str
):
    if update.effective_message:
        _target_uuid = get_uuid_from(update, _arg)

        if not _target_uuid:
            raise UsageError

        _item = get_mi_queue_item(_target_uuid.lower())

        if _item:
            await update.effective_message.reply_text(
                mi_data_to_detailed_message((_target_uuid.lower(), _item)),
                parse_mode="HTML",
            )
        else:
            await update.effective_message.reply_text("Error: Target not found.")
        return


@register_command(
    ["set", "add"],
    help_text=["Set parameters in target item.", "Add parameters to target item."],
    usage_text='`{self} PARAMETER VALUE` as reply to target OR\n`{self} UUID PARAMETER VALUE` to specify by UUID\nUse single double-quote (`"`) to clear parameter.',
    detail_text=['Use single-double-quote (`"`) to clear parameter.', ""],
    raise_on_args=RaiseCondition.RAISE_NO_ARG,
)
async def _set(
    update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str, _args: list[str]
):
    if update.effective_message:

        if len(_args) < 2:  # AT LEAST /set [uuid] param value
            raise UsageError

        # Check args for target, parameter, value
        _arg_idx = 0
        _target_uuid = get_uuid_from(update, _args[_arg_idx] if _args else None)

        if not _target_uuid:
            raise UsageError

        _item = get_mi_queue_item(_target_uuid.lower())

        if not _item:
            await update.effective_message.reply_text("Error: Target not found.")
            raise UsageError

        if not update.effective_message.reply_to_message:
            _arg_idx += 1

        _parameter = _args[_arg_idx]
        _subparameter = None

        if called_as != "add" and _parameter not in _item.keys():
            await update.effective_message.reply_text(
                "Error: Parameter not present in target. Use `/add` to inject parameters.",
                parse_mode="Markdown",
            )
            raise UsageError

        _subcheck = _item[_parameter]
        if isinstance(_subcheck, dict) and _args[_arg_idx + 1] != '"':
            _arg_idx += 1
            _subparameter = _args[_arg_idx]

            if called_as != "add" and _subparameter not in _subcheck.keys():
                await update.effective_message.reply_text(
                    "Error: Parameter/Subparameter not present in target. Use `/add` to inject parameters.",
                    parse_mode="Markdown",
                )
                raise UsageError

        _arg_idx += 1
        _value = " ".join(_args[_arg_idx:])

        if not _value:
            await update.effective_message.reply_text(
                'Error: Value must be provided. Use a single double-quote (`"`) to clear parameter.'
            )
            raise UsageError

        if _subparameter is None:
            if _value == '"':
                _old = _item[_parameter]
                _item.pop(_parameter)
                await update.effective_message.reply_text(
                    f"Removed '{_parameter}': was '{_old}'"
                )
            else:
                _old = _item[_parameter]
                _item[_parameter] = _value
                await update.effective_message.reply_text(
                    f"Updated '{_parameter}' to '{_value}' from '{_old}'"
                )
        else:
            if _value == '"':
                _old = _item[
                    _parameter
                ].get(  # pyright: ignore[reportAttributeAccessIssue]
                    _subparameter
                )
                _item[_parameter].pop(  # pyright: ignore[reportAttributeAccessIssue]
                    _subparameter
                )
                await update.effective_message.reply_text(
                    f"Removed '{_parameter}[{_subparameter}]': was '{_old}'"
                )
            else:
                _old = _item[
                    _parameter
                ].get(  # pyright: ignore[reportAttributeAccessIssue]
                    _subparameter
                )
                _item[_parameter][  # pyright: ignore[reportIndexIssue]
                    _subparameter
                ] = _value
                await update.effective_message.reply_text(
                    f"Updated '{_parameter}[{_subparameter}]' to '{_value}' from '{_old}'"
                )

        set_mi_queue_item(_target_uuid.lower(), _item)

        await update.effective_message.reply_text(
            mi_data_to_detailed_message((_target_uuid.lower(), _item)),
            parse_mode="HTML",
        )


@register_command(
    "drop",
    help_text="Drop the item from the Manual Intervention queue.",
    usage_text=USAGE_TARGET_BASIC,
    detail_text="This command does NOT automatically save.",
)
async def _drop(
    update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str, _arg: str
):
    if update.effective_message:
        _target_uuid = get_uuid_from(update, _arg)

        if not _target_uuid:
            raise UsageError

        _item = get_mi_queue_item(_target_uuid.lower())

        if _item:
            drop_mi_queue_item(_target_uuid)
            # save_mi_queue() -- Intentionally skipped!

            await update.effective_message.reply_text(
                f"Item {_target_uuid} ({_item["title"]}) dropped.\n<b>YOU MUST <code>/savequeue</code> NEXT TO CONFIRM OR CHANGES WILL NOT PERSIST.</b>",
                parse_mode="HTML",
            )
        else:
            await update.effective_message.reply_text("Error: Target not found.")


@register_command(
    ["enqueue", "requeue"],
    help_text="Move item to Decision queue.",
    usage_text=USAGE_TARGET_BASIC,
)
async def _enqueue(
    update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str, _arg: str
):
    if update.effective_message:
        _target_uuid = get_uuid_from(update, _arg)

        if not _target_uuid:
            raise UsageError

        _item = get_mi_queue_item(_target_uuid.lower())

        if _item:
            _mi_insert: dict = {"reason": "manual_intervention: telegram"}
            if update.effective_message.from_user:
                _mi_insert["user"] = update.effective_message.from_user.full_name
            _item["manual_intervention"] = _mi_insert

            decision_enqueue(_item)
            drop_mi_queue_item(_target_uuid)
            save_mi_queue()

            await update.effective_message.reply_text(
                f"Item {_target_uuid} ({_item["title"]}) moved to Decision queue.",
                parse_mode="HTML",
            )
        else:
            await update.effective_message.reply_text("Error: Target not found.")


@register_command(
    ["savequeue", "loadqueue"],
    help_text=[
        "Save Manual Intervention queue.",
        "Reload Manual Intervention queue without saving.",
    ],
)
async def _queue_saveload(
    update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str
):
    if update.effective_message:
        match called_as:
            case "savequeue":
                save_mi_queue()
                await update.effective_message.reply_text(
                    "Manual Intervention queue saved."
                )
            case "loadqueue":
                load_mi_queue()
                await update.effective_message.reply_text(
                    "Manual Intervention queue reloaded."
                )
            case _:
                raise UsageError


@register_command("help", help_text="Command list with short descriptions.")
async def _help(
    update: Update, context: ContextTypes.DEFAULT_TYPE, called_as: str, _arg: str
):
    if update.effective_message:
        _msg = "Available commands:\n"
        for _key, _val in cmd_dict.items():
            if len(_arg) == 0 or _key == _arg or _arg == "*" or _arg == "all":
                _help = _val["help"]
                _msg += f"/{_key} - {_help}\n"

                _detail = _val.get("detail_text")
                if _detail and len(_arg) > 0:
                    _msg += f"- {_detail}\n"
        await update.effective_message.reply_text(_msg)


async def _unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message:
        await update.effective_message.reply_text("Unknown command")
        await _help(update, context, "", "")


# #####################
# NOTIFICATION CALLBACK
# #####################


def mi_notify_callback(mi_data: mi_tuple_type) -> None:
    if loop and app:
        asyncio.run_coroutine_threadsafe(
            send_to_notify(mi_data_to_short_message(mi_data, "New item: ")), loop
        )
    return


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

    # app.add_handler(
    #     MessageHandler(filters.TEXT & ~filters.COMMAND, _check_reply), group=2
    # )

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
