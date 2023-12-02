import json

from utils_python import make_parent_dir
from yt_dlq.types import DownloadStates


def get_archive_id(info_dict: dict):
    ie_key_derived = "Youtube" if info_dict["type"] == "video" else "YoutubeTab"
    ie_key = info_dict.get("ie_key", ie_key_derived)
    return f"{ie_key.lower()} {info_dict['id']}"


def create_json_file(path):
    make_parent_dir(path)
    with open(path, "w+") as f:
        json.dump({}, f)


def get_download_state(video, channel_playlist_info, archive_path, output_format):
    try:
        with open(archive_path, "r") as f:
            info_extended = json.load(f)
            try:
                output_info_extended = info_extended[output_format]
                video_info_extended = output_info_extended[video["id"]]
                playlist_id = channel_playlist_info["playlist_id"]
                try:
                    playlist_info = video_info_extended["in_playlists"][playlist_id]
                except KeyError:
                    return DownloadStates.DUPLICATE_NOT_DOWNLOADED
                return playlist_info["download_state"]
            except KeyError:
                return DownloadStates.NEVER_DOWNLOADED
    except FileNotFoundError:
        create_json_file(archive_path)
    return DownloadStates.NEVER_DOWNLOADED


def set_download_state(
    video, channel_playlist_info, archive_path, download_state, output_format
):
    try:
        with open(archive_path, "r") as f:
            info_extended: dict = json.load(f)
    except FileNotFoundError:
        create_json_file(archive_path)
        info_extended = {}

    video_id = video["id"]
    playlist_id = channel_playlist_info["playlist_id"]
    format_info_extended = info_extended.setdefault(output_format, {})
    video_info_extended = format_info_extended.get(video_id)
    channel_playlist_state_info = channel_playlist_info | {
        "download_state": download_state
    }
    if not video_info_extended:
        format_info_extended[video_id] = {
            "id": video_id,
            "title": video["title"],
            "url": video["url"],
            "in_playlists": {playlist_id: channel_playlist_state_info},
            "legacy_archive_id": get_archive_id(video),
        }
    else:
        video_info_extended["in_playlists"][playlist_id] = channel_playlist_state_info
    with open(archive_path, "w") as f:
        json.dump(info_extended, f, indent=4)
