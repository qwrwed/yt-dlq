from yt_dlp.utils import traverse_obj
from yt_dlp.extractor.youtube import YoutubeTabBaseInfoExtractor, YoutubeTabIE

def _rich_entries_patched(self, rich_grid_renderer):
    # video
    renderer = traverse_obj(rich_grid_renderer, ('content', ('videoRenderer', 'reelItemRenderer')), get_all=False) or {}
    video_id = renderer.get('videoId')
    if video_id:
        yield self._extract_video(renderer)
    # playlist
    renderer = traverse_obj(rich_grid_renderer, ('content', ('playlistRenderer')), get_all=False) or {}
    title = self._get_text(renderer, 'title')
    playlist_id = renderer.get('playlistId')
    if playlist_id:
        yield self.url_result(
            'https://www.youtube.com/playlist?list=%s' % playlist_id,
            ie=YoutubeTabIE.ie_key(), video_id=playlist_id,
            video_title=title)

def patch_releases_tab():
    YoutubeTabBaseInfoExtractor._rich_entries = _rich_entries_patched
