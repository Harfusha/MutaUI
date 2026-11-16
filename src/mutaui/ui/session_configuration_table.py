"""Read-only native configuration rows with editable local proposals."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from forward_configuration import ForwardConfigField, ForwardConfigRow
from mutaui.ui.localization import set_localized_tooltip
from sync_configuration import SyncConfigField, SyncConfigRow


def fill_session_configuration_table(
    table: QTableWidget,
    rows: Sequence[SyncConfigRow | ForwardConfigRow],
    fields_by_key: Mapping[str, SyncConfigField | ForwardConfigField],
    proposals: Mapping[str, Any],
    *,
    proposal_tooltip: str,
) -> None:
    for row_index, row in enumerate(rows):
        field = fields_by_key[row.key]
        current = (
            json.dumps(row.current_value, ensure_ascii=False) if row.present else "Not reported"
        )
        values = (
            field.label,
            current,
            row.origin,
            row.impact,
            row.support_status,
            json.dumps(row.proposed_value, ensure_ascii=False) if row.key in proposals else "",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column != 5:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row_index, column, item)
        options_text = f"\nOptions: {', '.join(field.options)}" if field.options else ""
        cast(QTableWidgetItem, table.item(row_index, 0)).setToolTip(
            f"{field.help_short}\n\n{field.help_full}\nRecommended: {field.recommended}{options_text}"
        )
        set_localized_tooltip(cast(QTableWidgetItem, table.item(row_index, 5)), proposal_tooltip)
