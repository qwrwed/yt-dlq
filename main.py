import json
import os
from pprint import pprint
import subprocess

import PySimpleGUI as sg


INPUT_FILE = os.path.join("data", "to_download.txt")
DOWNLOAD_ARCHIVE = os.path.join("data", "download_archive.txt")
DOWNLOAD_FOLDER = "data"
WINDOW_TITLE = "Window Title"


def get_sub_urls(url_channel):
    if url_channel:
        return " ".join(
            [url_channel + subpath for subpath in ("/playlists", "/videos")]
        )
    return ""


def ml_conv(urls):
    return "\n".join(
        [get_sub_urls(channel_url) for channel_url in urls.strip().split("\n")]
    )


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
        sg.Output(
            key="-OUT-",
            expand_x=True,
            size=(80, 15),
            font=("Courier", 11),
            background_color="black",
            text_color="white",
            echo_stdout_stderr=True,
        )
    ],
]

window = sg.Window(WINDOW_TITLE, layout, finalize=True)
window["-MLO-"].Widget.config(bg="lightgray", fg="#777777")


def run_cmd_subprocess(cmd: list):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    cmd_string = " ".join([f"'{arg}'" if " " in arg else arg for arg in cmd])
    print(f">>> {cmd_string}")
    window.Refresh()
    lines = []
    for line in iter(p.stdout.readline, b""):
        line_decoded = line.rstrip().decode(errors="replace")
        print(line_decoded)
        window.Refresh()
        lines.append(line_decoded)
    print("")
    return lines


def run_cmd_sg(cmd: list):
    sp = sg.execute_command_subprocess(*cmd, wait=False, pipe_output=True)
    print(f">>> {sp.args}")
    window.Refresh()
    res, err = sg.execute_get_results(sp)
    print(res)
    window.Refresh()


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
            playlist_url, videos_url = line.split()
            # playlists
            cmd_playlist = [
                "yt-dlp.exe",
                "-o", os.path.join(DOWNLOAD_FOLDER, "%(playlist_uploader)s", "%(playlist)s", "%(title)s[%(id)s].%(ext)s"),
                "-f140",
                "--add-metadata",
                "--restrict-filenames",
                "--parse-metadata", "playlist_title:%(album)s",
                "--parse-metadata", "uploader:%(artist)s",
                "--parse-metadata", "playlist_uploader:%(album_artist)s",
                "--parse-metadata", "playlist_index:%(track_number)s",
                "--download-archive", DOWNLOAD_ARCHIVE,
                playlist_url,
            ]
            run_cmd_subprocess(cmd_playlist)
            # info = [json.loads(line) for line in run_cmd_subprocess(f"yt-dlp.exe -j --flat-playlist {url}")]

            # other videos
            cmd_videos = [
                "yt-dlp.exe",
                "-o", os.path.join(DOWNLOAD_FOLDER, "%(uploader)s", "%(title)s[%(id)s].%(ext)s"),
                "-f140",
                "--add-metadata",
                "--restrict-filenames",
                "--parse-metadata", "%(uploader)s - [Videos]:%(album)s",
                "--parse-metadata", "%(uploader)s:%(album_artist)s",
                "--download-archive", DOWNLOAD_ARCHIVE,
                videos_url,
            ]
            run_cmd_subprocess(cmd_videos)
        print("*** DONE ***")

window.close()
