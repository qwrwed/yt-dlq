from pathlib import Path

from configargparse import ArgumentParser, Namespace

from yt_dlq.file import generate_json_output_filename
from yt_dlq.types import Url


class ProgramArgsNamespace(Namespace):  # pylint: disable=too-few-public-methods
    url: Url
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
    verbose: bool
    json_file_prefix: str


def process_args():
    parser = ArgumentParser()
    parser.add_argument("-c","--config-file",is_config_file=True)
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

    parsed = parser.parse_args(namespace=ProgramArgsNamespace())
    return parsed
