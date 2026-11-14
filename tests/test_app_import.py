import runpy
import sys
from pathlib import Path

import app


def test_import_adds_source_package_path_when_missing(monkeypatch):
    app_path = Path(app.__file__).resolve()
    source_path = str(app_path.parent / "src")
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if entry != source_path])
    assert source_path not in sys.path

    namespace = runpy.run_path(str(app_path), run_name="mutaui_secondary_import")

    assert namespace["_SOURCE_PACKAGE_PATH"] == app_path.parent / "src"
    assert source_path in sys.path
