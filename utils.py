import functools
from pathlib import Path
import shutil

import PySimpleGUI as sg
import requests
from tqdm.auto import tqdm
from yt_dlp.utils import sanitize_filename


def download(url, filepath, verbose=True):
    """
    Download URL to filepath
    """
    # https://stackoverflow.com/a/63831344

    if verbose:
        print(f"Downloading {url} to {filepath}")

    r = requests.get(url, stream=True, allow_redirects=True)
    if r.status_code != 200:
        r.raise_for_status()  # Will only raise for 4xx codes, so...
        raise RuntimeError(f"Request to {url} returned status code {r.status_code}")
    file_size = int(r.headers.get("Content-Length", 0))

    path = Path(filepath).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    desc = "(Unknown total file size)" if file_size == 0 else ""
    r.raw.read = functools.partial(
        r.raw.read, decode_content=True
    )  # Decompress if needed
    with tqdm.wrapattr(r.raw, "read", total=file_size, desc=desc) as r_raw:
        with path.open("wb") as f:
            shutil.copyfileobj(r_raw, f)

    return path


def input_popup(msg, default_input="", window_title="Input Required", beep=True):
    """
    PySimpleGUI window equivalent of input()
    """
    layout = [
        [sg.Text(msg)],
        [sg.InputText(key="-IN-", default_text=default_input, size=(80))],
        [sg.Submit()],
    ]
    if beep:
        print("\a")
    window = sg.Window(window_title, layout, modal=True)
    _, values = window.read()
    window.close()
    return values["-IN-"]


PATTERN_ID = r"[\w\-]+"
PATTERN_QUERY = r"(?:\?[\w=\&]+)"
PATTERN_CHANNEL_BASE = rf"https:\/\/(?:www\.)?youtube\.com\/(?:c|channel)\/{PATTERN_ID}"
URL_TYPE_PATTERNS = {
    "channel_home": rf"^({PATTERN_CHANNEL_BASE})(?:\/featured)?\/?$",
    "channel_group_playlists": rf"^({PATTERN_CHANNEL_BASE}(?:\/playlists){PATTERN_QUERY}?)\/?$",
    "playlist": rf"^(https:\/\/(?:www\.)?youtube\.com\/playlist\?list={PATTERN_ID})\/?$",
    "channel_group_videos": rf"^({PATTERN_CHANNEL_BASE}(?:\/videos))\/?$",
    "video": rf"^(https:\/\/(?:youtu\.be\/|(?:www\.)?youtube\.com\/watch\?v=)({PATTERN_ID})){PATTERN_QUERY}?\/?$",
}


def restrict_filename(filename):
    return sanitize_filename(filename, restricted=True)


def escape_spaces(arg, use_singlequote=False):
    quote = "'" if use_singlequote else "'"
    return (
        f"{quote}{arg}{quote}"
        if (" " in arg and not (arg.startswith(quote)) and not (arg.endswith(quote)))
        else arg
    )


def get_archive_id(info_dict: dict):
    ie_key_derived = "Youtube" if info_dict["type"] == "video" else "YoutubeTab"
    ie_key = info_dict.get("ie_key", ie_key_derived)
    return f"{ie_key.lower()} {info_dict['id']}"


def already_in_archive(info_dict, archive_path):
    archive_id = get_archive_id(info_dict)
    try:
        with open(archive_path) as f:
            archived_items = f.read().splitlines()
            if archive_id in archived_items:
                return True
    except FileNotFoundError:
        Path(archive_path).parent.mkdir(parents=True, exist_ok=True)
        open(archive_path, "w+").close()
    return False

def write_to_archives(info_dict, archive_paths: list):
    for archive_path in archive_paths:
        with open(archive_path, "a") as f:
            archive_id = get_archive_id(info_dict)
            f.write(archive_id)
            f.write("\n")