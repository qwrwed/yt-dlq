import functools
import pathlib
import shutil

import PySimpleGUI as sg
import requests
from tqdm.auto import tqdm


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

    path = pathlib.Path(filepath).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    desc = "(Unknown total file size)" if file_size == 0 else ""
    r.raw.read = functools.partial(
        r.raw.read, decode_content=True
    )  # Decompress if needed
    with tqdm.wrapattr(r.raw, "read", total=file_size, desc=desc) as r_raw:
        with path.open("wb") as f:
            shutil.copyfileobj(r_raw, f)

    return path


def input_popup(msg, default_input="", window_title="Input Required", beep=True):
    """
    PySimpleGUI window equivalent of input()
    """
    layout = [
        [sg.Text(msg)],
        [sg.InputText(key="-IN-", default_text=default_input, size=(80))],
        [sg.Submit()],
    ]
    if beep:
        print("\a")
    window = sg.Window(window_title, layout, modal=True)
    _, values = window.read()
    window.close()
    return values["-IN-"]
