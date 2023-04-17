import functools
import shutil
import zipfile
from pathlib import Path

import requests
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
