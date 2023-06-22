from yt_dlp.extractor.youtube import YoutubeTabBaseInfoExtractor, YoutubeTabIE
from yt_dlp.utils import traverse_obj


def _rich_entries_with_playlist(self, rich_grid_renderer):
    # video
    renderer = (
        traverse_obj(
            rich_grid_renderer,
            ("content", ("videoRenderer", "reelItemRenderer")),
            get_all=False,
        )
        or {}
    )
    video_id = renderer.get("videoId")
    if video_id:
        yield self._extract_video(renderer)
    # playlist
    renderer = (
        traverse_obj(
            rich_grid_renderer, ("content", ("playlistRenderer")), get_all=False
        )
        or {}
    )
    title = self._get_text(renderer, "title")
    playlist_id = renderer.get("playlistId")
    if playlist_id:
        yield self.url_result(
            "https://www.youtube.com/playlist?list=%s" % playlist_id,
            ie=YoutubeTabIE.ie_key(),
            video_id=playlist_id,
            video_title=title,
        )


def extract_metadata_from_tabs_with_subtitle(self, item_id, data):
    info = self._extract_metadata_from_tabs_original(item_id, data)
    playlist_header_renderer = traverse_obj(
        data, ("header", "playlistHeaderRenderer"), expected_type=dict
    )
    subtitle = self._get_text(playlist_header_renderer, "subtitle")
    music_info = {}
    if subtitle:
        release_artists_string, release_type = subtitle.split(" • ")
        release_artists_list = release_artists_string.split(", ")
        music_info["release_type"] = release_type
        music_info["artists"] = release_artists_list
    info["music_info"] = music_info
    return info


def patch_extract_metadata_from_tabs():
    YoutubeTabBaseInfoExtractor._extract_metadata_from_tabs_original = (
        YoutubeTabBaseInfoExtractor._extract_metadata_from_tabs
    )
    YoutubeTabBaseInfoExtractor._extract_metadata_from_tabs = (
        extract_metadata_from_tabs_with_subtitle
    )


def patch_releases_tab():
    YoutubeTabBaseInfoExtractor._rich_entries = _rich_entries_with_playlist
