"""End-to-end processing: transcribe -> separate speakers -> recognise known
voices -> deduce names from introductions -> analyse the discussion."""
from datetime import datetime

from . import data_dir, db
from .analysis.discussion import analyze
from .engine.diarizer import diarize, match_known_speakers
from .engine.names import deduce_names
from .engine.transcriber import transcribe
from .models import Session


def _rename_speakers(session_like_segments, centroids, mapping):
    for seg in session_like_segments:
        if seg.speaker in mapping:
            seg.speaker = mapping[seg.speaker]
    for old, new in mapping.items():
        if old in centroids:
            centroids[new] = centroids.pop(old)


def run_pipeline(audio_path, title, dtype, cfg, database, progress=lambda msg: None):
    models_dir = data_dir() / "models"

    segments, duration = transcribe(
        audio_path,
        model_size=cfg.get("model_size", "small"),
        language=cfg.get("language", "auto"),
        models_dir=models_dir,
        progress=progress,
        task=cfg.get("task", "transcribe"),
    )
    if not segments:
        raise RuntimeError("No speech was detected in the audio.")

    progress("Separating speakers…")
    segments, centroids = diarize(
        audio_path, segments, models_dir,
        sensitivity=cfg.get("sensitivity", 0.55),
        progress=progress,
    )

    # Recognise voices already saved in the speaker database.
    known = db.list_speakers(database)
    if known and centroids:
        progress("Matching against known speakers…")
        mapping = match_known_speakers(
            centroids, known, threshold=cfg.get("match_threshold", 0.70))
        _rename_speakers(segments, centroids, mapping)

    # Deduce names for remaining generic speakers from self-introductions.
    deduced = deduce_names(segments)
    existing = {seg.speaker for seg in segments}
    deduced = {old: new for old, new in deduced.items() if new not in existing}
    _rename_speakers(segments, centroids, deduced)

    progress("Analyzing discussion…")
    prior = db.get_prior_issues(database)
    issues = analyze(segments, prior_issues=prior)

    return Session(
        title=title,
        dtype=dtype,
        started_at=datetime.now().isoformat(timespec="seconds"),
        audio_path=str(audio_path),
        duration=duration,
        segments=segments,
        issues=issues,
        centroids=centroids,
    )
