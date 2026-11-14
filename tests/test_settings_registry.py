from dataclasses import replace
from pathlib import Path

from forward_configuration import render_forward_reference
from mutaui.ui.settings_registry import (
    HELP_BY_KEY,
    SETTINGS_HELP,
    _build_help_index,
    render_reference,
    setting_tooltip,
    write_reference,
)
from settings import DEFAULT_SETTINGS
from sync_configuration import render_sync_reference


def test_every_registered_setting_has_complete_bilingual_metadata():
    assert len(HELP_BY_KEY) == len(SETTINGS_HELP)
    assert set(HELP_BY_KEY) <= set(DEFAULT_SETTINGS)
    for item in SETTINGS_HELP:
        assert item.title_en and item.title_cs
        assert item.description_en and item.description_cs
        assert item.default == DEFAULT_SETTINGS[item.key]
        assert item.validation_en and item.validation_cs
        assert item.scope_en and item.scope_cs
        assert item.native_mapping is not None
        assert item.platforms


def test_registry_tooltips_and_generated_reference_share_the_same_metadata():
    assert "Recommended" in setting_tooltip("interval", "en")
    assert "Doporučeno" in setting_tooltip("interval", "cs")
    reference = render_reference()
    for key in HELP_BY_KEY:
        assert f"`{key}`" in reference


def test_checked_in_reference_is_generated_from_current_registry():
    reference_path = Path(__file__).resolve().parents[1] / "docs" / "settings-reference.md"
    expected = (
        render_reference() + "\n" + render_sync_reference() + "\n" + render_forward_reference()
    )
    assert reference_path.read_text(encoding="utf-8") == expected


def test_help_index_rejects_duplicate_keys_and_defaults_out_of_sync():
    import pytest

    item = SETTINGS_HELP[0]
    with pytest.raises(RuntimeError, match="duplicate keys"):
        _build_help_index((item, item), DEFAULT_SETTINGS)

    changed = replace(item, default=object())
    with pytest.raises(RuntimeError, match="defaults do not match"):
        _build_help_index((changed,), DEFAULT_SETTINGS)


def test_write_reference_writes_rendered_content(tmp_path):
    target = tmp_path / "ref.md"
    write_reference(target)
    assert target.read_text(encoding="utf-8") == render_reference()
