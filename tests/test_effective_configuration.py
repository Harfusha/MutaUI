import pytest

from sync_configuration import (
    build_effective_forward_configuration,
    build_effective_sync_configuration,
    load_effective_sync_configuration,
)

GLOBAL_DEFAULTS = b"""sync:
  defaults:
    mode: one-way-safe
    watch:
      mode: force-poll
      pollingInterval: 40
    ignore:
      paths:
        - '*.log'
      vcs: true
"""


def test_effective_preview_applies_cli_overrides_and_appends_ignore_paths():
    preview = build_effective_sync_configuration(
        GLOBAL_DEFAULTS,
        (
            "--mode=two-way-safe",
            "--watch-polling-interval=5",
            "--ignore=*.tmp",
            "--no-ignore-vcs",
            "C:/alpha",
            "C:/beta",
        ),
        source_path="C:/Users/test/.mutagen.yml",
    )

    assert preview.valid
    assert preview.as_mapping() == {
        "mode": "two-way-safe",
        "watch.mode": "force-poll",
        "watch.pollingInterval": 5,
        "ignore.paths": ["*.log", "*.tmp"],
        "ignore.vcs": False,
    }
    assert preview.origin_for("ignore.paths") == "global config + command line (appended)"
    assert preview.origin_for("mode") == "command line"


@pytest.mark.parametrize(
    ("argument", "key", "global_yaml", "expected_value"),
    (
        (
            "--mode=two-way-safe",
            "mode",
            b"sync:\n  defaults:\n    mode: one-way-safe\n    future: keep\n",
            "two-way-safe",
        ),
        (
            "--watch-mode=no-watch",
            "watch.mode",
            b"sync:\n  defaults:\n    watch:\n      mode: portable\n    future: keep\n",
            "no-watch",
        ),
        (
            "--watch-polling-interval=5",
            "watch.pollingInterval",
            b"sync:\n  defaults:\n    watch:\n      pollingInterval: 40\n    future: keep\n",
            5,
        ),
        (
            "--scan-mode=full",
            "scanMode",
            b"sync:\n  defaults:\n    scanMode: accelerated\n    future: keep\n",
            "full",
        ),
        (
            "--ignore-vcs",
            "ignore.vcs",
            b"sync:\n  defaults:\n    ignore:\n      vcs: false\n    future: keep\n",
            True,
        ),
        (
            "--no-ignore-vcs",
            "ignore.vcs",
            b"sync:\n  defaults:\n    ignore:\n      vcs: true\n    future: keep\n",
            False,
        ),
    ),
)
def test_each_supported_cli_override_replaces_global_value_with_cli_provenance(
    argument, key, global_yaml, expected_value
):
    preview = build_effective_sync_configuration(global_yaml, (argument,))

    assert preview.valid
    assert preview.as_mapping()[key] == expected_value
    assert preview.origin_for(key) == "command line"
    assert preview.as_mapping()["future"] == "keep"
    if key != "mode":
        assert preview.as_mapping() == {key: expected_value, "future": "keep"}


def test_effective_preview_can_disable_global_configuration():
    preview = build_effective_sync_configuration(
        GLOBAL_DEFAULTS,
        ("--no-global-configuration", "--mode=two-way-safe"),
    )

    assert preview.valid
    assert preview.as_mapping() == {"mode": "two-way-safe"}

    invalid_global_is_ignored = build_effective_sync_configuration(
        b"sync: [invalid", ("--no-global-configuration",)
    )
    assert invalid_global_is_ignored.valid
    assert invalid_global_is_ignored.as_mapping() == {}


def test_effective_preview_fails_closed_for_invalid_yaml_or_ignore_shape():
    invalid_yaml = build_effective_sync_configuration(b"sync: [broken", ())
    invalid_ignore = build_effective_sync_configuration(
        b"sync:\n  defaults:\n    ignore:\n      paths: '*.log'\n", ()
    )

    assert not invalid_yaml.valid
    assert not invalid_ignore.valid
    assert invalid_yaml.error
    assert invalid_ignore.error


def test_effective_preview_preserves_unknown_global_values_and_provenance():
    global_yaml = b"""sync:
  defaults:
    futureScalar: keep-me
    futureGroup:
      futureOption: true
    futureEmptyGroup: {}
"""

    preview = build_effective_sync_configuration(global_yaml, ())

    assert preview.valid
    assert preview.as_mapping() == {
        "futureScalar": "keep-me",
        "futureGroup.futureOption": True,
        "futureEmptyGroup": {},
    }
    assert preview.origin_for("futureScalar") == "global config"
    assert preview.origin_for("futureGroup.futureOption") == "global config"
    assert preview.origin_for("futureEmptyGroup") == "global config"


def test_effective_preview_reads_global_file_or_marks_it_absent(tmp_path):
    config = tmp_path / ".mutagen.yml"
    config.write_bytes(GLOBAL_DEFAULTS)
    loaded = load_effective_sync_configuration(config, ())
    absent = load_effective_sync_configuration(tmp_path / "missing.yml", ())

    assert loaded.valid
    assert loaded.source_path == str(config)
    assert loaded.as_mapping()["mode"] == "one-way-safe"
    assert absent.valid
    assert absent.as_mapping() == {}


def test_forward_effective_preview_flattens_global_socket_defaults():
    preview = build_effective_forward_configuration(
        b"forward:\n  defaults:\n    socket:\n      overwriteMode: overwrite\n      owner: operator\n",
        ("--name=web", "tcp:localhost:8080", "tcp:localhost:9000"),
    )

    assert preview.valid
    assert preview.as_mapping() == {
        "socket.overwriteMode": "overwrite",
        "socket.owner": "operator",
    }
    assert preview.origin_for("socket.overwriteMode") == "global config"
