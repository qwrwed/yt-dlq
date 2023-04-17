import json

from yt_dlq.file import make_parent_dir
from yt_dlq.types import DownloadStates


def get_archive_id(info_dict: dict):
    ie_key_derived = "Youtube" if info_dict["type"] == "video" else "YoutubeTab"
    ie_key = info_dict.get("ie_key", ie_key_derived)
    return f"{ie_key.lower()} {info_dict['id']}"


def already_in_archive(info_dict, archive_path):
    archive_id = get_archive_id(info_dict)
    try:
        with open(archive_path) as f:
            archived_items = f.read().splitlines()
            if archive_id in archived_items:
                return True
    except FileNotFoundError:
        make_parent_dir(archive_path)
        open(archive_path, "w+").close()
    return False


def read_entry_extended(video, channel_playlist_info, archive_path):
    # -1: video has not been previously recorded as  downloaded
    #  0: video has been previously recorded as downloaded in a different playlist
    #  1: video has been previously recorded as downloaded in the same playlist
    print("read_entry_extended(video, channel_playlist_info, archive_path)")
    try:
        with open(archive_path, "r") as f:
            info_extended = json.load(f)
            try:
                video_info_extended = info_extended[video["id"]]
                if channel_playlist_info in video_info_extended["in_playlists"]:
                    return 1
                return 0
            except KeyError:
                return -1
    except FileNotFoundError:
        make_parent_dir(archive_path)
        with open(archive_path, "w+") as f:
            json.dump({}, f)
    return -1


def write_entry_extended(video, channel_playlist_info, archive_path):
    with open(archive_path, "r") as f:
        info_extended = json.load(f)
    video_id = video["id"]
    video_info_extended = info_extended.get(video_id)
    if video_info_extended:
        video_info_extended["in_playlists"].append(channel_playlist_info)
    else:
        info_extended[video_id] = {
            "id": video_id,
            "title": video["title"],
            "url": video["url"],
            "in_playlists": [channel_playlist_info],
            "legacy_archive_id": get_archive_id(video),
        }
    with open(archive_path, "w") as f:
        json.dump(info_extended, f, indent=4)


def write_to_archives(info_dict, archive_paths: list):
    for archive_path in archive_paths:
        with open(archive_path, "a") as f:
            archive_id = get_archive_id(info_dict)
            f.write(archive_id)
            f.write("\n")


def get_download_state(video, channel_playlist_info, archive_path):
    try:
        with open(archive_path, "r") as f:
            info_extended = json.load(f)
            try:
                video_info_extended = info_extended[video["id"]]
                playlist_id = channel_playlist_info["playlist_id"]
                try:
                    playlist_info = video_info_extended["in_playlists"][playlist_id]
                except KeyError:
                    return DownloadStates.DUPLICATE_NOT_DOWNLOADED
                return playlist_info["download_state"]
            except KeyError:
                return DownloadStates.NEVER_DOWNLOADED
    except FileNotFoundError:
        make_parent_dir(archive_path)
        with open(archive_path, "w+") as f:
            json.dump({}, f)
    return DownloadStates.NEVER_DOWNLOADED


def set_download_state(video, channel_playlist_info, archive_path, download_state):
    with open(archive_path, "r") as f:
        info_extended = json.load(f)
    video_id = video["id"]
    playlist_id = channel_playlist_info["playlist_id"]
    video_info_extended = info_extended.get(video_id)
    channel_playlist_state_info = channel_playlist_info | {
        "download_state": download_state
    }
    if not video_info_extended:
        info_extended[video_id] = {
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
