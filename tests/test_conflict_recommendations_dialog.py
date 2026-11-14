import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mutaui.services.conflict_recommendations import ConflictRecommendationPolicy
from mutaui.ui.conflict_recommendations_dialog import ConflictRecommendationsDialog


def test_recommendation_dialog_requires_opt_in_and_only_authors_exact_advice():
    app = QApplication.instance() or QApplication([])
    dialog = ConflictRecommendationsDialog(ConflictRecommendationPolicy(()))

    assert not dialog.enabled_checkbox.isChecked()
    dialog._remove_rule()
    dialog.path_input.setText("src/data.db")
    dialog.side_input.setCurrentIndex(dialog.side_input.findData("alpha"))
    dialog.reason_input.setText("This side is the authoritative database.")
    dialog.add_button.click()

    assert dialog.rules_table.rowCount() == 1
    dialog.enabled_checkbox.setChecked(True)
    dialog.accept()

    policy = dialog.policy
    assert policy.enabled
    assert len(policy.rules) == 1
    assert policy.rules[0].exact_relative_path == "src/data.db"
    assert policy.rules[0].preferred_side == "alpha"
    assert not hasattr(dialog, "resolve_button")
    dialog.rules_table.setCurrentCell(0, 0)
    dialog._remove_rule()
    assert dialog.rules_table.rowCount() == 0
    app.processEvents()


def test_recommendation_dialog_shows_warning_on_invalid_rule_or_policy(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from mutaui.services.conflict_recommendations import RecommendationPolicyError

    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )

    app = QApplication.instance() or QApplication([])
    dialog = ConflictRecommendationsDialog(ConflictRecommendationPolicy(()))

    # Invalid rule: empty path triggers warning on _add_rule
    dialog.path_input.setText("")
    dialog.add_button.click()
    assert len(warnings) == 1
    assert "exact conflict-relative path" in warnings[0]

    # Malformed policy on accept triggers warning on accept
    def _fail_policy():
        raise RecommendationPolicyError("corrupt policy")

    monkeypatch.setattr(dialog, "_candidate_policy", _fail_policy)
    dialog.accept()
    assert len(warnings) == 2
    assert "corrupt policy" in warnings[1]
    app.processEvents()
