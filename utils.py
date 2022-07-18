from enum import Enum
import functools
import json
from pathlib import Path
from pprint import pprint
import shutil
import zipfile

import PySimpleGUI as sg
import requests
from tqdm.auto import tqdm
from yt_dlp.utils import sanitize_filename

class DownloadStates(str, Enum):
    NEVER_DOWNLOADED = "never_downloaded"
    ORIGINAL_DOWNLOADED = "original_downloaded"
    DUPLICATE_DOWNLOADED = "duplicate_downloaded"
    DUPLICATE_NOT_DOWNLOADED = "duplicate_not_downloaded"
    CREATED_PLACEHOLDER = "placeholder"
    # IGNORED = "ignored",
    DOWNLOAD_FAILED = "download_failed"

def make_parent_dir(filepath):
    Path(filepath).parent.mkdir(exist_ok=True,parents=True)

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
    make_parent_dir(path)

    desc = "(Unknown total file size)" if file_size == 0 else ""
    r.raw.read = functools.partial(
        r.raw.read, decode_content=True
    )  # Decompress if needed
    with tqdm.wrapattr(r.raw, "read", total=file_size, desc=desc) as r_raw:
        with path.open("wb") as f:
            shutil.copyfileobj(r_raw, f)

    return path

def filename_from_url(url):
    return url.split("/")[-1]

def unzip(filename):
    with zipfile.ZipFile(filename, "r") as zip_ref:
        zip_ref.extractall()

def download_ytdl():
    ytdl_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    ytdl_filename = filename_from_url(ytdl_url)
    download(ytdl_url, ytdl_filename)

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
PATTERN_CHANNEL_BASE = rf"https:\/\/(?:www\.)?youtube\.com\/(?:c|channel|user)\/{PATTERN_ID}"
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
        make_parent_dir(archive_path)
        open(archive_path, "w+").close()
    return False

def read_entry_extended(video, channel_playlist_info, archive_path):
    # -1: video has not been previously recorded as  downloaded
    #  0: video has been previously recorded as downloaded in a different playlist
    #  1: video has been previously recorded as downloaded in the same playlist
    print("read_entry_extended(video, channel_playlist_info, archive_path)")
    try:
        with open(archive_path, "r") as f:
            info_extended = json.load(f)
            try:
                video_info_extended = info_extended[video["id"]]
                if channel_playlist_info in video_info_extended["in_playlists"]:
                    return 1
                return 0
            except KeyError:
                return -1
    except FileNotFoundError:
        make_parent_dir(archive_path)
        with open(archive_path, "w+") as f:
            json.dump({}, f)
    return -1

def write_entry_extended(video, channel_playlist_info, archive_path):
    with open(archive_path, "r") as f:
        info_extended = json.load(f)
    video_id = video["id"]
    video_info_extended = info_extended.get(video_id)
    if video_info_extended:
        video_info_extended["in_playlists"].append(channel_playlist_info)
    else:
        info_extended[video_id] = {
            "id": video_id,
            "title": video["title"],
            "url": video["url"],
            "in_playlists": [channel_playlist_info],
            "legacy_archive_id": get_archive_id(video),
        }
    with open(archive_path, "w") as f:
        json.dump(info_extended, f, indent=4)

def write_to_archives(info_dict, archive_paths: list):
    for archive_path in archive_paths:
        with open(archive_path, "a") as f:
            archive_id = get_archive_id(info_dict)
            f.write(archive_id)
            f.write("\n")

def get_download_state(video, channel_playlist_info, archive_path):
    try:
        with open(archive_path, "r") as f:
            info_extended = json.load(f)
            try:
                video_info_extended = info_extended[video["id"]]
                playlist_id = channel_playlist_info["playlist_id"]
                try:
                    playlist_info = video_info_extended["in_playlists"][playlist_id]
                except KeyError:
                    return DownloadStates.DUPLICATE_NOT_DOWNLOADED
                return playlist_info["download_state"]
            except KeyError:
                return DownloadStates.NEVER_DOWNLOADED
    except FileNotFoundError:
        make_parent_dir(archive_path)
        with open(archive_path, "w+") as f:
            json.dump({}, f)
    return DownloadStates.NEVER_DOWNLOADED

def set_download_state(video, channel_playlist_info, archive_path, download_state):
    with open(archive_path, "r") as f:
        info_extended = json.load(f)
    video_id = video["id"]
    playlist_id = channel_playlist_info["playlist_id"]
    video_info_extended = info_extended.get(video_id)
    channel_playlist_state_info = channel_playlist_info | {"download_state": download_state}
    if not video_info_extended:
        info_extended[video_id] = {
            "id": video_id,
            "title": video["title"],
            "url": video["url"],
            "in_playlists": {playlist_id: channel_playlist_state_info},
            "legacy_archive_id": get_archive_id(video),
        }
    else:
        video_info_extended["in_playlists"][playlist_id] = channel_playlist_state_info
    with open(archive_path, "w") as f:
        json.dump(info_extended, f, indent=4)
