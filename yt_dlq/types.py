from enum import Enum
from typing import Optional

Url = str
UrlList = list[Url]
UrlSet = set[Url]
UrlCategoryDict = dict[str, UrlList]

PLAYLIST_CATEGORIES = ("release", "playlist")


class DownloadStates(str, Enum):
    NEVER_DOWNLOADED = "never_downloaded"
    ORIGINAL_DOWNLOADED = "original_downloaded"
    DUPLICATE_DOWNLOADED = "duplicate_downloaded"
    DUPLICATE_NOT_DOWNLOADED = "duplicate_not_downloaded"
    CREATED_PLACEHOLDER = "placeholder"
    # IGNORED = "ignored",
    DOWNLOAD_FAILED = "download_failed"
