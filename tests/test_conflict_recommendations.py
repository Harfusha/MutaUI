import json

import pytest

from mutaui.services.conflict_inspector import ConflictRecord
from mutaui.services.conflict_recommendations import (
    ConflictChoiceRule,
    ConflictRecommendationPolicy,
    RecommendationPolicyError,
    load_recommendation_policy,
    recommend_conflict_choice,
    save_recommendation_policy,
)


def _record(path="src/data.db"):
    return ConflictRecord("sync-exact", "Project", path, (), (), native_digest="d1")


def test_recommendations_require_policy_opt_in_and_exact_path_rule():
    disabled_policy = ConflictRecommendationPolicy(
        (ConflictChoiceRule("keep-alpha-db", "src/data.db", "alpha", "Operator-owned DB"),)
    )
    assert recommend_conflict_choice(_record(), disabled_policy) is None

    policy = ConflictRecommendationPolicy(
        (ConflictChoiceRule("keep-alpha-db", "src/data.db", "alpha", "Operator-owned DB"),),
        enabled=True,
    )

    suggestion = recommend_conflict_choice(_record(), policy)
    assert suggestion is not None
    assert suggestion.preferred_side == "alpha"
    assert suggestion.rule_id == "keep-alpha-db"
    assert not suggestion.automatic
    assert suggestion.requires_manual_confirmation
    assert recommend_conflict_choice(_record("src/other.db"), policy, enabled=True) is None
    assert recommend_conflict_choice(_record(), policy, enabled=False) is None
    assert recommend_conflict_choice(_record("(path unavailable)"), policy, enabled=True) is None


def test_recommendation_policy_store_defaults_disabled_and_round_trips(tmp_path):
    path = tmp_path / "conflict-recommendations.json"
    assert load_recommendation_policy(path) == ConflictRecommendationPolicy(())

    policy = ConflictRecommendationPolicy(
        (ConflictChoiceRule("keep-alpha-db", "src/data.db", "alpha", "Operator-owned DB"),),
        enabled=True,
    )
    save_recommendation_policy(path, policy)

    assert load_recommendation_policy(path) == policy


@pytest.mark.parametrize(
    "payload",
    [b"{", b'{"schema_version":999,"enabled":false,"rules":[]}'],
)
def test_recommendation_policy_store_rejects_invalid_documents_without_rewriting(tmp_path, payload):
    path = tmp_path / "conflict-recommendations.json"
    path.write_bytes(payload)

    with pytest.raises(RecommendationPolicyError):
        load_recommendation_policy(path)

    assert path.read_bytes() == payload
    with pytest.raises(RecommendationPolicyError):
        save_recommendation_policy(path, ConflictRecommendationPolicy(()))
    assert path.read_bytes() == payload


def test_recommendation_policy_rejects_duplicate_json_fields_and_nontext_rules(tmp_path):
    path = tmp_path / "conflict-recommendations.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,"enabled":false,"rules":[]}',
        encoding="utf-8",
    )
    with pytest.raises(RecommendationPolicyError, match="duplicate fields"):
        load_recommendation_policy(path)

    path.write_text(
        '{"schema_version":1,"enabled":true,"rules":[{"rule_id":"r1",'
        '"exact_relative_path":"src/file","preferred_side":"alpha",'
        '"explanation":3}]}',
        encoding="utf-8",
    )
    with pytest.raises(RecommendationPolicyError, match="must be text"):
        load_recommendation_policy(path)


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "**/*.db", "src\\..\\x", ""])
def test_recommendation_rules_reject_broad_or_traversing_paths(path):
    with pytest.raises(RecommendationPolicyError):
        ConflictRecommendationPolicy((ConflictChoiceRule("rule", path, "beta", "reason"),))


def test_recommendation_rules_reject_ambiguous_duplicate_paths_and_excessive_count():
    rule = ConflictChoiceRule("r1", "src/file", "alpha", "reason")
    with pytest.raises(RecommendationPolicyError, match="same exact path"):
        ConflictRecommendationPolicy(
            (rule, ConflictChoiceRule("r2", "src/file", "beta", "other reason"))
        )
    with pytest.raises(RecommendationPolicyError, match="rule count"):
        ConflictRecommendationPolicy(
            tuple(ConflictChoiceRule(f"r{i}", f"path/{i}", "alpha", "reason") for i in range(21))
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        b'{"schema_version":1,"schema_version":1,"enabled":false,"rules":[]}',
        b'{"schema_version":1,"enabled":false,"rules":{},"extra":0}',
        b'{"schema_version":1,"enabled":false,"rules":[{}]}',
    ],
)
def test_recommendation_policy_rejects_encoding_duplicate_and_shape_errors(tmp_path, payload):
    path = tmp_path / "policy.json"
    path.write_bytes(payload)

    with pytest.raises(RecommendationPolicyError):
        load_recommendation_policy(path)


def test_recommendation_policy_save_refuses_wrong_type_missing_directory_and_oversize(tmp_path):
    with pytest.raises(RecommendationPolicyError, match="validated recommendation policy"):
        save_recommendation_policy(tmp_path / "policy.json", object())

    missing = tmp_path / "missing" / "policy.json"
    with pytest.raises(RecommendationPolicyError, match="directory is unavailable"):
        save_recommendation_policy(missing, ConflictRecommendationPolicy(()))

    oversized = ConflictRecommendationPolicy(
        (ConflictChoiceRule("large", "data.bin", "alpha", "x" * (2 * 1024 * 1024)),)
    )
    with pytest.raises(RecommendationPolicyError, match="size limit"):
        save_recommendation_policy(tmp_path / "large.json", oversized)


def test_recommendation_policy_save_and_load_refuse_symlinks(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    original_is_symlink = type(path).is_symlink

    def is_symlink(candidate):
        return candidate == path or original_is_symlink(candidate)

    monkeypatch.setattr(type(path), "is_symlink", is_symlink)
    with pytest.raises(RecommendationPolicyError, match="symbolic link"):
        load_recommendation_policy(path)

    with pytest.raises(RecommendationPolicyError, match="symbolic link"):
        save_recommendation_policy(path, ConflictRecommendationPolicy(()))


def test_recommendation_policy_save_refuses_symlink_created_before_replace(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    original_is_symlink = type(path).is_symlink
    target_checks = 0

    def create_link_at_replace(candidate):
        nonlocal target_checks
        if candidate == path:
            target_checks += 1
            return target_checks >= 2
        return original_is_symlink(candidate)

    monkeypatch.setattr(type(path), "is_symlink", create_link_at_replace)
    with pytest.raises(RecommendationPolicyError, match="symbolic link"):
        save_recommendation_policy(path, ConflictRecommendationPolicy(()))

    assert target_checks == 2
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_recommendation_policy_rejects_unreadable_store_and_nonobject_rule(tmp_path):
    with pytest.raises(RecommendationPolicyError, match="cannot be read"):
        load_recommendation_policy(tmp_path)

    path = tmp_path / "policy.json"
    path.write_text('{"schema_version":1,"enabled":true,"rules":[null]}', encoding="utf-8")
    with pytest.raises(RecommendationPolicyError, match="rule schema"):
        load_recommendation_policy(path)

    with pytest.raises(RecommendationPolicyError, match="unique short identifiers"):
        ConflictRecommendationPolicy(
            (
                ConflictChoiceRule("same", "src/one", "alpha", "reason"),
                ConflictChoiceRule("same", "src/two", "beta", "reason"),
            )
        )


def test_recommendation_policy_rejects_oversized_file(tmp_path):
    path = tmp_path / "policy.json"
    path.write_bytes(b" " * (2 * 1024 * 1024))
    with pytest.raises(RecommendationPolicyError, match="size limit"):
        load_recommendation_policy(path)


@pytest.mark.parametrize("side,reason", [("gamma", "clear reason"), ("alpha", "  ")])
def test_recommendation_policy_rejects_invalid_choice_or_blank_reason(tmp_path, side, reason):
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "enabled": True,
                "rules": [
                    {
                        "rule_id": "r1",
                        "exact_relative_path": "src/file",
                        "preferred_side": side,
                        "explanation": reason,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RecommendationPolicyError, match="preferred side"):
        load_recommendation_policy(path)


@pytest.mark.parametrize("rules,enabled", [((), 1), ([], False)])
def test_recommendation_policy_requires_explicit_state_types(rules, enabled):
    with pytest.raises(RecommendationPolicyError, match="explicit"):
        ConflictRecommendationPolicy(rules, enabled=enabled)
