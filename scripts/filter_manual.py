"""
Filter a JSON url file based on user input for each video.
"""
import argparse
import json
from copy import deepcopy
from pathlib import Path

import readchar


class ArgsNamespace(argparse.Namespace):
    input_file: Path
    output_suffix: str = "_filtered_manual"


def ensure_underscore_str(input_: any):
    if not (input_str := str(input_)).startswith("_"):
        input_str = "_" + input_str
    return input_str


def add_stem_suffix(path: Path, suffix: str):
    return Path(path.parent, path.stem + suffix + path.suffix)


def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("input_file", metavar="INPUT_FILE", type=Path)
    parser.add_argument("-s", "--output-suffix", type=ensure_underscore_str)

    return parser.parse_args(namespace=ArgsNamespace)


def prompt_y_n(prompt="", true_key="y", false_key="n", default=None):
    shown_true_key = true_key = true_key.lower()
    shown_false_key = false_key = false_key.lower()
    if default is not None:
        if default is True:
            default_key = shown_true_key = true_key.upper()
        elif default is False:
            default_key = shown_false_key = false_key.upper()
    s = f"{prompt} [{shown_true_key}/{shown_false_key}]: "
    while True:
        print(s, end="", flush=True)
        key = readchar.readkey().lower()
        if key == "\r" and default is not None:
            print(default_key)
            return default
        elif key == true_key:
            print(true_key)
            return True
        elif key == false_key:
            print(false_key)
            return False
        else:
            print(key)
            print(f"\n{key!r} is not a valid choice.")


if __name__ == "__main__":
    args = get_args()
    input_filepath = args.input_file

    with open(input_filepath) as f:
        urls_dict_input: dict = json.load(f)
    urls_dict_keep = deepcopy(urls_dict_input)
    urls_dict_remove = deepcopy(urls_dict_input)
    for channel_id, channel_dict in urls_dict_input.items():
        for playlist_id, playlist_dict in channel_dict["entries"].items():
            video_ids_to_keep = set()
            video_ids_to_remove = set()
            for video_id, video_dict in playlist_dict["entries"].items():
                keep = prompt_y_n(f"Keep {video_dict['title']!r}?", default=True)
                if keep:
                    video_ids_to_keep.add(video_id)
                else:
                    video_ids_to_remove.add(video_id)

            for video_id in video_ids_to_keep:
                video_title = playlist_dict["entries"][video_id]["title"]
                del urls_dict_remove[channel_id]["entries"][playlist_id]["entries"][
                    video_id
                ]

            for video_id in video_ids_to_remove:
                video_title = playlist_dict["entries"][video_id]["title"]
                del urls_dict_keep[channel_id]["entries"][playlist_id]["entries"][
                    video_id
                ]

    output_file_kept = add_stem_suffix(input_filepath, args.output_suffix)
    with open(output_file_kept, "w+") as f:
        json.dump(urls_dict_keep, f, indent=4)
    print(f"wrote kept urls to {output_file_kept}")

    output_file_removed = add_stem_suffix(
        input_filepath, args.output_suffix + "_removed"
    )
    with open(output_file_removed, "w+") as f:
        json.dump(urls_dict_keep, f, indent=4)
    print(f"wrote removed urls to {output_file_removed}")
