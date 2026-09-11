import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from comics_lib import CACHE_DIR

DB_PATH = os.environ.get("JOBS_DB_PATH", str(CACHE_DIR / "jobs.db"))

# Link status values: pending, downloading, done, skipped, error
_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    blog_url TEXT NOT NULL,
    publisher TEXT NOT NULL,
    series TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    filename TEXT,
    error_msg TEXT,
    bytes_done INTEGER NOT NULL DEFAULT 0,
    bytes_total INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_job_links_status ON job_links(status);
CREATE INDEX IF NOT EXISTS idx_job_links_job_id ON job_links(job_id);
"""

# Columns added after the initial release — applied with ALTER TABLE so
# existing jobs.db files on already-deployed servers pick them up too.
_MIGRATIONS = [
    "ALTER TABLE job_links ADD COLUMN bytes_done INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE job_links ADD COLUMN bytes_total INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE job_links ADD COLUMN position INTEGER NOT NULL DEFAULT 0",
]


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_job(blog_url, publisher, series, links):
    job_id = uuid.uuid4().hex[:12]
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, blog_url, publisher, series, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, blog_url, publisher, series, now),
        )
        conn.executemany(
            "INSERT INTO job_links (job_id, url, status, position, updated_at) VALUES (?, ?, 'pending', ?, ?)",
            [(job_id, url, i + 1, now) for i, url in enumerate(links)],
        )
    return job_id


def list_recent_jobs(limit=10):
    with _connect() as conn:
        jobs = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for job in jobs:
            links = conn.execute(
                "SELECT * FROM job_links WHERE job_id = ? ORDER BY id ASC", (job["id"],)
            ).fetchall()
            result.append({**dict(job), "links": [dict(l) for l in links]})
        return result


def claim_next_pending_link():
    """Atomically pick the oldest pending link, mark it 'downloading', and return
    (link_id, url, publisher, series, position) or None if the queue is empty."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT jl.id AS link_id, jl.url AS url, jl.position AS position,
                   j.publisher AS publisher, j.series AS series
            FROM job_links jl
            JOIN jobs j ON j.id = jl.job_id
            WHERE jl.status = 'pending'
            ORDER BY jl.id ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE job_links SET status = 'downloading', updated_at = ? WHERE id = ?",
            (_now(), row["link_id"]),
        )
        return row["link_id"], row["url"], row["publisher"], row["series"], row["position"]


def update_link_status(link_id, status, filename=None, error_msg=None):
    with _connect() as conn:
        conn.execute(
            "UPDATE job_links SET status = ?, filename = ?, error_msg = ?, updated_at = ? WHERE id = ?",
            (status, filename, error_msg, _now(), link_id),
        )


def update_link_progress(link_id, bytes_done, bytes_total):
    with _connect() as conn:
        conn.execute(
            "UPDATE job_links SET bytes_done = ?, bytes_total = ?, updated_at = ? WHERE id = ?",
            (bytes_done, bytes_total, _now(), link_id),
        )
