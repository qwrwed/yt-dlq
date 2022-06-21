import os
from pprint import pprint

import PySimpleGUI as sg

from utils import download

INPUT_FILE = os.path.join("data", "to_download.txt")
DOWNLOAD_ARCHIVE = os.path.join("data, download_archive.txt")
WINDOW_TITLE = "Window Title"


def download_binary():
    binary_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    download(binary_url, binary_url.split("/")[-1])


with open(INPUT_FILE) as f:
    multiline_text_prev = f.read()

# sg.theme('DarkGrey9')

layout = [
    [
        sg.Multiline(
            key="-ML-",
            size=(60, 20),
            default_text=multiline_text_prev,
            enable_events=True,
            rstrip=False,
        )
    ],
    [sg.Button("Save")],
]
window = sg.Window(WINDOW_TITLE, layout)

while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED:
        break

    multiline_text_curr = values["-ML-"][:-1]
    # removes inexplicable additional newline not in input

    if event == "Save":
        with open(INPUT_FILE, "w") as f:
            f.write(multiline_text_curr)
        multiline_text_prev = multiline_text_curr

    if multiline_text_curr != multiline_text_prev:
        window.set_title(f"{WINDOW_TITLE}*")
    else:
        window.set_title(f"{WINDOW_TITLE}")


window.close()
