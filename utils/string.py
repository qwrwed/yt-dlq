PATTERN_ID = r"[@\w\-]+"
PATTERN_QUERY = r"(?:\?[\w=\&]+)"
PATTERN_CHANNEL_BASE = (
    rf"https:\/\/(?:www\.)?youtube\.com(?:\/(?:c|channel|user))?\/{PATTERN_ID}"
)
URL_TYPE_PATTERNS = {
    "channel_home": rf"^({PATTERN_CHANNEL_BASE})(?:\/featured)?\/?$",
    "channel_group_playlists": rf"^({PATTERN_CHANNEL_BASE}(?:\/playlists){PATTERN_QUERY}?)\/?$",
    "playlist": rf"^(https:\/\/(?:www\.)?youtube\.com\/playlist\?list={PATTERN_ID})\/?$",
    "channel_group_videos": rf"^({PATTERN_CHANNEL_BASE}(?:\/videos))\/?$",
    "video": rf"^(https:\/\/(?:youtu\.be\/|(?:www\.)?youtube\.com\/watch\?v=)({PATTERN_ID})){PATTERN_QUERY}?\/?$",
}


def escape_spaces(arg, use_singlequote=False):
    quote = "'" if use_singlequote else "'"
    return (
        f"{quote}{arg}{quote}"
        if (" " in arg and not (arg.startswith(quote)) and not (arg.endswith(quote)))
        else arg
    )
