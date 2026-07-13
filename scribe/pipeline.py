"""End-to-end processing: transcribe -> separate speakers -> recognise known
voices -> deduce names from introductions -> analyse the discussion."""
import wave
from datetime import datetime
from pathlib import Path

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


def merge_sessions(old, new, database, recordings_dir):
    """Append a freshly transcribed `new` session onto `old` (continue mode).

    New segments are shifted by the old recording's length, the audio files
    are joined into one WAV (so segment replay works across the whole
    session), and the analysis is re-run over the combined transcript.
    """
    import numpy as np

    offset = float(old.duration or 0.0)
    old_audio = Path(old.audio_path) if old.audio_path else None
    if old_audio is not None and old_audio.exists():
        from faster_whisper.audio import decode_audio
        a = decode_audio(str(old_audio), sampling_rate=16000)
        b = decode_audio(str(new.audio_path), sampling_rate=16000)
        offset = len(a) / 16000.0
        mix = np.concatenate([a, b])
        out = Path(recordings_dir) / f"rec_{datetime.now():%Y%m%d_%H%M%S}_full.wav"
        pcm = (np.clip(mix, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm.tobytes())
        old.audio_path = str(out)
        old.duration = len(mix) / 16000.0
    else:
        # Original audio is gone; keep the new recording and stack durations.
        old.audio_path = str(new.audio_path)
        old.duration = offset + float(new.duration)

    for seg in new.segments:
        seg.start += offset
        seg.end += offset
    old.segments = list(old.segments) + list(new.segments)

    prior = db.get_prior_issues(database, exclude_session_id=old.id)
    old.issues = analyze(old.segments, prior_issues=prior)
    old.centroids = new.centroids
    return old
