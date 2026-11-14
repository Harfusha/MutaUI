import pytest

from ignore_presets import (
    IgnorePresetError,
    IgnorePresetStore,
    apply_converted_rules,
    apply_preset_import,
    explain_ignore_path,
    format_ignore_layers,
    parse_ignore_file,
    path_aware_ignore_rule,
    preset_to_record,
    preview_preset_import,
    validate_ignore_pattern,
)


def test_ignore_patterns_preserve_ordered_negation_and_reject_unsafe_paths():
    assert validate_ignore_pattern("build/") == "build/"
    assert validate_ignore_pattern("!build/keep.txt") == "!build/keep.txt"
    assert validate_ignore_pattern("/build/") == "/build/"
    for pattern in ("", "../outside", r"C:\\secret", "bad\x00pattern"):
        with pytest.raises(IgnorePresetError):
            validate_ignore_pattern(pattern)


def test_versioned_store_crud_and_backup_preserve_pattern_order(tmp_path):
    path = tmp_path / "ignore-presets.json"
    store = IgnorePresetStore(path)
    preset = store.create("Python work", ("__pycache__/", "*.py[cod]", "!keep.py"))
    store.update(preset.id, name="Python source", patterns=("build/", "!build/keep.txt"))

    loaded = IgnorePresetStore(path)
    assert loaded.presets[0].name == "Python source"
    assert loaded.presets[0].patterns == ("build/", "!build/keep.txt")
    assert path.with_suffix(".json.bak").exists()

    loaded.delete(preset.id)
    assert tuple(IgnorePresetStore(path).presets) == ()


def test_store_refuses_stale_write_instead_of_overwriting_newer_presets(tmp_path):
    path = tmp_path / "ignore-presets.json"
    first = IgnorePresetStore(path)
    stale = IgnorePresetStore(path)
    first.create("First", ("build/",))

    with pytest.raises(IgnorePresetError, match="changed on disk"):
        stale.create("Lost update", ("dist/",))
    assert [preset.name for preset in IgnorePresetStore(path).presets] == ["First"]


def test_portable_preset_import_has_preview_and_explicit_create_merge_skip(tmp_path):
    source = IgnorePresetStore(tmp_path / "source.json")
    incoming = source.create("Node", ("node_modules/", "!node_modules/keep/"))
    target = IgnorePresetStore(tmp_path / "target.json")
    preview = preview_preset_import([preset_to_record(incoming)], target.presets)
    assert preview[0].action == "create"

    assert apply_preset_import(target, [preset_to_record(incoming)], {incoming.id: "create"}) == (
        "create",
    )
    assert target.presets[0].patterns == ("node_modules/", "!node_modules/keep/")


def test_portable_preset_import_stops_if_local_store_changes_after_preview(tmp_path):
    path = tmp_path / "target.json"
    store = IgnorePresetStore(path)
    other = IgnorePresetStore(path)
    incoming = IgnorePresetStore(tmp_path / "incoming.json").create("Test", ("*.tmp",))
    other.create("Local edit", ("cache/",))
    with pytest.raises(IgnorePresetError, match="changed after preview"):
        apply_preset_import(store, [preset_to_record(incoming)], {incoming.id: "create"})


def test_malformed_and_future_stores_fail_closed_without_rewriting(tmp_path):
    path = tmp_path / "ignore-presets.json"
    raw = '{"schema_version":99,"presets":[],"future":{"keep":true}}\n'
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(IgnorePresetError):
        IgnorePresetStore(path)
    assert path.read_text(encoding="utf-8") == raw


def test_gitignore_conversion_shows_negation_overrides_and_keeps_order():
    preview = parse_ignore_file("build/\n!build/keep.txt\n*.log\n", source_format="gitignore")

    assert [rule.pattern for rule in preview.rules if rule.supported] == [
        "build/",
        "!build/keep.txt",
        "*.log",
    ]
    assert preview.rules[1].overrides == (1,)
    assert apply_converted_rules(preview, {1, 2, 3}) == (
        "build/",
        "!build/keep.txt",
        "*.log",
    )


def test_conversion_skips_unsupported_or_unsafe_rules_until_selected():
    preview = parse_ignore_file(
        "node_modules/\n../outside\n\\#literal\n# comment\n", source_format="gitignore"
    )

    assert preview.rules[0].supported
    assert not preview.rules[1].supported
    assert not preview.rules[2].supported
    assert not preview.rules[3].supported
    assert apply_converted_rules(preview, {1}) == ("node_modules/",)
    with pytest.raises(IgnorePresetError):
        apply_converted_rules(preview, {2})


def test_docker_conversion_does_not_silently_normalize_rooted_patterns():
    preview = parse_ignore_file("/build\nnode_modules\n", source_format="dockerignore")

    assert not preview.rules[0].supported
    assert preview.rules[1].supported
    assert "root" in preview.rules[0].reason.lower()


def test_conversion_is_bounded_and_rejects_invalid_encoding():
    with pytest.raises(IgnorePresetError):
        parse_ignore_file("x" * 40, source_format="gitignore", max_bytes=10)
    with pytest.raises(IgnorePresetError):
        parse_ignore_file(b"bad\xff", source_format="gitignore")


def test_effective_ignore_preview_explains_layer_order_and_negation():
    result = explain_ignore_path(
        "build/keep.txt",
        global_rules=("*.txt",),
        project_rules=("build/",),
        session_rules=("!build/keep.txt",),
    )
    assert not result.ignored
    assert result.matched_rule == "!build/keep.txt"
    assert result.scope == "session"
    assert "Approximate" in result.note

    ignored = explain_ignore_path("src/debug.log", session_rules=("*.log",))
    assert ignored.ignored and ignored.scope == "session"


def test_ignore_layer_preview_keeps_order_and_marks_unloaded_layers():
    rendered = format_ignore_layers(
        global_rules=(".git/",),
        project_rules=(),
        session_rules=("*.log", "!keep.log"),
    )
    assert rendered.index("Global:") < rendered.index("Project:") < rendered.index("Session:")
    assert "1. *.log\n  2. !keep.log" in rendered
    assert rendered.count("(none loaded)") == 1


def test_quick_ignore_returns_root_relative_rule_and_blocks_unsafe_paths(tmp_path):
    root = tmp_path / "sync-root"
    nested = root / "folder"
    nested.mkdir(parents=True)
    target = nested / "report file.txt"
    target.write_text("data", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    syntax_name = root / "#literal.txt"
    syntax_name.write_text("syntax", encoding="utf-8")

    assert path_aware_ignore_rule(root, target) == "folder/report file.txt"
    for candidate in (outside, syntax_name, nested):
        with pytest.raises(IgnorePresetError):
            path_aware_ignore_rule(root, candidate)
