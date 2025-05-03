from utils_python import get_logger_with_class, setup_config_logging
from yt_dlq.args import process_args
from yt_dlq.download import download_all
from yt_dlq.file import merge_json_files, resolve_json_files
from yt_dlq.url import get_all_urls_dict
from yt_dlq.utils import YtdlqLogger

LOGGER = get_logger_with_class(__name__, YtdlqLogger)


def main():
    args = process_args()
    setup_config_logging(args.logging_config_path)
    LOGGER.info("yt-dlq starting with args: %s", dict(args._get_kwargs()))

    if args.json_file:
        json_files = resolve_json_files(args.json_file)
        url_info_dict = merge_json_files(json_files)
    else:
        url_info_dict = get_all_urls_dict(args)
    if not args.data_only:
        download_all(args, url_info_dict)


if __name__ == "__main__":
    main()
