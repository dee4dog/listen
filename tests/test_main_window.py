"""The window a new user meets: what it shows before there is anything to
show, and how much of it is on screen at once."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTextBrowser, QToolBar

from scribe.exporters.docx_template import export_docx_template, write_starter_template
from scribe.ui.dialogs import SettingsDialog, TemplateHelpDialog
from scribe.ui.main_window import DEFAULT_SETTINGS
from tests.conftest import store_sessions


def toolbar_of(window):
    return window.findChildren(QToolBar)[0]


# ------------------------------------------------------------ empty state

def test_opens_on_the_welcome_page(window):
    assert window.stack.currentIndex() == 0
    text = window.welcome_view.toPlainText()
    assert "Three steps" in text
    assert "Record" in text and "Export" in text


def test_empty_session_list_explains_itself(window):
    assert window.session_list.count() == 1
    placeholder = window.session_list.item(0)
    assert "Nothing recorded yet" in placeholder.text()
    assert placeholder.flags() == Qt.NoItemFlags, "placeholder is selectable"
    assert placeholder.data(Qt.UserRole) is None


def test_nothing_exportable_without_a_session(window):
    assert not window.export_button.isEnabled()
    for action in (window.export_pdf_action, window.export_docx_action,
                   window.export_template_action, window.export_xlsx_action):
        assert not action.isEnabled()


# ------------------------------------------------------- how much is shown

def test_toolbar_carries_only_the_everyday_actions(window):
    visible = [a.text() for a in toolbar_of(window).actions() if a.text()]
    assert visible == ["● Record", "■ Stop", "Import audio…",
                       "Name the speakers…", "Save changes", "Settings…"]
    assert window.export_button.menu() is not None, "Export dropdown missing"


def test_everything_else_is_reachable_from_the_menus(window):
    assert [a.text() for a in window.menuBar().actions()] == [
        "&Session", "&Transcript", "&Export", "&Word template", "&View",
        "&Help"]


def test_every_action_explains_itself(window):
    """A bare label in a menu is a guess; a tooltip is an answer."""
    actions = [a for a in window.findChildren(type(window.record_action))
               if a.text() and a is not window.quit_action]
    without = [a.text() for a in actions if not a.toolTip()]
    assert not without, f"no tooltip on: {without}"


def test_the_common_actions_have_shortcuts(window):
    shortcuts = {
        window.record_action: "Ctrl+R",
        window.import_action: "Ctrl+O",
        window.save_action: "Ctrl+S",
        window.export_template_action: "Ctrl+E",
        window.help_action: "F1",
    }
    for action, expected in shortcuts.items():
        assert action.shortcut().toString() == expected, action.text()


# ---------------------------------------------------------- with a session

def test_selecting_a_session_shows_it(make_window, data_dir):
    store_sessions(data_dir / "listen.db", "First meeting")
    window = make_window()
    window.session_list.setCurrentItem(window.session_list.item(0))

    assert window.stack.currentIndex() == 1
    assert window.table.rowCount() == 2
    assert window.export_button.isEnabled()
    assert "First meeting" in window.windowTitle()


def test_help_returns_to_the_welcome_page_and_back(make_window, data_dir):
    store_sessions(data_dir / "listen.db", "First meeting")
    window = make_window()
    item = window.session_list.item(0)
    window.session_list.setCurrentItem(item)

    window.on_help()
    assert window.stack.currentIndex() == 0

    # Clicking the recording that is still highlighted changes no selection,
    # so it has to work off the click itself.
    window.session_list.itemClicked.emit(item)
    assert window.stack.currentIndex() == 1
    assert window.session.title == "First meeting"


def test_deleting_the_last_session_returns_to_the_welcome_page(
        make_window, data_dir, prompts):
    from PySide6.QtWidgets import QMessageBox
    store_sessions(data_dir / "listen.db", "Only meeting")
    window = make_window()
    window.session_list.setCurrentItem(window.session_list.item(0))

    prompts.expect(QMessageBox.Yes)
    window.on_delete_session()

    assert window.stack.currentIndex() == 0
    assert window.session is None
    assert "Nothing recorded yet" in window.session_list.item(0).text()


# --------------------------------------------------------- word templates

def test_template_help_documents_every_field(window):
    dialog = TemplateHelpDialog(window, "")
    text = dialog.findChild(QTextBrowser).toPlainText()

    for field in ("{{title}}", "{{transcript}}", "{{action_items}}",
                  "{{summary}}", "{{participants}}"):
        assert field in text
    assert "Making one takes three steps" in text


def test_setting_a_template_is_remembered_and_shown(window, tmp_path):
    template = tmp_path / "house style.docx"
    write_starter_template(template)

    window._set_template(template)

    assert window.settings["template_path"] == str(template)
    assert window._template_for_export() == template
    assert "house style.docx" in window.welcome_view.toPlainText()


def test_template_export_follows_the_speaker_filter(make_window, data_dir,
                                                    session, tmp_path):
    """Exporting one person's copy should not leak the rest of the meeting."""
    window = make_window()
    window.session = session
    window.show_session()
    window.speaker_filter.setCurrentIndex(window.speaker_filter.findData("Johan"))

    template = tmp_path / "t.docx"
    write_starter_template(template)
    out = tmp_path / "johan.docx"
    export_docx_template(window._filtered_session(), template, out)

    from docx import Document
    text = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "Johan" in text
    assert "Morning everyone" not in text, "another speaker's line leaked in"


# -------------------------------------------------------------- settings

def test_settings_round_trip(window, tmp_path):
    template = tmp_path / "t.docx"
    write_starter_template(template)
    window._set_template(template)

    values = SettingsDialog(window, window.settings).values()

    assert values["template_path"] == str(template)
    assert values["model_size"] == "small"      # "Balanced — recommended"
    assert values["language"] == "auto"         # "Detect automatically"
    assert set(values) <= set(DEFAULT_SETTINGS)


def test_an_unlisted_language_code_still_works(window):
    window.settings["language"] = "yue"
    dialog = SettingsDialog(window, window.settings)
    assert dialog.values()["language"] == "yue"
