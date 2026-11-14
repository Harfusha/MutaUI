import ast
from pathlib import Path

from PySide6.QtGui import QKeySequence

from mutaui.ui.page_shell import PAGE_ROUTES
from mutaui.ui.preferences import (
    _DIALOG_CATALOG,
    _PLACEHOLDER_CATALOG,
    _ROUTE_CATALOG,
    _TEXT_CATALOG,
    _TITLE_CATALOG,
    _TOOLTIP_CATALOG,
    ADVANCED_ROUTE_IDS,
    native_shortcut_text,
    resolve_theme,
    theme_stylesheet,
    translate,
    translate_route,
    translate_text,
)
from settings import DEFAULT_SETTINGS, validate_settings


def test_shortcut_labels_use_qt_native_key_sequence_text():
    native = QKeySequence("Ctrl+K").toString(QKeySequence.SequenceFormat.NativeText)
    assert native_shortcut_text("Open palette · Ctrl+K") == f"Open palette · {native}"
    shifted = QKeySequence("Ctrl+Shift+1").toString(QKeySequence.SequenceFormat.NativeText)
    assert native_shortcut_text("Ctrl+Shift+1") == shifted


def test_ui_preferences_default_to_system_theme_and_english():
    assert DEFAULT_SETTINGS["theme"] == "system"
    assert DEFAULT_SETTINGS["language"] == "en"


def test_ui_preferences_validate_supported_theme_and_language():
    result = validate_settings({"theme": "light", "language": "cs"})

    assert result.values["theme"] == "light"
    assert result.values["language"] == "cs"
    assert not result.warnings


def test_invalid_ui_preferences_fall_back_without_rejecting_other_settings():
    result = validate_settings({"theme": "neon", "language": "fr", "interval": 8})

    assert result.values["theme"] == "system"
    assert result.values["language"] == "en"
    assert result.values["interval"] == 8
    assert len(result.warnings) == 2


def test_theme_resolution_and_initial_translation_catalog():
    assert resolve_theme("system", system_is_light=True) == "light"
    assert resolve_theme("system", system_is_light=False) == "dark"
    assert resolve_theme("dark", system_is_light=True) == "dark"
    assert translate("mode.basic", "cs") == "Základní"
    assert translate("mode.advanced", "en") == "Advanced"
    assert translate("mode.basic", "fr") == "Basic"


def test_settings_recovery_notice_has_czech_translation():
    assert (
        translate_text("Settings were restored from the last valid backup. Review Settings.", "cs")
        == "Nastavení byla obnovena z poslední platné zálohy. Zkontrolujte Nastavení."
    )
    assert translate("unregistered.translation.key", "cs") == "unregistered.translation.key"


def test_theme_stylesheet_only_replaces_dark_colors_in_light_mode():
    stylesheet = "QWidget { color: #101824; background: #111D2B; }"

    assert theme_stylesheet(stylesheet, "dark") == stylesheet
    light = theme_stylesheet(stylesheet, "light")
    assert light != stylesheet
    assert "#EDF1F5" in light
    assert "#FFFFFF" in light


def test_only_secondary_pages_are_hidden_in_basic_mode():
    route_ids = {route.route_id for route in PAGE_ROUTES}
    assert route_ids >= ADVANCED_ROUTE_IDS
    assert {
        "action-history",
        "daemon",
        "monitoring",
        "diagnostics",
        "alerts",
        "endpoints",
        "servers",
    } == ADVANCED_ROUTE_IDS


def test_route_and_shared_widget_texts_have_czech_catalog_entries():
    assert translate_route("overview", "title", "cs", "Overview") == "Přehled"
    assert translate_route("settings", "title", "cs", "Settings") == "Nastavení"
    assert translate_route("settings", "title", "en", "Settings") == "Settings"
    assert translate_text("WORKSPACE", "cs") == "PRACOVNÍ PROSTOR"


def test_dynamic_mutagen_status_and_endpoint_messages_are_localized():
    statuses = {
        "Disconnected": "Odpojeno",
        "Halted: empty root": "Pozastaveno: kořen je prázdný",
        "Halted: deleted root": "Pozastaveno: kořen byl odstraněn",
        "Halted: root type change": "Pozastaveno: změnil se typ kořene",
        "Connecting ALPHA": "Připojování k ALPHA",
        "Connecting BETA": "Připojování k BETA",
        "Watching": "Sledování změn",
        "Scanning": "Prohledávání",
        "Waiting to retry": "Čekání na opakování",
        "Reconciling": "Vyhodnocování změn",
        "Staging to ALPHA": "Příprava pro ALPHA",
        "Staging to BETA": "Příprava pro BETA",
        "Saving": "Ukládání",
        "Connecting source": "Připojování ke zdroji",
        "Connecting destination": "Připojování k cíli",
        "Forwarding active": "Přesměrování aktivní",
        "Needs attention": "Vyžaduje pozornost",
    }
    assert {text: translate_text(text, "cs") for text in statuses} == statuses
    assert translate_text("The local Mutagen daemon is unavailable.", "cs") == (
        "Místní služba Mutagen není dostupná."
    )
    assert translate_text("Unknown native status 99", "cs") == "Unknown native status 99"
    assert translate_text("Connecting ALPHA", "en") == "Connecting ALPHA"


def test_literal_label_and_button_texts_have_czech_catalog_entries():
    application = Path(__file__).parents[1] / "app.py"
    tree = ast.parse(application.read_text(encoding="utf-8"))
    source_texts = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
        )
        arg_index = 1 if name == "set_localized_text" else 0
        if (
            name
            in {
                "label",
                "button",
                "set_localized_text",
                "localized_label",
                "localized_button",
                "localized_checkbox",
                "localized_action",
            }
            and len(node.args) > arg_index
            and isinstance(node.args[arg_index], ast.Constant)
            and isinstance(node.args[arg_index].value, str)
        ):
            source_texts.add(node.args[arg_index].value)

    assert source_texts <= _TEXT_CATALOG.keys()
    for route in PAGE_ROUTES:
        assert {"title", "caption", "tooltip"} <= _ROUTE_CATALOG[route.route_id].keys()


def test_literal_tooltips_have_czech_catalog_entries():
    application = Path(__file__).parents[1] / "app.py"
    tree = ast.parse(application.read_text(encoding="utf-8"))
    tooltip_texts = {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set_localized_tooltip"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }

    assert tooltip_texts <= _TOOLTIP_CATALOG.keys()


def test_literal_placeholders_have_czech_catalog_entries():
    application = Path(__file__).parents[1] / "app.py"
    tree = ast.parse(application.read_text(encoding="utf-8"))
    placeholders = {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set_localized_placeholder"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }

    assert placeholders <= _PLACEHOLDER_CATALOG.keys()


def test_literal_titles_have_czech_catalog_entries():
    application = Path(__file__).parents[1] / "app.py"
    tree = ast.parse(application.read_text(encoding="utf-8"))
    titles = {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set_localized_title"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }

    assert titles <= _TITLE_CATALOG.keys()


def test_static_message_dialog_copy_uses_czech_catalog():
    application = Path(__file__).parents[1] / "app.py"
    tree = ast.parse(application.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"warning", "information", "question", "critical"}
        ):
            continue
        for index in (1, 2):
            if index >= len(node.args):
                continue
            translated = node.args[index]
            if isinstance(translated, ast.Constant) and isinstance(translated.value, str):
                assert not translated.value
                continue
            if not isinstance(translated, ast.Call):
                continue
            if not (
                isinstance(translated.func, ast.Name)
                and translated.func.id == "translate_text"
                and translated.args
                and isinstance(translated.args[0], ast.Constant)
                and isinstance(translated.args[0].value, str)
            ):
                continue
            assert (
                translated.args[0].value in _DIALOG_CATALOG
                or translate_text(translated.args[0].value, "cs") != translated.args[0].value
            )


def test_file_dialog_titles_and_filters_use_czech_catalog():
    application = Path(__file__).parents[1] / "app.py"
    tree = ast.parse(application.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"getOpenFileName", "getSaveFileName", "getExistingDirectory"}
        ):
            continue
        indexes = (1,) if node.func.attr == "getExistingDirectory" else (1, 3)
        for index in indexes:
            if index >= len(node.args):
                continue
            value = node.args[index]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                assert not value.value
                continue
            assert isinstance(value, ast.Call)
            assert isinstance(value.func, ast.Name) and value.func.id == "translate_text"
            assert value.args and isinstance(value.args[0], ast.Constant)
            assert (
                value.args[0].value in _DIALOG_CATALOG
                or translate_text(value.args[0].value, "cs") != value.args[0].value
            )


def test_form_rows_and_combo_items_have_czech_catalog_entries():
    application = Path(__file__).parents[1] / "app.py"
    tree = ast.parse(application.read_text(encoding="utf-8"))
    row_texts = {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "add_localized_row"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }
    item_texts = {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "add_localized_item"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "add_localized_items"
            and len(node.args) > 1
            and isinstance(node.args[1], (ast.List, ast.Tuple))
        ):
            item_texts.update(
                value.value
                for value in node.args[1].elts
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            )

    assert row_texts <= _TEXT_CATALOG.keys()
    assert item_texts <= _TEXT_CATALOG.keys()


def test_input_dialog_titles_and_prompts_use_czech_catalog():
    application = Path(__file__).parents[1] / "app.py"
    tree = ast.parse(application.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "getText"
        ):
            continue
        for value in node.args[1:3]:
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "format"
                and isinstance(value.func.value, ast.Call)
                and isinstance(value.func.value.func, ast.Name)
                and value.func.value.func.id == "translate_text"
            ):
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                assert not value.value
                continue
            assert isinstance(value, ast.Call)
            assert isinstance(value.func, ast.Name) and value.func.id == "translate_text"
            assert value.args and isinstance(value.args[0], ast.Constant)
            assert value.args[0].value in _DIALOG_CATALOG
