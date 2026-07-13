"""Push sessions to a central Listen server on the local network.

The server end is `server/central_server.py` — a small stdlib-only HTTP
service backed by SQLite that any machine on the LAN can host. Sessions are
upserted by (source machine, client session id), so pushing the same session
again after edits updates the central copy instead of duplicating it.
"""
import platform

import requests


def push_session(session, server_url, api_key="", timeout=15):
    """POST a session to the central server. Returns the server's JSON reply."""
    if not server_url:
        raise ValueError("No central server URL is configured (see Settings).")
    url = server_url.rstrip("/") + "/api/sessions"
    payload = {
        "source": platform.node(),
        "client_session_id": session.id,
        "title": session.title,
        "dtype": session.dtype,
        "started_at": session.started_at,
        "duration": session.duration,
        "speakers": session.speaker_names(),
        "segments": [
            {"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text}
            for s in session.segments
        ],
        "issues": [
            {"kind": i.kind, "text": i.text, "speaker": i.speaker,
             "recurring": i.recurring, "prior_date": i.prior_date}
            for i in session.issues
        ],
    }
    headers = {"X-Api-Key": api_key} if api_key else {}
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def check_server(server_url, api_key="", timeout=5):
    """Return True if the central server answers its health check."""
    resp = requests.get(server_url.rstrip("/") + "/health",
                        headers={"X-Api-Key": api_key} if api_key else {},
                        timeout=timeout)
    resp.raise_for_status()
    return True
