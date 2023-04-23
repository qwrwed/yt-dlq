def escape_spaces(arg, use_singlequote=False):
    quote = "'" if use_singlequote else "'"
    return (
        f"{quote}{arg}{quote}"
        if (" " in arg and not (arg.startswith(quote)) and not (arg.endswith(quote)))
        else arg
    )


def match_filter_func(info_dict):
    if info_dict.get("is_live") is True or info_dict.get("was_live") is True:
        return "Video is/was livestream; skipping"
    # if info_dict.get("availability") != 'public':
    #     return "Video is private; skipping"
    return None