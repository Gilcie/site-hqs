import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote_plus, urlsplit

import requests
from bs4 import BeautifulSoup

from comics_lib import SUPPORTED_EXTENSIONS

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
REQUEST_TIMEOUT = 30

MEGA_RE = re.compile(r"mega\.(nz|co\.nz)", re.I)
MEDIAFIRE_RE = re.compile(r"mediafire\.com", re.I)


class FeederError(Exception):
    """Raised for expected failures (dead link, unsupported file, etc)."""


def classify_link(url):
    if MEGA_RE.search(url):
        return "mega"
    if MEDIAFIRE_RE.search(url):
        return "mediafire"
    return None


def extract_download_links(html):
    """Return, in document order, the deduplicated Mega/MediaFire hrefs found in a post's HTML."""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if classify_link(href) and href not in seen:
            seen.add(href)
            links.append(href)
    return links


def fetch_post_html(post_url):
    resp = requests.get(post_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _with_position_prefix(filename, position):
    """Prefix a filename with its position in the source post (e.g. "003 - Name.cbr"),
    so the library's alphabetical sort matches the original reading order even when
    the underlying filenames come from mismatched naming conventions (Mega vs MediaFire,
    different release groups, etc)."""
    if not position:
        return filename
    return "{:03d} - {}".format(position, filename)


def _stream_to_dest(url, dest_dir, filename, headers=None, on_progress=None, position=None):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise FeederError("Formato não suportado: {}".format(ext or "(sem extensão)"))

    filename = _with_position_prefix(filename, position)
    final_path = dest_dir / filename
    if final_path.exists():
        raise FeederError("Já existe um arquivo com esse nome nessa série.")

    with requests.get(url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with tempfile.NamedTemporaryFile(delete=False, dir=str(dest_dir)) as tmp:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    tmp.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)
            tmp_path = Path(tmp.name)

    shutil.move(str(tmp_path), str(final_path))
    return final_path


def download_mediafire(url, dest_dir, on_progress=None, position=None):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    button = soup.find("a", id="downloadButton")
    if not button or not button.get("href"):
        raise FeederError("Link do MediaFire inválido, expirado ou arquivo removido.")

    direct_url = button["href"]
    # MediaFire encodes spaces in the path as "+" (form-encoding style, not
    # standard for URL paths). It's also inconsistent about the byte encoding
    # behind %XX for accented characters — usually UTF-8, but sometimes
    # Latin-1. Decode as Latin-1 first (never fails) and promote to UTF-8
    # when the bytes are actually valid UTF-8; otherwise keep the Latin-1 read.
    raw_name = Path(urlsplit(direct_url).path).name
    filename = unquote_plus(raw_name, encoding="latin-1")
    try:
        filename = filename.encode("latin-1").decode("utf-8")
    except UnicodeError:
        pass
    if not filename:
        raise FeederError("Não foi possível determinar o nome do arquivo.")

    return _stream_to_dest(
        direct_url, dest_dir, filename,
        headers={"User-Agent": USER_AGENT}, on_progress=on_progress, position=position,
    )


class _MegaProgressHandler:
    """Hooks mega.py's own 'X of Y downloaded' INFO log lines to report progress,
    since the library doesn't expose a progress callback."""

    def __init__(self, on_progress):
        import logging
        self.on_progress = on_progress
        self.logger = logging.getLogger("mega.mega")
        self._previous_level = self.logger.level

        class _Handler(logging.Handler):
            def emit(_self, record):
                if record.args and len(record.args) == 2:
                    try:
                        self.on_progress(int(record.args[0]), int(record.args[1]))
                    except (TypeError, ValueError):
                        pass

        self._handler = _Handler()

    def __enter__(self):
        self.logger.addHandler(self._handler)
        self.logger.setLevel("INFO")
        return self

    def __exit__(self, *exc_info):
        self.logger.removeHandler(self._handler)
        self.logger.setLevel(self._previous_level)


def download_mega(url, dest_dir, on_progress=None, position=None):
    from mega import Mega
    from mega.errors import RequestError

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        m = Mega()
        # Download to a temp name first so we can enforce our own
        # duplicate/extension checks before it lands in the real series folder.
        with tempfile.TemporaryDirectory() as tmp_dir:
            if on_progress:
                with _MegaProgressHandler(on_progress):
                    downloaded = m.download_url(url, dest_path=tmp_dir)
            else:
                downloaded = m.download_url(url, dest_path=tmp_dir)

            filename = downloaded.name
            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                raise FeederError("Formato não suportado: {}".format(ext or "(sem extensão)"))

            filename = _with_position_prefix(filename, position)
            final_path = dest_dir / filename
            if final_path.exists():
                raise FeederError("Já existe um arquivo com esse nome nessa série.")

            shutil.move(str(downloaded), str(final_path))
            return final_path
    except RequestError as e:
        raise FeederError("Link do Mega inválido ou expirado: {}".format(e))


def download_link(url, dest_dir, on_progress=None, position=None):
    """Download a Mega/MediaFire link into dest_dir. Returns the final Path."""
    kind = classify_link(url)
    if kind == "mega":
        return download_mega(url, dest_dir, on_progress=on_progress, position=position)
    if kind == "mediafire":
        return download_mediafire(url, dest_dir, on_progress=on_progress, position=position)
    raise FeederError("Link não reconhecido (não é Mega nem MediaFire).")
