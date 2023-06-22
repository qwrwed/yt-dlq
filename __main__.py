import json

from yt_dlq.args import process_args
from yt_dlq.download import download_all
from yt_dlq.url import get_all_urls_dict


def main():
    args = process_args()
    if args.json_file:
        with open(args.json_file, "r") as file:
            url_info_dict = json.load(file)
    else:
        url_info_dict = get_all_urls_dict(args)
    if not args.data_only:
        download_all(args, url_info_dict)


if __name__ == "__main__":
    main()
