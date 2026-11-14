from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ignore_presets import parse_ignore_file
from mutaui.ui.ignore_rules import IgnoreConversionDialog, IgnorePresetManagerDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_conversion_dialog_applies_only_reviewed_supported_rows():
    _app()
    preview = parse_ignore_file("build/\n../outside\n!build/keep.txt\n", source_format="gitignore")
    dialog = IgnoreConversionDialog(preview)

    assert dialog.selected_patterns() == ("build/", "!build/keep.txt")
    dialog.table.item(2, 0).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.selected_patterns() == ("build/",)
    clean = IgnoreConversionDialog(parse_ignore_file("build/", source_format="gitignore"))
    assert clean.warnings == ()


def test_preset_manager_persists_custom_ordered_patterns(tmp_path):
    _app()
    path = tmp_path / "ignore-presets.json"
    dialog = IgnorePresetManagerDialog(path)
    dialog.name.setText("Review project")
    dialog.description.setText("Kept ordered")
    dialog.patterns.setPlainText("build/\n!build/keep.txt")
    dialog._create()

    from ignore_presets import IgnorePresetStore

    saved = IgnorePresetStore(path).presets
    assert len(saved) == 1
    assert saved[0].patterns == ("build/", "!build/keep.txt")
    reloaded = IgnorePresetManagerDialog(path)
    assert reloaded.presets.count() == 1


def test_preset_manager_update_delete_and_empty_selection_paths(tmp_path, monkeypatch):
    _app()
    path = tmp_path / "ignore-presets.json"
    dialog = IgnorePresetManagerDialog(path)
    dialog.name.setText("Review")
    dialog.patterns.setPlainText("build/")
    dialog._create()
    dialog.presets.setCurrentRow(0)
    assert dialog.presets.currentRow() == 0

    dialog._update()
    dialog._new()
    dialog.presets.setCurrentRow(-1)
    dialog._update()
    dialog._delete()
    assert dialog.name.text() == ""
    assert len(dialog.store.presets) == 1

    dialog.presets.setCurrentRow(0)
    dialog.name.setText("Updated")
    dialog.patterns.setPlainText("cache/\n!cache/keep.txt")
    dialog._update()
    assert dialog.store.presets[0].name == "Updated"
    assert dialog.store.presets[0].patterns == ("cache/", "!cache/keep.txt")

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Cancel,
    )
    dialog._delete()
    assert len(dialog.store.presets) == 1

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    dialog._delete()
    assert dialog.store.presets == []


def test_sync_wizard_loads_saved_custom_presets_and_applies_in_order(tmp_path, monkeypatch):
    _app()
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from app import SessionDialog
    from ignore_presets import IgnorePresetStore

    IgnorePresetStore(tmp_path / "MutagenControl" / "ignore-presets.json").create(
        "Review", ("cache/", "!cache/keep.txt")
    )
    dialog = SessionDialog("sync")
    index = dialog.ignore_preset.findText("Review")
    assert index >= 0
    dialog.apply_ignore_preset(index)
    assert dialog.ignore.toPlainText().splitlines() == ["cache/", "!cache/keep.txt"]


def test_portable_import_preview_offers_explicit_custom_preset_choice(tmp_path):
    _app()
    from app import PortableImportPreviewDialog
    from ignore_presets import IgnorePresetStore, preset_to_record
    from portable_bundle import build_bundle, load_bundle

    preset = IgnorePresetStore(tmp_path / "source.json").create("Project", ("dist/",))
    bundle = load_bundle(
        build_bundle([], {}, app_version="test", ignore_presets=[preset_to_record(preset)]).text
    )
    dialog = PortableImportPreviewDialog(None, bundle, [], [])
    assert dialog.ignore_choices() == {preset.id: "create"}
