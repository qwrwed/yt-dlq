import glob
import os
import re
import time
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import MetadataParserPP
from yt_dlp.utils import DownloadError

from utils_python import (
    get_logger_with_class,
    make_parent_dir,
    preserve_filedate,
    set_tag_mp4_text,
)
from yt_dlq.args import ProgramArgsNamespace
from yt_dlq.file import restrict_filename
from yt_dlq.state import get_download_state, set_download_state
from yt_dlq.types import DownloadStates
from yt_dlq.utils import YtdlqLogger, match_filter_func

LOGGER = get_logger_with_class(__name__, YtdlqLogger)

base_postprocessors = [
    {
        "key": "MetadataParser",
        "actions": [(MetadataParserPP.replacer, "description", "\n", "\r\n")],
        "when": "pre_process",
    },
    {"key": "FFmpegMetadata"},
    {"key": "EmbedThumbnail"},
]

format_postprocessors = {
    "m4a": [
        {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
    ],
    "mkv": [
        {
            "key": "FFmpegVideoRemuxer",
            "preferedformat": "mkv",
        },
    ],
    "mp3": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        },
    ],
}


def download_all(args: ProgramArgsNamespace, all_urls_dict):
    postprocessors = (
        format_postprocessors.get(args.output_format, []) + base_postprocessors
    )
    ydl_opts = {
        "logger": LOGGER,
        "color": "never",
        "verbose": args.verbose,
        "format": "m4a/bestaudio/best",
        "postprocessors": postprocessors,
        "postprocessor_args": {"ffmpeg": []},
        "restrictfilenames": True,
        "windowsfilenames": True,
        # "ignoreerrors": "only_download",
        # "postprocessors": None,
        # "ffmpeg_location": None,
        "match_filter": match_filter_func,
        # "prefer_ffmpeg": True,
        "ffmpeg_location": args.ffmpeg_location,
        # "embedthumbnail": True,
        "writethumbnail": True,
    }
    failed_downloads = []
    with YoutubeDL(params=ydl_opts) as ydl:
        channels = all_urls_dict

        # create a dict of video ids in the root dir to avoid downloading duplicates
        videos_in_output_dir = {}
        for m4a_filepath in args.output_dir.rglob(f"*.{args.output_format}"):
            match = re.search(r"\[(.*?)\]$", m4a_filepath.stem)
            if not match:
                continue
            _video_id = match.group(1)
            videos_in_output_dir[_video_id] = m4a_filepath

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
            LOGGER.info(
                f"DOWNLOADING CHANNEL {ch_idx+1}/{len(channels)}: {channel['title']!r}"
            )
            playlists = channel["entries"]
            for pl_idx, (playlist_id, playlist) in enumerate(playlists.items()):
                log_string = f" DOWNLOADING PLAYLIST {pl_idx+1}/{len(playlists)}:"
                archives_to_write = [channel_archive_filepath]
                ppa = [
                    "-metadata",
                    f"album_artist={channel['title']}",
                ]
                if playlist["title"]:
                    LOGGER.info(log_string + f"{playlist['title']!r}")
                    album_name = (playlist.get("music_info") or {}).get(
                        "album"
                    ) or playlist["title"]
                    playlist_dir_components = [
                        channel_dir,
                        restrict_filename(playlist["title"]),
                    ]
                    if playlist["type"] == "release":
                        playlist_dir_components.insert(1, "releases")
                        if len(playlist["entries"]) <= 1 and not args.permit_single:
                            # remove release folder if release doesn't have multiple entries
                            playlist_dir_components.pop()
                            album_name = "Releases"
                    ppa += [
                        "-metadata",
                        f"album={album_name}",
                        "-metadata",
                        "track=0",
                    ]
                    playlist_dir = Path(*playlist_dir_components)
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
                    LOGGER.info(log_string + f"[loose videos] {channel['title']!r}")
                    ppa += [
                        "-metadata",
                        # f"album={channel['title']}",
                        # f"album=Videos",
                        f"album={args.loose_videos_prefix or ''}{channel['title']}{args.loose_videos_suffix or ''}",
                    ]
                    playlist_dir = channel_dir
                    # archive_filename = channel_archive_filename
                    # archive_filepath = channel_archive_filepath
                channel_playlist_info = {
                    "channel_id": channel_id,
                    "channel_title": channel["title"],
                    "playlist_id": playlist_id,
                    "playlist_title": playlist["title"],
                    "playlist_type": playlist["type"],
                }
                videos = playlist["entries"]
                for video_index, (video_id, video) in enumerate(videos.items()):
                    if args.filter_video_title is not None and not re.search(
                        args.filter_video_title, video["title"]
                    ):
                        log_string = f"  SKIPPING TITLE-FILTERED VIDEO {video_index+1}/{len(videos)}: {video['title']!r} (filter='{args.filter_video_title}')"
                        continue
                    downloaded = False
                    expected_path = Path(
                        playlist_dir,
                        f"{restrict_filename(video['title'])}[{video_id}].{args.output_format}",
                    )
                    placeholder_path = expected_path.with_suffix(".txt")
                    log_string = f"  DOWNLOADING VIDEO {video_index+1}/{len(videos)}: {video['title']!r}"
                    if video["title"] == "[Private video]":
                        LOGGER.info(log_string + " - UNAVAILABLE; SKIPPING")
                        continue
                    remove_placeholder = False
                    if args.use_archives and False:
                        video_download_state = get_download_state(
                            video,
                            channel_playlist_info,
                            channel_archive_filepath_json,
                            args.output_format,
                        )
                        match video_download_state:
                            case DownloadStates.NEVER_DOWNLOADED:
                                is_duplicate = False
                                LOGGER.info(log_string)
                            case DownloadStates.DOWNLOAD_FAILED:
                                is_duplicate = False
                                LOGGER.info(log_string + " (PREVIOUSLY FAILED)")
                            case DownloadStates.ORIGINAL_DOWNLOADED:
                                LOGGER.info(
                                    log_string + " - ALREADY DOWNLOADED IN PLAYLIST"
                                )
                                continue
                            case DownloadStates.DUPLICATE_DOWNLOADED:
                                LOGGER.info(
                                    log_string + " - ALREADY DOWNLOADED IN PLAYLIST"
                                )
                                continue
                            case DownloadStates.DUPLICATE_NOT_DOWNLOADED:
                                log_string += " - DOWNLOADED IN ANOTHER PLAYLIST"
                                if args.playlist_duplicates:
                                    is_duplicate = True
                                    LOGGER.info(log_string + " (DUPLICATES ENABLED)")
                                elif (
                                    channel_playlist_info["playlist_type"] == "release"
                                ):
                                    is_duplicate = True
                                    LOGGER.info(
                                        log_string + " (DUPLICATES ALLOWED IN RELEASES)"
                                    )
                                elif args.text_placeholders:
                                    LOGGER.info(log_string + " - CREATING PLACEHOLDER")
                                    make_parent_dir(placeholder_path)
                                    open(placeholder_path, "w+").close()
                                    set_download_state(
                                        video,
                                        channel_playlist_info,
                                        channel_archive_filepath_json,
                                        DownloadStates.CREATED_PLACEHOLDER,
                                        "txt",
                                    )
                                    continue
                                else:
                                    LOGGER.info(log_string + " - SKIPPING")
                                    continue
                            case DownloadStates.CREATED_PLACEHOLDER:
                                if args.playlist_duplicates:
                                    LOGGER.info(
                                        log_string + " - OVERWRITING PLACEHOLDER"
                                    )
                                    remove_placeholder = True
                                    is_duplicate = True
                                else:
                                    LOGGER.info(
                                        log_string
                                        + " - PLACEHOLDER PREVIOUSLY CREATED - SKIPPING"
                                    )
                                    continue
                            case _:
                                # input()
                                raise RuntimeError(
                                    f"Unhandled download state: {repr(video_download_state)}"
                                )
                    else:
                        video_download_state = DownloadStates.NEVER_DOWNLOADED

                    if video["id"] in videos_in_output_dir:
                        log_string += " - EXISTS IN OUTPUT DIR"
                        if args.text_placeholders and not placeholder_path.exists():
                            LOGGER.info(log_string + " - CREATING PLACEHOLDER")
                            make_parent_dir(placeholder_path)
                            open(placeholder_path, "w+").close()
                            continue
                        else:
                            LOGGER.info(log_string + " - SKIPPING")
                            continue

                    if playlist_id and len(playlist["entries"]) > 1:
                        ppa[-1] = f"track={video_index+1}"
                    uploader_metadata = [
                        "-metadata",
                        f"uploader={video['uploader']}",
                    ]  # only compatible with mkv
                    year_metadata = ["-metadata", f"date={video['upload_date']}"]
                    ydl.params["postprocessor_args"]["ffmpeg"] = (
                        ppa + uploader_metadata + year_metadata
                    )

                    ydl.params["outtmpl"]["default"] = os.path.join(
                        playlist_dir, "%(title)s[%(id)s].%(ext)s"
                    )
                    if args.output_format == "mp3":
                        ydl.params["keepvideo"] = expected_path.with_suffix(
                            ".m4a"
                        ).is_file()
                    tries = 0
                    while True:
                        tries += 1
                        try:
                            success = False
                            ydl.download([video["url"]])
                            # TODO: add configuration to allow creating shortcuts?
                            # from yt_dlq.utils import make_shortcut
                            # make_shortcut(placeholder_path.with_suffix(".url"), url=video["url"])
                            # ? remove_placeholder = False
                            success = True
                            break
                        except DownloadError as exc:
                            if "WinError" in exc.msg:
                                continue
                            elif "Read timed out" in exc.msg:
                                continue
                            elif "more expected" in exc.msg:
                                continue
                            elif (
                                "Join this channel to get access to members-only content like this video, and other exclusive perks."
                                in exc.msg
                            ):
                                break
                            elif re.search(
                                "Video unavailable. This video contains content from .*, who has blocked it in your country on copyright grounds",
                                exc.msg,
                            ):
                                break
                            elif "Sign in to confirm your age." in exc.msg:
                                break
                            elif "ffmpeg not found" in exc.msg:
                                LOGGER.info(
                                    "  Install by running 'python download_ffmpeg.py'"
                                )
                                exit()
                            elif (
                                "Supported filetypes for thumbnail embedding are:"
                                in exc.msg
                            ):
                                stem = expected_path.stem
                                exts = {
                                    path.suffix[1:]
                                    for path in expected_path.parent.glob(
                                        f"{glob.escape(stem)}.*"
                                    )
                                }
                                LOGGER.info(
                                    f"Deleting {stem}.{{{','.join(exts)}}} and trying again"
                                )
                                for ext in exts:
                                    expected_path.with_suffix(f".{ext}").unlink()
                                if tries > 1:
                                    breakpoint()
                                    pass
                                continue
                            else:
                                breakpoint()
                                pass

                        except PermissionError as exc:
                            if tries >= 5:
                                raise
                            LOGGER.warning(exc)
                            time.sleep(5)
                            continue
                        except Exception as exc:
                            breakpoint()
                            pass
                        finally:
                            if args.output_format == "mp3":
                                del ydl.params["keepvideo"]

                    # try:
                    #     retcode =
                    # except DownloadError as exc:
                    #     # LOGGER.info("****************************")
                    #     # LOGGER.info(exc)
                    #     # breakpoint()
                    #     raise
                    #     # if "blocked" in exc.msg:
                    #     #     # LOGGER.info(f"DOWNLOAD FAILED: {exc.msg}", )
                    #     #     failed_downloads.append(video)
                    #     # else:
                    #     #     breakpoint()
                    #     #     raise
                    # if retcode == 1:
                    #     breakpoint()

                    if not args.text_placeholders:
                        if args.output_format == "m4a":
                            if "uploader" in video:
                                with preserve_filedate(expected_path):
                                    set_tag_mp4_text(
                                        expected_path, "uploader", video["uploader"]
                                    )

                    if remove_placeholder:
                        os.remove(placeholder_path)

                    if args.use_archives and False:
                        if not success:
                            download_state = DownloadStates.DOWNLOAD_FAILED
                        elif is_duplicate:
                            download_state = DownloadStates.DUPLICATE_DOWNLOADED
                        else:
                            download_state = DownloadStates.ORIGINAL_DOWNLOADED
                        set_download_state(
                            video,
                            channel_playlist_info,
                            channel_archive_filepath_json,
                            download_state,
                            args.output_format,
                        )
    if failed_downloads:
        raise RuntimeError(f"{len(failed_downloads)} failed downloads")
