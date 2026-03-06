from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os.path
import re
import sys
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime
from functools import partial
from pathlib import Path
from pprint import pformat, pprint
from typing import TYPE_CHECKING, Callable, Optional

from prettyprinter import cpprint
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, int_or_none

from utils_python import dump_data, get_logger_with_class, read_dict_from_file
from yt_dlq.args import ProgramArgsNamespace
from yt_dlq.patches import patch_extract_metadata_from_tabs, patch_releases_tab
from yt_dlq.types import PLAYLIST_CATEGORIES, UrlSet
from yt_dlq.utils import (
    DownloadErrorAgeRestricted,
    DownloadErrorMembersOnly,
    DownloadErrorPrivateVideo,
    DownloadErrorTOSViolation,
    DownloadErrorUnavailableVideo,
    YtdlqLogger,
    hyphenate_date,
    matches_filter,
    sorted_nested_with_entries,
    specify_download_error,
)

if TYPE_CHECKING:
    from typing import Iterable

    from yt_dlq.types import Url, UrlCategoryDict, UrlList

LOGGER = get_logger_with_class(__name__, YtdlqLogger)

pprint = partial(pprint, sort_dicts=False)
patch_extract_metadata_from_tabs()
# patch_releases_tab() # https://github.com/yt-dlp/yt-dlp/issues/6893

PATTERN_ID = r"[@\w\-]+"
PATTERN_QUERY_FULL = r"(?:\?[\w=\&]+)"
PATTERN_QUERY_CONTINUED = r"(?:[\w=\&\-%]+)"
PATTERN_CHANNEL_BASE = (
    # rf"https:\/\/(?:www\.|music\.)?youtube\.com(?:\/(?:c|channel|user))?\/{PATTERN_ID}"
    rf"https:\/\/(?:www\.)?youtube\.com(?:\/(?:c|channel|user))?\/({PATTERN_ID})"
)

PATTERN_YOUTUBE = r"^https:\/\/(?:youtu\.be\/|(?:www\.)?youtube\.com)"

URL_CATEGORY_PATTERNS = {
    "channel": rf"^({PATTERN_CHANNEL_BASE})(?:\/featured)?\/?$",
    "channel_releases": rf"^({PATTERN_CHANNEL_BASE}(?:\/releases){PATTERN_QUERY_FULL}?)\/?$",
    "channel_playlists": rf"^({PATTERN_CHANNEL_BASE}(?:\/playlists){PATTERN_QUERY_FULL}?)\/?$",
    "playlist": rf"^(https:\/\/(?:(?:www|music)\.)?youtube\.com\/playlist\?list=({PATTERN_ID}))\/?$",
    "channel_videos": rf"^({PATTERN_CHANNEL_BASE}(?:\/videos))\/?$",
    "video": rf"^(https:\/\/(?:youtu\.be\/|(?:(?:www|music)\.)?youtube\.com\/watch\?v=)({PATTERN_ID})){PATTERN_QUERY_CONTINUED}?\/?$",
}

DEFAULT_ALBUM_ARTIST_OVERRIDE_ID = "_playlists"
DEFAULT_ALBUM_ARTIST_OVERRIDE_TITLE = "Various Artists"
# this is the default "channel"/album artist which will
#   contain albums created using album override
# TODO: This will apply to singly downloaded videos as well - consider setting
#  to uploader if url list has one channel, and only using Various Artists if
#   multiple channels


def read_urls_from_file(filepath: Path, comment_char="#") -> UrlList:
    with open(filepath) as file:
        rawlines = file.readlines()
    url_list = []
    for rawline in rawlines:
        line = rawline.strip()
        if line and line[0] != comment_char:
            url_list.append(line.split(comment_char)[0].strip())
    return url_list


def parse_url(url: Url) -> dict:
    res = {
        "category": None,
        "id": None,
        "url": url,
    }
    for url_category, pattern in URL_CATEGORY_PATTERNS.items():
        match = re.match(pattern, url)
        if match:
            res["category"] = url_category
            res["id"] = match.group(2)
            if url_category == "video":
                res["url"] = f"https://www.youtube.com/watch?v={res['id']}"
            else:
                res["url"] = match.group(1)
            break
    if res["category"] is None:
        if not re.match(PATTERN_YOUTUBE, url):
            raise ValueError(f"Could not categorise URL '{url}' (not a valid URL?)")
        LOGGER.info(pformat(URL_CATEGORY_PATTERNS).replace("\\\\", "\\"))
        raise ValueError(f"Could not categorise URL '{url}'")
    return res


def get_url_category(url: Url) -> str | None:
    return parse_url(url)["category"]


def get_url_id(url: Url) -> str:
    return parse_url(url)["id"]


def categorise_urls(url_list: UrlList) -> UrlCategoryDict:
    url_dict_categorised: dict[Optional[str], UrlList] = (
        {"release": {}} | {k: {} for k in URL_CATEGORY_PATTERNS} | {None: {}}
    )
    unknown_urls: UrlSet = set()
    known_urls: UrlSet = set()
    for url in url_list:
        if url in (known_urls | unknown_urls):
            continue
        url_parsed_info = parse_url(url)
        url_category = url_parsed_info["category"]
        url_categorised = url_parsed_info["url"]
        if url_category is not None:
            known_urls.add(url)
            known_urls.add(url_categorised)
        else:
            LOGGER.warning(f"URL format not recognised: {url!r}")
            unknown_urls.add(url)
        url_dict_categorised[url_category][url_categorised] = ""
    del url_dict_categorised[None]
    return url_dict_categorised


def retrieve_info(
    ydl: YoutubeDL,
    url: str,
    category: str,
    counter: Optional[tuple[int, int]] = None,
    remaining: Optional[int] = None,
    info_func: Callable = lambda info: info["title"],
):
    assert (counter is None) != (
        remaining is None
    ), "must provide exactly 1 of 'counter' and 'remaining'"
    if counter is None:
        progress = f"{remaining} remaining"
    else:
        progress = f"{counter[0]}/{counter[1]}"
    # LOGGER.info(f"RETRIEVING INFO: {category} {progress} {url!r}")
    try:
        info = ydl.extract_info(url, download=False)
    except Exception as exc:
        breakpoint()
        pass
    LOGGER.info(f"RETRIEVED INFO: {category} {progress} {url!r} | {info_func(info)}")
    return info


def resolve_recursive_playlist_group(
    playlist_subgroup_url: str, playlist_subgroup_title
):
    breakpoint()
    playlist_group_urls_fixed_path = Path(
        Path(__file__).parent, "playlist_group_urls_fixed.json"
    )

    try:
        with open(playlist_group_urls_fixed_path, "r") as file:
            playlist_subgroup_urls_fixed = json.load(file)
    except FileNotFoundError:
        playlist_subgroup_urls_fixed = {}

    if playlist_subgroup_url in playlist_subgroup_urls_fixed:
        playlist_subgroup_url_fixed = playlist_subgroup_urls_fixed[
            playlist_subgroup_url
        ]
        LOGGER.info(f"URL resolved using {playlist_group_urls_fixed_path}")
    else:
        # TODO: distinguish between interactive and non-interactive?
        LOGGER.info("ERROR: Youtube served us a broken URL.")
        LOGGER.info(
            f"  Go to {playlist_subgroup_url!r}, navigate in the dropdown to {playlist_subgroup_title!r}"
        )
        playlist_subgroup_url_fixed = input("  Paste the resulting URL here: ")
        playlist_subgroup_urls_fixed[playlist_subgroup_url] = (
            playlist_subgroup_url_fixed
        )
        with open(playlist_group_urls_fixed_path, "w+") as file:
            json.dump(playlist_subgroup_urls_fixed, file, indent=2)
    return playlist_subgroup_url_fixed


def sort_playlist_groups(playlist_groups_resolved):
    # want "Albums & Singles" playlist group to be downloaded first
    albums_singles_key = "Albums & Singles"
    try:
        albums_singles_url = playlist_groups_resolved.pop(albums_singles_key)
    except KeyError:
        return playlist_groups_resolved
    return {albums_singles_key: albums_singles_url, **playlist_groups_resolved}

