import os
import re
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from yt_dlq.args import ProgramArgsNamespace
from yt_dlq.file import make_parent_dir, restrict_filename
from yt_dlq.state import get_download_state, set_download_state
from yt_dlq.types import DownloadStates
from yt_dlq.utils import match_filter_func


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
        {"key": "EmbedThumbnail"},
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
        "ffmpeg_location": args.ffmpeg_location,
        # "embedthumbnail": True,
        "writethumbnail": True,
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
                    f" DOWNLOADING PLAYLIST {pl_idx+1}/{len(playlists)}:",
                    end=" ",
                )
                archives_to_write = [channel_archive_filepath]
                ppa = [
                    "-metadata",
                    f"album_artist={channel['title']}",
                ]
                if playlist_id:
                    print(f"{playlist['title']!r}")
                    album_name = playlist["music_info"]["album"]
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
                    print(f"[loose videos] {channel['title']!r}")
                    ppa += [
                        "-metadata",
                        # f"album={channel['title']}",
                        f"album=Videos",
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
                                elif (
                                    channel_playlist_info["playlist_type"] == "release"
                                ):
                                    is_duplicate = True
                                    print(" (DUPLICATES ALLOWED IN RELEASES)")
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
                    while True:
                        try:
                            ydl.download([video["url"]])
                            break
                        except DownloadError as exc:
                            # if "WinError" in exc.msg:
                            # continue
                            # elif (
                            if (
                                "Join this channel to get access to members-only content like this video, and other exclusive perks."
                                in exc.msg
                            ):
                                break
                            elif re.search(
                                "Video unavailable. This video contains content from .*, who has blocked it in your country on copyright grounds",
                                exc.msg,
                            ):
                                break
                            elif "ffmpeg not found" in exc.msg:
                                print(
                                    "  Install by running 'python download_ffmpeg.py'"
                                )
                                exit()
                            else:
                                breakpoint()
                            raise
                        except PermissionError as exc:
                            if "WinError" in exc.msg:
                                continue
                            else:
                                breakpoint()
                        except Exception as exc:
                            breakpoint()
                        # TODO: PermissionError: [WinError 5] Access is denied: '{path}.temp.m4a' -> '{path}.m4a'
                        finally:
                            # TODO: check if this works after `break``
                            if args.output_format == "mp3":
                                del ydl.params["keepvideo"]

                    # try:
                    #     retcode =
                    # except DownloadError as exc:
                    #     # print("****************************")
                    #     # print(exc)
                    #     # breakpoint()
                    #     raise
                    #     # if "blocked" in exc.msg:
                    #     #     # print(f"DOWNLOAD FAILED: {exc.msg}", )
                    #     #     failed_downloads.append(video)
                    #     # else:
                    #     #     breakpoint()
                    #     #     raise
                    # if retcode == 1:
                    #     breakpoint()
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
        breakpoint()
