import io
import json
import os
from pathlib import Path
from pprint import pprint
import subprocess
import sys

import PySimpleGUI as sg
from yt_dlp.utils import sanitize_filename

INPUT_FILE = os.path.join("data", "to_download.txt")
DOWNLOAD_FOLDER = "data"
WINDOW_TITLE = "Window Title"


def get_sub_urls(url_channel):
    if url_channel:
        return " ".join(
            [url_channel + subpath for subpath in ("/videos", "/playlists")]
        )
    return ""


def ml_conv(urls):
    return "\n".join(
        [
            get_sub_urls(channel_url)
            for channel_url in urls.strip().split("\n")
            if channel_url.strip()[0] != "#"
        ]
    )


assert not isinstance(
    sys.__stdout__.buffer, io.BufferedWriter
), "must run with -u flag for download progress"

with open(INPUT_FILE) as f:
    multiline_text_prev = f.read()

# sg.theme('DarkGrey9')
col1 = sg.Column(
    [
        [
            sg.Multiline(
                key="-MLI-",
                size=(60, 20),
                default_text=multiline_text_prev,
                enable_events=True,
                rstrip=False,
            )
        ],
        [sg.Button("Save")],
    ]
)
col2 = sg.Column(
    [
        [
            sg.Multiline(
                key="-MLO-",
                size=(60, 20),
                default_text=ml_conv(multiline_text_prev),
                font=("Courier", 11),
                rstrip=False,
                write_only=True,
                disabled=True,
                horizontal_scroll=True,
            )
        ],
        [sg.Button("Download")],
    ]
)

layout = [
    [col1, col2],
    [
        # sg.Output(
        #     key="-OUT-",
        #     expand_x=True,
        #     size=(80, 15),
        #     font=("Courier", 11),
        #     background_color="black",
        #     text_color="white",
        #     echo_stdout_stderr=True,
        # )
    ],
]

window = sg.Window(WINDOW_TITLE, layout, finalize=True)
window["-MLO-"].Widget.config(bg="lightgray", fg="#777777")


def escape_spaces(arg, use_singlequote=False):
    quote = "'" if use_singlequote else "'"
    return (
        f"{quote}{arg}{quote}"
        if (" " in arg and not (arg.startswith(quote)) and not (arg.endswith(quote)))
        else arg
    )


def run_cmd_subprocess(cmd: list, quiet=False):
    cmd_string = " ".join([escape_spaces(arg) for arg in cmd])
    print(f">>> {cmd_string}")
    window.Refresh()

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = b""
    for c in iter(lambda: process.stdout.read(1), b""):
        if not quiet:
            sys.stdout.buffer.write(c)
        out += c
    return out


def run_cmd_sg(cmd: list):
    sp = sg.execute_command_subprocess(*cmd, wait=False, pipe_output=True)
    print(f">>> {sp.args}")
    window.Refresh()
    res, err = sg.execute_get_results(sp)
    print(res)
    window.Refresh()


def restrict_filename(filename):
    return sanitize_filename(filename, restricted=True)


def get_archive_id(info_dict):
    return f"{info_dict['ie_key'].lower()} {info_dict['id']}"


def already_in_archive(info_dict, archive_path):
    archive_id = get_archive_id(info_dict)
    try:
        with open(archive_path) as f:
            archived_items = f.read().splitlines()
            if archive_id in archived_items:
                return True
    except FileNotFoundError:
        open(archive_path, "w+").close()
    return False


def write_to_archives(info_dict, archive_paths: list):
    for archive_path in archive_paths:
        with open(archive_path, "a") as f:
            archive_id = get_archive_id(info_dict)
            f.write(archive_id)
            f.write("\n")


def get_video_cmd(video_url, download_dir, album, track=None):
    ppa_arg = f"Metadata:-metadata album_artist={escape_spaces(channel_title, True)} -metadata album={escape_spaces(album, True)}"
    if track is not None:
        ppa_arg += f" -metadata track={track}"
    return [
        "yt-dlp.exe",
        "-o", os.path.join(download_dir, "%(title)s[%(id)s].%(ext)s"),
        "-f140",
        "--add-metadata",
        "--restrict-filenames",
        "--parse-metadata", f"uploader:%(artist)s",
        "--ppa", ppa_arg,
        video_url,
    ]


while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED:
        break

    multiline_text_curr = values["-MLI-"][:-1]
    # removes inexplicable additional newline not in input

    if event == "Save":
        with open(INPUT_FILE, "w") as f:
            f.write(multiline_text_curr)
        multiline_text_prev = multiline_text_curr

    if multiline_text_curr != multiline_text_prev:
        window.set_title(f"{WINDOW_TITLE}*")
    else:
        window.set_title(f"{WINDOW_TITLE}")

    urls_conv = ml_conv(multiline_text_curr)
    window["-MLO-"].update(urls_conv)

    if event == "Download":
        for line in urls_conv.split("\n"):

            videos_url, playlists_url = line.split()

            cmd_info = [
                "yt-dlp.exe",
                "-J",
                "--flat-playlist",
            ]
            cmd_channel_videos_info = cmd_info + [videos_url]
            cmd_playlist_info = cmd_info + [playlists_url]

            channel_videos_info = json.loads(
                run_cmd_subprocess(cmd_channel_videos_info, quiet=True)
            )
            playlists_info = json.loads(
                run_cmd_subprocess(cmd_playlist_info, quiet=True)
            )

            channel_title = channel_videos_info["channel"]

            channel_dir = os.path.join(
                DOWNLOAD_FOLDER, restrict_filename(channel_title)
            )
            Path(channel_dir).mkdir(parents=True, exist_ok=True)
            videos_archive_filename = restrict_filename(
                f"videos_{channel_videos_info['channel']}.txt"
            )
            videos_archive_filepath = os.path.join(channel_dir, videos_archive_filename)

            for p in playlists_info["entries"]:
                playlist_url = p["url"]
                playlist_title = p["title"]

                playlist_dir = os.path.join(
                    channel_dir, restrict_filename(playlist_title)
                )

                playlist_archive_filename = restrict_filename(
                    f"playlist_{p['title']}.txt"
                )
                playlist_archive_filepath = os.path.join(
                    channel_dir, playlist_archive_filename
                )

                cmd_playlist_videos_info = cmd_info + [playlist_url]
                playlist_videos_info = json.loads(
                    run_cmd_subprocess(cmd_playlist_videos_info, quiet=True)
                )

                for i, v in enumerate(playlist_videos_info["entries"]):

                    if already_in_archive(v, playlist_archive_filepath):
                        print(
                            f"{v['id']} {v['title']!r} already in {playlist_archive_filename}"
                        )
                        continue

                    cmd_playlist_video = get_video_cmd(
                        v["url"],
                        download_dir=playlist_dir,
                        album=playlist_title,
                        track=i + 1,
                    )

                    run_cmd_subprocess(cmd_playlist_video)
                    write_to_archives(
                        v, [playlist_archive_filepath, videos_archive_filepath]
                    )

            channel_videos_info = json.loads(
                run_cmd_subprocess(cmd_channel_videos_info, quiet=True)
            )
            for v in channel_videos_info["entries"]:

                if already_in_archive(v, videos_archive_filepath):
                    print(
                        f"{v['id']} {v['title']!r} already in {playlist_archive_filename}"
                    )
                    continue

                cmd_channel_video = get_video_cmd(
                    v["url"],
                    download_dir=channel_dir,
                    album="[Videos]" + channel_title,
                )
                run_cmd_subprocess(cmd_channel_video)
                write_to_archives(v, [videos_archive_filepath])
            print(f"**** DONE channel {channel_title!r} ****")
        print("** DONE ALL **")

window.close()
