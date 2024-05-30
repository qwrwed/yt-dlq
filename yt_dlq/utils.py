import logging
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from types import TracebackType
from typing import TypeVar

from utils_python import is_iterable, make_parent_dir

ROOT_PROJECT_DIR = Path(__file__).parent.parent


def get_resolve_filepath(file_path: Path | str, root: Path | str = ROOT_PROJECT_DIR):
    if not isinstance(file_path, Path):
        file_path = Path(file_path)
    if not isinstance(root, Path):
        root = Path(root)

    dir_path = file_path.parent
    file_name = file_path.name
    if (
        not dir_path.exists()
        and not dir_path.is_absolute()
        and (dir_path_new := Path(root, dir_path)).exists()
    ):
        return Path(dir_path_new, file_name).absolute()
    return file_path


def set_resolve_filepath(file_path: Path, root: Path = ROOT_PROJECT_DIR):
    return Path(
        *(".." for _ in root.relative_to(Path().absolute()).parts),
        file_path,
    )


if True:
    get_path = get_resolve_filepath  # resolve paths from project_root_directory
    set_path = set_resolve_filepath
else:
    get_path = Path  # resolve paths from current working directory
    set_path = Path


def escape_spaces(arg, use_singlequote=False):
    quote = "'" if use_singlequote else "'"
    return (
        f"{quote}{arg}{quote}"
        if (" " in arg and not (arg.startswith(quote)) and not (arg.endswith(quote)))
        else arg
    )


def match_filter_func(info_dict):
    if info_dict.get("is_live") is True or info_dict.get("was_live") is True:
        return "Video is/was livestream; skipping"
    # if info_dict.get("availability") != 'public':
    #     return "Video is private; skipping"
    return None


def hyphenate_date(YYYYMMDD: str):
    match = re.match(r"(\d{4})(\d{2})(\d{2})", YYYYMMDD)
    if not match:
        raise ValueError(f"date {YYYYMMDD} not recognised")
    return "-".join(match.groups())


class YtdlqLogger(logging.Logger):
    def debug(
        self,
        msg: object,
        *args: object,
        exc_info: (
            None
            | bool
            | tuple[type[BaseException], BaseException, TracebackType | None]
            | tuple[None, None, None]
            | BaseException
        ) = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        # re-calling logging functions adds another level to the stack, so we must
        #  negate that by passing stacklevel: https://stackoverflow.com/a/59492341
        YTDLP_STACK_OFFSET = 3

        # https://github.com/yt-dlp/yt-dlp#adding-logger-and-progress-hook
        # yt-dlp logs "info" as "debug"
        # debug messages start with [debug], but info messages do not start with [info]
        # as a workaround, assume log message starting with "["" was logged by yt-dlp
        # then assume any such message apart from `[debug]` should be info
        if msg.startswith("["):
            if msg.startswith("[debug]"):
                return super().debug(
                    msg,
                    *args,
                    exc_info=exc_info,
                    stack_info=stack_info,
                    stacklevel=stacklevel + YTDLP_STACK_OFFSET,
                    extra=extra,
                )
            return super().info(
                msg,
                *args,
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=stacklevel + YTDLP_STACK_OFFSET,
                extra=extra,
            )
        return super().debug(
            msg,
            *args,
            exc_info=exc_info,
            stack_info=stack_info,
            stacklevel=stacklevel + 1,
            extra=extra,
        )


def make_shortcut(
    path: Path | str = "shortcut.url",
    url: str = "http://google.com",
):
    path = Path(path)
    make_parent_dir(path)
    with open(path, mode="w", newline="\r\n") as f:
        f.write(f"[InternetShortcut]\nURL={url}")


ENTRIES_KEY = "entries"
INDEX_KEY = "index"
T = TypeVar("T")


def sorted_nested_with_entries(obj: T) -> T:
    obj_copy = deepcopy(obj)
    if isinstance(obj_copy, dict):
        iterable_items = {}
        non_iterable_items = {}

        entries_value = obj_copy.pop(ENTRIES_KEY) if ENTRIES_KEY in obj_copy else None

        def get_key(elem):
            k, v = elem
            if isinstance(v, dict) and "index" in v:
                return v["index"]
            return k

        for k, v in sorted(obj_copy.items(), key=get_key):
            if is_iterable(v):
                iterable_items[k] = sorted_nested_with_entries(v)
            else:
                non_iterable_items[k] = sorted_nested_with_entries(v)

        result = {**non_iterable_items, **iterable_items}
        if entries_value is not None:
            result[ENTRIES_KEY] = sorted_nested_with_entries(entries_value)
        return result

    elif isinstance(obj_copy, (list, tuple)):
        return obj_copy.__class__(sorted((sorted_nested_with_entries(e) for e in obj)))

    else:
        return obj_copy
