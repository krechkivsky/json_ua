# -*- coding: utf-8 -*-
# Copyright (C) 2026 Mykhailo Krechkivskyi

#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import inspect
import os
import sys
from datetime import datetime

LOG = False

_plugin_dir = os.path.dirname(__file__)
_log_path = os.path.join(_plugin_dir, "log.md")

logFile = None


def _open_log(mode: str):
    return open(_log_path, mode, encoding="utf-8")


def clear_log() -> None:
    with _open_log("w") as f:
        f.write("")
        f.flush()


def set_log_enabled(enabled: bool) -> None:
    global LOG, logFile

    enabled = bool(enabled)
    if enabled:
        if logFile is None or getattr(logFile, "closed", True):
            logFile = _open_log("a")
        LOG = True
        log_msg(logFile, f"Plugin debug enabled at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return

    LOG = False
    try:
        if logFile is not None and not logFile.closed:
            logFile.close()
    except Exception:
        pass
    logFile = None
    clear_log()


def _caller(i: int) -> str:
    try:
        return inspect.stack()[i].function
    except Exception:
        return "<?>"


def log_msg(log_file, msg: str = "") -> None:
    if log_file is None:
        return
    try:
        filename = os.path.basename(inspect.stack()[1].frame.f_code.co_filename)
        lineno = sys._getframe().f_back.f_lineno
        log_file.write(f"\n##### [{_caller(2)}():]({filename}#L{lineno}) {msg}")
        log_file.flush()
    except Exception:
        pass


def _get_call_stack() -> str:
    stack = inspect.stack()
    result = ""
    i = 0
    for frame_info in reversed(stack[2:]):
        i += 1
        frame = frame_info.frame
        filename = os.path.basename(frame.f_code.co_filename)
        lineno = frame.f_lineno
        spaces = " " * max(1, (24 - len(filename)))
        func_name = frame.f_code.co_name
        if filename != "<string>":
            result += f"\n [{i}. {filename} {spaces} {func_name}]({filename}#L{lineno})"
    return result


def log_calls(log_file, *items) -> None:
    if log_file is None:
        return
    try:
        stack_info = _get_call_stack()
        if not items:
            msg = ""
        elif len(items) == 1:
            msg = str(items[0])
        else:
            msg = " ".join(str(x) for x in items)
        log_file.write(f"{stack_info}→\n{msg}\n")
        log_file.flush()
    except Exception:
        pass

