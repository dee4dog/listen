"""Dialogs: new session, continue-or-new prompt, speaker naming, settings."""
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QRadioButton,
    QVBoxLayout,
)

from ..analysis.discussion import DISCUSSION_TYPES

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]


class ContinueDialog(QDialog):
    """Asked when Record is pressed and earlier sessions exist:
    start fresh, or append to a previous session?"""

    def __init__(self, parent, sessions):
        super().__init__(parent)
        self.setWindowTitle("Record")
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel("Start a new session or continue a previous one?"))

        self.new_radio = QRadioButton("Start a new session")
        self.new_radio.setChecked(True)
        outer.addWidget(self.new_radio)

        self.cont_radio = QRadioButton("Continue a previous session:")
        outer.addWidget(self.cont_radio)
        self.session_combo = QComboBox()
        for sid, title, _dtype, started in sessions:
            self.session_combo.addItem(
                f"{title}  ({started[:16].replace('T', ' ')})", sid)
        self.session_combo.setEnabled(False)
        self.cont_radio.toggled.connect(self.session_combo.setEnabled)
        outer.addWidget(self.session_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def choice(self):
        """('continue', session_id) or ('new', None)."""
        if self.cont_radio.isChecked() and self.session_combo.count():
            return "continue", self.session_combo.currentData()
        return "new", None


class NewSessionDialog(QDialog):
    """Title, discussion type and (for recordings) system-audio capture."""

    def __init__(self, parent, for_recording, default_dtype="meeting",
                 default_system_audio=True, title_hint=None,
                 default_translate=False):
        super().__init__(parent)
        self.setWindowTitle("Start recording" if for_recording else "Import audio")
        layout = QFormLayout(self)

        default_title = title_hint or f"Session {datetime.now():%Y-%m-%d %H:%M}"
        self.title_edit = QLineEdit(default_title)
        layout.addRow("Title:", self.title_edit)

        self.dtype_combo = QComboBox()
        for key, cfg in DISCUSSION_TYPES.items():
            self.dtype_combo.addItem(cfg["label"], key)
        idx = self.dtype_combo.findData(default_dtype)
        if idx >= 0:
            self.dtype_combo.setCurrentIndex(idx)
        layout.addRow("Discussion type:", self.dtype_combo)

        self.sys_audio = QCheckBox(
            "Also capture system audio (Teams / Google Meet participants)")
        self.sys_audio.setChecked(default_system_audio)
        if for_recording:
            layout.addRow(self.sys_audio)

        self.translate_box = QCheckBox(
            "Translate speech to English (e.g. Afrikaans → English transcript)")
        self.translate_box.setChecked(default_translate)
        layout.addRow(self.translate_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return (self.title_edit.text().strip() or "Untitled session",
                self.dtype_combo.currentData(),
                self.sys_audio.isChecked(),
                self.translate_box.isChecked())


class SpeakerNameDialog(QDialog):
    """Rename detected speakers; optionally save their voice to the database.
    The ▶ button plays that speaker's longest sentence for identification."""

    def __init__(self, parent, labels, has_voice_profiles,
                 session=None, player=None):
        super().__init__(parent)
        self.setWindowTitle("Name the speakers")
        self.setMinimumWidth(500)
        self._session = session
        self._player = player
        can_play = bool(
            session is not None and player is not None and session.audio_path
            and Path(session.audio_path).exists())
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel(
            "Give each detected speaker a name — press ▶ to hear that speaker.\n"
            "Tick “Remember voice” to store the voice profile so this person is\n"
            "recognised automatically next time."))

        grid = QGridLayout()
        self._rows = []
        for row, label in enumerate(labels):
            grid.addWidget(QLabel(label), row, 0)
            play = QPushButton("▶")
            play.setFixedWidth(36)
            play.setToolTip(f"Play a sentence spoken by {label}")
            play.setEnabled(can_play)
            play.clicked.connect(lambda _=False, lab=label: self._play(lab))
            grid.addWidget(play, row, 1)
            edit = QLineEdit(label if not label.startswith("Speaker ") else "")
            edit.setPlaceholderText("Name…")
            grid.addWidget(edit, row, 2)
            remember = QCheckBox("Remember voice")
            remember.setEnabled(label in has_voice_profiles)
            remember.setChecked(label in has_voice_profiles)
            grid.addWidget(remember, row, 3)
            self._rows.append((label, edit, remember))
        outer.addLayout(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _play(self, label):
        """Play the longest sentence spoken by `label`."""
        seg = max((s for s in self._session.segments if s.speaker == label),
                  key=lambda s: s.end - s.start, default=None)
        if seg is not None:
            self._player.play(self._session.audio_path, seg.start, seg.end)

    def mapping(self):
        """Return {old_label: (new_name, remember_voice)} for renamed speakers."""
        result = {}
        for label, edit, remember in self._rows:
            name = edit.text().strip()
            if name and name != label:
                result[label] = (name, remember.isChecked())
            elif name and remember.isChecked():
                result[label] = (name, True)
        return result


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        outer = QVBoxLayout(self)

        engine = QGroupBox("Transcription")
        form = QFormLayout(engine)
        self.model_combo = QComboBox()
        self.model_combo.addItems(MODEL_SIZES)
        self.model_combo.setCurrentText(settings.get("model_size", "small"))
        form.addRow("Whisper model:", self.model_combo)
        self.language_edit = QLineEdit(settings.get("language", "auto"))
        self.language_edit.setToolTip(
            "Language code such as en (English), af (Afrikaans), nl, de — or\n"
            "'auto' to detect. Setting 'af' explicitly improves Afrikaans accuracy;\n"
            "use the 'small' model or larger for Afrikaans.")
        form.addRow("Language:", self.language_edit)
        self.translate_default = QCheckBox(
            "Translate speech to English by default")
        form.addRow(self.translate_default)
        self.translate_default.setChecked(bool(settings.get("translate", False)))
        outer.addWidget(engine)

        speakers = QGroupBox("Speaker separation")
        form2 = QFormLayout(speakers)
        self.sensitivity = QDoubleSpinBox()
        self.sensitivity.setRange(0.30, 0.90)
        self.sensitivity.setSingleStep(0.05)
        self.sensitivity.setValue(float(settings.get("sensitivity", 0.55)))
        self.sensitivity.setToolTip(
            "Lower = more speakers detected, higher = fewer. Default 0.55.")
        form2.addRow("Split sensitivity:", self.sensitivity)
        self.match_threshold = QDoubleSpinBox()
        self.match_threshold.setRange(0.50, 0.95)
        self.match_threshold.setSingleStep(0.05)
        self.match_threshold.setValue(float(settings.get("match_threshold", 0.70)))
        self.match_threshold.setToolTip(
            "Minimum similarity before a voice is matched to a saved speaker.")
        form2.addRow("Known-voice match threshold:", self.match_threshold)
        outer.addWidget(speakers)

        server = QGroupBox("Central server (optional)")
        form_srv = QFormLayout(server)
        self.server_url = QLineEdit(settings.get("server_url", ""))
        self.server_url.setPlaceholderText("http://192.168.1.10:8765")
        self.server_url.setToolTip(
            "URL of a Listen central server on your network\n"
            "(run server/central_server.py on the host machine).\n"
            "Leave empty if you don't use a central database.")
        form_srv.addRow("Server URL:", self.server_url)
        self.api_key = QLineEdit(settings.get("api_key", ""))
        self.api_key.setPlaceholderText("only if the server was started with --api-key")
        form_srv.addRow("API key:", self.api_key)
        outer.addWidget(server)

        recording = QGroupBox("Recording")
        form3 = QFormLayout(recording)
        self.sys_audio = QCheckBox("Capture system audio by default (for Teams / Meet)")
        self.sys_audio.setChecked(bool(settings.get("system_audio", True)))
        form3.addRow(self.sys_audio)
        self.default_dtype = QComboBox()
        for key, cfg in DISCUSSION_TYPES.items():
            self.default_dtype.addItem(cfg["label"], key)
        idx = self.default_dtype.findData(settings.get("default_dtype", "meeting"))
        if idx >= 0:
            self.default_dtype.setCurrentIndex(idx)
        form3.addRow("Default discussion type:", self.default_dtype)
        outer.addWidget(recording)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self):
        return {
            "model_size": self.model_combo.currentText(),
            "language": self.language_edit.text().strip() or "auto",
            "translate": self.translate_default.isChecked(),
            "sensitivity": round(self.sensitivity.value(), 2),
            "match_threshold": round(self.match_threshold.value(), 2),
            "system_audio": self.sys_audio.isChecked(),
            "default_dtype": self.default_dtype.currentData(),
            "server_url": self.server_url.text().strip(),
            "api_key": self.api_key.text().strip(),
        }
