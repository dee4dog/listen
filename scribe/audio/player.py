"""Plays back transcript segments so speakers can be identified by ear."""
import threading

SR = 16000
TAIL = 0.15  # extra seconds so the last word isn't clipped


class SegmentPlayer:
    """Plays one [start, end] slice of a session's audio at a time."""

    def __init__(self):
        self._cache_path = None
        self._cache = None
        self._thread = None
        self._error = None

    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def play(self, audio_path, start, end) -> bool:
        """Start playback in the background. Returns False if already playing."""
        if self.is_playing():
            return False
        audio_path = str(audio_path)
        self._error = None

        def run():
            try:
                if audio_path != self._cache_path:
                    from faster_whisper.audio import decode_audio
                    self._cache = decode_audio(audio_path, sampling_rate=SR)
                    self._cache_path = audio_path
                a = max(0, int(start * SR))
                b = min(len(self._cache), int((end + TAIL) * SR))
                chunk = self._cache[a:b]
                if len(chunk):
                    import soundcard as sc
                    sc.default_speaker().play(chunk, samplerate=SR)
            except Exception as exc:
                self._error = str(exc)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return True
