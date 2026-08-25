"""Closing the window must not bin work that is still in flight.

A lost recording is the one thing here that cannot be redone, so closing
mid-recording offers to keep the audio as a file.
"""
import wave

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from scribe.audio.recorder import Recorder
from tests.conftest import store_sessions


class BufferedRecorder(Recorder):
    """A real Recorder with audio already in its buffers.

    stop() and discard() then run their genuine code — mixing, normalising
    and writing the WAV — without needing a sound device.
    """

    def __init__(self, seconds=1.0):
        super().__init__(capture_system_audio=False)
        samples = int(16000 * seconds)
        tone = (0.4 * np.sin(np.linspace(0, 400, samples))).astype(np.float32)
        self._buffers = {"mic": [tone] if samples else [], "sys": []}
        self._levels = {"mic": 0.1, "sys": 0.0}
        self._threads = []
        self.started_at = 0.0


class RunningWorker:
    def isRunning(self):
        return True


@pytest.fixture
def recordings(data_dir):
    folder = data_dir / "recordings"

    def listing():
        return sorted(folder.glob("*.wav"))

    return listing


def start_recording(window, title="Board meeting"):
    window.recorder = BufferedRecorder()
    window._record_meta = (title, "meeting", False)
    window.level_label.show()
    window.level_bar.show()
    window._update_actions()


# ------------------------------------------------------ closing mid-record

def test_cancel_carries_on_recording(window, prompts, recordings):
    before = recordings()
    start_recording(window)

    prompts.expect(QMessageBox.Cancel)
    window.close()

    assert prompts.answered_everything, "closing while recording did not ask"
    assert window.recorder is not None
    assert window.stop_action.isEnabled()
    assert recordings() == before, "a file was written despite Cancel"


def test_save_writes_the_audio_and_says_where(window, prompts, recordings):
    before = recordings()
    start_recording(window)

    prompts.expect(QMessageBox.Save)
    window.close()

    assert prompts.answered_everything
    assert window.recorder is None
    written = [p for p in recordings() if p not in before]
    assert len(written) == 1, written

    with wave.open(str(written[0])) as handle:
        assert handle.getframerate() == 16000
        assert handle.getnframes() > 15000
    assert "Import audio" in prompts.last, "the user was not told what to do"


def test_save_tidies_the_recording_indicators(window, prompts):
    start_recording(window)
    prompts.expect(QMessageBox.Save)
    window.close()
    assert not window.level_bar.isVisible()
    assert not window.stop_action.isEnabled()


def test_discard_writes_nothing(window, prompts, recordings):
    before = recordings()
    start_recording(window)

    prompts.expect(QMessageBox.Discard)
    window.close()

    assert prompts.answered_everything
    assert window.recorder is None
    assert recordings() == before


def test_an_empty_recording_is_reported_not_faked(window, prompts,
                                                  recordings):
    """Recorder.stop() raises when nothing was captured; the user should
    hear about that rather than assume a file exists."""
    before = recordings()
    window.recorder = BufferedRecorder(seconds=0)
    window.recorder._buffers = {"mic": [], "sys": []}
    window._record_meta = ("Silent", "meeting", False)

    prompts.expect(QMessageBox.Save)
    window.close()

    assert prompts.answered_everything
    assert recordings() == before
    assert "could not be saved" in prompts.last


# ------------------------------------------------ closing mid-transcription

def test_transcription_in_progress_is_guarded(window, prompts):
    window.worker = RunningWorker()

    prompts.expect(QMessageBox.Cancel)
    window.close()
    assert prompts.answered_everything, "closing while busy did not ask"

    prompts.expect(QMessageBox.Close)
    window.close()
    assert prompts.answered_everything


# --------------------------------------------------------------- together

def test_the_guards_stack(make_window, data_dir, prompts):
    """A recording and an unsaved edit are two separate questions."""
    store_sessions(data_dir / "listen.db", "A meeting")
    window = make_window()
    window.session_list.setCurrentItem(window.session_list.item(0))
    window.table.item(0, 2).setText("EDITED.")
    assert window._dirty

    start_recording(window)
    prompts.expect(QMessageBox.Discard,    # the recording
                   QMessageBox.Discard)    # the unsaved edit
    window.close()

    assert prompts.answered_everything, "both guards should have fired"
    assert window.recorder is None
    assert not window._dirty


def test_cancelling_a_later_guard_leaves_a_consistent_window(
        make_window, data_dir, prompts):
    """Saying yes to the recording then no to the edit keeps the window open,
    with the recording genuinely finished."""
    store_sessions(data_dir / "listen.db", "A meeting")
    window = make_window()
    window.session_list.setCurrentItem(window.session_list.item(0))
    window.table.item(0, 2).setText("EDITED.")
    start_recording(window)

    prompts.expect(QMessageBox.Discard,    # drop the recording
                   QMessageBox.Cancel)     # but do not close after all
    window.close()

    assert prompts.answered_everything
    assert window.recorder is None
    assert not window.stop_action.isEnabled()
    assert not window.level_bar.isVisible()
    assert window._dirty, "the edit is still unsaved"


def test_nothing_in_flight_closes_quietly(window, prompts):
    window.close()      # any prompt would fail in Prompts._ask
    assert not prompts.messages
