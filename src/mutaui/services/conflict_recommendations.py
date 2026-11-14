"""Optional user-authored, advisory conflict choice rules; never auto-resolve."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from mutaui.services.conflict_inspector import ConflictRecord

WinnerChoice = Literal["alpha", "beta"]
# Advisory display is available only through the user-controlled disabled-by-default policy.
RECOMMENDATIONS_ENABLED = True
MAX_RECOMMENDATION_RULES = 20
POLICY_SCHEMA_VERSION = 1
MAX_POLICY_BYTES = 64 * 1024


class RecommendationPolicyError(ValueError):
    """Raised when advisory rules are broad, ambiguous, or malformed."""


@dataclass(frozen=True, slots=True)
class ConflictChoiceRule:
    rule_id: str
    exact_relative_path: str
    preferred_side: WinnerChoice
    explanation: str


@dataclass(frozen=True, slots=True)
class ConflictRecommendation:
    rule_id: str
    session_identifier: str
    relative_path: str
    preferred_side: WinnerChoice
    explanation: str
    automatic: bool = False
    requires_manual_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class ConflictRecommendationPolicy:
    rules: tuple[ConflictChoiceRule, ...]
    enabled: bool = False

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool or not isinstance(self.rules, tuple):
            raise RecommendationPolicyError("Policy state and rule collection must be explicit.")
        if len(self.rules) > MAX_RECOMMENDATION_RULES:
            raise RecommendationPolicyError("Recommendation policy exceeds its bounded rule count.")
        ids: set[str] = set()
        paths: set[str] = set()
        for rule in self.rules:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", rule.rule_id) or rule.rule_id in ids:
                raise RecommendationPolicyError("Rule IDs must be unique short identifiers.")
            path = PurePosixPath(rule.exact_relative_path)
            if (
                not rule.exact_relative_path
                or rule.exact_relative_path.startswith("/")
                or "\\" in rule.exact_relative_path
                or ".." in path.parts
                or "." in path.parts
                or "/".join(path.parts) != rule.exact_relative_path
                or "*" in rule.exact_relative_path
                or "?" in rule.exact_relative_path
                or "\x00" in rule.exact_relative_path
            ):
                raise RecommendationPolicyError("Rules must name one exact conflict-relative path.")
            if rule.exact_relative_path in paths:
                raise RecommendationPolicyError(
                    "Conflicting rules for the same exact path are refused."
                )
            if (
                rule.preferred_side not in {"alpha", "beta"}
                or not isinstance(rule.explanation, str)
                or not rule.explanation.strip()
            ):
                raise RecommendationPolicyError("Rules need one preferred side and a clear reason.")
            ids.add(rule.rule_id)
            paths.add(rule.exact_relative_path)


def recommend_conflict_choice(
    record: ConflictRecord,
    policy: ConflictRecommendationPolicy,
    *,
    enabled: bool = RECOMMENDATIONS_ENABLED,
) -> ConflictRecommendation | None:
    """Return at most one exact-path advisory; this function has no write path."""
    if not enabled or not policy.enabled:
        return None
    if record.relative_path in {"", "(path unavailable)"}:
        return None
    rule = next(
        (item for item in policy.rules if item.exact_relative_path == record.relative_path), None
    )
    if rule is None:
        return None
    return ConflictRecommendation(
        rule.rule_id,
        record.session_identifier,
        record.relative_path,
        rule.preferred_side,
        rule.explanation,
    )


def load_recommendation_policy(path: str | Path) -> ConflictRecommendationPolicy:
    """Load a strict, bounded policy. Missing file means the disabled default."""
    source = Path(path)
    if source.is_symlink():
        raise RecommendationPolicyError("Recommendation policy cannot be a symbolic link.")
    try:
        encoded = source.read_bytes()
    except FileNotFoundError:
        return ConflictRecommendationPolicy(())
    except OSError as exc:
        raise RecommendationPolicyError("Recommendation policy cannot be read.") from exc
    if len(encoded) > MAX_POLICY_BYTES:
        raise RecommendationPolicyError("Recommendation policy exceeds its size limit.")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise RecommendationPolicyError("Recommendation policy has duplicate fields.")
            result[key] = value
        return result

    try:
        raw = json.loads(encoded.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecommendationPolicyError("Recommendation policy is not valid UTF-8 JSON.") from exc
    if (
        not isinstance(raw, dict)
        or set(raw) != {"schema_version", "enabled", "rules"}
        or type(raw["schema_version"]) is not int
        or raw["schema_version"] != POLICY_SCHEMA_VERSION
        or type(raw["enabled"]) is not bool
        or not isinstance(raw["rules"], list)
    ):
        raise RecommendationPolicyError("Recommendation policy schema is unsupported or invalid.")

    rules: list[ConflictChoiceRule] = []
    for item in raw["rules"]:
        if not isinstance(item, dict) or set(item) != {
            "rule_id",
            "exact_relative_path",
            "preferred_side",
            "explanation",
        }:
            raise RecommendationPolicyError("Recommendation rule schema is invalid.")
        if not all(isinstance(item[key], str) for key in item):
            raise RecommendationPolicyError("Recommendation rule fields must be text.")
        rules.append(
            ConflictChoiceRule(
                item["rule_id"],
                item["exact_relative_path"],
                item["preferred_side"],
                item["explanation"],
            )
        )
    return ConflictRecommendationPolicy(tuple(rules), enabled=raw["enabled"])


def save_recommendation_policy(path: str | Path, policy: ConflictRecommendationPolicy) -> None:
    """Atomically save a validated policy; never replace corrupt or linked files."""
    if not isinstance(policy, ConflictRecommendationPolicy):
        raise RecommendationPolicyError("A validated recommendation policy is required.")
    target = Path(path)
    if target.is_symlink():
        raise RecommendationPolicyError("Recommendation policy cannot be a symbolic link.")
    if target.exists():
        load_recommendation_policy(target)
    if not target.parent.is_dir():
        raise RecommendationPolicyError("Recommendation policy directory is unavailable.")
    payload = (
        json.dumps(
            {
                "schema_version": POLICY_SCHEMA_VERSION,
                "enabled": policy.enabled,
                "rules": [
                    {
                        "rule_id": rule.rule_id,
                        "exact_relative_path": rule.exact_relative_path,
                        "preferred_side": rule.preferred_side,
                        "explanation": rule.explanation,
                    }
                    for rule in policy.rules
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    if len(payload.encode("utf-8")) > MAX_POLICY_BYTES:
        raise RecommendationPolicyError("Recommendation policy exceeds its size limit.")
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".conflict-recommendations-", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if target.is_symlink():
            raise RecommendationPolicyError("Recommendation policy cannot be a symbolic link.")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
