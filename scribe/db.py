"""SQLite persistence: sessions, transcripts, extracted items, speaker voice profiles."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import numpy as np

from .models import IssueItem, Segment, Session

_SCHEMA = """
CREATE TABLE IF NOT EXISTS speakers(
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    embedding TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    dtype TEXT NOT NULL,
    started_at TEXT NOT NULL,
    audio_path TEXT,
    duration REAL
);
CREATE TABLE IF NOT EXISTS segments(
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    start REAL, end REAL,
    speaker TEXT, text TEXT
);
CREATE TABLE IF NOT EXISTS issues(
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    kind TEXT, text TEXT, speaker TEXT, normalized TEXT,
    recurring INTEGER DEFAULT 0, prior_date TEXT
);
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def _connect(path):
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(path):
    with _connect(path) as con:
        con.executescript(_SCHEMA)
        try:
            con.execute("ALTER TABLE sessions ADD COLUMN synced_at TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists


def mark_synced(path, session_id):
    with _connect(path) as con:
        con.execute("UPDATE sessions SET synced_at = ? WHERE id = ?",
                    (datetime.now().isoformat(timespec="seconds"), session_id))


# ---------------------------------------------------------------- settings

def get_settings(path, defaults):
    out = dict(defaults)
    with _connect(path) as con:
        for key, value in con.execute("SELECT key, value FROM settings"):
            try:
                out[key] = json.loads(value)
            except (TypeError, ValueError):
                out[key] = value
    return out


def save_settings(path, settings):
    with _connect(path) as con:
        con.executemany(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(k, json.dumps(v)) for k, v in settings.items()],
        )


# ---------------------------------------------------------------- speakers

def list_speakers(path):
    """Return [(name, unit-norm embedding ndarray)] for all saved voice profiles."""
    out = []
    with _connect(path) as con:
        for name, emb in con.execute("SELECT name, embedding FROM speakers ORDER BY name"):
            if emb:
                vec = np.asarray(json.loads(emb), dtype=np.float32)
                norm = float(np.linalg.norm(vec))
                if norm > 0:
                    out.append((name, vec / norm))
    return out


def speaker_names(path):
    with _connect(path) as con:
        return [r[0] for r in con.execute("SELECT name FROM speakers ORDER BY name")]


def save_speaker(path, name, embedding=None):
    """Create or update a speaker; a new embedding is averaged with any existing one."""
    name = name.strip()
    if not name:
        return
    with _connect(path) as con:
        row = con.execute("SELECT id, embedding FROM speakers WHERE name = ?", (name,)).fetchone()
        emb_json = None
        if embedding is not None:
            vec = np.asarray(embedding, dtype=np.float32)
            if row and row[1]:
                old = np.asarray(json.loads(row[1]), dtype=np.float32)
                vec = (old + vec) / 2.0
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec = vec / norm
            emb_json = json.dumps([float(x) for x in vec])
        if row:
            if emb_json:
                con.execute("UPDATE speakers SET embedding = ? WHERE id = ?", (emb_json, row[0]))
        else:
            con.execute(
                "INSERT INTO speakers(name, embedding, created_at) VALUES(?, ?, ?)",
                (name, emb_json, datetime.now().isoformat(timespec="seconds")),
            )


# ---------------------------------------------------------------- sessions

def save_session(path, session: Session) -> int:
    with _connect(path) as con:
        if session.id is None:
            cur = con.execute(
                "INSERT INTO sessions(title, dtype, started_at, audio_path, duration) "
                "VALUES(?, ?, ?, ?, ?)",
                (session.title, session.dtype, session.started_at,
                 session.audio_path, session.duration),
            )
            session.id = cur.lastrowid
        else:
            con.execute(
                "UPDATE sessions SET title = ?, dtype = ?, started_at = ?, "
                "audio_path = ?, duration = ? WHERE id = ?",
                (session.title, session.dtype, session.started_at,
                 session.audio_path, session.duration, session.id),
            )
            con.execute("DELETE FROM segments WHERE session_id = ?", (session.id,))
            con.execute("DELETE FROM issues WHERE session_id = ?", (session.id,))
        con.executemany(
            "INSERT INTO segments(session_id, seq, start, end, speaker, text) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            [(session.id, i, s.start, s.end, s.speaker, s.text)
             for i, s in enumerate(session.segments)],
        )
        con.executemany(
            "INSERT INTO issues(session_id, kind, text, speaker, normalized, recurring, prior_date) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            [(session.id, it.kind, it.text, it.speaker, it.normalized,
              int(it.recurring), it.prior_date)
             for it in session.issues],
        )
    return session.id


def list_sessions(path):
    """Return [(id, title, dtype, started_at)] newest first."""
    with _connect(path) as con:
        return list(con.execute(
            "SELECT id, title, dtype, started_at FROM sessions ORDER BY started_at DESC"))


def load_session(path, session_id) -> Session:
    with _connect(path) as con:
        row = con.execute(
            "SELECT id, title, dtype, started_at, audio_path, duration "
            "FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise KeyError(f"session {session_id} not found")
        session = Session(id=row[0], title=row[1], dtype=row[2], started_at=row[3],
                          audio_path=row[4] or "", duration=row[5] or 0.0)
        for start, end, speaker, text in con.execute(
                "SELECT start, end, speaker, text FROM segments "
                "WHERE session_id = ? ORDER BY seq", (session_id,)):
            session.segments.append(Segment(start, end, speaker or "", text or ""))
        for kind, text, speaker, normalized, recurring, prior in con.execute(
                "SELECT kind, text, speaker, normalized, recurring, prior_date "
                "FROM issues WHERE session_id = ?", (session_id,)):
            session.issues.append(IssueItem(kind, text, speaker or "",
                                            normalized or "", bool(recurring), prior))
    return session


def delete_session(path, session_id):
    with _connect(path) as con:
        con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def get_prior_issues(path, exclude_session_id=None):
    """Return [(normalized_text, session_date, session_title)] of 'issue' items
    from earlier sessions, used to flag recurring issues."""
    query = ("SELECT i.normalized, s.started_at, s.title FROM issues i "
             "JOIN sessions s ON s.id = i.session_id "
             "WHERE i.kind = 'issue' AND i.normalized != ''")
    args = []
    if exclude_session_id is not None:
        query += " AND s.id != ?"
        args.append(exclude_session_id)
    with _connect(path) as con:
        return list(con.execute(query, args))
