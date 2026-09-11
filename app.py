import os
import time
import zipfile
import hashlib
import secrets
import shutil
import subprocess
from datetime import timedelta
from flask import (
    Flask, render_template, send_file, jsonify, abort,
    request, redirect, url_for, session, flash,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pathlib import Path
import mimetypes
import requests

import feeder
import jobs_db
from comics_lib import (
    COMICS_DIR, CACHE_DIR, SUPPORTED_EXTENSIONS,
    safe_path_component, series_dest_dir,
)

# unrar path — used for CBR (RAR) extraction. 7-Zip's own RAR codec fails
# ("Unsupported Method") on a lot of older/nonstandard RAR compression
# methods that the official unrar binary reads without issue.
UNRAR = r"C:\Program Files\WinRAR\UnRAR.exe"
if not os.path.exists(UNRAR):
    UNRAR = shutil.which("unrar") or ""

app = Flask(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Bumped every process start (i.e. every deploy), and appended as ?v=...
# to static asset URLs so browsers (especially iOS Safari on a PWA, which
# caches aggressively) pick up new CSS/JS instead of serving a stale copy.
_ASSET_VERSION = str(int(time.time()))


@app.context_processor
def _inject_asset_version():
    return {"asset_v": _ASSET_VERSION}

jobs_db.init_db()

# ---- Auth / admin config ----
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Ative quando o site estiver atrás de HTTPS (domínio + certbot):
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE") == "1"
app.permanent_session_lifetime = timedelta(days=7)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024  # 300MB por upload

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
if not ADMIN_PASSWORD_HASH:
    _generated_password = secrets.token_urlsafe(9)
    ADMIN_PASSWORD_HASH = generate_password_hash(_generated_password)
    print("=" * 60)
    print("AVISO: ADMIN_PASSWORD_HASH nao configurado.")
    print("Senha de admin gerada para esta sessao: {}".format(_generated_password))
    print("Usuario: {}".format(ADMIN_USERNAME))
    print("Para fixar essa senha, gere um hash com:")
    print("  python -c \"from werkzeug.security import generate_password_hash; "
          "print(generate_password_hash('SUA_SENHA'))\"")
    print("E defina ADMIN_USERNAME / ADMIN_PASSWORD_HASH como variaveis de ambiente.")
    print("=" * 60)

# Viewer account — read-only access to the library/reader, separate from the
# admin account so a reading password can be shared without granting upload access.
VIEWER_USERNAME = os.environ.get("VIEWER_USERNAME", "leitor")
VIEWER_PASSWORD_HASH = os.environ.get("VIEWER_PASSWORD_HASH")
if not VIEWER_PASSWORD_HASH:
    _generated_viewer_password = secrets.token_urlsafe(9)
    VIEWER_PASSWORD_HASH = generate_password_hash(_generated_viewer_password)
    print("=" * 60)
    print("AVISO: VIEWER_PASSWORD_HASH nao configurado.")
    print("Senha de leitura gerada para esta sessao: {}".format(_generated_viewer_password))
    print("Usuario: {}".format(VIEWER_USERNAME))
    print("Para fixar essa senha, gere um hash com:")
    print("  python -c \"from werkzeug.security import generate_password_hash; "
          "print(generate_password_hash('SUA_SENHA'))\"")
    print("E defina VIEWER_USERNAME / VIEWER_PASSWORD_HASH como variaveis de ambiente.")
    print("=" * 60)

_LOGIN_ATTEMPTS = {}  # ip -> [fail_count, first_fail_timestamp]
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_SECONDS = 300


def _login_is_locked(ip):
    entry = _LOGIN_ATTEMPTS.get(ip)
    if not entry:
        return False
    count, first_fail = entry
    if count < _LOGIN_MAX_ATTEMPTS:
        return False
    if time.time() - first_fail > _LOGIN_LOCKOUT_SECONDS:
        _LOGIN_ATTEMPTS.pop(ip, None)
        return False
    return True


def _register_login_failure(ip):
    count, first_fail = _LOGIN_ATTEMPTS.get(ip, (0, time.time()))
    if time.time() - first_fail > _LOGIN_LOCKOUT_SECONDS:
        count, first_fail = 0, time.time()
    _LOGIN_ATTEMPTS[ip] = (count + 1, first_fail)


# Routes reachable with no session at all. Everything else defaults to
# closed — new routes are protected automatically instead of needing to
# remember to decorate them.
_PUBLIC_ENDPOINTS = {"login", "logout", "static"}


@app.before_request
def _require_login():
    if request.endpoint is None or request.endpoint in _PUBLIC_ENDPOINTS:
        return
    role = session.get("role")
    if role is None:
        return redirect(url_for("login", next=request.path))
    if request.endpoint.startswith("admin") and role != "admin":
        return redirect(url_for("login", next=request.path))


def get_comic_id(path):
    return hashlib.md5(str(path).encode()).hexdigest()[:12]


def scan_library():
    library = {}
    if not COMICS_DIR.exists():
        return library

    for root, dirs, files in os.walk(str(COMICS_DIR)):
        dirs.sort()
        root_path = Path(root)
        parts = root_path.relative_to(COMICS_DIR).parts

        # depth 0: comics/arquivo.cbr          → série avulsa, sem editora
        # depth 1: comics/Serie/arquivo.cbr    → série, sem editora
        # depth 2: comics/Editora/Serie/       → série com editora
        # depth 3+: ignorado
        if len(parts) == 0:
            series_key = "_Avulsos"
            publisher = ""
        elif len(parts) == 1:
            series_key = parts[0]
            publisher = ""
        elif len(parts) == 2:
            publisher = parts[0]
            series_key = parts[1]
        else:
            continue

        for filename in sorted(files):
            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = root_path / filename
            comic_id = get_comic_id(filepath)
            title = Path(filename).stem

            if series_key not in library:
                library[series_key] = []

            library[series_key].append({
                "id": comic_id,
                "title": title,
                "filename": filename,
                "path": str(filepath),
                "ext": ext,
                "series": series_key,
                "publisher": publisher,
            })

    return library


def get_comic_by_id(comic_id):
    library = scan_library()
    for series in library.values():
        for comic in series:
            if comic["id"] == comic_id:
                return comic
    return None


def extract_cover_only(comic_path, comic_id):
    """Extract only the first page for cover display. Returns Path or None."""
    cache_path = CACHE_DIR / comic_id
    marker = cache_path / ".complete"

    # Se extração completa já existe, usa primeira página dela
    if cache_path.exists() and marker.exists():
        pages = sorted([f for f in os.listdir(str(cache_path))
                        if Path(f).suffix.lower() in IMAGE_EXTENSIONS])
        if pages:
            return cache_path / pages[0]

    # Se só a capa já foi extraída (sem marcador), usa ela
    if cache_path.exists():
        pages = sorted([f for f in os.listdir(str(cache_path))
                        if Path(f).suffix.lower() in IMAGE_EXTENSIONS])
        if pages:
            return cache_path / pages[0]

    cache_path.mkdir(parents=True, exist_ok=True)

    try:
        if _is_rar(comic_path):
            if not UNRAR:
                return None
            r = subprocess.run([UNRAR, "lb", comic_path],
                               capture_output=True, text=True, timeout=15)
            candidates = [line.strip() for line in r.stdout.splitlines()
                          if Path(line.strip()).suffix.lower() in IMAGE_EXTENSIONS]
            if not candidates:
                return None
            first = sorted(candidates)[0]
            subprocess.run(
                [UNRAR, "e", "-y", comic_path, str(cache_path) + os.sep, first],
                capture_output=True, timeout=30
            )
            imgs = sorted([f for f in os.listdir(str(cache_path))
                           if Path(f).suffix.lower() in IMAGE_EXTENSIONS])
            if not imgs:
                return None
            src = cache_path / imgs[0]
            dst = cache_path / ("0000" + Path(imgs[0]).suffix.lower())
            if src != dst:
                os.rename(str(src), str(dst))
            return dst
        else:
            with zipfile.ZipFile(comic_path, "r") as zf:
                names = sorted([n for n in zf.namelist()
                                if Path(n).suffix.lower() in IMAGE_EXTENSIONS
                                and not os.path.basename(n).startswith(".")])
                if not names:
                    return None
                ext = Path(names[0]).suffix.lower()
                out_name = "0000" + ext
                data = zf.read(names[0])
                out_path = cache_path / out_name
                with open(str(out_path), "wb") as f:
                    f.write(data)
                return out_path
    except Exception:
        return None


def get_adjacent_comics(comic_id):
    """Return (prev, next) comic dicts within the same series, or None."""
    library = scan_library()
    for series in library.values():
        for i, comic in enumerate(series):
            if comic["id"] == comic_id:
                prev_c = series[i - 1] if i > 0 else None
                next_c = series[i + 1] if i + 1 < len(series) else None
                return prev_c, next_c
    return None, None


def _is_rar(path):
    try:
        with open(path, "rb") as f:
            magic = f.read(7)
            return magic[:4] == b"Rar!" or magic[:7] == b"Rar!\x1a\x07\x01"
    except Exception:
        return False


def _extract_with_unrar(comic_path, out_dir):
    """Extract all image files from a RAR archive using unrar. Returns sorted list of filenames."""
    if not UNRAR:
        raise RuntimeError("unrar nao encontrado. Instale o pacote 'unrar'.")

    result = subprocess.run(
        [UNRAR, "e", "-y", comic_path, out_dir + os.sep],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError("unrar falhou ({}): {}".format(
            result.returncode, (result.stderr or result.stdout)[-300:]))

    images = sorted([
        f for f in os.listdir(out_dir)
        if Path(f).suffix.lower() in IMAGE_EXTENSIONS
        and not f.startswith(".")
    ])

    # Renomear para 0000.jpg, 0001.jpg ... para garantir ordem correta
    renamed = []
    for i, fname in enumerate(images):
        ext = Path(fname).suffix.lower()
        new_name = "{:04d}{}".format(i, ext)
        os.rename(os.path.join(out_dir, fname), os.path.join(out_dir, new_name))
        renamed.append(new_name)

    return renamed


def _extract_with_zipfile(comic_path, out_dir):
    """Extract images from CBZ (ZIP) archive."""
    with zipfile.ZipFile(comic_path, "r") as zf:
        names = sorted([
            n for n in zf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTENSIONS
            and not os.path.basename(n).startswith(".")
        ])
        pages = []
        for i, name in enumerate(names):
            ext = Path(name).suffix.lower()
            out_name = "{:04d}{}".format(i, ext)
            data = zf.read(name)
            with open(os.path.join(out_dir, out_name), "wb") as f:
                f.write(data)
            pages.append(out_name)
    return pages


def extract_cbz_pages(comic_path, comic_id):
    cache_path = CACHE_DIR / comic_id
    marker = cache_path / ".complete"

    # Só usa cache se a extração COMPLETA já foi feita (marcador presente)
    if cache_path.exists() and marker.exists():
        pages = sorted([
            f for f in os.listdir(str(cache_path))
            if Path(f).suffix.lower() in IMAGE_EXTENSIONS
        ])
        if pages:
            return pages, cache_path

    # Cache parcial (só capa) ou corrompido — descarta e extrai tudo
    if cache_path.exists():
        shutil.rmtree(str(cache_path))

    cache_path.mkdir(parents=True, exist_ok=True)

    try:
        if _is_rar(comic_path):
            pages = _extract_with_unrar(comic_path, str(cache_path))
        else:
            try:
                pages = _extract_with_zipfile(comic_path, str(cache_path))
            except zipfile.BadZipFile:
                pages = _extract_with_unrar(comic_path, str(cache_path))
    except Exception as e:
        shutil.rmtree(str(cache_path), ignore_errors=True)
        raise e

    # Marca extração completa
    marker.touch()
    return pages, cache_path


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if _login_is_locked(ip):
            flash("Muitas tentativas. Aguarde alguns minutos e tente novamente.")
            return render_template("login.html"), 429

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        role = None
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            role = "admin"
        elif username == VIEWER_USERNAME and check_password_hash(VIEWER_PASSWORD_HASH, password):
            role = "viewer"

        if role:
            _LOGIN_ATTEMPTS.pop(ip, None)
            session.clear()
            session["role"] = role
            session.permanent = True
            default_target = "admin_panel" if role == "admin" else "index"
            next_url = request.form.get("next") or url_for(default_target)
            return redirect(next_url)

        _register_login_failure(ip)
        flash("Usuário ou senha inválidos.")

    next_url = request.args.get("next", "")
    return render_template("login.html", next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
def admin_panel():
    library = scan_library()
    publishers = sorted(set(c["publisher"] for comics in library.values() for c in comics if c["publisher"]))
    series_names = sorted(library.keys())
    total_comics = sum(len(c) for c in library.values())
    disk = shutil.disk_usage(str(COMICS_DIR))
    return render_template(
        "admin.html",
        publishers=publishers,
        series_names=series_names,
        total_comics=total_comics,
        total_series=len(library),
        recent_jobs=jobs_db.list_recent_jobs(),
        disk_total_gb=disk.total / (1024 ** 3),
        disk_used_gb=disk.used / (1024 ** 3),
        disk_free_gb=disk.free / (1024 ** 3),
        disk_pct_used=(disk.used / disk.total * 100) if disk.total else 0,
    )


@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Nenhum arquivo selecionado.")
        return redirect(url_for("admin_panel"))

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        flash("Formato não suportado. Use .cbz, .cbr ou .pdf.")
        return redirect(url_for("admin_panel"))

    publisher = request.form.get("publisher", "")
    series = request.form.get("series", "")
    filename = secure_filename(file.filename)
    if not filename:
        flash("Nome de arquivo inválido.")
        return redirect(url_for("admin_panel"))

    dest_dir = series_dest_dir(publisher, series)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    if dest_path.exists():
        flash("Já existe um arquivo com esse nome nessa série.")
        return redirect(url_for("admin_panel"))

    file.save(str(dest_path))
    flash("\"{}\" adicionado com sucesso.".format(filename))
    return redirect(url_for("admin_panel"))


@app.route("/admin/add-by-link", methods=["POST"])
def admin_add_by_link():
    blog_url = (request.form.get("blog_url") or "").strip()
    publisher = safe_path_component(request.form.get("publisher", ""))
    series = safe_path_component(request.form.get("series", ""))

    if not blog_url.lower().startswith(("http://", "https://")):
        flash("URL inválida.")
        return redirect(url_for("admin_panel"))

    if not series:
        flash("Informe a série.")
        return redirect(url_for("admin_panel"))

    try:
        html = feeder.fetch_post_html(blog_url)
    except requests.RequestException as e:
        flash("Não foi possível acessar essa URL: {}".format(e))
        return redirect(url_for("admin_panel"))

    links = feeder.extract_download_links(html)
    if not links:
        flash("Nenhum link de Mega/MediaFire encontrado nessa página.")
        return redirect(url_for("admin_panel"))

    jobs_db.create_job(blog_url, publisher, series, links)
    flash("{} link(s) encontrado(s). Baixando em segundo plano.".format(len(links)))
    return redirect(url_for("admin_panel"))


@app.route("/admin/jobs.json")
def admin_jobs_json():
    return jsonify(jobs_db.list_recent_jobs())


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/series/<path:series_name>")
def series_page(series_name):
    library = scan_library()
    if series_name not in library:
        abort(404)
    return render_template("series.html", series_name=series_name)


@app.route("/api/series/<path:series_name>")
def api_series(series_name):
    library = scan_library()
    series = library.get(series_name)
    if series is None:
        abort(404)
    return jsonify({"series": series_name, "comics": series})


@app.route("/comic/<comic_id>/cover")
def serve_cover(comic_id):
    comic = get_comic_by_id(comic_id)
    if not comic or comic["ext"] == ".pdf":
        abort(404)
    cover = extract_cover_only(comic["path"], comic_id)
    if not cover or not Path(cover).exists():
        abort(404)
    mime = mimetypes.guess_type(str(cover))[0] or "image/jpeg"
    return send_file(str(cover), mimetype=mime)


@app.route("/api/publishers")
def api_publishers():
    library = scan_library()
    publishers = sorted(set(
        c["publisher"] for comics in library.values()
        for c in comics if c["publisher"]
    ))
    return jsonify(publishers)


@app.route("/api/library")
def api_library():
    library = scan_library()
    result = []
    for series_name, comics in sorted(library.items()):
        cover_id = comics[0]["id"] if comics else None
        result.append({
            "series": series_name,
            "count": len(comics),
            "cover_id": cover_id,
            "publisher": comics[0]["publisher"] if comics else "",
            "comics": comics
        })
    return jsonify(result)


@app.route("/api/comic/<comic_id>")
def api_comic(comic_id):
    comic = get_comic_by_id(comic_id)
    if not comic:
        abort(404)

    prev_c, next_c = get_adjacent_comics(comic_id)

    def adj(c):
        return {"id": c["id"], "title": c["title"]} if c else None

    if comic["ext"] == ".pdf":
        return jsonify({
            "id": comic_id,
            "title": comic["title"],
            "type": "pdf",
            "url": "/comic/{}/pdf".format(comic_id),
            "prev": adj(prev_c),
            "next": adj(next_c),
        })

    if comic["ext"] in (".cbz", ".cbr"):
        try:
            pages, cache_path = extract_cbz_pages(comic["path"], comic_id)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        page_urls = ["/comic/{}/page/{}".format(comic_id, p) for p in pages]
        return jsonify({
            "id": comic_id,
            "title": comic["title"],
            "type": "cbz",
            "pages": page_urls,
            "total": len(page_urls),
            "prev": adj(prev_c),
            "next": adj(next_c),
        })

    abort(400)


@app.route("/comic/<comic_id>/page/<filename>")
def serve_page(comic_id, filename):
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(filename)
    page_path = CACHE_DIR / comic_id / filename
    if not page_path.exists():
        abort(404)
    mime = mimetypes.guess_type(str(page_path))[0] or "image/jpeg"
    return send_file(str(page_path), mimetype=mime)


@app.route("/comic/<comic_id>/pdf")
def serve_pdf(comic_id):
    comic = get_comic_by_id(comic_id)
    if not comic or comic["ext"] != ".pdf":
        abort(404)
    return send_file(comic["path"], mimetype="application/pdf")


@app.route("/read/<comic_id>")
def reader(comic_id):
    comic = get_comic_by_id(comic_id)
    if not comic:
        abort(404)
    return render_template("reader.html", comic_id=comic_id, title=comic["title"])


@app.errorhandler(413)
def too_large(e):
    flash("Arquivo muito grande (limite de 300MB).")
    return redirect(url_for("admin_panel")), 413


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
