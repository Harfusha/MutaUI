"""Regression for passing the layout instead of the card widget to Qt."""
from pathlib import Path

from verify_source import find_qt_layout_misuses


def test_card_layout_passed_to_add_widget_is_rejected():
    source = '''
def page(self):
    frame, inner = card()
    outer = QVBoxLayout()
    outer.addWidget(inner)
'''
    errors = find_qt_layout_misuses(source)
    assert len(errors) == 1
    assert 'addWidget(inner)' in errors[0]


def test_widget_passed_to_add_layout_is_rejected():
    source = '''
def page(self):
    frame, inner = card()
    outer = QVBoxLayout()
    outer.addLayout(frame)
'''
    errors = find_qt_layout_misuses(source)
    assert len(errors) == 1
    assert 'addLayout(frame)' in errors[0]


def test_correct_card_layout_is_accepted():
    source = '''
def page(self):
    frame, inner = card()
    outer = QVBoxLayout()
    inner.addWidget(QLabel("Some text"))
    outer.addWidget(frame)
'''
    assert find_qt_layout_misuses(source) == []


def test_production_app_has_no_detectable_layout_mixups():
    source = (Path(__file__).resolve().parent.parent / 'app.py').read_text(encoding='utf-8')
    assert find_qt_layout_misuses(source) == []
