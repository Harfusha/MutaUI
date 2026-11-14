from PySide6.QtWidgets import QApplication

from app import (
    BORDER,
    _czech_plural,
    button,
    field_format,
    readable_record_lines,
    session_detail_html,
)


def test_nested_record_details_are_labeled_instead_of_raw_repr():
    lines = readable_record_lines(
        {
            "sessionName": "alpha",
            "conflicts": [{"localPath": "src/a.py", "status": "modified"}],
        }
    )

    rendered = "\n".join(lines)
    assert "Session name: alpha" in rendered
    assert "Conflicts:" in rendered
    assert "Local path: src/a.py" in rendered
    assert "Status: modified" in rendered
    assert "{'sessionName'" not in rendered


def test_session_detail_html_escapes_values_and_keeps_group_separators():
    lines = ["SESSION DETAILS", "Name\n<alpha & beta>", "Problem: <needs review>", "---"]

    rendered = session_detail_html(lines, "---")

    assert "&lt;alpha &amp; beta&gt;" in rendered
    assert "&lt;needs review&gt;" in rendered
    assert '<hr style="border:0;border-top:1px solid ' + BORDER in rendered
    assert "<alpha & beta>" not in rendered


def test_empty_records_show_clear_fallbacks():
    assert readable_record_lines({}) == ["Details unavailable"]
    assert readable_record_lines([]) == ["None"]


def test_missing_metric_is_labeled_not_measured():
    assert field_format("forward_out_rate", None) == "Not measured"
    assert field_format("cpu", 1.25) == "1.2 %"
    assert field_format("memory", 1024) == "1.0 KB"
    assert field_format("forward_out_rate", 1024) == "1.0 KB/s"
    assert _czech_plural(1, ("one", "few", "many")) == "one"
    assert _czech_plural(3, ("one", "few", "many")) == "few"
    assert _czech_plural(12, ("one", "few", "many")) == "many"


def test_button_optional_size_and_callback_and_nested_sequence_details():
    app = QApplication.instance() or QApplication([])
    assert app is not None
    clicked = []
    plain = button("Plain")
    connected = button("Run", lambda: clicked.append(True), minwidth=90)
    connected.click()

    assert plain.minimumWidth() == 0
    assert connected.minimumWidth() == 90
    assert clicked == [True]
    rendered = readable_record_lines([{"nested": [1, "two"]}, "scalar"])
    assert any("Item 1" in line for line in rendered)
    assert any("• scalar" in line for line in rendered)
    assert readable_record_lines("plain") == ["plain"]
