"""Build validated local proposals from session-configuration form text."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from forward_configuration import (
    ForwardConfigField,
    ForwardConfigurationDraft,
)
from sync_configuration import SyncConfigField, SyncConfigurationDraft


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
        value: Any
        if field.validation in ("positive-int", "nonnegative-int"):
            value = int(value_text, 10)
        elif field.validation == "bool":
            if value_text.lower() not in ("true", "false"):
                raise ValueError(f"{field.label} must be true or false")
            value = value_text.lower() == "true"
        elif field.validation == "string-list":
            value = json.loads(value_text)
        else:
            value = value_text
        draft.propose(key, value)
    return draft.proposals
