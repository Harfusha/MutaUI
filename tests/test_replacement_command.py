import pytest

import mutaui.services.replacement_command as replacement_command
from mutaui.services.replacement_command import render_sync_replacement_arguments
from sync_configuration import SYNC_CONFIG_FIELDS

HELP = (
    "--mode string (two-way-safe|two-way-resolved|one-way-safe|one-way-replica) "
    "--watch-mode string (portable|force-poll|no-watch) "
    "--ignore --ignore-vcs --no-ignore-vcs"
)


def test_renderer_preserves_exact_endpoints_and_overlays_only_reviewed_flags():
    original = ("sync", "create", "--mode=two-way-safe", "--name=work", "/alpha", "/beta")

    rendered = render_sync_replacement_arguments(
        original, {"mode": "one-way-safe", "ignore.paths": ["build", "*.tmp"]}, HELP
    )

    assert rendered == (
        "sync",
        "create",
        "--name=work",
        "/alpha",
        "/beta",
        "--mode=one-way-safe",
        "--ignore=build",
        "--ignore=*.tmp",
    )


def test_renderer_requires_documented_capabilities_and_refuses_unknown_fields():
    original = ("sync", "create", "/alpha", "/beta")
    with pytest.raises(ValueError, match="does not document"):
        render_sync_replacement_arguments(original, {"mode": "two-way-safe"}, "--watch-mode")
    with pytest.raises(ValueError, match="does not document"):
        render_sync_replacement_arguments(original, {"alpha.watch.mode": "portable"}, HELP)
    with pytest.raises(ValueError, match="Unknown proposed"):
        render_sync_replacement_arguments(original, {"future.field": "x"}, HELP)


def test_renderer_replaces_boolean_ignore_flags_without_widening_target():
    original = ("sync", "create", "--ignore-vcs", "/alpha", "/beta")

    rendered = render_sync_replacement_arguments(original, {"ignore.vcs": False}, HELP)

    assert rendered == ("sync", "create", "/alpha", "/beta", "--no-ignore-vcs")


def test_renderer_requires_both_supported_boolean_variants():
    with pytest.raises(ValueError, match="does not document both"):
        render_sync_replacement_arguments(
            ("sync", "create", "/alpha", "/beta"),
            {"ignore.vcs": True},
            "--ignore-vcs",
        )


def test_renderer_supports_endpoint_specific_flag_when_help_exposes_it():
    rendered = render_sync_replacement_arguments(
        ("sync", "create", "/alpha", "/beta"),
        {"alpha.watch.mode": "force-poll"},
        "--watch-mode-alpha string (portable|force-poll|no-watch)",
    )

    assert rendered[-1] == "--watch-mode-alpha=force-poll"


def test_renderer_matches_exact_option_before_endpoint_variant_in_help():
    rendered = render_sync_replacement_arguments(
        ("sync", "create", "/alpha", "/beta"),
        {"watch.mode": "portable"},
        "--watch-mode-alpha string (force-poll|no-watch) "
        "--watch-mode string (portable|force-poll|no-watch)",
    )

    assert rendered[-1] == "--watch-mode=portable"


def test_renderer_rejects_schema_choice_not_supported_by_installed_cli_help():
    with pytest.raises(ValueError, match="does not support"):
        render_sync_replacement_arguments(
            ("sync", "create", "/alpha", "/beta"),
            {"stageMode": "internal"},
            "--stage-mode string Specify staging mode (mutagen|neighboring)",
        )


def _enum_help_cases():
    flags = {
        "mode": "--mode",
        "watch.mode": "--watch-mode",
        "scanMode": "--scan-mode",
        "probeMode": "--probe-mode",
        "stageMode": "--stage-mode",
        "symbolicLink.mode": "--symlink-mode",
        "ignore.syntax": "--ignore-syntax",
        "compression.algorithm": "--compression",
        "hash.algorithm": "--hash",
    }
    versioned = {"compression.algorithm", "hash.algorithm"}
    cases = []
    for field in SYNC_CONFIG_FIELDS:
        endpoint = None
        base_key = field.key
        if field.key.startswith(("alpha.", "beta.")):
            endpoint, base_key = field.key.split(".", 1)
        if not field.options and base_key not in versioned:
            continue
        flag = flags[base_key]
        if endpoint:
            flag += "-" + endpoint
        value = field.options[0] if field.options else "value-without-documented-choice"
        cases.append((field.key, value, flag))
    return cases


@pytest.mark.parametrize(("field", "value", "flag"), _enum_help_cases())
def test_renderer_fails_closed_when_cli_help_omits_enum_choices(field, value, flag):
    with pytest.raises(ValueError, match="does not document supported values"):
        render_sync_replacement_arguments(
            ("sync", "create", "/alpha", "/beta"),
            {field: value},
            f"{flag} string without an enumerated choice list",
        )


@pytest.mark.parametrize(
    "original",
    [
        ("sync",),
        ("sync", "resume", "/alpha", "/beta"),
        ("sync", "create", "", "/beta"),
        ("sync", "create", "bad\x00arg", "/beta"),
        ("sync", "create", "--all", "/alpha", "/beta"),
    ],
)
def test_renderer_rejects_malformed_or_broad_original_targets(original):
    with pytest.raises(ValueError):
        render_sync_replacement_arguments(original, {}, HELP)


@pytest.mark.parametrize(
    ("proposal", "help_text", "message"),
    [
        ({"ignore.paths": [""]}, HELP, "nonempty strings"),
        ({"ignore.paths": ["bad\x00path"]}, HELP, "nonempty strings"),
        ({"mode": "one-way-safe"}, "--mode string", "does not document supported values"),
    ],
)
def test_renderer_rejects_invalid_proposal_values_and_undocumented_choices(
    proposal, help_text, message
):
    with pytest.raises(ValueError, match=message):
        render_sync_replacement_arguments(
            ("sync", "create", "/alpha", "/beta"), proposal, help_text
        )


def test_renderer_defensively_rejects_types_returned_by_invalid_validator(monkeypatch):
    monkeypatch.setattr(replacement_command, "validate_sync_proposal", lambda *_: "yes")
    with pytest.raises(ValueError, match="must be boolean"):
        render_sync_replacement_arguments(
            ("sync", "create", "/alpha", "/beta"), {"ignore.vcs": True}, HELP
        )

    monkeypatch.setattr(replacement_command, "validate_sync_proposal", lambda *_: [])
    with pytest.raises(ValueError, match="unsupported value type"):
        render_sync_replacement_arguments(
            ("sync", "create", "/alpha", "/beta"), {"mode": "one-way-safe"}, HELP
        )


def test_documented_choices_require_a_matching_exact_option_and_complete_values():
    assert replacement_command._documented_choices("no options here", "--mode") == frozenset()
    assert replacement_command._documented_choices(
        "--mode string (safe|mirror) --watch-mode string", "--mode"
    ) == frozenset({"safe", "mirror"})
    assert (
        replacement_command._documented_choices(
            "--mode string (safe|) --watch-mode string", "--mode"
        )
        == frozenset()
    )
