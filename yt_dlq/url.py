from __future__ import annotations

import atexit
import json
import logging
import re
import sys
from copy import deepcopy
from datetime import datetime
from functools import partial
from pathlib import Path
from pprint import pprint
from typing import TYPE_CHECKING, Callable, Optional

from prettyprinter import cpprint
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, int_or_none

from utils_python import (
    dump_data,
    get_logger_with_class,
    read_dict_from_file,
)
from yt_dlq.args import ProgramArgsNamespace
from yt_dlq.file import generate_json_output_filename, restrict_filename
from yt_dlq.patches import patch_extract_metadata_from_tabs, patch_releases_tab
from yt_dlq.types import PLAYLIST_CATEGORIES, UrlSet
from yt_dlq.utils import YtdlqLogger, hyphenate_date

if TYPE_CHECKING:
    from typing import Iterable

    from yt_dlq.types import Url, UrlCategoryDict, UrlList

LOGGER = get_logger_with_class(__name__, YtdlqLogger)

pprint = partial(pprint, sort_dicts=False)
patch_extract_metadata_from_tabs()
# patch_releases_tab() # https://github.com/yt-dlp/yt-dlp/issues/6893

PATTERN_ID = r"[@\w\-]+"
PATTERN_QUERY = r"(?:\?[\w=\&]+)"
PATTERN_CHANNEL_BASE = (
    # rf"https:\/\/(?:www\.|music\.)?youtube\.com(?:\/(?:c|channel|user))?\/{PATTERN_ID}"
    rf"https:\/\/(?:www\.)?youtube\.com(?:\/(?:c|channel|user))?\/({PATTERN_ID})"
)

URL_CATEGORY_PATTERNS = {
    "channel": rf"^({PATTERN_CHANNEL_BASE})(?:\/featured)?\/?$",
    "channel_releases": rf"^({PATTERN_CHANNEL_BASE}(?:\/releases){PATTERN_QUERY}?)\/?$",
    "channel_playlists": rf"^({PATTERN_CHANNEL_BASE}(?:\/playlists){PATTERN_QUERY}?)\/?$",
    "playlist": rf"^(https:\/\/(?:www\.)?youtube\.com\/playlist\?list=({PATTERN_ID}))\/?$",
    "channel_videos": rf"^({PATTERN_CHANNEL_BASE}(?:\/videos))\/?$",
    "video": rf"^(https:\/\/(?:youtu\.be\/|(?:www\.)?youtube\.com\/watch\?v=)({PATTERN_ID})){PATTERN_QUERY}?\/?$",
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
    return res


def get_url_category(url: Url) -> str | None:
    return parse_url(url)["category"]


def get_url_id(url: Url) -> str:
    return parse_url(url)["id"]


def categorise_urls(url_list: UrlList) -> UrlCategoryDict:
    url_dict_categorised: dict[Optional[str], UrlList] = (
        {"release": []} | {k: [] for k in URL_CATEGORY_PATTERNS} | {None: []}
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
        url_dict_categorised[url_category].append(url_categorised)
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


class YoutubeInfoExtractor:
    def __init__(self, args: ProgramArgsNamespace) -> None:
        self.args = args
        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
        }
        self.ydl = YoutubeDL(params=ydl_opts)
        self.url_to_channel_id = {}
        self.channel_id_to_channel_title = {}
        self.url_info_dict = {}
        self.url_info_dict_path: Path | None = None
        self.seen_video_ids = set()

    def load_info_dict_from_path(self, allow_empty=False):
        if self.url_info_dict_path:
            loaded_url_info_dict = read_dict_from_file(self.url_info_dict_path)
            if loaded_url_info_dict or allow_empty:
                self.url_info_dict = loaded_url_info_dict
                self.apply_seen_videos()

    def apply_seen_videos(self):
        for channel_dict in self.url_info_dict.values():
            for playlist_dict in channel_dict["entries"].values():
                for video_dict in playlist_dict["entries"].values():
                    self.seen_video_ids.add(video_dict["id"])

    def construct_url_info_dict(
        self,
        urls_input_list: UrlCategoryDict,
    ):
        urls_input_dict_categorised = categorise_urls(urls_input_list)
        urls_input_dict_channels_resolved = self.resolve_channel_urls(
            urls_input_dict_categorised
        )
        urls_input_dict_resolved = self.resolve_playlist_groups(
            urls_input_dict_channels_resolved, self.args
        )
        self.load_info_dict_from_path()
        self.add_playlists_to_url_info_dict(urls_input_dict_resolved)
        self.add_channels_to_url_info_dict(urls_input_dict_resolved)
        self.add_videos_to_url_info_dict(urls_input_dict_resolved)
        self.fill_metadata()
        return self.url_info_dict

    def persist_url_info_dict(self):
        if self.url_info_dict_path is not None:
            dump_data(self.url_info_dict, self.url_info_dict_path)

    def add_playlists_to_url_info_dict(
        self,
        urls_input: UrlCategoryDict,
        playlist_categories_ordered: Iterable[str] = PLAYLIST_CATEGORIES,
        disallow_duplicates_in: Iterable[str] = (),
    ):
        """
        iterate through playlist groups in given order
        if duplicates are disallowed for a group and a video in it has been
         previously encountered, first one encountered takes preference
        """

        for playlist_category in playlist_categories_ordered:
            playlist_urls = urls_input[playlist_category]
            for i, playlist_url in enumerate(playlist_urls):
                # get info from downloader
                LOGGER.info(
                    f"RETRIEVING INFO: {playlist_category} {i+1}/{len(playlist_urls)} {playlist_url!r}"
                )
                playlist_info = self.ydl.extract_info(playlist_url, download=False)
                playlist_entries = playlist_info["entries"]

                # set channel properties
                if self.args.no_channels:
                    ch_id = ""
                    ch_title = ""
                    ch_url = ""
                elif self.args.albumartist_override:
                    ch_id = self.args.albumartist_override
                    ch_title = self.args.albumartist_override
                    ch_url = ""
                elif self.args.album_override:
                    ch_id = DEFAULT_ALBUM_ARTIST_OVERRIDE_ID
                    ch_title = DEFAULT_ALBUM_ARTIST_OVERRIDE_TITLE
                    ch_url = ""
                elif self.url_to_channel_id.get(playlist_url) is not None:
                    ch_id = self.url_to_channel_id[playlist_url]
                    ch_title = self.channel_id_to_channel_title.get(ch_id)
                    ch_url = f"https://www.youtube.com/channel/{ch_id}"
                else:
                    ch_id = (
                        playlist_info["channel_id"] or playlist_entries[0]["channel_id"]
                    )
                    ch_title = (
                        playlist_info["channel"] or playlist_entries[0]["channel"]
                    )
                    ch_url = (
                        playlist_info["channel_url"]
                        or f"https://www.youtube.com/channel/{ch_id}"
                    )

                # set playlist properties
                if self.args.album_override:
                    pl_id = self.args.album_override
                    pl_title = self.args.album_override
                    pl_url = ""
                else:
                    pl_id = playlist_info["id"]
                    pl_title = playlist_info["title"]
                    pl_url = playlist_info["webpage_url"]

                # create or load channel dict
                if ch_id in self.url_info_dict:
                    channel_dict = self.url_info_dict[ch_id]
                else:
                    channel_dict = {
                        "id": ch_id,
                        "type": "channel",
                        "title": ch_title,
                        "url": ch_url,
                        "entries": {},
                    }
                    self.url_info_dict[ch_id] = channel_dict
                    self.persist_url_info_dict()  # added channel for playlist

                # create or load playlist dict
                if pl_id in channel_dict["entries"]:
                    playlist_dict = channel_dict["entries"][pl_id]
                else:
                    playlist_dict = {
                        "id": pl_id,
                        "type": playlist_category,
                        "title": pl_title,
                        "url": pl_url,
                        "music_info": playlist_info["music_info"],
                        "entries": {},
                        "description": playlist_info["description"],
                    }
                    channel_dict["entries"][pl_id] = playlist_dict
                    self.persist_url_info_dict()  # added playlist for playlist

                # add videos (unless disallowed duplicate)
                for idx, video_entry in enumerate(playlist_entries):
                    video_id = video_entry["id"]
                    if (
                        playlist_category in disallow_duplicates_in
                        and video_id in self.seen_video_ids
                    ) or video_id in playlist_dict["entries"]:
                        LOGGER.info(
                            f" SKIPPING SEEN INFO: {playlist_category} video {idx+1}/{len(playlist_entries)} {video_entry['url']!r}"
                        )
                        continue

                    LOGGER.info(
                        f" RETRIEVING INFO: {playlist_category} video {idx+1}/{len(playlist_entries)} {video_entry['url']!r}"
                    )
                    try:
                        video_info_full = self.ydl.extract_info(
                            video_entry["url"], download=False
                        )
                    except DownloadError as exc:
                        continue

                    video_info = self.get_info(video_entry["url"])
                    video_dict = {
                        "id": video_id,
                        "type": "video",
                        "title": video_entry["title"],
                        "url": video_entry["url"],
                        "upload_date": hyphenate_date(video_info_full["upload_date"]),
                        "uploader": video_entry["channel_url"],
                        "index": idx + 1,
                        "music_info": self.music_info_from_description(video_info),
                        "description": video_info["description"],
                        "duration": video_info["duration"],
                    }

                    playlist_dict["entries"][video_id] = video_dict
                    self.persist_url_info_dict()  # added video for playlist

                    self.seen_video_ids.add(video_id)

    def add_channels_to_url_info_dict(
        self,
        urls_input: UrlCategoryDict,
    ):
        channel_videos_urls = urls_input["channel_videos"]
        for i, channel_videos_url in enumerate(channel_videos_urls):
            # get info from downloader
            LOGGER.info(
                f"RETRIEVING INFO: channel {i+1}/{len(channel_videos_urls)} {channel_videos_url!r}"
            )
            channel_videos_info = self.ydl.extract_info(
                channel_videos_url, download=False
            )
            channel_videos_entries = channel_videos_info["entries"]

            # set channel properties
            if self.args.no_channels:
                ch_id = ""
                ch_title = ""
                ch_url = ""
            elif self.args.albumartist_override:
                ch_id = self.args.albumartist_override
                ch_title = self.args.albumartist_override
                ch_url = ""
            elif self.args.album_override:
                ch_id = DEFAULT_ALBUM_ARTIST_OVERRIDE_ID
                ch_title = DEFAULT_ALBUM_ARTIST_OVERRIDE_TITLE
                ch_url = ""
            else:
                ch_id = channel_videos_info["channel_id"]
                ch_title = channel_videos_info["channel"]
                ch_url = channel_videos_info["channel_url"]

            # set playlist properties
            if self.args.album_override:
                pl_id = self.args.album_override
                pl_title = self.args.album_override
                pl_url = ""
            else:
                pl_id = ""
                pl_title = ""
                pl_url = ""

            # create or load channel dict
            if ch_id in self.url_info_dict:
                channel_dict = self.url_info_dict[ch_id]
            else:
                channel_dict = {
                    "id": ch_id,
                    "type": "channel",
                    "title": ch_title,
                    "url": ch_url,
                    "entries": {},
                    "description": channel_videos_info["description"],
                }
                self.url_info_dict[ch_id] = channel_dict
                self.persist_url_info_dict()  # added channel for channel

            # why was this added...?
            # if pl_id in channel_dict["entries"]:
            #     continue

            # create or load playlist dict
            if pl_id in channel_dict["entries"]:
                playlist_dict = channel_dict["entries"][pl_id]
            else:
                playlist_dict = {
                    "id": pl_id,
                    "type": "videos_loose",
                    "title": pl_title,
                    "url": pl_url,
                    "entries": {},
                }
                channel_dict["entries"][pl_id] = playlist_dict
                self.persist_url_info_dict()  # added playlist for channel

            # add videos not previously seen
            for idx, video_entry in enumerate(channel_videos_entries):
                video_id = video_entry["id"]
                if (
                    video_id in self.seen_video_ids
                    or video_id in playlist_dict["entries"]
                ):
                    LOGGER.info(
                        f" SKIPPING SEEN INFO: channel video {idx+1}/{len(channel_videos_entries)} {video_entry['url']!r}"
                    )
                    continue

                LOGGER.info(
                    f" RETRIEVING INFO: channel video {idx+1}/{len(channel_videos_entries)} {video_entry['url']!r}"
                )
                try:
                    video_info_full = self.ydl.extract_info(
                        video_entry["url"], download=False
                    )
                except DownloadError as exc:
                    continue
                video_dict = {
                    "id": video_entry["id"],
                    "type": "video",
                    "title": video_entry["title"],
                    "url": video_entry["url"],
                    "upload_date": hyphenate_date(video_info_full["upload_date"]),
                    "uploader": ch_url,
                    "description": video_info_full["description"],
                    "duration": video_info_full["duration"],
                }
                playlist_dict["entries"][video_entry["id"]] = video_dict
                self.persist_url_info_dict()  # added video for channel
                self.seen_video_ids.add(video_entry["id"])

    def add_videos_to_url_info_dict(
        self,
        urls_input: UrlCategoryDict,
    ):
        video_urls = urls_input["video"]
        for i, video_url in enumerate(video_urls):
            video_id = get_url_id(video_url)

            # only add videos not previously seen
            if video_id in self.seen_video_ids:
                LOGGER.info(
                    f"SKIPPING SEEN INFO: video {i+1}/{len(video_urls)} {video_url!r}"
                )
                continue

            LOGGER.info(f"RETRIEVING INFO: video {i+1}/{len(video_urls)} {video_url!r}")
            # get info from downloader
            try:
                video_info = self.ydl.extract_info(video_url, download=False)
            except DownloadError as exc:
                continue

            # set channel properties
            if self.args.no_channels:
                ch_id = ""
                ch_title = ""
                ch_url = ""
            elif self.args.albumartist_override:
                ch_id = self.args.albumartist_override
                ch_title = self.args.albumartist_override
                ch_url = ""
            elif self.args.album_override:
                ch_id = DEFAULT_ALBUM_ARTIST_OVERRIDE_ID
                ch_title = DEFAULT_ALBUM_ARTIST_OVERRIDE_TITLE
                ch_url = ""
            else:
                ch_id = video_info["channel_id"]
                ch_title = video_info["channel"]
                ch_url = video_info["channel_url"]

            # set playlist properties
            if self.args.album_override:
                pl_id = self.args.album_override
                pl_title = self.args.album_override
                pl_url = ""
            else:
                pl_id = ""
                pl_title = ""
                pl_url = ""

            # create or load channel dict
            if ch_id in self.url_info_dict:
                channel_dict = self.url_info_dict[ch_id]
            else:
                channel_dict = {
                    "id": ch_id,
                    "type": "channel",
                    "title": ch_title,
                    "url": ch_url,
                    "entries": {},
                }
                self.url_info_dict[ch_id] = channel_dict
                self.persist_url_info_dict()  # added channel for loose-video

            # create or load playlist dict
            if pl_id in channel_dict["entries"]:
                playlist_dict = channel_dict["entries"][pl_id]
            else:
                playlist_dict = {
                    "id": pl_id,
                    "type": "videos_loose",
                    "title": pl_title,
                    "url": pl_url,
                    "entries": {},
                }
                channel_dict["entries"][pl_id] = playlist_dict
                self.persist_url_info_dict()  # added playlist for loose-video

            video_dict = {
                "id": video_id,
                "type": "video",
                "title": video_info["title"],
                "url": video_info["webpage_url"],
                "upload_date": hyphenate_date(video_info["upload_date"]),
                "uploader": video_info["uploader_url"],
                "description": video_info["description"],
                "duration": video_info["duration"],
            }
            playlist_dict["entries"][video_id] = video_dict
            self.persist_url_info_dict()  # added video for loose-video
            self.seen_video_ids.add(video_id)

    def get_info(self, url: str):
        return self.ydl.extract_info(url, download=False)

    def get_title(self, url: str):
        category = get_url_category(url)
        info = self.ydl.extract_info(url, download=False)
        if info["id"].startswith("@"):
            channel_name = info["id"]
        else:
            channel_name = info["channel"]

        item_title = info["title"]

        channel_name = restrict_filename(channel_name)
        item_title = restrict_filename(item_title)
        match category:
            case "channel":
                title = channel_name
            case "channel_releases":
                title = item_title
            case "channel_playlists":
                title = item_title
            case "playlist":
                title = f"{channel_name} {item_title}"
            case "channel_videos":
                title = item_title
            case "video":
                title = f"{channel_name} {item_title}"
            case _:
                title = item_title
        return title

    def music_info_from_url(self, url: str):
        video_info = self.get_info(url)
        return self.music_info_from_description(video_info)

    def music_info_from_description(self, info: dict, hyphenate_date=True):
        info_out = {}
        if (video_description := info.get("description")) is None:
            return info_out
        else:
            # Youtube Music Auto-generated description (modified from yt-dlp)
            mobj = re.search(
                r"""(?xs)
                    (?P<track>[^·\n]+)·(?P<artist>[^\n]+)\n+
                    (?P<album>[^\n]+)
                    (?:.+?℗\s*(?P<release_year>\d{4})(?!\d))?
                    (?:.+?Released on\s*:\s*(?P<release_date>\d{4}-\d{2}-\d{2}))?
                    (.+?\nArtist\s*:\s*(?P<clean_artist>[^\n]+))?
                    .+\nAuto-generated\ by\ YouTube\.\s*$
                """,
                video_description,
            )
            if mobj:
                release_year = mobj.group("release_year")
                release_date = mobj.group("release_date")
                if release_date:
                    if not hyphenate_date:
                        release_date = release_date.replace("-", "")
                    if not release_year:
                        release_year = release_date[:4]
                info_out = {
                    "album": mobj.group("album".strip()),
                    "artists": (
                        clean_artist
                        if (clean_artist := mobj.group("clean_artist"))
                        else [a.strip() for a in mobj.group("artist").split("·")]
                    ),
                    "track": mobj.group("track").strip(),
                    "release_date": release_date,
                    "release_year": int_or_none(release_year),
                }
            return info_out

    def resolve_channel_urls(
        self, url_dict_categorised: UrlCategoryDict
    ) -> UrlCategoryDict:
        url_dict_new = deepcopy(url_dict_categorised)
        channel_urls = url_dict_new.pop("channel")
        while len(channel_urls) > 0:
            url = channel_urls.pop()
            try:
                url_releases = f"{url}/releases"
                self.ydl.extract_info(url_releases, download=False)
                if "release" not in url_dict_new:
                    url_dict_new = {"channel_releases": [], **url_dict_new}
                url_dict_new["channel_releases"].append(url_releases)
            except DownloadError as exc:
                pass
            url_dict_new["channel_playlists"].append(f"{url}/playlists")
            url_dict_new["channel_videos"].append(f"{url}/videos")
        urls_from_channel = {}
        for category in PLAYLIST_CATEGORIES:
            urls_from_channel.setdefault(category, [])
            for channel_category_url in url_dict_new.pop(f"channel_{category}s"):
                channel_category_info = self.get_info(channel_category_url)
                for entry in channel_category_info["entries"]:
                    entry_url = entry["url"]
                    self.url_to_channel_id[entry_url] = channel_category_info[
                        "uploader_id"
                    ]
                    self.channel_id_to_channel_title[
                        channel_category_info["uploader_id"]
                    ] = channel_category_info["uploader"]
                    urls_from_channel[category].append(entry_url)
        url_dict_resolved = {
            category: urls_from_channel.get(category, [])
            + url_dict_new.get(category, [])
            for category in url_dict_new.keys()
        }
        return url_dict_resolved

    def resolve_playlist_groups(
        self, urls_input: dict[str, set[str]], args: ProgramArgsNamespace
    ):
        """turns playlist groups into playlists"""
        ydl = self.ydl
        playlist_groups_resolved_tab = {}
        urls_group_playlist = urls_input["playlist"]
        playlist_urls_resolved = set()
        for i, playlist_group_url in enumerate(urls_group_playlist):
            # playlist group e.g. https://www.youtube.com/c/daftpunk/playlists or
            # playlist subgroup e.g. https://www.youtube.com/c/daftpunk/playlists?view=71&sort=dd&shelf_id=0
            playlist_group_info = retrieve_info(
                ydl=ydl,
                category="playlist group",
                url=playlist_group_url,
                counter=(i + 1, len(urls_group_playlist)),
            )
            playlist_group_contents_unresolved = playlist_group_info["entries"]
            # LOGGER.info(pformat(playlist_group_contents_unresolved))
            playlist_group_content_categories = {
                get_url_category(entry["url"])
                for entry in playlist_group_contents_unresolved
            }
            if playlist_group_content_categories == {"playlist"}:
                playlist_urls_resolved |= {
                    playlist["url"] for playlist in playlist_group_contents_unresolved
                }
                continue
            elif playlist_group_content_categories == {"video"}:
                if playlist_group_info["id"].startswith("FL"):
                    LOGGER.info(
                        f" ^ SKIPPING Favourites playlist ({playlist_group_info['title']=}) ^ "
                    )
                else:
                    playlist_urls_resolved.add(playlist_group_url)
                continue
            raise NotImplementedError
            ## only to be updated if able to reproduce issue:
            # for i, playlist_subgroup_entry in enumerate(
            #     playlist_group_contents_unresolved
            # ):
            #     # LOGGER.info(pformat(playlist_subgroup_entry))
            #     playlist_subgroup_title = playlist_subgroup_entry["title"]
            #     playlist_subgroup_url = playlist_subgroup_entry["url"]
            #     while True:
            #         playlist_subgroup_info = retrieve_info(
            #             ydl=ydl,
            #             category="playlist subgroup",
            #             url=playlist_subgroup_url,
            #             counter=(i + 1, len(playlist_group_contents_unresolved)),
            #             info_func=lambda *args: playlist_subgroup_title,
            #         )
            #         if playlist_subgroup_url not in {
            #             entry["url"] for entry in playlist_subgroup_info["entries"]
            #         }:
            #             playlist_groups_resolved["playlist"][
            #                 playlist_subgroup_title
            #             ] = playlist_subgroup_url
            #             break
            #         else:
            #             playlist_subgroup_url = resolve_recursive_playlist_group(
            #                 playlist_subgroup_url, playlist_subgroup_title
            #             )
            # playlist_subgroup_children = playlist_subgroup_info["entries"]
            # playlist_subgroup_children_urls = {
            #     child["url"] for child in playlist_subgroup_children
            # }

        # playlist_urls_resolved.extend(playlist_groups_resolved_tab.values())
        return {**urls_input, "playlist": playlist_urls_resolved}

    def fill_metadata(self):
        for channel_info in self.url_info_dict.values():
            for playlist_info in channel_info["entries"].values():
                for field_name in ("album", "release_year"):
                    try:
                        fields_debug = {
                            (video_info["title"], video_info["url"]): video_info[
                                "music_info"
                            ][field_name]
                            for video_info in playlist_info["entries"].values()
                            if video_info.get("music_info")
                            and video_info["music_info"].get(field_name)
                        }
                    except Exception as exc:
                        breakpoint()
                        pass

                    fields_list = list(fields_debug.values())
                    fields_set = set(fields_debug.values())
                    if len(fields_set) > 1:
                        field = max(fields_set, key=fields_list.count)
                        LOGGER.warning(
                            f"Got conflicting {field_name!r}: {fields_set}. choosing most common: {field}"
                        )
                    elif len(fields_set) == 1:
                        field = fields_set.pop()
                    elif field_name == "album" and playlist_info["title"]:
                        field = playlist_info["title"]
                    else:
                        continue
                    for video_info in playlist_info["entries"].values():
                        video_info.setdefault("music_info", {})[field_name] = field
                    playlist_info.setdefault("music_info", {})[field_name] = field


def get_all_urls_dict(args: ProgramArgsNamespace):
    if args.batchfile:
        urls_input_list = read_urls_from_file(args.batchfile)
    else:
        urls_input_list = args.urls

    yie = YoutubeInfoExtractor(args)

    if args.use_archives:
        if args.json_file_prefix is None and len(urls_input_list) == 1:
            json_file_prefix = yie.get_title(urls_input_list[0])
        else:
            json_file_prefix = args.json_file_prefix
        json_output_filename = restrict_filename(f"{json_file_prefix}.json")
        json_output_filepath = Path(args.output_dir, "_json", json_output_filename)
        yie.url_info_dict_path = json_output_filepath
    url_info_dict = yie.construct_url_info_dict(urls_input_list)

    if args.use_archives:
        atexit.register(
            lambda: show_retrieved_urls_filepath(json_output_filepath, args)
        )

    # with open(json_output_filepath, "w+") as file:
        # json.dump(url_info_dict, file, indent=4)
    return url_info_dict


def show_retrieved_urls_filepath(json_output_filepath, args):
    if not json_output_filepath:
        return
    LOGGER.info(
        "\nTo skip URL retrieval next time, run:\n"
        f"yt-dlq -j {str(json_output_filepath)!r} -o {args.output_dir}\n"
    )
