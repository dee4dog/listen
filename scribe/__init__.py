import os
from pathlib import Path

APP_NAME = "Listen"


def data_dir() -> Path:
    """App data folder under %LOCALAPPDATA%\\Listen (db, recordings, models, exports)."""
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    base = root / APP_NAME
    # One-time migration from the app's previous name.
    old = root / "MeetScribe"
    if old.is_dir() and not base.exists():
        try:
            old.rename(base)
            legacy_db = base / "meetscribe.db"
            if legacy_db.exists():
                legacy_db.rename(base / "listen.db")
        except OSError:
            pass
    for sub in ("recordings", "models", "exports"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "listen.db"
