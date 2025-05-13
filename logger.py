import inspect
import re
from datetime import datetime
from threading import Lock

msg_lock = Lock()

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def visible_length(text):
    clean_text = ANSI_ESCAPE.sub("", text)
    return len(clean_text)


# I'm sure there's a better way to do this
_BLUE = "\033[94m"
_YELLOW = "\033[93m"
_GREEN = "\033[92m"
_RED = "\033[91m"
_GREY = "\033[90m"
_RESET = "\033[0m"


def msg(message, stack_offset=1):
    frame = inspect.stack()[stack_offset]
    module = inspect.getmodule(frame[0])
    caller_name = frame.function
    caller_file = module.__file__.split("/")[-1] if module else "Unknown"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stack_prepend = (
        f"{_BLUE}[{_YELLOW}{caller_file}{_BLUE}:{_GREEN}{caller_name}{_BLUE}]{_RESET} "
    )
    timecode_prepend = f"{_GREEN}[{_GREY}{timestamp}{_GREEN}]{_RESET} "
    stack_len = visible_length(stack_prepend)
    timecode_len = visible_length(timecode_prepend)
    stack_offset = max(stack_len, timecode_len) - stack_len
    timecode_offset = max(stack_len, timecode_len) - timecode_len

    message_list = [line.strip() for line in message.split("\n")]
    if len(message_list) == 1:
        message_list.append("")

    with msg_lock:
        for idx, msg_line in enumerate(message_list):
            if idx > 1:
                print(f"{' ' * max(timecode_len, stack_len)}{msg_line}")
            elif idx == 1:
                print(f"{timecode_prepend}{' ' * timecode_offset}{msg_line}")
            else:
                print(f"{stack_prepend}{' ' * stack_offset}{msg_line}")
        print("\n")
