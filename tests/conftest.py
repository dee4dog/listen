"""Shared fixtures for the Listen test suite.

The GUI tests build the real ``MainWindow`` on Qt's offscreen platform,
against a throwaway data directory, with the modal message boxes stubbed —
so an unexpected prompt fails the test instead of blocking it forever.
"""
import os

# Must be set before PySide6 is imported, or Qt will look for a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from scribe.models import IssueItem, Segment, Session


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole run — Qt allows no more than one."""
    app = QApplication.instance() or QApplication([])
    from scribe.ui import theme
    theme.apply_theme(app)
    return app


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point %LOCALAPPDATA% at a throwaway folder so tests never touch the
    user's real database, recordings or exports."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    from scribe import data_dir as resolve
    return resolve()


class Prompts:
    """Stands in for the modal message boxes.

    Queue the answers a test expects with :meth:`expect`; anything that asks
    without a queued answer is a prompt the test did not intend, and fails.
    """

    def __init__(self):
        self.answers = []
        self.messages = []

    def expect(self, *answers):
        self.answers.extend(answers)

    @property
    def answered_everything(self):
        """False if a prompt the test queued never actually appeared."""
        return not self.answers

    @property
    def last(self):
        return self.messages[-1] if self.messages else ""

    @staticmethod
    def _text(args):
        # QMessageBox.warning(parent, title, text, buttons, default)
        return args[2] if len(args) > 2 else ""

    def _ask(self, *args, **kwargs):
        assert self.answers, f"unexpected prompt: {self._text(args)!r}"
        self.messages.append(self._text(args))
        return self.answers.pop(0)

    def _tell(self, *args, **kwargs):
        self.messages.append(self._text(args))
        return QMessageBox.Ok


@pytest.fixture
def prompts(monkeypatch):
    stub = Prompts()
    for name in ("warning", "question"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(stub._ask))
    for name in ("information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(stub._tell))
    return stub


@pytest.fixture
def make_window(qapp, data_dir):
    """Build a MainWindow *after* the test has seeded the database, since the
    window reads its session list on construction."""
    built = []

    def factory():
        from scribe.ui.main_window import MainWindow
        window = MainWindow()
        built.append(window)
        return window

    yield factory

    for window in built:
        # Leave nothing in flight, so closing never trips a guard during
        # teardown — when the message boxes may already be un-stubbed.
        window._dirty = False
        window.recorder = None
        window.worker = None
        window.close()


@pytest.fixture
def window(make_window):
    return make_window()


@pytest.fixture
def session():
    """A small meeting with one item of each kind, in two languages."""
    return Session(
        title="Site meeting — Block C",
        dtype="meeting",
        started_at="2026-08-25T14:03:22",
        audio_path="",
        duration=4360.0,
        segments=[
            Segment(0.0, 5.2, "Sarah", "Morning everyone, let's start."),
            Segment(5.2, 19.0, "Johan", "Ek sal die verslag teen Vrydag stuur."),
            Segment(19.0, 44.5, "Sarah", "The drainage is still a problem."),
        ],
        issues=[
            IssueItem("action", "Send the report by Friday", "Johan"),
            IssueItem("issue", "Drainage on the east side is unresolved",
                      "Sarah", recurring=True, prior_date="2026-07-14"),
            IssueItem("decision", "Approved the revised layout", "Sarah"),
            IssueItem("key_point", "Handover moves to September", "Sarah"),
        ],
    )


def store_sessions(database, *titles):
    """Save one two-line session per title, and return their ids in order."""
    from scribe import db
    db.init_db(database)
    for title in titles:
        db.save_session(database, Session(
            title=title, dtype="meeting", started_at="2026-08-25T14:03:22",
            audio_path="", duration=60.0,
            segments=[Segment(0, 5, "Speaker 1", f"{title} line one."),
                      Segment(5, 9, "Speaker 2", f"{title} line two.")]))
    by_title = {title: sid for sid, title, _, _ in db.list_sessions(database)}
    return [by_title[title] for title in titles]
