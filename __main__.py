# from pprint import pprint

from yt_dlq.args import process_args
from yt_dlq.download import download_all
from yt_dlq.url import get_all_urls_dict


def main():
    args = process_args()
    all_urls_dict = get_all_urls_dict(args)
    if not args.data_only:
        download_all(args, all_urls_dict)


if __name__ == "__main__":
    main()
