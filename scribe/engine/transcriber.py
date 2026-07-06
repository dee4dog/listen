"""Speech-to-text using faster-whisper (local, CPU, models auto-download on first use)."""
from ..models import Segment, fmt_ts


def transcribe(audio_path, model_size="small", language=None, models_dir=None,
               progress=None, task="transcribe"):
    """Return (segments, duration_seconds). `language` of None/'auto' auto-detects.

    `task` is "transcribe" (keep the spoken language) or "translate"
    (Whisper's built-in translation of any language, e.g. Afrikaans, to English).
    """
    from faster_whisper import WhisperModel

    if progress:
        progress(f"Loading Whisper model '{model_size}' (downloaded on first use)…")
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        download_root=str(models_dir) if models_dir else None,
    )

    if language in (None, "", "auto"):
        language = None
    if progress:
        progress("Translating to English…" if task == "translate" else "Transcribing…")
    seg_iter, info = model.transcribe(str(audio_path), language=language,
                                      task=task, vad_filter=True)

    segments = []
    for s in seg_iter:
        text = s.text.strip()
        if not text:
            continue
        segments.append(Segment(start=float(s.start), end=float(s.end), speaker="", text=text))
        if progress and len(segments) % 10 == 0:
            progress(f"Transcribing… {fmt_ts(s.end)} / {fmt_ts(info.duration)}")

    duration = float(info.duration or (segments[-1].end if segments else 0.0))
    return segments, duration
