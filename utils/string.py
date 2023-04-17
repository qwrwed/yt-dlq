def escape_spaces(arg, use_singlequote=False):
    quote = "'" if use_singlequote else "'"
    return (
        f"{quote}{arg}{quote}"
        if (" " in arg and not (arg.startswith(quote)) and not (arg.endswith(quote)))
        else arg
    )
