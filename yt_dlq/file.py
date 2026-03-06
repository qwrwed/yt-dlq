import json
from copy import deepcopy
from datetime import datetime
from glob import glob
from pathlib import Path
import re
from typing import Optional

from mergedeep import merge
from yt_dlp.utils import sanitize_filename

from utils_python import download, get_logger_with_class, PathInput, get_tag_text_mp4

from yt_dlq.utils import YtdlqLogger
from yt_dlq.url.utils import parse_url

LOGGER = get_logger_with_class(__name__, YtdlqLogger)


def filename_from_url(url):
    return url.split("/")[-1]


def video_id_from_file_name(path: PathInput):
    path = Path(path)
    pattern = r"\[([\w-]*)\](?:\.\w*)?$"
    m = re.search(pattern, path.name)
    if m is None:
        raise ValueError(f"Could not find video ID in {path.name=!r}")
    return m.group(1)

def video_id_from_file_meta(path: PathInput):
    path = Path(path)
    comment = get_tag_text_mp4(path, "comment")
    if not comment:
        raise ValueError(f"No 'comment' present in path '{path}'")

    comment_url_parsed = parse_url(comment)

    assert comment_url_parsed["category"] == "video"

    return comment_url_parsed["id"]


def restrict_filename(filename: str):
    return sanitize_filename(filename, restricted=True)


def resolve_json_files(json_file_expression: Path):
    return [Path(json_file) for json_file in glob(str(json_file_expression))]


def merge_json_files(json_files: list[Path]):
    url_info_dict = {}
    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as file:
            url_info_dict_part = json.load(file)
        url_info_dict_part_mutable = deepcopy(url_info_dict_part)

        for channel_id, channel_dict in url_info_dict_part.items():
            for playlist_id, playlist_dict in channel_dict["entries"].items():
                if playlist_dict["title"] and not playlist_id:
                    del url_info_dict_part_mutable[channel_id]["entries"][playlist_id]
                    playlist_id = restrict_filename(playlist_dict["title"])
                    playlist_dict["id"] = playlist_id
                    url_info_dict_part_mutable[channel_id]["entries"][
                        playlist_id
                    ] = playlist_dict
        merge(url_info_dict, url_info_dict_part_mutable)
    return url_info_dict


def download_ytdl():
    ytdl_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    ytdl_filename = filename_from_url(ytdl_url)
    download(ytdl_url, ytdl_filename)

def video_id_from_metadata(path: Path):
    ...
