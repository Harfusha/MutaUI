import json
from collections.abc import Mapping
from typing import Any

from forward_configuration import ForwardConfigField, ForwardConfigurationDraft
from sync_configuration import SyncConfigField, SyncConfigurationDraft
from sync_profiles import profile_flags


def build_session_configuration_proposal(
    kind: str,
    session: Mapping[str, Any],
    fields: Mapping[str, SyncConfigField | ForwardConfigField],
    values: Mapping[str, str],
) -> dict[str, Any]:
    draft = (
        SyncConfigurationDraft(session) if kind == "sync" else ForwardConfigurationDraft(session)
    )
    for key, raw_value in values.items():
        value_text = raw_value.strip()
        if not value_text:
            continue
        field = fields[key]
        if field.validation in ("positive-int", "nonnegative-int"):
            value: Any = int(value_text, 10)
        elif field.validation == "bool":
            if value_text.lower() not in ("true", "false"):
                raise ValueError(f"{field.label} must be true or false")
            value = value_text.lower() == "true"
        elif field.validation == "string-list":
            value = json.loads(value_text)
        else:
            value = value_text
        draft.propose(key, value)
    proposals: dict[str, Any] = draft.proposals
    return proposals


def build_session_arguments(
    kind: str,
    *,
    name: str,
    paused: bool,
    mode: str,
    profile: str,
    ignore_vcs: bool | None,
    ignore_patterns: list[str],
    alpha: str,
    beta: str,
    socket_options: Mapping[str, tuple[str | None, str, str, str]],
) -> list[str]:
    args: list[str] = []
    if name.strip():
        args.append("--name=" + name.strip())
    if paused:
        args.append("--paused")
    if kind == "sync":
        args.append("--mode=" + mode)
        args.extend(profile_flags(profile))
        if ignore_vcs is True:
            args.append("--ignore-vcs")
        elif ignore_vcs is False:
            args.append("--no-ignore-vcs")
        args.extend("--ignore=" + entry.strip() for entry in ignore_patterns if entry.strip())
    elif any(
        endpoint.startswith("unix:") or ":unix:" in endpoint
        for endpoint in (alpha.lower(), beta.lower())
    ):
        args.append("--socket-overwrite-mode=leave")
        for side, endpoint in (("source", alpha), ("destination", beta)):
            if not endpoint.lower().startswith("unix:") and ":unix:" not in endpoint.lower():
                continue
            overwrite, owner, group, permission = socket_options[side]
            if overwrite is not None and overwrite != "leave":
                args.append(f"--socket-overwrite-mode-{side}={overwrite}")
            for flag, value in (
                ("owner", owner),
                ("group", group),
                ("permission-mode", permission),
            ):
                if value.strip():
                    args.append(f"--socket-{flag}-{side}={value.strip()}")
    return [*args, alpha.strip(), beta.strip()]
