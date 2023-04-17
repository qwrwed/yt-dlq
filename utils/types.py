from enum import Enum


class DownloadStates(str, Enum):
    NEVER_DOWNLOADED = "never_downloaded"
    ORIGINAL_DOWNLOADED = "original_downloaded"
    DUPLICATE_DOWNLOADED = "duplicate_downloaded"
    DUPLICATE_NOT_DOWNLOADED = "duplicate_not_downloaded"
    CREATED_PLACEHOLDER = "placeholder"
    # IGNORED = "ignored",
    DOWNLOAD_FAILED = "download_failed"
