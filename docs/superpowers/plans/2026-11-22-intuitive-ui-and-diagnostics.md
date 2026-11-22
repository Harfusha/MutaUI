# Intuitive UI, Button Clipping Fix, and Diagnostics Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate text clipping on primary/standard buttons across all DPI scales, make Diagnostics accessible in the Basic (simple) UI mode, and streamline application navigation into 5 intuitive hubs with guided empty states while preserving all existing features.

**Architecture:** Update Qt stylesheet rules for `QPushButton` and `QPushButton#primary` to guarantee adequate vertical height and padding for font descenders. Adjust `ADVANCED_ROUTE_IDS` so `diagnostics` is visible in both Basic and Advanced modes, alongside Overview, Sync, Forwarding, and Settings. Add quick-action hubs to Diagnostics and enhance empty states with intuitive guided onboarding.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-cov.

**Spec:** User feedback on 2026-11-22 regarding button text clipping (`svnc` vs `sync`), Diagnostics visibility in simple/basic mode, and overall usability simplification without losing any features.

## Global Constraints

- Never break or remove any of the 11 pages, existing shortcuts (`Ctrl+1`..`Ctrl+0`, `Ctrl+Shift+1`, `Ctrl+D`, `Ctrl+,`, `F1`), or settings.
- Maintain $\ge 95\%$ branch and line test coverage.
- All static checks (`run_static_checks.py`: ruff, mypy, mkdocs, pymarkdown, verify_source) must pass cleanly.
- Support both English and Czech localizations with full fidelity.

## Review Focus

- Font descenders (`y`, `g`, `p`, `q`, `j`) must never be clipped at 100%, 125%, 150%, or 200% DPI scales.
- In Basic mode, exactly 5 navigation items are visible: Overview, Sync, Forwarding, Diagnostics, Settings.
- In Advanced mode, all 11 navigation items remain accessible.
- Diagnostics page provides direct one-click access to Troubleshooter dialog, Daemon management, Action History, and Support Bundle.
- Empty states on Sync and Forwarding pages cleanly guide users with drag & drop and clear call-to-actions.

## Tasks

- [ ] **Task 1: Fix button text clipping and font descender metrics**
  - [ ] Add tests in `tests/test_ui_improvements.py` asserting that `QPushButton` and `QPushButton#primary` have `cr.height() >= 22` and render lowercase descenders without truncation.
  - [ ] In `src/mutaui/ui/styles/main_stylesheet.py`, update `QPushButton` with `padding: 7px 16px 8px 16px; min-height: 22px; font-weight: 600;` and `QPushButton#primary` with `font-weight: 700; min-height: 22px;`.
  - [ ] Run pytest on `tests/test_ui_improvements.py` and verify fix with grabbed button pixmap.

- [ ] **Task 2: Make Diagnostics available in Basic mode and enhance Diagnostics hub**
  - [ ] Remove `"diagnostics"` from `ADVANCED_ROUTE_IDS` in `src/mutaui/ui/preferences.py`.
  - [ ] Update `tests/test_ui_preferences.py` to assert the updated `ADVANCED_ROUTE_IDS` set (6 secondary items).
  - [ ] Add test in `tests/test_preferences_controller.py` verifying `diagnostics` is visible in Basic mode.
  - [ ] Enhance `diagnostics_page` in `src/mutaui/ui/controllers/diagnostics_controller.py` with quick-action cards for Troubleshooter (`Ctrl+D`), Daemon management (`Ctrl+5`), Action History (`Ctrl+4`), and Support Bundle.
  - [ ] Add localized translations in `src/mutaui/ui/preferences.py` for new quick-action text.
  - [ ] Verify tests in `test_preferences_controller.py` and `test_diagnostics_controller.py`.

- [ ] **Task 3: Enhance empty states with guided onboarding and intuitive actions**
  - [ ] In `src/mutaui/ui/controllers/pages_controller.py`, update `syncEmptyStateFrame` and `forwardEmptyStateFrame` with clear 2-step onboarding text, drag & drop prompt, and secondary action button for Diagnostics/Troubleshooter.
  - [ ] Ensure `empty_create_btn` has proper sizing, padding, and flawless text rendering.
  - [ ] Add tests in `tests/test_mainwindow_flows.py` or `tests/test_ui_improvements.py` verifying empty state elements and secondary button navigation.

- [ ] **Task 4: Full verification, coverage gate, and visual validation**
  - [ ] Run `python scripts/ci/run_static_checks.py` (all 8 static check steps).
  - [ ] Run `python scripts/ci/run_tests.py` (ensure 100% pass, $\ge 95\%$ coverage).
  - [ ] Generate visual screenshot of the fixed button and empty state to confirm descenders are crisp and unclipped.
