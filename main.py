# from pprint import pprint

import argparse
import atexit
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from pdb import set_trace
from typing import Optional

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from utils.file import make_parent_dir, restrict_filename
from utils.state import get_download_state, set_download_state
from utils.string import URL_TYPE_PATTERNS
from utils.types import DownloadStates


class ProgramArgsNamespace(
    argparse.Namespace
):  # pylint: disable=too-few-public-methods
    url: str
    batchfile: Path
    permit_single: bool
    json_file: Path
    output_dir: Path
    playlist_duplicates: bool
    text_placeholders: bool
    ffmpeg_location: Path
    use_archives: bool
    no_channels: bool
    data_only: bool
    output_format: str


def process_args():
    parser = argparse.ArgumentParser()
    chosen_url_group = parser.add_mutually_exclusive_group(required=True)
    chosen_url_group.add_argument(
        "-j",
        "--json-file",
        metavar="FILE",
        help="File previously generated by this program containing URLs to download",
        type=Path,
    )
    chosen_url_group.add_argument(
        "-a",
        "--batch-file",
        dest="batchfile",
        metavar="FILE",
        help=(
            "File containing URLs to download, one URL per line. "
            'Lines starting with "#" are considered as comments and ignored'
        ),
        type=Path,
    )
    chosen_url_group.add_argument(
        "url",
        metavar="URL",
        help="URL to download",
        nargs="?",
    )

    parser.add_argument(
        "-p",
        "--permit-single",
        action="store_true",
        help=(
            "Allow playlists with only one video to have their own folder. "
            "Otherwise, ignore such videos and treat them as not having a playlist."
        ),
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        metavar="FOLDER",
        help="Main folder to store downloaded videos and other info (default: %(default)s)",
        default="data",
        type=Path,
    )
    parser.add_argument(
        "--ffmpeg-location",
        metavar="PATH",
        help="Location of the ffmpeg binary; either the path to the binary or its containing directory",
    )
    duplicate_handler_group = parser.add_mutually_exclusive_group()
    duplicate_handler_group.add_argument(
        "-b",
        "--playlist-duplicates",
        action="store_true",
        help=(
            "Allow videos to be downloaded multiple times if they are in multiple playlists."
        ),
    )
    duplicate_handler_group.add_argument(
        "-t",
        "--text-placeholders",
        action="store_true",
        help=(
            "Create text file placeholders instead of duplicating videos in multiple playlists"
        ),
    )
    duplicate_handler_group.add_argument(
        "-n",
        "--no-archives",
        action="store_false",
        dest="use_archives",
        help=(
            "Don't read or write any archive files (apart from those passed as arguments to the program)"
        ),
    )
    parser.add_argument(
        "-g",
        "--no-channels",
        action="store_true",
        help="Don't split downloads into folder by channel",
    )
    parser.add_argument(
        "-d",
        "--data-only",
        action="store_true",
        help="Only retrieve URLs; don't download videos",
    )
    parser.add_argument(
        "-f",
        "--output-format",
        choices=["mp3", "m4a"],
        default="m4a",
        help="Output audio file format",
    )

    parsed = parser.parse_args(namespace=ProgramArgsNamespace())
    return parsed


def get_url_type(url):
    for url_type, pattern in URL_TYPE_PATTERNS.items():
        match = re.match(pattern, url)
        if match:
            if url_type == "video":
                video_id = match.group(2)
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                url = match.group(1)
            return url_type, url
    return None, url


def process_urls_input(urls_input: list[str]):
    urls_processed_dict: dict[Optional[str], set] = {
        k: set() for k in URL_TYPE_PATTERNS
    } | {None: set()}
    unknown_urls: set[str] = set()
    known_urls: set[str] = set()
    for url in urls_input:
        if url in (known_urls | unknown_urls):
            continue
        url_type, url_processed = get_url_type(url)
        if url_type:
            known_urls.add(url)
            known_urls.add(url_processed)
        else:
            print(f"URL format not recognised: {url!r}")
            unknown_urls.add(url)
        urls_processed_dict[url_type].add(url_processed)
    return urls_processed_dict


def get_urls_input(args: ProgramArgsNamespace):
    comment_char = "#"
    if args.batchfile:
        with open(args.batchfile) as file:
            urls_input = []
            for rawline in file.readlines():
                line = rawline.strip()
                if line and line[0] != comment_char:
                    urls_input.append(line.split(comment_char)[0].strip())
    else:
        urls_input = [args.url]
    return process_urls_input(urls_input)


def construct_all_urls_dict(urls_input, args: ProgramArgsNamespace):
    all_urls_dict = {}
    channel_dict = {}
    seen_video_ids = set()
    with YoutubeDL(
        params={
            "extract_flat": True,
            "quiet": True,
        }
    ) as ydl:
        playlist_urls = resolve_playlist_groups(ydl, urls_input, args)
        # print(playlist_urls, len(playlist_urls))
        for i, playlist_url in enumerate(playlist_urls):
            print(
                f"RETRIEVING INFO: playlist {i+1}/{len(playlist_urls)} {playlist_url!r}"
            )
            playlist_info = ydl.extract_info(playlist_url, download=False)
            playlist_entries = playlist_info["entries"]
            if not args.permit_single and len(playlist_entries) == 1:
                urls_input["video"].add(playlist_entries[0]["url"])
                continue
            # playlist_entries_urls = [child["url"] for child in playlist_entries]
            pl_channel_id = (
                (playlist_info["channel_id"] or playlist_entries[0]["channel_id"])
                if not args.no_channels
                else ""
            )
            pl_channel_title = (
                (playlist_info["channel"] or playlist_entries[0]["channel"])
                if not args.no_channels
                else ""
            )
            pl_channel_url = (
                (
                    playlist_info["channel_url"]
                    or f"https://www.youtube.com/channel/{pl_channel_id}"
                )
                if not args.no_channels
                else ""
            )
            pl_title = playlist_info["title"]
            pl_id = playlist_info["id"]
            pl_url = playlist_info["webpage_url"]
            if pl_channel_id not in all_urls_dict:
                channel_dict = {
                    "id": pl_channel_id,
                    "type": "channel",
                    "title": pl_channel_title,
                    "url": pl_channel_url,
                    "entries": {},
                }
                all_urls_dict[pl_channel_id] = channel_dict
            else:
                channel_dict = all_urls_dict[pl_channel_id]
            playlist_dict = {
                "id": pl_id,
                "type": "playlist",
                "title": pl_title,
                "url": pl_url,
                "entries": {},
            }
            channel_dict["entries"][pl_id] = playlist_dict
            for idx, video_entry in enumerate(playlist_entries):
                video_dict = {
                    "id": video_entry["id"],
                    "type": "video",
                    "title": video_entry["title"],
                    "url": video_entry["url"],
                    "uploader": video_entry["channel_url"],
                    "index": idx + 1,
                }
                playlist_dict["entries"][video_entry["id"]] = video_dict
                seen_video_ids.add(video_entry["id"])
        for i, channel_videos_url in enumerate(urls_input["channel_group_videos"]):
            print(
                f"RETRIEVING INFO: channel {i+1}/{len(urls_input['channel_group_videos'])} {channel_videos_url!r}"
            )
            channel_videos_info = ydl.extract_info(channel_videos_url, download=False)
            # pprint(channel_videos_info)
            ch_id = channel_videos_info["channel_id"] if not args.no_channels else ""
            ch_title = channel_videos_info["channel"] if not args.no_channels else ""
            ch_url = channel_videos_info["channel_url"] if not args.no_channels else ""

            pl_id = ""
            pl_title = ""
            pl_url = ""

            if ch_id in all_urls_dict:
                channel_dict = all_urls_dict[ch_id]
                if pl_id in channel_dict["entries"]:
                    continue
            else:
                channel_dict = {
                    "id": ch_id,
                    "type": "channel",
                    "title": ch_title,
                    "url": ch_url,
                    "entries": {},
                }
                all_urls_dict[ch_id] = channel_dict

            playlist_dict = {
                "id": pl_id,
                "type": "videos_loose",
                "title": pl_title,
                "url": pl_url,
                "entries": {},
            }
            channel_dict["entries"][pl_id] = playlist_dict
            # pprint(all_dict, sort_dicts=False)
            channel_videos_entries = channel_videos_info["entries"]
            for video_entry in channel_videos_entries:
                if video_entry["id"] in seen_video_ids:
                    continue
                video_dict = {
                    "type": "video",
                    "title": video_entry["title"],
                    "url": video_entry["url"],
                    "id": video_entry["id"],
                    "uploader": ch_url,
                }
                playlist_dict["entries"][video_entry["id"]] = video_dict
                seen_video_ids.add(video_entry["id"])
        for i, video_url in enumerate(urls_input["video"]):
            print(
                f"RETRIEVING INFO: video {i+1}/{len(urls_input['video'])} {video_url!r}"
            )
            video_info = ydl.extract_info(video_url, download=False)
            ch_id = video_info["channel_id"] if not args.no_channels else ""
            ch_title = video_info["channel"] if not args.no_channels else ""
            ch_url = video_info["channel_url"] if not args.no_channels else ""

            pl_id = ""
            pl_title = ""
            pl_url = ""

            v_id = video_info["id"]
            v_title = video_info["title"]
            v_url = video_info["webpage_url"]
            v_uploader = video_info["uploader_url"]
            if v_id in seen_video_ids:
                continue
            if ch_id in all_urls_dict:
                channel_dict = all_urls_dict[ch_id]
            else:
                channel_dict = {
                    "id": ch_id,
                    "type": "channel",
                    "title": ch_title,
                    "url": ch_url,
                    "entries": {},
                }
                all_urls_dict[ch_id] = channel_dict

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

            video_dict = {
                "type": "video",
                "title": v_title,
                "url": v_url,
                "id": v_id,
                "uploader": v_uploader
            }
            playlist_dict["entries"][v_id] = video_dict
            seen_video_ids.add(v_id)
    return all_urls_dict


def resolve_playlist_groups(ydl, urls_input, args):
    playlist_urls = set(urls_input["playlist"])
    playlist_group_urls = sorted(list(urls_input["channel_group_playlists"]))
    for (i, playlist_group_url) in enumerate(playlist_group_urls):
        # playlist group or subgroup, e.g.
        #   https://www.youtube.com/c/daftpunk/playlists
        #   https://www.youtube.com/c/daftpunk/playlists?view=71&sort=dd&shelf_id=0
        print(
            f"RETRIEVING INFO: group {i+1}/{len(playlist_group_urls)} {playlist_group_url!r}"
        )
        playlist_group_info = ydl.extract_info(playlist_group_url, download=False)
        playlist_group_children_unresolved = playlist_group_info["entries"]
        playlist_group_children_urls_titles = {
            playlist["url"]: playlist["title"]
            for playlist in playlist_group_children_unresolved
        }
        playlist_group_children_urls_list = list(
            playlist_group_children_urls_titles.keys()
        )

        # sort group children urls into playlist subgroups and playlists
        playlist_group_children_urls_types = {
            k: v
            for k, v in process_urls_input(playlist_group_children_urls_list).items()
            if k and "playlist" in k
        }
        # pprint(playlist_group_children_urls_types)

        playlist_urls |= playlist_group_children_urls_types["playlist"]
        playlist_subgroup_urls = playlist_group_children_urls_types[
            "channel_group_playlists"
        ]
        # pprint(playlist_subgroup_urls)

        while len(playlist_subgroup_urls) > 0:
            playlist_subgroup_url = playlist_subgroup_urls.pop()
            print(
                f"RETRIEVING INFO:  playlist subgroup ({len(playlist_subgroup_urls)+1} left) {playlist_subgroup_url!r}"
            )
            playlist_subgroup_info = ydl.extract_info(
                playlist_subgroup_url, download=False
            )
            # pprint(playlist_subgroup_info)
            playlist_subgroup_children = playlist_subgroup_info["entries"]
            # pprint(playlist_subgroup_url)
            # pprint(playlist_subgroup_children)
            playlist_subgroup_children_urls = {
                child["url"] for child in playlist_subgroup_children
            }
            # pprint(playlist_subgroup_children_urls)
            if playlist_subgroup_url in playlist_subgroup_children_urls:
                # we have a broken (infinite) youtube redirect
                playlist_group_urls_fixed_path = Path(
                    args.output_dir, "_json", "playlist_group_urls_fixed.json"
                )
                make_parent_dir(playlist_group_urls_fixed_path)
                try:
                    with open(playlist_group_urls_fixed_path, "r") as file:
                        playlist_group_urls_fixed = json.load(file)
                except FileNotFoundError:
                    playlist_group_urls_fixed = {}
                if playlist_subgroup_url in playlist_group_urls_fixed:
                    playlist_subgroup_url_fixed = playlist_group_urls_fixed[
                        playlist_subgroup_url
                    ]
                else:
                    print("ERROR: Youtube served us a broken URL.")
                    print(
                        f"  Go to {playlist_subgroup_url!r}, navigate in the dropdown to {playlist_group_children_urls_titles[playlist_subgroup_url]!r}"
                    )
                    playlist_subgroup_url_fixed = input(
                        "  Paste the resulting URL here: "
                    )
                    playlist_group_urls_fixed[
                        playlist_subgroup_url
                    ] = playlist_subgroup_url_fixed
                    with open(playlist_group_urls_fixed_path, "w+") as file:
                        json.dump(playlist_group_urls_fixed, file)

                playlist_subgroup_urls.add(playlist_subgroup_url_fixed)

            else:
                playlist_urls |= playlist_subgroup_children_urls
    return playlist_urls


def get_all_urls_dict(args: ProgramArgsNamespace):
    if args.json_file:
        with open(args.json_file, "r") as file:
            all_urls_dict = json.load(file)
    else:
        urls_input = get_urls_input(args)
        urls_channel_home = urls_input["channel_home"]
        while len(urls_channel_home) > 0:
            url = urls_channel_home.pop()
            urls_input["channel_group_playlists"].add(url + "/playlists")
            urls_input["channel_group_videos"].add(url + "/videos")
        del urls_input["channel_home"]
        del urls_input[None]

        all_urls_dict = construct_all_urls_dict(urls_input, args)
        if args.use_archives:
            json_output_filename = restrict_filename(
                f"urls_all_{datetime.now().replace(microsecond=0).isoformat()}.json"
            )
            json_output_filepath = Path(args.output_dir, "_json", json_output_filename)
            atexit.register(
                lambda: show_retrieved_urls_filepath(json_output_filepath, args)
            )
            make_parent_dir(json_output_filepath)
            with open(json_output_filepath, "w+") as file:
                json.dump(all_urls_dict, file, indent=4)
    return all_urls_dict


def show_retrieved_urls_filepath(json_output_filepath, args):
    if not json_output_filepath:
        return
    print(
        "\nTo skip URL retrieval next time, run:\n"
        f"python {sys.argv[0]} -j {str(json_output_filepath)!r} -o {args.output_dir}\n"
    )


def match_filter_func(info_dict):
    if info_dict.get("is_live") is True or info_dict.get("was_live") is True:
        return "Video is/was livestream; skipping"
    # if info_dict.get("availability") != 'public':
    #     return "Video is private; skipping"
    return None


def download_all(args: ProgramArgsNamespace, all_urls_dict):
    postprocessors = [
        # {
        #     'key': 'FFmpegExtractAudio',
        #     'preferredcodec': 'm4a',
        # },
        {"key": "FFmpegMetadata"},
        # {
        #     "key": "MetadataParser",
        #     "actions": [(MetadataParserPP.Actions.INTERPRET, "uploader", "%(artist)s")],
        # },
        # { "key" : "FFmpegVideoRemuxer", "preferedformat" : "mkv", }, # required for custom/arbitrary fields
    ]
    if args.output_format == "mp3":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        )
    ydl_opts = {
        "format": "m4a/bestaudio/best",
        "postprocessors": postprocessors,
        "postprocessor_args": {"ffmpeg": []},
        "restrictfilenames": True,
        "windowsfilenames": True,
        # "ignoreerrors": "only_download",
        # "postprocessors": None,
        # "ffmpeg_location": None,
        "match_filter": match_filter_func,
        "ffmpeg_location": args.ffmpeg_location,
    }
    failed_downloads = []
    with YoutubeDL(ydl_opts) as ydl:
        channels = all_urls_dict
        for ch_idx, (channel_id, channel) in enumerate(channels.items()):
            channel_dir = Path(args.output_dir, restrict_filename(channel["title"]))
            if channel_id:
                channel_archive_filename = restrict_filename(
                    f"videos_{channel['title']}.txt"
                )
                channel_archive_filename_json = restrict_filename(
                    f"videos_{channel['title']}.json"
                )
            else:
                channel_archive_filename = "videos.txt"
                channel_archive_filename_json = "videos.json"
            channel_archive_filepath = Path(channel_dir, channel_archive_filename)
            channel_archive_filepath_json = Path(
                channel_dir, channel_archive_filename_json
            )
            print(
                f"DOWNLOADING CHANNEL {ch_idx+1}/{len(channels)}: {channel['title']!r}"
            )
            playlists = channel["entries"]
            for pl_idx, (playlist_id, playlist) in enumerate(playlists.items()):
                print(
                    f" DOWNLOADING PLAYLIST {pl_idx+1}/{len(playlists)}",
                    end=" ",
                )
                archives_to_write = [channel_archive_filepath]
                ppa = [
                    "-metadata",
                    f"album_artist={channel['title']}",
                ]
                if playlist_id:
                    print(f"{playlist['title']!r}")
                    ppa += [
                        "-metadata",
                        f"album={playlist['title']}",
                        "-metadata",
                        "track=0",
                    ]
                    playlist_dir = Path(
                        channel_dir, restrict_filename(playlist["title"])
                    )
                    playlist_archive_filename = restrict_filename(
                        f"playlist_{playlist['title']}.txt"
                    )
                    playlist_archive_filepath = Path(
                        playlist_dir, playlist_archive_filename
                    )
                    archives_to_write.append(playlist_archive_filepath)
                    # archive_filename = playlist_archive_filename
                    # archive_filepath = playlist_archive_filepath
                else:
                    print(f"[loose videos] {channel['title']!r}")
                    ppa += [
                        "-metadata",
                        f"album=[Videos]{channel['title']}",
                    ]
                    playlist_dir = channel_dir
                    # archive_filename = channel_archive_filename
                    # archive_filepath = channel_archive_filepath
                channel_playlist_info = {
                    "channel_id": channel_id,
                    "channel_title": channel["title"],
                    "playlist_id": playlist_id,
                    "playlist_title": playlist["title"],
                }
                videos = playlist["entries"]
                for video_index, (video_id, video) in enumerate(videos.items()):
                    expected_path = Path(
                        playlist_dir,
                        f"{restrict_filename(video['title'])}[{video_id}].{args.output_format}",
                    )
                    placeholder_path = expected_path.with_suffix(".txt")
                    print(
                        f"  DOWNLOADING VIDEO {video_index+1}/{len(videos)}: {video['title']!r}",
                        end="",
                    )
                    if video["title"] == "[Private video]":
                        print(" - UNAVAILABLE; SKIPPING")
                        continue
                    remove_placeholder = False
                    if args.use_archives:
                        video_download_state = get_download_state(
                            video, channel_playlist_info, channel_archive_filepath_json
                        )
                        match video_download_state:
                            case DownloadStates.NEVER_DOWNLOADED:
                                is_duplicate = False
                            case DownloadStates.ORIGINAL_DOWNLOADED:
                                print(" - ALREADY DOWNLOADED IN PLAYLIST")
                                continue
                            case DownloadStates.DUPLICATE_DOWNLOADED:
                                print(" - ALREADY DOWNLOADED IN PLAYLIST")
                                continue
                            case DownloadStates.DUPLICATE_NOT_DOWNLOADED:
                                print(" - DOWNLOADED IN ANOTHER PLAYLIST", end="")
                                if args.playlist_duplicates:
                                    is_duplicate = True
                                    print(" (DUPLICATES ENABLED)")
                                elif args.text_placeholders:
                                    print(" - CREATING PLACEHOLDER")
                                    make_parent_dir(placeholder_path)
                                    open(placeholder_path, "w+").close()
                                    set_download_state(
                                        video,
                                        channel_playlist_info,
                                        channel_archive_filepath_json,
                                        DownloadStates.CREATED_PLACEHOLDER,
                                    )
                                    continue
                                else:
                                    print(" - SKIPPING")
                                    continue
                            case DownloadStates.CREATED_PLACEHOLDER:
                                if args.playlist_duplicates:
                                    print(" - OVERWRITING PLACEHOLDER")
                                    remove_placeholder = True
                                    is_duplicate = True
                                else:
                                    print(
                                        " - PLACEHOLDER PREVIOUSLY CREATED - SKIPPING"
                                    )
                                    continue
                            case _:
                                print(
                                    "Unhandled download state",
                                    repr(video_download_state),
                                )
                                input()
                    else:
                        video_download_state = DownloadStates.NEVER_DOWNLOADED

                    if playlist_id:
                        ppa[-1] = f"track={video_index+1}"
                    uploader_metadata = [
                        "-metadata",
                        f"uploader={video['uploader']}",
                    ] # only compatible with mkv
                    ydl.params["postprocessor_args"]["ffmpeg"] = ppa + uploader_metadata

                    ydl.params["outtmpl"]["default"] = os.path.join(
                        playlist_dir, "%(title)s[%(id)s].%(ext)s"
                    )
                    try:
                        if args.output_format == "mp3":
                            ydl.params["keepvideo"] = expected_path.with_suffix(".m4a").is_file()
                        ydl.download([video["url"]])
                        if args.output_format == "mp3":
                            del ydl.params["keepvideo"]
                    except DownloadError as exc:
                        if (
                            "Join this channel to get access to members-only content like this video, and other exclusive perks."
                            in exc.msg
                        ):
                            continue
                        elif re.search(
                            "Video unavailable. This video contains content from .*, who has blocked it in your country on copyright grounds",
                            exc.msg,
                        ):
                            continue
                        elif "ffmpeg not found" in exc.msg:
                            print("  Install by running 'python download_ffmpeg.py'")
                            exit()
                        raise
                    # try:
                    #     retcode =
                    # except DownloadError as exc:
                    #     # print("****************************")
                    #     # print(exc)
                    #     # set_trace()
                    #     raise
                    #     # if "blocked" in exc.msg:
                    #     #     # print(f"DOWNLOAD FAILED: {exc.msg}", )
                    #     #     failed_downloads.append(video)
                    #     # else:
                    #     #     set_trace()
                    #     #     raise
                    # if retcode == 1:
                    #     set_trace()
                    if remove_placeholder:
                        os.remove(placeholder_path)

                    # write_to_archives(video, archives_to_write)
                    # write_entry_extended(video, channel_playlist_info, channel_archive_filepath_json)
                    if args.use_archives:
                        set_download_state(
                            video,
                            channel_playlist_info,
                            channel_archive_filepath_json,
                            (
                                DownloadStates.DUPLICATE_DOWNLOADED
                                if is_duplicate
                                else DownloadStates.ORIGINAL_DOWNLOADED
                            ),
                        )
    if failed_downloads:
        print(f"{len(failed_downloads)} failed downloads")
        set_trace()


def main():
    args = process_args()
    all_urls_dict = get_all_urls_dict(args)
    if not args.data_only:
        download_all(args, all_urls_dict)


if __name__ == "__main__":
    main()
