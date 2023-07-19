import functools
import json
import shutil
import zipfile
from copy import deepcopy
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import Optional

import requests
from mergedeep import merge
from tqdm.auto import tqdm


def make_parent_dir(filepath):
    Path(filepath).parent.mkdir(exist_ok=True, parents=True)


def unzip(filename):
    with zipfile.ZipFile(filename, "r") as zip_ref:
        zip_ref.extractall()


def filename_from_url(url):
    return url.split("/")[-1]


from yt_dlp.utils import sanitize_filename


def restrict_filename(filename):
    return sanitize_filename(filename, restricted=True)


def generate_json_output_filename(prefix: Optional[str]):
    prefix = prefix or ""
    if prefix and not prefix.endswith("_"):
        prefix = prefix + "_"
    ts = datetime.now()
    return restrict_filename(
        f"{prefix}urls_all_{ts.replace(microsecond=0).isoformat()}.json"
    )


def resolve_json_files(json_file_expression: Path):
    return [Path(json_file) for json_file in glob(str(json_file_expression))]


def merge_json_files(json_files: list[Path]):
    url_info_dict = {}
    for json_file in json_files:
        with open(json_file, "r") as file:
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


def download_ytdl():
    ytdl_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    ytdl_filename = filename_from_url(ytdl_url)
    download(ytdl_url, ytdl_filename)
