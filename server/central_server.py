"""Listen central server — collects sessions pushed from Listen desktop apps.

Runs anywhere with plain Python 3 (no packages needed) and stores everything
in a single SQLite file. Start it on the machine that should host the central
database:

    python central_server.py                       # port 8765, listen_central.db
    python central_server.py --port 9000 --db D:\\data\\central.db
    python central_server.py --api-key mysecret    # require X-Api-Key header

Endpoints:
    GET  /health                     -> {"status": "ok"}
    POST /api/sessions               -> upsert a session (JSON body)
    GET  /api/sessions               -> list stored sessions (newest first)
    GET  /api/sessions/<id>          -> one full session incl. transcript
"""
import argparse
import json
import re
import sqlite3
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    client_session_id INTEGER NOT NULL,
    title TEXT, dtype TEXT, started_at TEXT, duration REAL,
    speakers TEXT, segments TEXT, issues TEXT,
    received_at TEXT,
    UNIQUE(source, client_session_id)
);
"""

_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    db_file = "listen_central.db"
    api_key = ""

    # ------------------------------------------------------------- helpers

    def _reply(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        if not self.api_key:
            return True
        if self.headers.get("X-Api-Key") == self.api_key:
            return True
        self._reply(401, {"error": "missing or wrong X-Api-Key header"})
        return False

    def _connect(self):
        con = sqlite3.connect(self.db_file)
        con.execute(_SCHEMA)
        return con

    def log_message(self, fmt, *args):  # quieter default logging
        print(f"[{datetime.now():%H:%M:%S}] {self.address_string()} {fmt % args}")

    # ------------------------------------------------------------- routes

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/health":
            self._reply(200, {"status": "ok", "app": "Listen central server"})
            return
        match = re.fullmatch(r"/api/sessions/(\d+)", self.path)
        if match:
            with _lock, self._connect() as con:
                row = con.execute(
                    "SELECT id, source, client_session_id, title, dtype, "
                    "started_at, duration, speakers, segments, issues, received_at "
                    "FROM sessions WHERE id = ?", (int(match.group(1)),)).fetchone()
            if not row:
                self._reply(404, {"error": "not found"})
                return
            self._reply(200, {
                "id": row[0], "source": row[1], "client_session_id": row[2],
                "title": row[3], "dtype": row[4], "started_at": row[5],
                "duration": row[6], "speakers": json.loads(row[7] or "[]"),
                "segments": json.loads(row[8] or "[]"),
                "issues": json.loads(row[9] or "[]"), "received_at": row[10],
            })
            return
        if self.path.rstrip("/") == "/api/sessions":
            with _lock, self._connect() as con:
                rows = con.execute(
                    "SELECT id, source, title, dtype, started_at, duration, "
                    "received_at FROM sessions ORDER BY started_at DESC").fetchall()
            self._reply(200, [
                {"id": r[0], "source": r[1], "title": r[2], "dtype": r[3],
                 "started_at": r[4], "duration": r[5], "received_at": r[6]}
                for r in rows])
            return
        self._reply(404, {"error": "unknown path"})

    def do_POST(self):
        if not self._authorized():
            return
        if self.path.rstrip("/") != "/api/sessions":
            self._reply(404, {"error": "unknown path"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            source = str(data["source"])
            client_id = int(data["client_session_id"])
        except (KeyError, TypeError, ValueError) as exc:
            self._reply(400, {"error": f"bad request: {exc}"})
            return
        with _lock, self._connect() as con:
            cur = con.execute(
                "INSERT INTO sessions(source, client_session_id, title, dtype, "
                "started_at, duration, speakers, segments, issues, received_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source, client_session_id) DO UPDATE SET "
                "title=excluded.title, dtype=excluded.dtype, "
                "started_at=excluded.started_at, duration=excluded.duration, "
                "speakers=excluded.speakers, segments=excluded.segments, "
                "issues=excluded.issues, received_at=excluded.received_at",
                (source, client_id,
                 data.get("title"), data.get("dtype"), data.get("started_at"),
                 data.get("duration"),
                 json.dumps(data.get("speakers", [])),
                 json.dumps(data.get("segments", [])),
                 json.dumps(data.get("issues", [])),
                 datetime.now().isoformat(timespec="seconds")))
            con.commit()
            row = con.execute(
                "SELECT id FROM sessions WHERE source = ? AND client_session_id = ?",
                (source, client_id)).fetchone()
        self._reply(200, {"status": "stored", "server_id": row[0]})


def main():
    parser = argparse.ArgumentParser(description="Listen central server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default="listen_central.db")
    parser.add_argument("--api-key", default="",
                        help="if set, clients must send this in X-Api-Key")
    args = parser.parse_args()

    Handler.db_file = args.db
    Handler.api_key = args.api_key
    sqlite3.connect(args.db).executescript(_SCHEMA)

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Listen central server on port {args.port}, database: {args.db}"
          + (" (API key required)" if args.api_key else ""))
    print("Point the desktop app's Settings -> Central server URL at "
          f"http://<this-machine's-IP>:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
