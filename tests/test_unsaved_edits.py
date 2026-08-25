"""Transcript edits must never disappear without being offered.

Every one of these paths used to throw an edit away silently.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from scribe import db
from tests.conftest import store_sessions


def open_window(make_window, data_dir):
    first, second = store_sessions(
        data_dir / "listen.db", "First meeting", "Second meeting")
    window = make_window()
    return window, first, second


def select(window, title):
    for row in range(window.session_list.count()):
        item = window.session_list.item(row)
        if item.data(Qt.UserRole) is not None and title in item.text():
            window.session_list.setCurrentItem(item)
            return item
    raise AssertionError(f"{title!r} is not in the list")


def edit_first_line(window, text):
    """Type into the Text column the way the user would."""
    window.table.item(0, 2).setText(text)


def visible_text(window):
    return [window.table.item(row, 2).text()
            for row in range(window.table.rowCount())]


# --------------------------------------------------------- noticing edits

def test_editing_marks_the_window_dirty(make_window, data_dir):
    window, _, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    assert not window._dirty

    edit_first_line(window, "EDITED line one.")

    assert window._dirty
    assert "•" in window.windowTitle()
    assert window.save_action.text().endswith("•")


def test_loading_a_session_is_not_an_edit(make_window, data_dir):
    """Repainting the table must not look like the user typing."""
    window, _, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    select(window, "Second meeting")
    assert not window._dirty
    assert "•" not in window.windowTitle()


# ------------------------------------------------- switching away is safe

def test_cancel_keeps_the_edit_and_the_place_in_the_list(make_window,
                                                         data_dir, prompts):
    window, _, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    edit_first_line(window, "EDITED line one.")

    prompts.expect(QMessageBox.Cancel)
    select(window, "Second meeting")

    assert prompts.answered_everything, "switching away did not prompt"
    assert window.session.title == "First meeting"
    assert window._dirty
    assert visible_text(window)[0] == "EDITED line one."
    selected = window.session_list.selectedItems()
    assert selected and "First meeting" in selected[0].text()


def test_save_persists_the_edit(make_window, data_dir, prompts):
    window, first, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    edit_first_line(window, "EDITED line one.")

    prompts.expect(QMessageBox.Save)
    select(window, "Second meeting")

    assert prompts.answered_everything
    assert window.session.title == "Second meeting"
    assert not window._dirty
    assert "•" not in window.windowTitle()
    stored = db.load_session(data_dir / "listen.db", first)
    assert stored.segments[0].text == "EDITED line one."


def test_discard_drops_the_edit_only_when_asked(make_window, data_dir,
                                                prompts):
    window, first, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    edit_first_line(window, "THROW THIS AWAY.")

    prompts.expect(QMessageBox.Discard)
    select(window, "Second meeting")

    assert prompts.answered_everything
    assert not window._dirty
    stored = db.load_session(data_dir / "listen.db", first)
    assert "THROW THIS AWAY." not in stored.segments[0].text


def test_a_clean_switch_never_prompts(make_window, data_dir, prompts):
    window, _, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    select(window, "Second meeting")      # prompts would assert if asked
    assert window.session.title == "Second meeting"


# ---------------------------------------------- the quieter loss paths

def test_switching_theme_keeps_the_edit_without_asking(make_window, data_dir):
    """show_session() repaints from the session, so the edit has to be
    folded in first — and since nothing is lost, there is nothing to ask."""
    window, _, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    edit_first_line(window, "EDITED line one.")

    window.on_toggle_theme()

    assert window._dirty
    assert visible_text(window)[0] == "EDITED line one."


def test_reopening_the_same_session_keeps_the_edit(make_window, data_dir):
    """Press F1, then click the recording you were reading. It is already
    selected, so this goes through the repaint path — the edit must survive
    and, since nothing is lost, without a prompt."""
    window, _, _ = open_window(make_window, data_dir)
    item = select(window, "First meeting")
    edit_first_line(window, "EDITED line one.")

    window.on_help()
    window.session_list.itemClicked.emit(item)

    assert window.stack.currentIndex() == 1
    assert window._dirty
    assert visible_text(window)[0] == "EDITED line one."


def test_recording_and_importing_are_guarded(make_window, data_dir, prompts,
                                             monkeypatch):
    window, _, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    edit_first_line(window, "EDITED line one.")

    # Cancelling the guard must stop the action before anything else happens.
    from scribe.ui import main_window as mw
    monkeypatch.setattr(mw, "ContinueDialog", _never_built)
    monkeypatch.setattr(mw.QFileDialog, "getOpenFileName", _never_built)

    prompts.expect(QMessageBox.Cancel)
    window.on_record()
    assert prompts.answered_everything, "Record did not ask about the edit"

    prompts.expect(QMessageBox.Cancel)
    window.on_import()
    assert prompts.answered_everything, "Import did not ask about the edit"

    assert window._dirty


def _never_built(*args, **kwargs):
    raise AssertionError("the guard should have stopped this")


def test_saving_explicitly_clears_the_mark(make_window, data_dir):
    window, first, _ = open_window(make_window, data_dir)
    select(window, "First meeting")
    edit_first_line(window, "EDITED line one.")

    window.on_save_changes()

    assert not window._dirty
    assert window.save_action.text() == "Save changes"
    assert "•" not in window.windowTitle()
    stored = db.load_session(data_dir / "listen.db", first)
    assert stored.segments[0].text == "EDITED line one."
