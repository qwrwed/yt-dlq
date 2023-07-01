"""
Filter a JSON url file based on strings to include/exclude
"""
import argparse
import json
from copy import deepcopy
from pathlib import Path


class ArgsNamespace(argparse.Namespace):
    input_file: Path
    output_suffix: str = "_filtered"
    video_includes: list[str] = []
    video_excludes: list[str] = []


def ensure_underscore_str(input_: any):
    if not (input_str := str(input_)).startswith("_"):
        input_str = "_" + input_str
    return input_str


def comma_separated_str_to_list(input_: str):
    return [e.lower() for e in input_.split(",")]


def add_stem_suffix(path: Path, suffix: str):
    return Path(path.parent, path.stem + suffix + path.suffix)


def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("input_file", metavar="INPUT_FILE", type=Path)
    parser.add_argument("-s", "--output-suffix", type=ensure_underscore_str)

    parser.add_argument("-vi", "--video-includes", type=comma_separated_str_to_list)
    parser.add_argument("-vx", "--video-excludes", type=comma_separated_str_to_list)

    return parser.parse_args(namespace=ArgsNamespace)


if __name__ == "__main__":
    args = get_args()
    input_filepath = args.input_file

    with open(input_filepath) as f:
        urls_dict_input: dict = json.load(f)
    urls_dict_keep = deepcopy(urls_dict_input)
    urls_dict_remove = deepcopy(urls_dict_input)
    for channel_id, channel_dict in urls_dict_input.items():
        for playlist_id, playlist_dict in channel_dict["entries"].items():
            video_ids = set()
            video_ids_with_included = set()
            video_ids_with_excluded = set()
            for video_id, video_dict in playlist_dict["entries"].items():
                video_ids.add(video_id)
                video_title = video_dict["title"].lower()
                if any(include in video_title for include in args.video_includes):
                    video_ids_with_included.add(video_id)
                if any(exclude in video_title for exclude in args.video_excludes):
                    video_ids_with_excluded.add(video_id)

            video_ids_to_keep = set() | (video_ids - video_ids_with_excluded)
            if args.video_includes:
                video_ids_to_keep &= video_ids_with_included

            video_ids_to_remove = video_ids - video_ids_to_keep

            print("  KEEPING VIDEOS:")
            for video_id in video_ids_to_keep:
                video_title = playlist_dict["entries"][video_id]["title"]
                print(video_title)
                del urls_dict_remove[channel_id]["entries"][playlist_id]["entries"][
                    video_id
                ]
            print()

            print(" REMOVING VIDEOS:")
            for video_id in video_ids_to_remove:
                video_title = playlist_dict["entries"][video_id]["title"]
                print(video_title)
                del urls_dict_keep[channel_id]["entries"][playlist_id]["entries"][
                    video_id
                ]
            print()

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
