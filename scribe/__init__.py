import os
from pathlib import Path

APP_NAME = "MeetScribe"


def data_dir() -> Path:
    """App data folder under %LOCALAPPDATA%\\MeetScribe (db, recordings, models, exports)."""
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
    for sub in ("recordings", "models", "exports"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "meetscribe.db"
