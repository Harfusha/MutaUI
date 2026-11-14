"""Optional, local-only Mutagen sync performance guidance."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from mutaui.services.performance_advisor import analyze_sync_session
from mutaui.ui.preferences import active_language
from sync_configuration import SyncConfigRow

_DOCS = (
    ("Watching", "https://mutagen.io/documentation/synchronization/watching/"),
    (
        "Probing and scanning",
        "https://mutagen.io/documentation/synchronization/probing-and-scanning/",
    ),
    ("Staging", "https://mutagen.io/documentation/synchronization/staging/"),
)


def fill_local_proposal_table(
    table: QTableWidget,
    rows: Sequence[SyncConfigRow],
    recommendations: Mapping[str, Any],
) -> None:
    """Copy supported suggestions into the existing editable local draft cells."""
    row_indices = {row.key: index for index, row in enumerate(rows)}
    for key, value in recommendations.items():
        row_index = row_indices.get(key)
        item = table.item(row_index, 5) if row_index is not None else None
        if item is not None:
            item.setText(json.dumps(value, ensure_ascii=False))


def apply_performance_assistant(
    session: Mapping[str, Any],
    table: QTableWidget,
    rows: Sequence[SyncConfigRow],
    *,
    stale: bool = False,
    parent: QWidget | None = None,
) -> bool:
    """Run optional advice and copy accepted values only into the local draft table."""
    assistant = PerformanceTuningDialog(session, stale=stale, parent=parent)
    if assistant.exec() != QDialog.DialogCode.Accepted:
        return False
    fill_local_proposal_table(table, rows, assistant.recommendations)
    return True


class PerformanceTuningDialog(QDialog):
    """Present qualitative advice; accepting only returns local draft values."""

    def __init__(
        self,
        session: Mapping[str, Any],
        *,
        stale: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        czech = active_language().casefold().startswith("cs")
        self._copy = {
            "title": "Asistent ladění výkonu" if czech else "Performance Tuning Assistant",
            "apply": "Přidat návrhy do místního konceptu"
            if czech
            else "Add suggestions to local draft",
            "close": "Zavřít" if czech else "Close",
            "recommendations": "Volitelné návrhy" if czech else "Optional suggestions",
            "no_recommendation": "Pro známé hodnoty není potřeba návrh změny."
            if czech
            else "No change suggested for the reported values.",
            "qualitative": "Dopady jsou kvalitativní, podle dokumentace; měření výkonu neproběhlo."
            if czech
            else "Impact is qualitative and documentation-based; no performance measurement was run.",
            "unknown_entries": "Počet položek relace neposkytuje. Kořen jsme neprocházeli."
            if czech
            else "Entry count is not reported by this session snapshot. No root scan was run.",
            "large_roots": "U velmi velkých kořenů může úplný sken přidat práci; zrychlený sken využívá dostupné údaje hlídání souborů."
            if czech
            else "For very large roots, full scans can add work; accelerated scans use available filesystem watching information.",
            "remote": "Vzdálené endpointy jsme nezkoušeli ani nekontaktovali."
            if czech
            else "Remote endpoints were not inspected or contacted.",
            "capabilities": "Podpora voleb na endpointech musí být před náhradou ověřena."
            if czech
            else "Endpoint support for these options must be verified before replacement.",
            "draft_only": "Přidání návrhů mění pouze místní koncept. Živá relace zůstává beze změny."
            if czech
            else "Adding suggestions changes only the local draft. The live session remains unchanged.",
            "replacement": "Použití u existující relace vyžaduje samostatnou kontrolu náhrady; náhrada relaci znovu vytvoří."
            if czech
            else "Applying to an existing session requires a separate reviewed replacement; replacement recreates the session.",
            "stale": "Snímek relace je zastaralý. Obnovte stav, než použijete návrhy."
            if czech
            else "The session snapshot is stale. Refresh it before using suggestions.",
            "source": "Oficiální dokumentace Mutagen"
            if czech
            else "Official Mutagen documentation",
        }
        self.setWindowTitle(self._copy["title"])
        self.setMinimumSize(650, 470)
        self.recommendations: dict[str, object] = {}
        self.advice = analyze_sync_session(session)
        if stale:
            self.advice["warnings"].append({"code": "snapshot_stale"})
        self.recommendations = {} if stale else dict(self.advice["recommendations"])

        layout = QVBoxLayout(self)
        heading = QLabel(self._copy["title"], self)
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(heading)

        self.report = QPlainTextEdit(self)
        self.report.setObjectName("performanceTuningReport")
        self.report.setReadOnly(True)
        self.report.setAccessibleName(self._copy["title"])
        self.report.setPlainText(self._report_text(czech, stale))
        layout.addWidget(self.report, 1)

        sources = QLabel(self._source_links(), self)
        sources.setTextFormat(Qt.TextFormat.RichText)
        sources.setOpenExternalLinks(True)
        sources.setWordWrap(True)
        sources.setAccessibleName(self._copy["source"])
        layout.addWidget(sources)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.apply_button = QPushButton(self._copy["apply"], self)
        self.apply_button.setObjectName("applyPerformanceSuggestions")
        self.apply_button.setEnabled(bool(self.recommendations))
        self.apply_button.clicked.connect(self.accept)
        self.close_button = QPushButton(self._copy["close"], self)
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def _report_text(self, czech: bool, stale: bool) -> str:
        lines = [
            self._copy["qualitative"],
            self._copy["unknown_entries"],
            self._copy["large_roots"],
        ]
        if self.recommendations:
            lines.extend(("", self._copy["recommendations"]))
            for key, value in self.recommendations.items():
                lines.append(f"• {key}: {value}")
        else:
            lines.extend(("", self._copy["no_recommendation"]))
        if stale:
            lines.extend(("", self._copy["stale"]))
        for warning in self.advice["warnings"]:
            code = warning["code"]
            side = warning.get("side", "").upper()
            seconds = warning.get("seconds", "")
            messages = {
                "high_frequency_polling": (
                    f"Forced polling every {seconds}s is faster than Mutagen's documented 10s default; consider portable watching."
                    if not czech
                    else f"Vynucené skenování po {seconds} s je rychlejší než výchozích 10 s v dokumentaci Mutagenu; zvažte portable hlídání."
                ),
                "polling_interval_unknown": "Polling interval is not reported."
                if not czech
                else "Interval vynuceného skenování není uveden.",
                "full_scan_large_roots": self._copy["large_roots"],
                "local_root_unreported": f"{side}: local root path is not reported."
                if not czech
                else f"{side}: cesta místního kořene není uvedena.",
                "local_root_network_uninspected": f"{side}: network-share root was not inspected."
                if not czech
                else f"{side}: kořen na síťovém úložišti nebyl zkoumán.",
                "local_root_symlink": f"{side}: the local sync root is a symbolic link; Mutagen does not allow symbolic-link roots."
                if not czech
                else f"{side}: místní kořen je symbolický odkaz; Mutagen takové kořeny nepovoluje.",
                "local_root_missing": f"{side}: the reported local root does not exist."
                if not czech
                else f"{side}: uvedený místní kořen neexistuje.",
                "local_root_unreadable": f"{side}: the current process cannot read the local root."
                if not czech
                else f"{side}: aplikace nemůže místní kořen číst.",
                "local_root_unwritable": f"{side}: the current process cannot write to a receiving endpoint root."
                if not czech
                else f"{side}: aplikace nemůže zapisovat do cílového místního kořene.",
                "cross_filesystem_staging": f"{side}: staging directory and local root are on different filesystems; neighboring staging may avoid an extra copy."
                if not czech
                else f"{side}: staging a místní kořen jsou na různých souborových systémech; sousední staging může vynechat další kopírování.",
                "staging_path_network_uninspected": "The Mutagen data directory is a network share; its filesystem was not inspected."
                if not czech
                else "Adresář dat Mutagenu je na síťovém úložišti; souborový systém nebyl zkoumán.",
                "snapshot_stale": self._copy["stale"],
            }
            lines.extend(("", messages.get(code, code)))
        lines.extend(
            (
                "",
                self._copy["remote"],
                self._copy["capabilities"],
                self._copy["draft_only"],
                self._copy["replacement"],
            )
        )
        return "\n".join(lines)

    def _source_links(self) -> str:
        links = " · ".join(f'<a href="{url}">{name}</a>' for name, url in _DOCS)
        label = self._copy["source"]
        return f"{label}: {links}"
