import glob
import os
import re
import time
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor.metadataparser import MetadataParserPP
from yt_dlp.utils import DownloadError, sanitize_path

from utils_python import (
    dump_data,
    get_logger_with_class,
    make_parent_dir,
    preserve_filedate,
    set_tag_text_mp4 as set_tag_text_mp4,
)
from yt_dlq.args import ProgramArgsNamespace
from yt_dlq.file import restrict_filename
from yt_dlq.postprocessors import YouTubeMusicLyricsPP, YouTubeMusicSquareThumbnailPP
from yt_dlq.utils import DownloadErrorAgeRestricted, DownloadErrorMembersOnly, DownloadErrorTOSViolation, DownloadErrorUnavailableVideo, YtdlqLogger, match_filter_func, specify_download_error

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


class Downloader:
    def __init__(
        self,
        args: ProgramArgsNamespace,
        all_urls_dict: dict,
    ):
        self.args = args
        postprocessors = (
            format_postprocessors.get(self.args.output_format, []) + base_postprocessors
        )
        ydl_opts = {
            "logger": LOGGER,
            "color": "never",
            "verbose": self.args.verbose,
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
            "ffmpeg_location": self.args.ffmpeg_location,
            # "embedthumbnail": True,
            "writethumbnail": True,
            "cookiefile": str(self.args.cookies),
        }
        self.ydl = YoutubeDL(params=ydl_opts)
        self.ydl.add_post_processor(YouTubeMusicSquareThumbnailPP(None))
        self.ydl.add_post_processor(YouTubeMusicLyricsPP(None))
        self.all_urls_dict = all_urls_dict

        # create a dict of video ids in the root dir to avoid downloading duplicates
        self.videos_in_output_dirs = self.get_videos_in_output_dirs()

    def get_videos_in_output_dirs(self):
        videos_in_output_dirs: dict[str, list[Path]] = {}
        if self.args.dl_duplicates:
            return videos_in_output_dirs
        dirs_to_check = [self.args.output_dir, *self.args.extra_dirs]
        found_filepaths: list[Path] = []
        for dir in dirs_to_check:
            found_filepaths.extend(list(dir.rglob(f"*.{self.args.output_format}")))

        partial_suffixes = [
            ".webp",
            ".png",
            ".mp4.part",
            ".mp4.ytdl",
        ]

        partial_files = {}
        for format_filepath in found_filepaths:
            match = re.search(r"\[(.*?)\]$", format_filepath.stem)
            if not match:
                continue
            _video_id = match.group(1)

            id_partial_files = {suffix_filepath for suffix in partial_suffixes if (suffix_filepath:=format_filepath.with_suffix(suffix)).exists()}
            if id_partial_files:
                partial_files.setdefault(_video_id, set()).update(id_partial_files)

            videos_in_output_dirs.setdefault(_video_id, []).append(format_filepath)

        for id_, id_partial_files in partial_files.items():
            id_videos = videos_in_output_dirs[id_]
            LOGGER.warning(f"Found partial files for video {id_}: {id_partial_files} for {id_videos}")
            del videos_in_output_dirs[id_]
        if partial_files:
            LOGGER.warning("All videos with partial files will be treated as 'not already downloaded'.")

        return videos_in_output_dirs

    def download_all(self):
        failed_downloads = []
        with self.ydl:
            channels = self.all_urls_dict

            for ch_idx, (_channel_id, channel) in enumerate(channels.items()):
                self.download_channel(
                    ch_idx,
                    channel,
                    channels,
                )
        if failed_downloads:
            raise RuntimeError(f"{len(failed_downloads)} failed downloads")

    def download_channel(
        self,
        ch_idx: int,
        channel: dict,
        channels,
    ):
        log_string = (
            f"DOWNLOADING CHANNEL {ch_idx+1}/{len(channels)}: {channel['title']!r}"
        )
        if self.args.albumartist_override:
            channel_title = self.args.albumartist_override
            log_string += f" (as {channel_title!r})"
        else:
            channel_title = channel["title"]
        LOGGER.info(log_string)
        channel_dir = Path(self.args.output_dir, restrict_filename(channel_title))
        channel_postprocess_args = [
            "-metadata",
            f"album_artist={channel_title}",
        ]

        playlists = channel["entries"]
        if len(playlists) > 1 and self.args.album_override:
            raise ValueError(
                f"got same album override '{self.args.album_override}' for multiple ({len(playlists)}) playlists"
            )
        for pl_idx, (playlist_id, playlist) in enumerate(playlists.items()):
            self.download_playlist(
                playlists,
                pl_idx,
                playlist_id,
                playlist,
                channel_dir,
                channel_postprocess_args,
                channel_title,
            )

    def download_playlist(
        self,
        playlists,
        pl_idx: int,
        playlist_id,
        playlist,
        channel_dir: Path,
        channel_postprocess_args: list[str],
        channel_title,
    ):
        videos = playlist["entries"]
        if not videos:
            return

        if playlist["title"]:
            if self.args.filter_playlist_title is not None and not re.search(
                self.args.filter_playlist_title,
                playlist["title"],
                flags=re.IGNORECASE,
            ):
                log_string = f"  SKIPPING TITLE-FILTERED PLAYLIST {pl_idx+1}/{len(playlists)}: {playlist['title']!r} (filter='{self.args.filter_playlist_title}')"
                LOGGER.info(log_string)
                return
            log_string = f" DOWNLOADING PLAYLIST {pl_idx+1}/{len(playlists)}: {playlist["title"]!r}"

            if self.args.album_override:
                playlist_title = self.args.album_override
                log_string += f" (as {playlist_title!r})"
            else:
                playlist_title = playlist["title"]
            LOGGER.info(log_string)

            album_name = (
                self.args.album_override
                or playlist.get("music_info", {}).get("album")
                or playlist_title
            )
            playlist_dir_components = [
                channel_dir,
                restrict_filename(playlist_title),
            ]
            if playlist["type"] == "release":
                playlist_dir_components.insert(1, "releases")
                if len(playlist["entries"]) <= 1 and not self.args.permit_single:
                    # remove release folder if release doesn't have multiple entries
                    playlist_dir_components.pop()
                    album_name = "Releases"
            postprocess_args = channel_postprocess_args + [
                "-metadata",
                f"album={album_name}",
            ]
            playlist_dir = Path(*playlist_dir_components)

        elif playlist["type"] == "releases_singles":
            log_string = f" DOWNLOADING PLAYLIST {pl_idx+1}/{len(playlists)}: [single releases] {channel_title!r}"

            album_name = self.args.album_override or "Releases"
            postprocess_args = channel_postprocess_args + [
                "-metadata",
                f"album={album_name}",
            ]
            playlist_dir = Path(channel_dir, "releases")

        else:
            log_string = f" DOWNLOADING PLAYLIST {pl_idx+1}/{len(playlists)}: [loose videos] {channel_title!r}"
            if self.args.album_override:
                playlist_title = self.args.album_override
            else:
                playlist_title = f"{self.args.loose_videos_prefix or ''}{channel_title}{self.args.loose_videos_suffix or ''}"
            log_string += f" (as {playlist_title!r})"
            LOGGER.info(log_string)

            album_name = self.args.album_override or ""
            postprocess_args = channel_postprocess_args + [
                "-metadata",
                f"album={album_name}",
            ]
            playlist_dir = channel_dir

        for video_index, (video_id, video) in enumerate(videos.items()):
            self.download_video(
                playlist_id,
                playlist,
                videos,
                video_index,
                video_id,
                video,
                playlist_dir,
                postprocess_args,
            )

    def download_video(
        self,
        playlist_id,
        playlist,
        videos,
        video_index: int,
        video_id,
        video: dict,
        playlist_dir: Path,
        postprocess_args: list[str],
    ):
        if self.args.filter_video_title is not None and not re.search(
            self.args.filter_video_title,
            video["title"],
            flags=re.IGNORECASE,
        ):
            log_string = f"  SKIPPING TITLE-FILTERED VIDEO {video_index+1}/{len(videos)}: {video['title']!r} (filter='{self.args.filter_video_title}')"
            LOGGER.info(log_string)
            return

        # downloaded = False
        expected_path = Path(sanitize_path(str(Path(
            playlist_dir,
            f"{restrict_filename(video['title'])}[{video_id}].{self.args.output_format}",
        ))))
        LOGGER.info(f"Expected path: {expected_path!r}")
        placeholder_path = expected_path.with_suffix(".txt")
        log_string = (
            f"  DOWNLOADING VIDEO {video_index+1}/{len(videos)}: {video['title']!r}"
        )

        if video["title"] == "[Private video]":
            LOGGER.info(log_string + " - UNAVAILABLE (PRIVATE); SKIPPING")
            return
        elif video["availability"] == "subscriber_only":
            LOGGER.info(log_string + " - UNAVAILABLE (MEMBERS-ONLY); SKIPPING")
            return

        remove_placeholder = False
        if video["id"] in self.videos_in_output_dirs:
            log_string += " - EXISTS IN OUTPUT DIRS"
            if self.args.playlist_duplicates and playlist["type"] != "videos_loose" and self.videos_in_output_dirs[video["id"]] != [expected_path]:
                log_string += " - DUPLICATES ENABLED"
            elif self.args.text_placeholders and not placeholder_path.exists():
                LOGGER.info(log_string + " - CREATING PLACEHOLDER")
                make_parent_dir(placeholder_path)
                open(placeholder_path, "w+").close()
                return
            else:
                LOGGER.info(log_string + " - SKIPPING")
                return
        LOGGER.info(log_string)

        if playlist_id and len(playlist["entries"]) > 1:
            postprocess_args.extend([
                "-metadata",
                f"track={video_index+1}",
            ])
        uploader_metadata = [
            "-metadata",
            f"uploader={video['uploader']}",
        ]  # only compatible with mkv
        date_value = video.get("music_info", {}).get("release_year") or video['upload_date']
        year_metadata = ["-metadata", f"date={date_value}"]
        self.ydl.params["postprocessor_args"]["ffmpeg"] = (
            postprocess_args + uploader_metadata + year_metadata
        )

        self.ydl.params["outtmpl"]["default"] = os.path.join(
            playlist_dir, "%(title)s[%(id)s].%(ext)s"
        )
        if self.args.output_format == "mp3":
            self.ydl.params["keepvideo"] = expected_path.with_suffix(".m4a").is_file()

        try:
            self.execute_download(
                video,
                expected_path,
            )
        except DownloadError as _exc:
            LOGGER.error(f"   FAILED DOWNLOADING UNAVAILABLE VIDEO {video_index+1}/{len(videos)}: {video['title']!r}; SKIPPING")
        else:
            if not self.args.text_placeholders:
                if self.args.output_format == "m4a":
                    if video.get("uploader") is not None:
                        uploader = video["uploader"]
                    elif (_desc := video.get("description")) is not None and (
                        "Auto-generated by YouTube" in _desc
                    ):
                        uploader = "YouTube Music"
                    else:
                        uploader = None
                    if uploader is not None:
                        try:
                            with preserve_filedate(expected_path):
                                set_tag_text_mp4(
                                    expected_path,
                                    "uploader",
                                    uploader,
                                )
                        except FileNotFoundError as exc:
                            LOGGER.exception(f"Expected path {expected_path!r} not found! Maybe title of '{video['url']}' was updated between data retrieval and now?")
                            # TODO: retrieve data before/during download for expected path?
                            # but then how will placeholders work if nothing downloaded?
                            # placeholders are for duplicates, maybe we can get info on the original download
                            raise
                    else:
                        LOGGER.error("uploader is none???")
                        # breakpoint()
                        # pass
            if remove_placeholder:
                os.remove(placeholder_path)

    def execute_download(
        self,
        video: dict,
        expected_path: Path,
    ):
        tries = 0
        while True:
            tries += 1
            try:
                success = False
                self.ydl.download([video["url"]])
                # TODO: add configuration to allow creating shortcuts?
                # from yt_dlq.utils import make_shortcut
                # make_shortcut(placeholder_path.with_suffix(".url"), url=video["url"])
                # ? remove_placeholder = False
                success = True
                break
            except DownloadError as exc:
                exc_specific = specify_download_error(exc)
                if exc.msg is None:
                    raise NotImplementedError("exc.msg is None")
                if "WinError" in exc.msg:
                    continue
                elif "Read timed out" in exc.msg:
                    continue
                elif "more expected" in exc.msg:
                    continue
                elif isinstance(exc_specific, DownloadErrorMembersOnly):
                    raise
                elif isinstance(exc_specific, DownloadErrorAgeRestricted):
                    raise
                elif isinstance(exc_specific, DownloadErrorTOSViolation):
                    raise
                elif re.search(
                    "Video unavailable. This video contains content from .*, who has blocked it in your country on copyright grounds",
                    exc.msg,
                ):
                    break
                elif "Video unavailable. This video is not available" in exc.msg:
                    raise
                elif "ffmpeg not found" in exc.msg:
                    LOGGER.info("  Install by running 'python download_ffmpeg.py'")
                    exit()
                elif "Supported filetypes for thumbnail embedding are:" in exc.msg:
                    stem = expected_path.stem
                    exts = {
                        path.suffix[1:]
                        for path in expected_path.parent.glob(f"{glob.escape(stem)}.*")
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
                if self.args.output_format == "mp3":
                    breakpoint()
                    # why is this here
                    del self.ydl.params["keepvideo"]
