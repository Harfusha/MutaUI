from app import BORDER, readable_record_lines, session_detail_html


def test_nested_record_details_are_labeled_instead_of_raw_repr():
    lines = readable_record_lines({
        "sessionName": "alpha",
        "conflicts": [{"localPath": "src/a.py", "status": "modified"}],
    })

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
    assert "<hr style=\"border:0;border-top:1px solid " + BORDER in rendered
    assert "<alpha & beta>" not in rendered


def test_empty_records_show_clear_fallbacks():
    assert readable_record_lines({}) == ["Details unavailable"]
    assert readable_record_lines([]) == ["None"]
