"""Fast offline pre-build checks; intentionally independent of PySide6.

Checks source syntax, mandatory files, build version and selected Qt layout
ownership/type mistakes that otherwise crash the application at startup.
This is NOT a substitute for the GUI smoke test on Windows.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
MODULES = (
    'app.py', 'mutagen_client.py', 'monitoring.py', 'async_recorder.py',
    'performance.py', 'endpoint_inspector.py', 'server_groups.py',
    'log_stream.py', 'insights.py', 'sync_profiles.py',
)
FILES = (
    'assets/mutagencontrol.ico', 'assets/version_info.txt',
    'requirements.txt', 'requirements-build.txt', 'benchmark.py',
    'build_exe.cmd', 'build_fast.cmd', 'demo.cmd', 'start.cmd',
    'gui_preview.cmd', 'gui_capture.py',
    'tests/test_gui_smoke.py',
)

LAYOUT_CONSTRUCTORS = frozenset({
    'QVBoxLayout', 'QHBoxLayout', 'QGridLayout', 'QFormLayout', 'QBoxLayout',
    'QStackedLayout',
})
WIDGET_CONSTRUCTORS = frozenset({
    'QWidget', 'QFrame', 'QScrollArea', 'QLabel', 'QPushButton', 'QComboBox',
    'QSpinBox', 'QCheckBox', 'QPlainTextEdit', 'QTableWidget', 'QProgressBar',
    'QSplitter', 'QDialog', 'QLineEdit', 'QListWidget', 'Graph', 'HealthRing',
})


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def find_qt_layout_misuses(source: str) -> list[str]:
    """Find obvious calls that pass a QLayout to addWidget or vice versa.

    In particular, ``card()`` returns ``(QFrame, QVBoxLayout)``; confusing
    these values previously caused two real Windows launch failures. This
    conservative static check handles local variable assignments, not arbitrary
    dynamic Qt expressions. Real GUI smoke tests remain mandatory for builds.
    """
    tree = ast.parse(source)
    problems = []
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        types: dict[str, list[tuple[int, str]]] = {}
        for node in ast.walk(scope):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            name = _called_name(node.value)
            if name == 'card' and len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple):
                elements = node.targets[0].elts
                if len(elements) == 2:
                    for target, kind in zip(elements, ('widget', 'layout')):
                        if isinstance(target, ast.Name):
                            types.setdefault(target.id, []).append((node.lineno, kind))
            elif name in LAYOUT_CONSTRUCTORS or name in WIDGET_CONSTRUCTORS:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        kind = 'layout' if name in LAYOUT_CONSTRUCTORS else 'widget'
                        types.setdefault(target.id, []).append((node.lineno, kind))
        for node in ast.walk(scope):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('addWidget', 'addLayout') and node.args
                    and isinstance(node.args[0], ast.Name)):
                continue
            var = node.args[0].id
            declared = [item for item in types.get(var, ()) if item[0] < node.lineno]
            if not declared:
                continue
            declared.sort()
            kind = declared[-1][1]
            expected = 'widget' if node.func.attr == 'addWidget' else 'layout'
            if kind != expected:
                problems.append(
                    f'{scope.name}:{node.lineno}: {node.func.attr}({var}) expects '
                    f'{expected}, but {var} is a {kind}'
                )
    return problems


def verify():
    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        raise RuntimeError('Use Python 3.11 through 3.13')
    for name in (*MODULES, *FILES):
        file = ROOT / name
        if not file.is_file() or file.stat().st_size == 0:
            raise RuntimeError('Missing file: ' + name)
    for name in MODULES:
        ast.parse((ROOT / name).read_text(encoding='utf-8'), filename=name)
    mistakes = find_qt_layout_misuses((ROOT / 'app.py').read_text(encoding='utf-8'))
    if mistakes:
        raise RuntimeError('Invalid Qt layout usage:\n' + '\n'.join(mistakes))
    version = (ROOT / 'assets/version_info.txt').read_text(encoding='utf-8')
    if "'8.2.0'" not in version:
        raise RuntimeError('Incorrect EXE version')
    print(f'OK: {len(MODULES)} Python modules, {len(FILES)} files, and static Qt layout checks')


if __name__ == '__main__':
    verify()
