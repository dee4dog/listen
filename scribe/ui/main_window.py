"""Listen main window."""
import html
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QSizePolicy, QSplitter,
    QStackedWidget, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QTextBrowser, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from .. import APP_NAME, data_dir, db, db_path
from ..analysis.discussion import (DISCUSSION_TYPES, SECTION_TITLES, analyze,
                                   items_for_section)
from ..audio.player import SegmentPlayer
from ..audio.recorder import Recorder
from ..models import Segment, Session, fmt_ts
from ..pipeline import merge_sessions, run_pipeline
from .dialogs import (ContinueDialog, NewSessionDialog, SettingsDialog,
                      SpeakerNameDialog, TemplateHelpDialog)
from . import theme

DEFAULT_SETTINGS = {
    "model_size": "small",
    "language": "auto",
    "translate": False,
    "sensitivity": 0.55,
    "match_threshold": 0.70,
    "system_audio": True,
    "default_dtype": "meeting",
    "server_url": "",
    "api_key": "",
    "theme": "dark",
    "template_path": "",
}

AUDIO_FILTER = "Audio files (*.wav *.mp3 *.m4a *.mp4 *.flac *.ogg *.wma *.aac *.webm);;All files (*.*)"
DOCX_FILTER = "Word document (*.docx)"


class SpeakerDelegate(QStyledItemDelegate):
    """Double-clicking a Speaker cell opens a dropdown of the session's
    speakers; a new name can also be typed directly."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setEditable(True)
        if self._window.session is not None:
            combo.addItems(self._window.session.speaker_names())
        return combo

    def setEditorData(self, editor, index):
        editor.setCurrentText(index.data() or "")

    def setModelData(self, editor, model, index):
        name = editor.currentText().strip()
        if name:
            model.setData(index, name)


class PushWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, session, server_url, api_key):
        super().__init__()
        self.session = session
        self.server_url = server_url
        self.api_key = api_key

    def run(self):
        try:
            from ..sync import push_session
            reply = push_session(self.session, self.server_url, self.api_key)
            self.done.emit(reply)
        except Exception as exc:
            self.failed.emit(str(exc))


class PipelineWorker(QThread):
    progress = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, audio_path, title, dtype, cfg, database):
        super().__init__()
        self.audio_path = audio_path
        self.title = title
        self.dtype = dtype
        self.cfg = cfg
        self.database = database

    def run(self):
        try:
            session = run_pipeline(
                self.audio_path, self.title, self.dtype, self.cfg,
                self.database, progress=self.progress.emit)
            self.done.emit(session)
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 780)
        self.database = db_path()
        db.init_db(self.database)
        self.settings = db.get_settings(self.database, DEFAULT_SETTINGS)
        theme.apply_theme(QApplication.instance(),
                          self.settings.get("theme", "dark"))
        self.session = None
        self.recorder = None
        self.worker = None
        self._dirty = False        # transcript edited but not saved yet
        self.push_worker = None
        self.player = SegmentPlayer()
        self._merge_into = None
        self._record_meta = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(100)
        self._level_timer.timeout.connect(self._update_level)
        self._build_ui()
        self.refresh_sessions()

    # ------------------------------------------------------------------ UI

    def _build_actions(self):
        """Every command the app offers, defined once. The toolbar carries
        only the few used on every session; the rest live in the menus."""
        def make(text, slot, tip=None, shortcut=None):
            action = QAction(text, self)
            action.triggered.connect(slot)
            if tip:
                action.setToolTip(tip)
                action.setStatusTip(tip)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            return action

        self.record_action = make(
            "● Record", self.on_record,
            "Record this PC's microphone, and optionally the meeting audio "
            "it is playing", "Ctrl+R")
        self.stop_action = make(
            "■ Stop", self.on_stop, "Stop recording and start transcribing",
            "Ctrl+.")
        self.stop_action.setEnabled(False)
        self.import_action = make(
            "Import audio…", self.on_import,
            "Transcribe an audio file you already have", "Ctrl+O")
        self.rename_action = make(
            "Name the speakers…", self.on_rename_speakers,
            "Put real names to Speaker 1, 2, 3 — and remember their voices")
        self.save_action = make(
            "Save changes", self.on_save_changes,
            "Save your edits to the transcript and work out the summary again",
            "Ctrl+S")
        self.translate_action = make(
            "Translate to English…", self.on_translate,
            "Re-process this session's audio into an English transcript, "
            "saved as a new session")
        self.export_pdf_action = make(
            "PDF…", lambda: self.on_export("pdf"), "Export as a PDF")
        self.export_docx_action = make(
            "Word…", lambda: self.on_export("docx"),
            "Export as a Word document in the built-in layout")
        self.export_template_action = make(
            "Word, using my template…", lambda: self.on_export("template"),
            "Export as a Word document laid out by your own template file",
            "Ctrl+E")
        self.export_xlsx_action = make(
            "Excel…", lambda: self.on_export("xlsx"),
            "Export as an Excel workbook")
        self.choose_template_action = make(
            "Choose my Word template…", self.on_choose_template,
            "Pick the .docx file Listen should export into")
        self.create_template_action = make(
            "Create a starter template…", self.on_create_template,
            "Save a ready-made template you can restyle in Word")
        self.template_help_action = make(
            "How Word templates work…", self.on_template_help,
            "What a template is, and every field you can put in one")
        self.push_action = make(
            "Send to the shared database", self.on_push,
            "Send this session to the central server set up in Settings")
        self.delete_action = make(
            "Delete this session…", self.on_delete_session,
            "Remove this session and its transcript from your PC")
        self.settings_action = make(
            "Settings…", self.on_settings, "Accuracy, language, template, "
            "recording and shared-database options")
        self.theme_action = make(
            "Switch light / dark", self.on_toggle_theme, None, "Ctrl+T")
        self.help_action = make(
            "Getting started", self.on_help, "A short walkthrough", "F1")
        self.quit_action = make("Exit", self.close, None, "Ctrl+Q")

    def _build_menus(self):
        bar = self.menuBar()

        session_menu = bar.addMenu("&Session")
        session_menu.addAction(self.record_action)
        session_menu.addAction(self.stop_action)
        session_menu.addAction(self.import_action)
        session_menu.addSeparator()
        session_menu.addAction(self.delete_action)
        session_menu.addSeparator()
        session_menu.addAction(self.quit_action)

        transcript_menu = bar.addMenu("&Transcript")
        transcript_menu.addAction(self.rename_action)
        transcript_menu.addAction(self.save_action)
        transcript_menu.addSeparator()
        transcript_menu.addAction(self.translate_action)

        self.export_menu = bar.addMenu("&Export")
        self._fill_export_menu(self.export_menu)
        self.export_menu.addSeparator()
        self.export_menu.addAction(self.push_action)

        template_menu = bar.addMenu("&Word template")
        template_menu.addAction(self.template_help_action)
        template_menu.addSeparator()
        template_menu.addAction(self.create_template_action)
        template_menu.addAction(self.choose_template_action)
        template_menu.addAction(self.export_template_action)

        view_menu = bar.addMenu("&View")
        view_menu.addAction(self.theme_action)
        view_menu.addAction(self.settings_action)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.help_action)
        help_menu.addAction(self.template_help_action)

    def _fill_export_menu(self, menu):
        menu.addAction(self.export_pdf_action)
        menu.addAction(self.export_docx_action)
        menu.addAction(self.export_template_action)
        menu.addAction(self.export_xlsx_action)

    def _build_toolbar(self):
        """Only what is needed on a typical session: record or import, fix the
        speakers, save, export. Everything else is a menu away."""
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        toolbar.addAction(self.record_action)
        toolbar.addAction(self.stop_action)
        toolbar.addAction(self.import_action)
        toolbar.addSeparator()
        toolbar.addAction(self.rename_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()

        # One Export button instead of three, so the formats stay together.
        self.export_button = QToolButton()
        self.export_button.setText("Export ▾")
        self.export_button.setToolTip("Save this session as a document")
        self.export_button.setPopupMode(QToolButton.InstantPopup)
        button_menu = QMenu(self.export_button)
        self._fill_export_menu(button_menu)
        self.export_button.setMenu(button_menu)
        toolbar.addWidget(self.export_button)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addAction(self.settings_action)

    def _build_ui(self):
        self._build_actions()
        self._build_menus()
        self._build_toolbar()

        self.session_list = QListWidget()
        self.session_list.itemSelectionChanged.connect(self.on_session_selected)

        # Left panel: logo, theme toggle below it, then the session list.
        self.logo_label = QLabel()
        self.logo_label.setObjectName("appTitle")
        self.logo_label.setAlignment(Qt.AlignHCenter)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("themeToggle")
        self.theme_btn.setToolTip("Switch between the dark and light theme")
        self.theme_btn.clicked.connect(self.on_toggle_theme)
        self._update_theme_button()

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        self.sessions_caption = QLabel("Your recordings")
        self.sessions_caption.setStyleSheet(
            f"color: {theme.MUTED}; padding: 8px 10px 0 10px; "
            f"font-weight: 600; background: {theme.PANEL};")

        left_layout.addWidget(self.logo_label)
        left_layout.addWidget(self.theme_btn, alignment=Qt.AlignHCenter)
        left_layout.addWidget(self.sessions_caption)
        left_layout.addWidget(self.session_list)
        left_panel.setMaximumWidth(320)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Speaker", "Text"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.cellClicked.connect(self.on_table_cell_clicked)
        self.table.itemChanged.connect(self._on_table_edited)
        self.table.setItemDelegateForColumn(1, SpeakerDelegate(self))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_table_menu)

        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(4, 4, 4, 0)
        filter_bar.addWidget(QLabel("Filter:"))
        self.speaker_filter = QComboBox()
        self.speaker_filter.addItem("All speakers", None)
        self.speaker_filter.setMinimumWidth(160)
        self.speaker_filter.currentIndexChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.speaker_filter)
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("All items", None)
        kind_labels = {"actions": "Tasks / action items", "decisions": "Decisions",
                       "issues": "Key issues", "key_points": "Key points"}
        for section in SECTION_TITLES:
            self.kind_filter.addItem(kind_labels[section], section)
        self.kind_filter.setMinimumWidth(160)
        self.kind_filter.currentIndexChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.kind_filter)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_filters)
        filter_bar.addWidget(clear_btn)
        filter_bar.addStretch(1)

        table_panel = QWidget()
        panel_layout = QVBoxLayout(table_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addLayout(filter_bar)
        panel_layout.addWidget(self.table)

        self.summary = QTextBrowser()
        self.summary.setOpenExternalLinks(False)

        right = QSplitter(Qt.Vertical)
        right.addWidget(table_panel)
        right.addWidget(self.summary)
        right.setSizes([500, 280])

        # Page 0 explains what to do; page 1 is the session itself. A blank
        # window on first launch is the quickest way to lose a new user.
        self.stack = QStackedWidget()
        self.stack.addWidget(self._welcome_page())
        self.stack.addWidget(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.stack)
        splitter.setSizes([280, 920])
        self.setCentralWidget(splitter)

        self.level_label = QLabel("🎤")
        self.level_label.hide()
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedSize(160, 14)
        self.level_bar.setToolTip("Recording input level (mic + system audio)")
        self.level_bar.hide()
        self.statusBar().addPermanentWidget(self.level_label)
        self.statusBar().addPermanentWidget(self.level_bar)

        self.statusBar().showMessage("Ready")
        self._update_actions()

    def _welcome_page(self):
        """The first thing a new user sees, instead of an empty window."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.welcome_view = QTextBrowser()
        self.welcome_view.setOpenExternalLinks(False)
        self.welcome_view.setFrameShape(QTextBrowser.NoFrame)
        layout.addWidget(self.welcome_view)
        self._refresh_welcome()
        return page

    def _refresh_welcome(self):
        """Rebuild the welcome text — also on a theme change, so its colours
        follow the rest of the window."""
        grunge = theme.grunge_font_family()
        template = self.settings.get("template_path", "")
        template_line = (
            f"Word exports use your template: <b>{html.escape(Path(template).name)}</b>."
            if template else
            "Want exports on your own letterhead? "
            "<b>Word template &rarr; How Word templates work…</b>")
        self.welcome_view.setHtml(f"""
<div style="padding:34px 44px">
  <h1 style="font-family:'{grunge}'; color:{theme.ACCENT}; letter-spacing:2px;
             margin-bottom:2px">Welcome to {APP_NAME}</h1>
  <p style="color:{theme.MUTED}; font-size:11pt; margin-top:0">
    Records a conversation, writes down who said what, and pulls out the
    action items. Everything happens on this PC — nothing is uploaded.</p>

  <h2 style="font-family:'{grunge}'; color:{theme.ACCENT_SOFT};
             letter-spacing:1px; margin-top:26px">Three steps</h2>
  <p style="font-size:11pt; line-height:150%">
    <b style="color:{theme.INFO}">1.</b>&nbsp; Press <b>● Record</b> to capture
    this room and any Teams or Meet call playing on this PC — or
    <b>Import audio…</b> for a file you already have.<br>
    <b style="color:{theme.INFO}">2.</b>&nbsp; When it finishes, put real names
    to Speaker&nbsp;1, 2 and 3. Tick <i>Remember voice</i> and {APP_NAME} will
    know them next time.<br>
    <b style="color:{theme.INFO}">3.</b>&nbsp; Read the summary, correct
    anything that is wrong, press <b>Save changes</b>, then <b>Export</b>.</p>

  <p style="color:{theme.MUTED}; margin-top:26px; line-height:150%">
    {template_line}<br>
    The first recording downloads the speech model, so it takes a few minutes
    longer than the ones after it.<br>
    Press <b>F1</b> at any time for this again.</p>

  <p style="color:{theme.WARN}; margin-top:22px">
    ⚠ Tell people they are being recorded — in many places that is the law.</p>
</div>""")

    def _show_welcome(self):
        self._refresh_welcome()
        self.stack.setCurrentIndex(0)

    # ------------------------------------------------------- unsaved edits

    def _on_table_edited(self, _item):
        """Any edit to a Speaker or Text cell. Repopulating the table blocks
        this signal, so it only fires for edits the user actually made."""
        if self.session is not None:
            self._mark_dirty()

    def _mark_dirty(self):
        if self._dirty:
            return
        self._dirty = True
        self.save_action.setText("Save changes •")
        self._update_title()
        self.statusBar().showMessage(
            "Edited — press Save changes (Ctrl+S) to keep it.")

    def _mark_clean(self):
        self._dirty = False
        self.save_action.setText("Save changes")
        self._update_title()

    def _update_title(self):
        """The window title names the open session, with a dot while it has
        unsaved edits."""
        if self.session is None:
            self.setWindowTitle(APP_NAME)
            return
        mark = " •" if self._dirty else ""
        self.setWindowTitle(f"{self.session.title}{mark} — {APP_NAME}")

    def _confirm_discard(self, what):
        """Ask before anything that would throw transcript edits away.
        Returns False if the user would rather stay where they are."""
        if not self._dirty or self.session is None:
            return True
        answer = QMessageBox.warning(
            self, APP_NAME,
            f"You have unsaved changes to “{self.session.title}”.\n\n"
            f"Save them before {what}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            self.on_save_changes()
        else:
            self._mark_clean()
        return True

    def _reselect_current_session(self):
        """Put the highlight back on the open session after the user cancels
        a switch, so the list never disagrees with what is on screen."""
        self.session_list.blockSignals(True)
        self.session_list.clearSelection()
        if self.session is not None:
            for row in range(self.session_list.count()):
                item = self.session_list.item(row)
                if item.data(Qt.UserRole) == self.session.id:
                    item.setSelected(True)
                    self.session_list.setCurrentItem(item)
                    break
        self.session_list.blockSignals(False)

    def _confirm_recording_close(self):
        """Closing mid-recording would bin the audio, which is the one thing
        here that cannot be redone. Offer to keep it as a file instead."""
        if self.recorder is None:
            return True
        title = self._record_meta[0] if self._record_meta else "This recording"
        answer = QMessageBox.warning(
            self, APP_NAME,
            f"“{title}” is still recording.\n\n"
            f"Save keeps the audio as a file you can transcribe later with "
            f"Import audio…\n"
            f"Discard throws the audio away.\n"
            f"Cancel carries on recording.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel)
        if answer == QMessageBox.Cancel:
            return False

        self._stop_recording_ui()
        recorder, self.recorder = self.recorder, None
        self._update_actions()   # in case a later prompt cancels the close
        if answer == QMessageBox.Discard:
            recorder.discard()
            return True

        out = data_dir() / "recordings" / f"rec_{datetime.now():%Y%m%d_%H%M%S}.wav"
        try:
            recorder.stop(out)
        except Exception as exc:
            # The capture threads have already stopped, so there is nothing
            # left to go back to — say what happened and let the close finish.
            QMessageBox.critical(
                self, APP_NAME, f"The recording could not be saved:\n{exc}")
            return True
        QMessageBox.information(
            self, APP_NAME,
            f"The recording was saved to:\n{out}\n\n"
            f"Start {APP_NAME} again and use Import audio… to transcribe it.")
        return True

    def _confirm_processing_close(self):
        if self.worker is None or not self.worker.isRunning():
            return True
        answer = QMessageBox.warning(
            self, APP_NAME,
            "A recording is still being transcribed.\n\n"
            "Closing now abandons that work. The audio file is kept, so you "
            "can import it again later.\n\nClose anyway?",
            QMessageBox.Close | QMessageBox.Cancel, QMessageBox.Cancel)
        return answer == QMessageBox.Close

    def closeEvent(self, event):
        if (self._confirm_recording_close()
                and self._confirm_processing_close()
                and self._confirm_discard(f"closing {APP_NAME}")):
            event.accept()
        else:
            event.ignore()

    def _update_actions(self):
        busy = self.worker is not None and self.worker.isRunning()
        recording = self.recorder is not None
        has_session = self.session is not None
        self.record_action.setEnabled(not busy and not recording)
        self.stop_action.setEnabled(recording)
        self.import_action.setEnabled(not busy and not recording)
        pushing = self.push_worker is not None and self.push_worker.isRunning()
        for action in (self.rename_action, self.save_action, self.delete_action,
                       self.export_pdf_action, self.export_docx_action,
                       self.export_template_action, self.export_xlsx_action,
                       self.translate_action):
            action.setEnabled(has_session and not busy)
        self.export_button.setEnabled(has_session and not busy)
        self.push_action.setEnabled(has_session and not busy and not pushing)

    # ------------------------------------------------------------ recording

    def on_record(self):
        if not self._confirm_discard("starting a new recording"):
            return
        self._merge_into = None
        sessions = db.list_sessions(self.database)
        if sessions:
            cont = ContinueDialog(self, sessions)
            if cont.exec() != ContinueDialog.Accepted:
                return
            mode, sid = cont.choice()
            if mode == "continue":
                try:
                    self._merge_into = db.load_session(self.database, sid)
                except Exception as exc:
                    QMessageBox.critical(self, APP_NAME,
                                         f"Could not load session:\n{exc}")
                    return

        if self._merge_into is not None:
            title = self._merge_into.title
            dtype = self._merge_into.dtype
            sys_audio = bool(self.settings.get("system_audio", True))
            translate = bool(self.settings.get("translate", False))
        else:
            dialog = NewSessionDialog(
                self, for_recording=True,
                default_dtype=self.settings.get("default_dtype", "meeting"),
                default_system_audio=bool(self.settings.get("system_audio", True)),
                default_translate=bool(self.settings.get("translate", False)))
            if dialog.exec() != NewSessionDialog.Accepted:
                self._merge_into = None
                return
            title, dtype, sys_audio, translate = dialog.values()

        try:
            self.recorder = Recorder(capture_system_audio=sys_audio)
            self.recorder.start()
        except Exception as exc:
            self.recorder = None
            self._merge_into = None
            QMessageBox.critical(self, APP_NAME, f"Could not start recording:\n{exc}")
            return
        self._record_meta = (title, dtype, translate)
        note = ("mic + system audio" if self.recorder.system_audio_active
                else "microphone only")
        verb = "Continuing" if self._merge_into is not None else "Recording"
        self.statusBar().showMessage(f"{verb} “{title}” ({note})… 00:00:00")
        self._timer.start(1000)
        self.level_label.show()
        self.level_bar.show()
        self._level_timer.start()
        self._update_actions()

    def _update_level(self):
        if self.recorder is not None:
            level = min(1.0, self.recorder.level() * 6.0)
            self.level_bar.setValue(int(level * 100))

    def _tick(self):
        if self.recorder:
            base = self.statusBar().currentMessage().rsplit(" ", 1)[0]
            self.statusBar().showMessage(f"{base} {fmt_ts(self.recorder.elapsed())}")

    def _stop_recording_ui(self):
        """Put the timer and level meter away once capture has ended."""
        self._timer.stop()
        self._level_timer.stop()
        self.level_label.hide()
        self.level_bar.hide()
        self.level_bar.setValue(0)

    def on_stop(self):
        if not self.recorder:
            return
        self._stop_recording_ui()
        out = data_dir() / "recordings" / f"rec_{datetime.now():%Y%m%d_%H%M%S}.wav"
        recorder, self.recorder = self.recorder, None
        try:
            recorder.stop(out)
        except Exception as exc:
            self._merge_into = None
            QMessageBox.critical(self, APP_NAME, f"Recording failed:\n{exc}")
            self._update_actions()
            return
        title, dtype, translate = self._record_meta
        self._start_pipeline(out, title, dtype, translate=translate)

    # -------------------------------------------------------------- import

    def on_import(self):
        if not self._confirm_discard("importing another recording"):
            return
        self._merge_into = None
        path, _ = QFileDialog.getOpenFileName(self, "Import audio", "", AUDIO_FILTER)
        if not path:
            return
        dialog = NewSessionDialog(
            self, for_recording=False,
            default_dtype=self.settings.get("default_dtype", "meeting"),
            title_hint=Path(path).stem,
            default_translate=bool(self.settings.get("translate", False)))
        if dialog.exec() != NewSessionDialog.Accepted:
            return
        title, dtype, _, translate = dialog.values()
        self._start_pipeline(Path(path), title, dtype, translate=translate)

    # ------------------------------------------------------------- pipeline

    def _start_pipeline(self, audio_path, title, dtype, translate=False):
        cfg = dict(self.settings)
        cfg["task"] = "translate" if translate else "transcribe"
        self.worker = PipelineWorker(audio_path, title, dtype, cfg, self.database)
        self.worker.progress.connect(self.statusBar().showMessage)
        self.worker.done.connect(self._pipeline_done)
        self.worker.failed.connect(self._pipeline_failed)
        self.worker.start()
        self.statusBar().showMessage("Processing…")
        self._update_actions()

    def _pipeline_done(self, session):
        self.worker = None
        if self._merge_into is not None:
            old, self._merge_into = self._merge_into, None
            try:
                session = merge_sessions(old, session, self.database,
                                         data_dir() / "recordings")
            except Exception as exc:
                QMessageBox.warning(
                    self, APP_NAME,
                    f"Could not append to “{old.title}” ({exc}); "
                    f"saving as a separate session instead.")
        self.session = session
        db.save_session(self.database, session)
        self._mark_clean()
        self.refresh_sessions(select_id=session.id)
        self.show_session()
        self.statusBar().showMessage("Transcription complete.")
        self._update_actions()
        self.on_rename_speakers()

    def _pipeline_failed(self, message):
        self.worker = None
        self._merge_into = None
        self.statusBar().showMessage("Processing failed.")
        self._update_actions()
        QMessageBox.critical(self, APP_NAME, f"Processing failed:\n\n{message}")

    # ------------------------------------------------------------- sessions

    def refresh_sessions(self, select_id=None):
        self.session_list.blockSignals(True)
        self.session_list.clear()
        for sid, title, dtype, started in db.list_sessions(self.database):
            label = DISCUSSION_TYPES.get(dtype, {}).get("label", dtype)
            item = QListWidgetItem(f"{title}\n{label} — {started.replace('T', ' ')}")
            item.setData(Qt.UserRole, sid)
            self.session_list.addItem(item)
            if select_id is not None and sid == select_id:
                item.setSelected(True)
                self.session_list.setCurrentItem(item)
        if not self.session_list.count():
            empty = QListWidgetItem(
                "Nothing recorded yet.\nPress ● Record to start.")
            empty.setFlags(Qt.NoItemFlags)
            empty.setForeground(QColor(theme.MUTED))
            self.session_list.addItem(empty)
        self.session_list.blockSignals(False)

    def on_session_selected(self):
        items = self.session_list.selectedItems()
        if not items:
            return
        sid = items[0].data(Qt.UserRole)
        if sid is None:
            return
        if self.session is not None and self.session.id == sid:
            self.show_session()   # e.g. coming back from the welcome page
            return
        if not self._confirm_discard("opening another recording"):
            self._reselect_current_session()
            return
        try:
            self.session = db.load_session(self.database, sid)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not load session:\n{exc}")
            return
        self._mark_clean()
        self.show_session()
        self._update_actions()

    def on_delete_session(self):
        if self.session is None or self.session.id is None:
            return
        answer = QMessageBox.question(
            self, APP_NAME,
            f"Delete session “{self.session.title}” and its transcript?")
        if answer != QMessageBox.Yes:
            return
        db.delete_session(self.database, self.session.id)
        self.session = None
        self.table.setRowCount(0)
        self.summary.clear()
        self._mark_clean()
        self.refresh_sessions()
        self._show_welcome()
        self._update_actions()

    # ---------------------------------------------------------------- theme

    def _update_theme_button(self):
        dark = self.settings.get("theme", "dark") == "dark"
        self.theme_btn.setText("☀  Light theme" if dark else "🌙  Dark theme")
        self.logo_label.setPixmap(theme.logo_pixmap(theme.ACCENT, height=52))

    def on_toggle_theme(self):
        mode = ("light" if self.settings.get("theme", "dark") == "dark"
                else "dark")
        self.settings["theme"] = mode
        db.save_settings(self.database, self.settings)
        theme.apply_theme(QApplication.instance(), mode)
        self._update_theme_button()
        self._refresh_welcome()
        if self.session is not None:
            # Keep any unsaved edits: show_session() repaints the table from
            # the session, so pull the edits into it first.
            self._collect_table()
            self.show_session()   # re-colour speakers, timestamps, summary
        self.statusBar().showMessage(f"{mode.capitalize()} theme applied.")

    # -------------------------------------------------------------- display

    def show_session(self):
        session = self.session
        self.stack.setCurrentIndex(1)
        self.table.blockSignals(True)
        self.table.setRowCount(len(session.segments))
        palette = theme.SPEAKER_COLORS
        colors = {}
        for name in session.speaker_names():
            colors[name] = palette[len(colors) % len(palette)]
        for row, seg in enumerate(session.segments):
            time_item = QTableWidgetItem(fmt_ts(seg.start))
            time_item.setFlags(time_item.flags() & ~Qt.ItemIsEditable)
            time_item.setForeground(QColor(theme.MUTED))
            speaker_item = QTableWidgetItem(seg.speaker)
            speaker_item.setForeground(QColor(colors.get(seg.speaker, theme.TEXT)))
            self.table.setItem(row, 0, time_item)
            self.table.setItem(row, 1, speaker_item)
            self.table.setItem(row, 2, QTableWidgetItem(seg.text))
        self.table.resizeRowsToContents()
        self.table.blockSignals(False)
        self._populate_speaker_filter()
        self._apply_filters()

    def on_table_cell_clicked(self, row, col):
        """Clicking a Speaker cell replays that sentence for identification."""
        if col != 1 or self.session is None or row >= len(self.session.segments):
            return
        audio = self.session.audio_path
        if not audio or not Path(audio).exists():
            self.statusBar().showMessage(
                "The audio file for this session is no longer available.")
            return
        seg = self.session.segments[row]
        if self.player.play(audio, seg.start, seg.end):
            self.statusBar().showMessage(
                f"▶ Playing {seg.speaker} at {fmt_ts(seg.start)}…")

    # -------------------------------------------------------- speaker edits

    def on_table_menu(self, pos):
        """Right-click menu on the transcript: play, reassign, rename."""
        item = self.table.itemAt(pos)
        if item is None or self.session is None:
            return
        row = item.row()
        speaker_item = self.table.item(row, 1)
        current = speaker_item.text() if speaker_item else ""

        menu = QMenu(self)
        play = menu.addAction("▶ Play this sentence")
        rename_all = menu.addAction(f"Rename “{current}” everywhere…")
        assign = menu.addMenu("Assign this line to")
        names = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 1)
            if it and it.text() and it.text() not in names:
                names.append(it.text())
        for name in names:
            action = assign.addAction(name)
            action.setEnabled(name != current)
        assign.addSeparator()
        new_speaker = assign.addAction("New speaker…")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == play:
            self.on_table_cell_clicked(row, 1)
        elif chosen == rename_all:
            self.rename_speaker_everywhere(current)
        elif chosen == new_speaker:
            name, ok = QInputDialog.getText(
                self, APP_NAME, "Assign this line to (new speaker name):")
            if ok and name.strip():
                self._assign_row(row, name.strip())
        else:  # one of the existing speakers
            self._assign_row(row, chosen.text())

    def _assign_row(self, row, name):
        """Reassign a single transcript line to `name` and save."""
        self._collect_table()
        self.session.segments[row].speaker = name
        db.save_session(self.database, self.session)
        self._mark_clean()
        self.show_session()
        self.statusBar().showMessage(f"Line reassigned to {name}.")

    def rename_speaker_everywhere(self, old):
        """Rename a speaker across every line and summary item of the session."""
        if not old:
            return
        new, ok = QInputDialog.getText(
            self, APP_NAME, f"Rename “{old}” everywhere in this session to:",
            text=old)
        new = new.strip() if ok else ""
        if not new or new == old:
            return
        self._collect_table()
        for seg in self.session.segments:
            if seg.speaker == old:
                seg.speaker = new
        for it in self.session.issues:
            if it.speaker == old:
                it.speaker = new
        if old in self.session.centroids:
            self.session.centroids[new] = self.session.centroids.pop(old)
        db.save_session(self.database, self.session)
        self._mark_clean()
        self.show_session()
        self.statusBar().showMessage(f"“{old}” renamed to “{new}” everywhere.")

    # -------------------------------------------------------------- filters

    def _populate_speaker_filter(self):
        """Rebuild the speaker filter for the current session, keeping the
        selection if that speaker still exists."""
        current = self.speaker_filter.currentData()
        self.speaker_filter.blockSignals(True)
        self.speaker_filter.clear()
        self.speaker_filter.addItem("All speakers", None)
        for name in self.session.speaker_names():
            self.speaker_filter.addItem(name, name)
        idx = self.speaker_filter.findData(current)
        self.speaker_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.speaker_filter.blockSignals(False)

    def _clear_filters(self):
        self.speaker_filter.blockSignals(True)
        self.kind_filter.blockSignals(True)
        self.speaker_filter.setCurrentIndex(0)
        self.kind_filter.setCurrentIndex(0)
        self.speaker_filter.blockSignals(False)
        self.kind_filter.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self):
        if self.session is None:
            return
        speaker = self.speaker_filter.currentData()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            hide = speaker is not None and (item is None or item.text() != speaker)
            self.table.setRowHidden(row, hide)
        self._render_summary()

    def _filters_active(self):
        return (self.speaker_filter.currentData() is not None
                or self.kind_filter.currentData() is not None)

    def _filtered_session(self):
        """A copy of the current session containing only what the active
        filters show; the session itself if no filters are set."""
        self._collect_table()
        speaker = self.speaker_filter.currentData()
        kind = self.kind_filter.currentData()
        if speaker is None and kind is None:
            return self.session
        src = self.session
        segments = [s for s in src.segments
                    if speaker is None or s.speaker == speaker]
        issues = [i for i in src.issues
                  if speaker is None or i.speaker == speaker]
        if kind is not None:
            issues = items_for_section(issues, kind)
        suffix = " — " + ", ".join(
            part for part in (speaker, SECTION_TITLES.get(kind)) if part)
        return Session(title=src.title + suffix, dtype=src.dtype,
                       started_at=src.started_at, audio_path=src.audio_path,
                       duration=src.duration, segments=segments, issues=issues,
                       sections_override=[kind] if kind is not None else None)

    def _render_summary(self):
        session = self.session
        speaker = self.speaker_filter.currentData()
        kind = self.kind_filter.currentData()
        dtype = DISCUSSION_TYPES.get(session.dtype, DISCUSSION_TYPES["general"])
        grunge = theme.grunge_font_family()
        h2 = (f"font-family:'{grunge}'; color:{theme.ACCENT}; "
              f"letter-spacing:2px; margin-bottom:2px;")
        h3 = (f"font-family:'{grunge}'; color:{theme.ACCENT_SOFT}; "
              f"letter-spacing:1px; margin-bottom:2px;")
        parts = [
            f"<h2 style=\"{h2}\">{html.escape(session.title)}</h2>",
            f"<p style='color:{theme.MUTED}'><b>{dtype['label']}</b> — "
            f"{session.started_at.replace('T', ' ')} — "
            f"duration {fmt_ts(session.duration)}<br>"
            f"Participants: {html.escape(', '.join(session.speaker_names()) or '—')}</p>",
        ]
        header_len = len(parts)
        if speaker is not None or kind is not None:
            active = ", ".join(part for part in
                               (speaker, SECTION_TITLES.get(kind)) if part)
            parts.append(f"<p style='color:{theme.INFO}'><b>Filtered: "
                         f"{html.escape(active)}</b> (exports follow this filter)</p>")
            header_len += 1
        visible_issues = [it for it in session.issues
                          if speaker is None or it.speaker == speaker]
        recurring = [it for it in visible_issues if it.recurring]
        if recurring:
            parts.append(
                f"<p style='color:{theme.WARN}'><b>⚠ {len(recurring)} recurring "
                f"issue(s) flagged — raised in earlier sessions.</b></p>")
            header_len += 1
        # A kind filter shows just that section, even if the discussion type
        # normally hides it.
        sections = [kind] if kind is not None else dtype["sections"]
        for section in sections:
            items = items_for_section(visible_issues, section)
            if not items:
                continue
            parts.append(f"<h3 style=\"{h3}\">{SECTION_TITLES[section]}</h3><ul>")
            for item in items:
                who = (f"<b style='color:{theme.INFO}'>{html.escape(item.speaker)}:</b> "
                       if item.speaker else "")
                flag = ""
                if item.recurring:
                    flag = (f" <b style='color:{theme.WARN}'>[RECURRING — first raised "
                            f"{html.escape(item.prior_date or 'earlier')}]</b>")
                parts.append(f"<li>{who}{html.escape(item.text)}{flag}</li>")
            parts.append("</ul>")
        if len(parts) <= header_len:
            parts.append("<p><i>Nothing matches the current filter.</i></p>"
                         if (speaker is not None or kind is not None) else
                         "<p><i>No action items or issues were detected.</i></p>")
        self.summary.setHtml("".join(parts))

    # ---------------------------------------------------------------- edits

    def _collect_table(self):
        """Pull edited speaker/text values from the table back into the session."""
        segments = []
        for row, seg in enumerate(self.session.segments):
            speaker_item = self.table.item(row, 1)
            text_item = self.table.item(row, 2)
            speaker = speaker_item.text().strip() if speaker_item else seg.speaker
            text = text_item.text().strip() if text_item else seg.text
            segments.append(Segment(seg.start, seg.end, speaker or seg.speaker, text))
        self.session.segments = segments

    def on_save_changes(self):
        if self.session is None:
            return
        self._collect_table()
        prior = db.get_prior_issues(self.database,
                                    exclude_session_id=self.session.id)
        self.session.issues = analyze(self.session.segments, prior_issues=prior)
        db.save_session(self.database, self.session)
        self._mark_clean()
        self.show_session()
        self.statusBar().showMessage("Changes saved and analysis re-run.")

    def on_translate(self):
        """Re-process the current session's audio with Whisper's translate task,
        producing an English transcript as a new session."""
        if self.session is None:
            return
        if not self._confirm_discard("translating this session"):
            return
        audio = Path(self.session.audio_path) if self.session.audio_path else None
        if audio is None or not audio.exists():
            QMessageBox.warning(
                self, APP_NAME,
                "The original audio file for this session is no longer "
                "available, so it cannot be re-processed.")
            return
        answer = QMessageBox.question(
            self, APP_NAME,
            f"Translate the audio of “{self.session.title}” into an English "
            f"transcript? It will be saved as a new session.")
        if answer != QMessageBox.Yes:
            return
        self._start_pipeline(audio, f"{self.session.title} (English)",
                             self.session.dtype, translate=True)

    def on_rename_speakers(self):
        if self.session is None:
            return
        self._collect_table()
        labels = self.session.speaker_names()
        if not labels:
            return
        dialog = SpeakerNameDialog(self, labels,
                                   has_voice_profiles=set(self.session.centroids),
                                   session=self.session, player=self.player)
        if dialog.exec() != SpeakerNameDialog.Accepted:
            return
        mapping = dialog.mapping()
        if not mapping:
            return
        for seg in self.session.segments:
            if seg.speaker in mapping:
                seg.speaker = mapping[seg.speaker][0]
        for item in self.session.issues:
            if item.speaker in mapping:
                item.speaker = mapping[item.speaker][0]
        for old, (new, remember) in mapping.items():
            centroid = self.session.centroids.pop(old, None)
            if centroid is not None:
                self.session.centroids[new] = centroid
                if remember:
                    db.save_speaker(self.database, new, centroid)
        db.save_session(self.database, self.session)
        self._mark_clean()
        self.refresh_sessions(select_id=self.session.id)
        self.show_session()
        self.statusBar().showMessage("Speakers updated.")

    # -------------------------------------------------------------- exports

    def on_export(self, fmt):
        if self.session is None:
            return
        template = None
        if fmt == "template":
            template = self._template_for_export()
            if template is None:
                return
        session = self._filtered_session()
        safe = "".join(c for c in session.title if c.isalnum() or c in " -_").strip()
        suffix = "docx" if fmt == "template" else fmt
        default = str(data_dir() / "exports" / f"{safe or 'session'}.{suffix}")
        filters = {"pdf": "PDF (*.pdf)", "docx": DOCX_FILTER,
                   "template": DOCX_FILTER, "xlsx": "Excel workbook (*.xlsx)"}
        path, _ = QFileDialog.getSaveFileName(self, "Export", default, filters[fmt])
        if not path:
            return
        try:
            if fmt == "pdf":
                from ..exporters.pdf_export import export_pdf
                export_pdf(session, path)
            elif fmt == "docx":
                from ..exporters.docx_export import export_docx
                export_docx(session, path)
            elif fmt == "template":
                from ..exporters.docx_template import export_docx_template
                export_docx_template(session, template, path)
            else:
                from ..exporters.xlsx_export import export_xlsx
                export_xlsx(session, path)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Export failed:\n{exc}")
            return
        note = " (filtered)" if self._filters_active() else ""
        self.statusBar().showMessage(f"Exported{note} to {path}")

    # ----------------------------------------------------- word templates

    def _template_for_export(self):
        """The configured template, or None — after offering to set one up.
        Nobody should hit a dead end here on their first try."""
        path = self.settings.get("template_path", "").strip()
        if path and Path(path).exists():
            return Path(path)
        if path:
            answer = QMessageBox.question(
                self, APP_NAME,
                f"Your Word template is no longer at:\n{path}\n\n"
                f"Choose a different one?")
            if answer != QMessageBox.Yes:
                return None
            return Path(p) if (p := self.on_choose_template()) else None
        QMessageBox.information(
            self, APP_NAME,
            "You have not set up a Word template yet.\n\n"
            "A template is your own Word document — letterhead, fonts and "
            "all — with fields such as {{title}} and {{transcript}} where "
            "the content should go.")
        self.on_template_help()
        path = self.settings.get("template_path", "").strip()
        return Path(path) if path and Path(path).exists() else None

    def _set_template(self, path):
        self.settings["template_path"] = str(path)
        db.save_settings(self.database, self.settings)
        self._refresh_welcome()
        self.statusBar().showMessage(f"Word template set to {Path(path).name}")

    def on_choose_template(self):
        """Pick the .docx Listen exports into, and check it over first."""
        start = (self.settings.get("template_path", "").strip()
                 or str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a Word template", start, DOCX_FILTER)
        if not path:
            return None
        try:
            from ..exporters.docx_template import scan_template
            found, unknown = scan_template(path)
        except Exception as exc:
            QMessageBox.critical(
                self, APP_NAME,
                f"That file could not be read as a Word document:\n{exc}")
            return None
        if not found:
            answer = QMessageBox.question(
                self, APP_NAME,
                f"“{Path(path).name}” contains no fields Listen recognises, "
                f"so exports would come out with nothing filled in.\n\n"
                f"Use it anyway?")
            if answer != QMessageBox.Yes:
                return None
        elif unknown:
            QMessageBox.warning(
                self, APP_NAME,
                "This template uses fields Listen does not recognise:\n\n"
                + "\n".join(f"    {{{{{name}}}}}" for name in sorted(unknown))
                + "\n\nThey will be left in the document as they are — most "
                  "often that means a typo. See Word template → How Word "
                  "templates work for the list of field names.")
        self._set_template(path)
        return path

    def on_create_template(self):
        """Write a starter template the user can restyle in Word."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save starter template",
            str(Path.home() / f"{APP_NAME} template.docx"), DOCX_FILTER)
        if not path:
            return None
        try:
            from ..exporters.docx_template import write_starter_template
            write_starter_template(path)
        except Exception as exc:
            QMessageBox.critical(
                self, APP_NAME, f"The template could not be saved:\n{exc}")
            return None
        self._set_template(path)
        QMessageBox.information(
            self, APP_NAME,
            f"Starter template saved to:\n{path}\n\n"
            f"Listen will export into it from now on. Open it in Word, make "
            f"it look the way you want, and keep the fields where you want "
            f"that content to appear.")
        return path

    def on_template_help(self):
        dialog = TemplateHelpDialog(
            self, self.settings.get("template_path", "").strip())
        dialog.exec()
        if dialog.choice == "create":
            self.on_create_template()
        elif dialog.choice == "choose":
            self.on_choose_template()
        elif dialog.choice == "clear":
            self.settings["template_path"] = ""
            db.save_settings(self.database, self.settings)
            self._refresh_welcome()
            self.statusBar().showMessage(
                "Word exports will use the built-in layout again.")

    def on_help(self):
        """F1 / Help → Getting started: the welcome page, on demand."""
        if self.stack.currentIndex() == 0:
            self._refresh_welcome()
            return
        self._show_welcome()
        self.statusBar().showMessage(
            "Pick a recording on the left to go back to it.")

    # ----------------------------------------------------------- server push

    def on_push(self):
        if self.session is None:
            return
        server_url = self.settings.get("server_url", "").strip()
        if not server_url:
            QMessageBox.information(
                self, APP_NAME,
                "No central server is configured yet.\n\n"
                "Open Settings and enter the Central server URL "
                "(run server/central_server.py on the host machine first).")
            return
        self._collect_table()
        db.save_session(self.database, self.session)
        self.push_worker = PushWorker(self.session, server_url,
                                      self.settings.get("api_key", ""))
        self.push_worker.done.connect(self._push_done)
        self.push_worker.failed.connect(self._push_failed)
        self.push_worker.start()
        self.statusBar().showMessage(f"Pushing to {server_url}…")
        self._update_actions()

    def _push_done(self, reply):
        self.push_worker = None
        if self.session is not None and self.session.id is not None:
            db.mark_synced(self.database, self.session.id)
        self.statusBar().showMessage(
            f"Pushed to central server (server id {reply.get('server_id', '?')}).")
        self._update_actions()

    def _push_failed(self, message):
        self.push_worker = None
        self.statusBar().showMessage("Push to server failed.")
        self._update_actions()
        QMessageBox.warning(
            self, APP_NAME,
            f"Could not push to the central server:\n{message}\n\n"
            "Check that the server is running and the URL/API key in "
            "Settings are correct.")

    # ------------------------------------------------------------- settings

    def on_settings(self):
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec() == SettingsDialog.Accepted:
            self.settings.update(dialog.values())
            db.save_settings(self.database, self.settings)
            self._refresh_welcome()   # it names the current template
            self.statusBar().showMessage("Settings saved.")


def main():
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(theme.app_icon())
    theme.apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
