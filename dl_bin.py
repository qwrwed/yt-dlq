import os
from pprint import pprint
import platform
import zipfile

import requests

from utils import download

# https://github.com/jely2002/youtube-dl-gui/blob/c7b586935754e7c3ebb346d16ef79495229c97c8/modules/BinaryUpdater.js#L63
# https://github.com/jely2002/youtube-dl-gui/blob/d4b62e9a9f8eadb4fc996713916d73a1de31de41/modules/FfmpegUpdater.js#L68


def filename_from_url(url):
    return url.split("/")[-1]


def get_ffmpeg_url():
    res_json = requests.get("https://ffbinaries.com/api/v1/version/latest").json()
    system = platform.system()
    bits = platform.architecture()[0][:2]
    if system == "Windows":
        ffmpeg_platform = f"windows-{bits}"
    else:
        raise NotImplementedError
    return res_json["bin"][ffmpeg_platform]["ffmpeg"]


def unzip(filename):
    with zipfile.ZipFile(filename, "r") as zip_ref:
        zip_ref.extractall()


def download_ytdl():
    ytdl_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    ytdl_filename = filename_from_url(ytdl_url)
    download(ytdl_url, ytdl_filename)


def download_ffmpeg():
    ffmpeg_url = get_ffmpeg_url()
    ffmpeg_filename_zip = filename_from_url(ffmpeg_url)
    download(ffmpeg_url, ffmpeg_filename_zip)
    unzip(ffmpeg_filename_zip)
    os.remove(ffmpeg_filename_zip)


download_ytdl()
download_ffmpeg()  # required for --add-metadata
