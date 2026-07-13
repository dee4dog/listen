"""Audio capture: microphone plus (optionally) Windows system audio via WASAPI loopback.

Capturing the loopback of the default speaker records whatever the PC is playing —
including remote participants in a Teams or Google Meet call — so recording a meeting
just means attending it on this machine with recording running.
"""
import threading
import time
import wave

import numpy as np

SAMPLE_RATE = 16000
BLOCK = 1024


class Recorder:
    def __init__(self, capture_system_audio=True):
        self.capture_system_audio = capture_system_audio
        self._stop = threading.Event()
        self._threads = []
        self._buffers = {"mic": [], "sys": []}
        self._error = None
        self.started_at = None
        self.system_audio_active = False

    def start(self):
        import soundcard as sc

        self._stop.clear()
        self._buffers = {"mic": [], "sys": []}
        self._levels = {"mic": 0.0, "sys": 0.0}
        self._error = None

        mic = sc.default_microphone()
        self._threads = [threading.Thread(target=self._capture, args=(mic, "mic"), daemon=True)]

        if self.capture_system_audio:
            loop = self._find_loopback(sc)
            if loop is not None:
                self.system_audio_active = True
                self._threads.append(
                    threading.Thread(target=self._capture, args=(loop, "sys"), daemon=True))

        self.started_at = time.time()
        for t in self._threads:
            t.start()

    @staticmethod
    def _find_loopback(sc):
        """Prefer the loopback of the default speaker, else any loopback device."""
        try:
            speaker_name = sc.default_speaker().name
        except Exception:
            speaker_name = ""
        loopbacks = [m for m in sc.all_microphones(include_loopback=True)
                     if getattr(m, "isloopback", False)]
        for m in loopbacks:
            if speaker_name and speaker_name in m.name:
                return m
        return loopbacks[0] if loopbacks else None

    def _capture(self, device, key):
        try:
            with device.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK) as rec:
                while not self._stop.is_set():
                    data = rec.record(numframes=BLOCK)
                    mono = data[:, 0]
                    self._buffers[key].append(mono.copy())
                    self._levels[key] = float(np.sqrt(np.mean(mono ** 2)))
        except Exception as exc:
            self._error = f"{key} capture failed: {exc}"

    def elapsed(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0

    def level(self) -> float:
        """Loudest current input level (RMS, 0..1) across mic and system audio."""
        return max(self._levels.values()) if self._levels else 0.0

    def stop(self, out_path):
        """Stop capture, mix mic + system audio, write 16 kHz mono WAV."""
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)

        mic = (np.concatenate(self._buffers["mic"])
               if self._buffers["mic"] else np.zeros(0, np.float32))
        sysa = (np.concatenate(self._buffers["sys"])
                if self._buffers["sys"] else np.zeros(0, np.float32))
        n = max(len(mic), len(sysa))
        if n == 0:
            raise RuntimeError(self._error or "No audio was captured.")

        mix = np.zeros(n, dtype=np.float32)
        mix[:len(mic)] += mic
        mix[:len(sysa)] += sysa
        peak = float(np.abs(mix).max())
        if peak > 1.0:
            mix /= peak

        pcm = (np.clip(mix, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())
        return out_path
