"""Dialogs: new session, continue-or-new prompt, speaker naming, settings."""
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QRadioButton, QTextBrowser, QVBoxLayout,
)

from ..analysis.discussion import DISCUSSION_TYPES
from . import theme

# Whisper model sizes, named for what the user gets rather than how big they are.
MODEL_CHOICES = [
    ("Fastest — rough notes", "tiny"),
    ("Fast", "base"),
    ("Balanced — recommended", "small"),
    ("Accurate — slower", "medium"),
    ("Most accurate — much slower", "large-v3"),
]

LANGUAGE_CHOICES = [
    ("Detect automatically", "auto"),
    ("English", "en"),
    ("Afrikaans", "af"),
    ("Dutch", "nl"),
    ("German", "de"),
    ("French", "fr"),
    ("Portuguese", "pt"),
    ("Spanish", "es"),
    ("Swahili", "sw"),
]


def _hint(text):
    """Small muted explanation shown under a setting."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.MUTED}; font-size: 9pt;")
    return label


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


class TemplateHelpDialog(QDialog):
    """Explains, in plain language, how to build a Word template and lists
    every field it can contain. Also the place to create a starter template
    or pick an existing one."""

    def __init__(self, parent, current_template=""):
        super().__init__(parent)
        self.setWindowTitle("Word templates — how they work")
        self.setMinimumSize(680, 620)
        self.choice = None          # "create" | "choose" | "clear" | None

        outer = QVBoxLayout(self)
        view = QTextBrowser()
        view.setOpenExternalLinks(False)
        view.setHtml(self._html(current_template))
        outer.addWidget(view)

        row = QHBoxLayout()
        create = QPushButton("Create a starter template…")
        create.setToolTip("Save a ready-made template you can restyle in Word")
        create.clicked.connect(lambda: self._pick("create"))
        choose = QPushButton("Use a template file…")
        choose.setToolTip("Choose the .docx file Listen should export into")
        choose.clicked.connect(lambda: self._pick("choose"))
        row.addWidget(create)
        row.addWidget(choose)
        if current_template:
            clear = QPushButton("Stop using it")
            clear.setToolTip("Go back to the built-in Word layout")
            clear.clicked.connect(lambda: self._pick("clear"))
            row.addWidget(clear)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        outer.addLayout(row)

    def _pick(self, choice):
        self.choice = choice
        self.accept()

    @staticmethod
    def _rows(fields):
        return "".join(
            f"<tr><td style='padding:3px 14px 3px 0'><code>{{{{{name}}}}}</code>"
            f"</td><td style='padding:3px 0'>{desc}</td></tr>"
            for name, desc in fields)

    def _html(self, current_template):
        # Imported here so python-docx is only loaded when the help is opened.
        from ..exporters.docx_template import BLOCK_FIELDS, INLINE_FIELDS
        current = (f"<p><b>Current template:</b> {current_template}</p>"
                   if current_template else
                   "<p><i>No template chosen yet — Word exports use the "
                   "built-in layout.</i></p>")
        return f"""
<h2>Export into your own Word document</h2>
{current}
<p>A template is just a normal Word document — your letterhead, your fonts,
your logo — with <b>fields</b> written in double curly braces where the
session's content should go. Listen replaces each field and saves the result
as a new document; your template is never changed.</p>

<h3>Making one takes three steps</h3>
<ol>
<li>Click <b>Create a starter template…</b> below and save it somewhere you
    will find it again.</li>
<li>Open it in Word and make it look the way you want — change the fonts and
    colours, add your logo, move fields into the header or into a table.
    Delete any fields you do not need.</li>
<li>Click <b>Use a template file…</b> and pick it. From then on
    <b>Export &rarr; Word from my template</b> produces documents in your own
    style.</li>
</ol>

<h3>Fields that fill in one spot</h3>
<p>Put these anywhere — in a sentence, a table cell, the header or the
footer. Whatever formatting you give the field is what the value gets, so
making <code>{{{{title}}}}</code> bold gives you a bold title.</p>
<table>{self._rows(INLINE_FIELDS)}</table>

<h3>Fields that grow into a list</h3>
<p>These need a <b>paragraph of their own</b>, with nothing else on the line.
Each one expands into as many paragraphs as the content needs, and every
paragraph copies the style of the field's own paragraph — so if you format
<code>{{{{action_items}}}}</code> as a bulleted list, every action item comes
out as a bullet.</p>
<table>{self._rows(BLOCK_FIELDS)}</table>

<h3>Worth knowing</h3>
<ul>
<li>Field names are not case sensitive, and spaces inside the braces are
    fine: <code>{{{{ Title }}}}</code> works.</li>
<li>Type each field in one go. If you edit the middle of a field name Word
    sometimes splits it internally — Listen copes with that, but retyping the
    whole field is the safe fix if one is not filled in.</li>
<li>A field Listen does not recognise is left in the document untouched, so
    a typo shows up plainly in the export.</li>
<li>Anything else in the template — page numbers, tables, images, styles —
    is carried through exactly as you designed it.</li>
<li>Transcript and speaker <b>filters apply to template exports too</b>, so
    you can produce one person's action list on your own letterhead.</li>
</ul>
"""


class SettingsDialog(QDialog):
    """Settings in plain language: what each choice does for the user, rather
    than what it does to the engine."""

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        outer = QVBoxLayout(self)
        self._template_path = settings.get("template_path", "")

        # ------------------------------------------------ accuracy & language
        engine = QGroupBox("Accuracy and language")
        form = QFormLayout(engine)
        self.model_combo = QComboBox()
        for label, value in MODEL_CHOICES:
            self.model_combo.addItem(label, value)
        index = self.model_combo.findData(settings.get("model_size", "small"))
        self.model_combo.setCurrentIndex(index if index >= 0 else 2)
        form.addRow("Quality:", self.model_combo)
        form.addRow("", _hint("Higher quality is slower and needs a bigger "
                              "one-off download. Balanced suits most meetings."))

        self.language_combo = QComboBox()
        self.language_combo.setEditable(True)
        for label, value in LANGUAGE_CHOICES:
            self.language_combo.addItem(label, value)
        self._select_language(settings.get("language", "auto"))
        form.addRow("Spoken language:", self.language_combo)
        form.addRow("", _hint("Leave on Detect automatically unless the audio "
                              "is noisy or mixes languages. You may also type "
                              "any language code, such as nl."))

        self.translate_default = QCheckBox(
            "Always write the transcript in English")
        self.translate_default.setChecked(bool(settings.get("translate", False)))
        form.addRow(self.translate_default)
        form.addRow("", _hint("Speech in any language is translated into "
                              "English. Turn this off to keep people's own "
                              "words."))
        outer.addWidget(engine)

        # --------------------------------------------------------- speakers
        speakers = QGroupBox("Telling speakers apart")
        form2 = QFormLayout(speakers)
        self.sensitivity = QDoubleSpinBox()
        self.sensitivity.setRange(0.30, 0.90)
        self.sensitivity.setSingleStep(0.05)
        self.sensitivity.setValue(float(settings.get("sensitivity", 0.55)))
        form2.addRow("Split voices at:", self.sensitivity)
        form2.addRow("", _hint("Lower finds more separate speakers, higher "
                               "merges them. Change it only if two people were "
                               "treated as one, or one as two. Default 0.55."))
        self.match_threshold = QDoubleSpinBox()
        self.match_threshold.setRange(0.50, 0.95)
        self.match_threshold.setSingleStep(0.05)
        self.match_threshold.setValue(
            float(settings.get("match_threshold", 0.70)))
        form2.addRow("Recognise saved voices at:", self.match_threshold)
        form2.addRow("", _hint("How sure Listen must be before it puts a saved "
                               "name to a voice. Raise it if the wrong name "
                               "keeps appearing. Default 0.70."))
        outer.addWidget(speakers)

        # -------------------------------------------------------- recording
        recording = QGroupBox("Recording")
        form3 = QFormLayout(recording)
        self.sys_audio = QCheckBox(
            "Also record what the PC plays (Teams / Google Meet callers)")
        self.sys_audio.setChecked(bool(settings.get("system_audio", True)))
        form3.addRow(self.sys_audio)
        self.default_dtype = QComboBox()
        for key, cfg in DISCUSSION_TYPES.items():
            self.default_dtype.addItem(cfg["label"], key)
        index = self.default_dtype.findData(
            settings.get("default_dtype", "meeting"))
        if index >= 0:
            self.default_dtype.setCurrentIndex(index)
        form3.addRow("Usually recording a:", self.default_dtype)
        outer.addWidget(recording)

        # ------------------------------------------------- Word template
        docs = QGroupBox("Word template for exports")
        form4 = QFormLayout(docs)
        row = QHBoxLayout()
        self.template_edit = QLineEdit(self._template_path)
        self.template_edit.setPlaceholderText(
            "Not set — Word exports use the built-in layout")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_template)
        help_btn = QPushButton("How do I make one?")
        help_btn.clicked.connect(self._show_template_help)
        row.addWidget(self.template_edit, 1)
        row.addWidget(browse)
        form4.addRow("Template:", row)
        form4.addRow("", help_btn)
        form4.addRow("", _hint("Export your sessions into your own Word "
                               "document — letterhead, fonts and all."))
        outer.addWidget(docs)

        # ---------------------------------------------------- central server
        server = QGroupBox("Shared database on your network (optional)")
        form5 = QFormLayout(server)
        self.server_url = QLineEdit(settings.get("server_url", ""))
        self.server_url.setPlaceholderText(
            "Leave empty unless your office runs one")
        form5.addRow("Server address:", self.server_url)
        self.api_key = QLineEdit(settings.get("api_key", ""))
        self.api_key.setPlaceholderText("only if the server needs a key")
        form5.addRow("Access key:", self.api_key)
        form5.addRow("", _hint("Sends finished sessions to one shared "
                               "database, so several PCs collect their "
                               "transcripts in one place."))
        outer.addWidget(server)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------- helpers

    def _select_language(self, code):
        index = self.language_combo.findData(code)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        else:
            self.language_combo.setCurrentText(code)

    def _browse_template(self):
        start = self.template_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a Word template", start, "Word document (*.docx)")
        if path:
            self.template_edit.setText(path)

    def _show_template_help(self):
        dialog = TemplateHelpDialog(self, self.template_edit.text().strip())
        dialog.exec()
        if dialog.choice == "choose":
            self._browse_template()
        elif dialog.choice == "clear":
            self.template_edit.clear()
        elif dialog.choice == "create":
            path, _ = QFileDialog.getSaveFileName(
                self, "Save starter template",
                str(Path.home() / "Listen template.docx"),
                "Word document (*.docx)")
            if path:
                from ..exporters.docx_template import write_starter_template
                write_starter_template(path)
                self.template_edit.setText(path)

    def values(self):
        text = self.language_combo.currentText().strip()
        index = self.language_combo.findText(text)
        language = (self.language_combo.itemData(index) if index >= 0
                    else text) or "auto"
        return {
            "model_size": self.model_combo.currentData(),
            "language": language,
            "translate": self.translate_default.isChecked(),
            "sensitivity": round(self.sensitivity.value(), 2),
            "match_threshold": round(self.match_threshold.value(), 2),
            "system_audio": self.sys_audio.isChecked(),
            "default_dtype": self.default_dtype.currentData(),
            "template_path": self.template_edit.text().strip(),
            "server_url": self.server_url.text().strip(),
            "api_key": self.api_key.text().strip(),
        }
