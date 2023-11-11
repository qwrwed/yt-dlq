from pathlib import Path
from pprint import pprint

from configargparse import ArgumentParser, Namespace
from utils_python import get_logger_with_class, get_platform

from yt_dlq.file import generate_json_output_filename
from yt_dlq.types import Url
from yt_dlq.utils import YtdlqLogger, get_path

LOGGER = get_logger_with_class(__name__, YtdlqLogger)


def get_default_config_file(prefix="", suffix="", extension="yml", config_dir="config"):
    if extension.startswith("."):
        extension = extension[1:]
    path = get_path(Path(config_dir, f"{prefix}{get_platform()}{suffix}.{extension}"))
    if path.is_file():
        return path
    return None


class ProgramArgsNamespace(Namespace):  # pylint: disable=too-few-public-methods
    _app_config_path: Path | None
    logging_config_path: Path | None
    urls: list[Url] | None
    batchfile: Path | None
    permit_single: bool
    json_file: Path | None
    output_dir: Path
    playlist_duplicates: bool
    text_placeholders: bool
    ffmpeg_location: Path | None
    use_archives: bool
    no_channels: bool
    data_only: bool
    output_format: str
    verbose: bool
    json_file_prefix: str | None
    album_override: str | None
    albumartist_override: str | None
    show_args_only: bool


def process_args():
    parser = ArgumentParser()
    parser.add_argument(
        "-c",
        "--app-config-path",
        is_config_file=True,
        dest="_app_config_path",
        type=get_path,
        default=get_default_config_file(prefix="app_", extension="yml"),
        help="Path to app config file (default: '%(default)s')",
    )
    parser.add_argument(
        "-l",
        "--logging-config-path",
        type=get_path,
        default=get_default_config_file(prefix="logging_", extension="cfg"),
        help="Path to logging config file (default: '%(default)s')",
    )
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
        "urls",
        metavar="URL",
        help="URL(s) to download",
        nargs="*",
        default=[],
    )

    parser.add_argument(
        "-p",
        "--permit-single",
        action="store_true",
        help=(
            "Allow releases with only one video to have their own folder. "
            "Otherwise, they will be downloaded to the `releases` subfolder."
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
        choices=["mp3", "m4a", "mkv"],
        default="m4a",
        help="Output audio file format",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Use downloader in verbose mode",
    )
    parser.add_argument(
        "-s",
        "--json-file-prefix",
        help="Prefix for output JSON file name.",
    )
    parser.add_argument(
        "--album-override",
        help="Set album/subfolder manually",
    )

    parser.add_argument(
        "--albumartist-override",
        help="Set album artist/parent folder manually",
    )

    parser.add_argument(
        "--show-args-only",
        action="store_true",
        help="Print args to stdout, then exit",
    )

    parsed: ProgramArgsNamespace = parser.parse_args(namespace=ProgramArgsNamespace())

    if parsed.show_args_only:
        pprint(parsed.__dict__)
        exit()

    return parsed
