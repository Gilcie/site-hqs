import os
import re
from pathlib import Path

COMICS_DIR = Path(os.environ.get("COMICS_DIR", "./comics"))
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "./cache"))
SUPPORTED_EXTENSIONS = {".cbz", ".pdf", ".cbr"}

COMICS_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)


def safe_path_component(name):
    """Sanitize a user-supplied folder name (publisher/series) for filesystem use."""
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = name.strip(". ")
    return name


def series_dest_dir(publisher, series):
    publisher = safe_path_component(publisher)
    series = safe_path_component(series)
    if publisher and series:
        return COMICS_DIR / publisher / series
    elif series:
        return COMICS_DIR / series
    return COMICS_DIR
