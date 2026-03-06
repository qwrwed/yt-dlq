import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yt_dlp.postprocessor.common import PostProcessor
from ytmusicapi import YTMusic
from ytmusicapi.models import LyricLine

from utils_python import set_tag_text_mp4

LOGGER = logging.getLogger(__name__)


def format_lyrics_timestamp(time: int) -> str:
    lrc_timestamp = datetime.fromtimestamp(
        time / 1000.0,
        tz=timezone.utc,
    )
    return lrc_timestamp.strftime("%M:%S.%f")[:-4]


def format_lyrics_line(lyric_line: LyricLine) -> str:
    return f"[{format_lyrics_timestamp(lyric_line.start_time)}]{lyric_line.text}"


def get_lyrics(
    video_id: str,
    synced_only: bool = False,
) -> str | None:
    ytmusic = YTMusic()
    watch_playlist_info = ytmusic.get_watch_playlist(video_id)

    if (lyrics_id := watch_playlist_info.get("lyrics")) is None:
        return None

    try:
        lyrics_result = ytmusic.get_lyrics(lyrics_id, timestamps=True)
        assert lyrics_result["hasTimestamps"]
        lyrics = lyrics_result["lyrics"]
        lyric_lines_formatted = [
            format_lyrics_line(lyric_line) for lyric_line in lyrics
        ]
        lyrics_full = "\n".join(lyric_lines_formatted)
    except KeyError as exc:
        if not exc.args[0] == "cueRange":
            raise
        if synced_only:
            return None
        lyrics_result = ytmusic.get_lyrics(lyrics_id, timestamps=False)
        lyrics_full = lyrics_result["lyrics"]

    return lyrics_full


class YouTubeMusicLyricsPP(PostProcessor):
    def run(self, information: dict[str, Any]):
        if information["uploader_id"]:
            return [], information

        video_id = information["id"]
        lyrics = get_lyrics(video_id, synced_only=False)

        if not lyrics:
            return [], information

        set_tag_text_mp4(
            Path(information["filepath"]), "lyrics", lyrics.replace("\n", "\r\n")
        )
        return [], information
