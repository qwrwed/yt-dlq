import re
from pathlib import Path

ROOT_PROJECT_DIR = Path(__file__).parent.parent

def get_resolve_filepath(file_path: Path | str, root: Path | str = ROOT_PROJECT_DIR):
    if not isinstance(file_path, Path):
        file_path = Path(file_path)
    if not isinstance(root, Path):
        root = Path(root)

    dir_path = file_path.parent
    file_name = file_path.name
    if (
        not dir_path.exists()
        and not dir_path.is_absolute()
        and (dir_path_new := Path(root, dir_path)).exists()
    ):
        return Path(dir_path_new, file_name).absolute()
    return file_path


def set_resolve_filepath(file_path: Path, root: Path = ROOT_PROJECT_DIR):
    return Path(
        *(".." for _ in root.relative_to(Path().absolute()).parts),
        file_path,
    )

if True:
    get_path = get_resolve_filepath  # resolve paths from project_root_directory
    set_path = set_resolve_filepath
else:
    get_path = Path  # resolve paths from current working directory
    set_path = Path

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


def hyphenate_date(YYYYMMDD: str):
    match = re.match("(\d{4})(\d{2})(\d{2})", YYYYMMDD)
    if not match:
        raise ValueError(f"date {YYYYMMDD} not recognised")
    return "-".join(match.groups())
