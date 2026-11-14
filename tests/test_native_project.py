import json

import pytest

from mutaui.projects.native_project import (
    ProjectReferenceStore,
    ProjectStoreError,
    create_native_project_file,
    load_native_project,
    load_project_references,
    project_diff,
    validate_native_project_text,
)


def test_native_project_import_preserves_source_and_summarizes_declarations(tmp_path):
    path = tmp_path / "mutagen.yml"
    original = (
        "# team comments stay intact\n"
        "sync:\n"
        "  defaults:\n"
        "    ignore:\n"
        "      paths: [cache/]\n"
        "  app:\n"
        "    alpha: ./src\n"
        "    beta: user@host:/srv/app\n"
        "    flushOnCreate: true\n"
        "    mode: two-way-safe\n"
        "  malformed: nope\n"
        "forward:\n"
        "  defaults:\n"
        "    socket: {}\n"
        "  web:\n"
        "    source: tcp:localhost:8080\n"
        "    destination: host:tcp:localhost:80\n"
        "beforeCreate:\n"
        "  - docker compose up -d\n"
        "commands:\n"
        "  logs: docker compose logs\n"
        "customRoot: preserved\n"
    )
    path.write_text(original, encoding="utf-8")
    before = path.read_bytes()

    snapshot = load_native_project(path)

    assert snapshot.valid
    assert [item.name for item in snapshot.sessions] == ["app", "web"]
    assert snapshot.sessions[0].flush_on_create is True
    assert snapshot.sessions[0].alpha_or_source == "./src"
    assert ("mode", "two-way-safe") in snapshot.sessions[0].effective_settings
    assert any(key == "ignore" for key, _ in snapshot.sessions[0].effective_settings)
    assert snapshot.sync_default_settings[0][0] == "ignore"
    assert snapshot.sessions[1].kind == "forward"
    assert snapshot.sync_defaults == ("ignore",)
    assert snapshot.forward_defaults == ("socket",)
    assert snapshot.hooks == (("beforeCreate", ("docker compose up -d",)),)
    assert snapshot.commands == (("logs", "docker compose logs"),)
    assert snapshot.unknown_root_keys == ("customRoot",)
    assert any("malformed" in warning for warning in snapshot.warnings)
    assert path.read_bytes() == before


def test_project_diff_shows_external_edits_without_writing(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync:\n  app:\n    alpha: ./one\n    beta: host:/one\n", encoding="utf-8")
    baseline = load_native_project(path)
    path.write_text("sync:\n  app:\n    alpha: ./two\n    beta: host:/one\n", encoding="utf-8")

    current = load_native_project(path)
    diff = project_diff(baseline, current)

    assert "(loaded)" in diff
    assert "(current)" in diff
    assert "-    alpha: ./one" in diff
    assert "+    alpha: ./two" in diff
    assert path.read_text(encoding="utf-8").endswith("alpha: ./two\n    beta: host:/one\n")
    assert project_diff(current, load_native_project(path)) == "No external changes detected."


def test_invalid_native_project_is_reported_without_rewriting(tmp_path):
    path = tmp_path / "mutagen.yml"
    raw = b"sync: {}\nsync: {}\n"
    path.write_bytes(raw)

    snapshot = load_native_project(path)

    assert not snapshot.valid
    assert snapshot.error
    assert path.read_bytes() == raw


def test_project_reference_store_is_local_backed_up_and_stale_safe(tmp_path):
    path = tmp_path / "mutagen-projects.json"
    project = tmp_path / "work" / "mutagen.yml"
    first = ProjectReferenceStore(path)
    stale = ProjectReferenceStore(path)
    reference = first.add(project)
    assert reference.name == "work"
    assert first.add(project).id == reference.id

    second = ProjectReferenceStore(path)
    second.add(tmp_path / "other" / "mutagen.yml")
    assert path.with_suffix(".json.bak").exists()
    try:
        stale.add(tmp_path / "stale" / "mutagen.yml")
    except ValueError as exc:
        assert "changed on disk" in str(exc)
    else:
        raise AssertionError("stale reference write should be rejected")
    assert len(ProjectReferenceStore(path).references) == 2


def test_project_reference_bad_future_schema_fails_closed(tmp_path):
    path = tmp_path / "mutagen-projects.json"
    raw = b'{"schema_version":2,"projects":[],"keep":true}\n'
    path.write_bytes(raw)
    state = load_project_references(path)
    assert not state.valid
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, "must be text"),
        ("sync: [", ""),
        ("custom: true\n", "Declare sync or forward"),
        ("sync: []\n", "sync must be a YAML mapping"),
        ("sync:\n  app: []\n", "entries must map text names"),
        (
            "sync:\n  app:\n    alpha: 1\n    beta: host:/app\n    flushOnCreate: yes\n",
            "flushOnCreate must be a boolean",
        ),
        ("forward:\n  web:\n    source: 1\n    destination: host:tcp:80\n", "requires text source"),
        ("beforeCreate: command\nforward: {}\n", "beforeCreate must be a list"),
        ("commands: []\nsync: {}\n", "commands must be a YAML mapping"),
        ("commands:\n  1: value\nsync: {}\n", "commands entries must map"),
    ],
)
def test_native_project_validation_rejects_invalid_shapes(text, expected):
    valid, errors = validate_native_project_text(text)

    assert not valid
    assert any(expected in error for error in errors)


def test_native_project_import_keeps_warnings_for_unusable_sections(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(
        "sync: []\n"
        "forward:\n  defaults: []\n  web: not-a-map\n"
        "afterCreate: invalid\n"
        "commands:\n  run: []\n",
        encoding="utf-8",
    )

    snapshot = load_native_project(path)

    assert snapshot.valid
    assert snapshot.sessions == ()
    assert any("sync is not a YAML mapping" in warning for warning in snapshot.warnings)
    assert any("forward.defaults is not a YAML mapping" in warning for warning in snapshot.warnings)
    assert any("afterCreate must be a list" in warning for warning in snapshot.warnings)
    assert any("commands entries must map" in warning for warning in snapshot.warnings)


def test_project_diff_rejects_different_paths_and_handles_non_utf8(tmp_path):
    first_path = tmp_path / "one.yml"
    second_path = tmp_path / "two.yml"
    first_path.write_text("sync: {}\n", encoding="utf-8")
    second_path.write_bytes(b"\xff")
    first = load_native_project(first_path)
    second = load_native_project(second_path)

    with pytest.raises(ValueError, match="same native project path"):
        project_diff(first, second)
    first_path.write_bytes(b"\xff")
    invalid_version = load_native_project(first_path)
    assert "Diff unavailable" in project_diff(first, invalid_version)


@pytest.mark.parametrize(
    ("name", "text", "audit_same", "directory_exists", "expected"),
    [
        ("other.yml", "sync: {}\n", False, True, "named mutagen.yml"),
        ("mutagen.yml", "invalid: [\n", False, True, "invalid native project"),
        ("mutagen.yml", "sync: {}\n", True, True, "separate local file"),
        ("mutagen.yml", "sync: {}\n", False, False, "directory must already exist"),
    ],
)
def test_native_project_create_validates_path_text_and_audit_scope(
    tmp_path, name, text, audit_same, directory_exists, expected
):
    directory = tmp_path / "existing"
    if directory_exists:
        directory.mkdir()
    target = directory / name
    audit = target if audit_same else tmp_path / "audit.jsonl"

    with pytest.raises(ProjectStoreError, match=expected):
        create_native_project_file(target, text, audit_path=audit)

    assert not target.exists()


def test_native_project_create_audits_and_never_overwrites_existing_file(tmp_path):
    target = tmp_path / "mutagen.yml"
    audit = tmp_path / "audit.jsonl"
    text = "sync:\n  local:\n    alpha: ./src\n    beta: ./copy\n"

    created = create_native_project_file(target, text, audit_path=audit)

    assert created.valid
    assert target.read_text(encoding="utf-8") == text
    events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [event["phase"] for event in events] == ["prepared", "created"]
    assert all(event["action"] == "create_project_file" for event in events)
    with pytest.raises(ProjectStoreError, match="never overwritten"):
        create_native_project_file(target, text, audit_path=audit)
    assert target.read_text(encoding="utf-8") == text


@pytest.mark.parametrize(
    "projects",
    [
        None,
        [None],
        [{"id": "", "name": "p", "path": "/tmp/p.yml", "created_at": "now"}],
        [{"id": "id", "name": " ", "path": "/tmp/p.yml", "created_at": "now"}],
        [{"id": "id", "name": "p", "path": "relative.yml", "created_at": "now"}],
        [{"id": "id", "name": "p", "path": "/tmp/p.yml", "created_at": 1}],
        [
            {"id": "same", "name": "one", "path": "/tmp/one.yml", "created_at": "now"},
            {"id": "same", "name": "two", "path": "/tmp/two.yml", "created_at": "now"},
        ],
        [
            {"id": "one", "name": "one", "path": "/tmp/shared.yml", "created_at": "now"},
            {"id": "two", "name": "two", "path": "/tmp/SHARED.yml", "created_at": "now"},
        ],
    ],
)
def test_project_reference_loader_rejects_invalid_or_duplicate_entries(tmp_path, projects):
    path = tmp_path / "projects.json"
    absolute_paths = [str(tmp_path / "one.yml"), str(tmp_path / "two.yml")]
    if projects and projects[0] and projects[0].get("path") == "/tmp/p.yml":
        projects[0]["path"] = str(tmp_path / "p.yml")
    elif projects and projects[0] and projects[0].get("path") == "/tmp/one.yml":
        projects[0]["path"] = absolute_paths[0]
        projects[1]["path"] = absolute_paths[1]
    elif projects and projects[0] and projects[0].get("path") == "/tmp/shared.yml":
        projects[0]["path"] = absolute_paths[0]
        projects[1]["path"] = absolute_paths[0].upper()
    path.write_text(json.dumps({"schema_version": 1, "projects": projects}), encoding="utf-8")

    result = load_project_references(path)

    assert not result.valid
    assert result.warnings


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"\xff",
        b'{"schema_version":true,"projects":[]}',
        b'{"schema_version":1,"projects":[],"extra":true}',
        b'{"schema_version":1,"projects":{}}',
    ],
)
def test_project_reference_loader_fails_closed_on_corrupt_store(tmp_path, raw):
    path = tmp_path / "projects.json"
    path.write_bytes(raw)

    result = load_project_references(path)

    assert not result.valid
    assert result.warnings
    assert path.read_bytes() == raw


def test_project_reference_store_remove_requires_existing_id_and_preserves_backup(tmp_path):
    path = tmp_path / "projects.json"
    store = ProjectReferenceStore(path)
    reference = store.add(tmp_path / "work" / "mutagen.yml", name="  Demo  ")
    assert reference.name == "Demo"

    with pytest.raises(KeyError):
        store.remove("missing")
    store.remove(reference.id)

    assert ProjectReferenceStore(path).references == []
    assert path.with_suffix(".json.bak").exists()


def test_native_project_import_warns_for_non_text_names_and_missing_endpoints(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(
        "sync:\n"
        "  7:\n    alpha: ./src\n    beta: ./copy\n"
        "  incomplete:\n    alpha: 7\n    flushOnCreate: yes\n"
        "forward:\n  web:\n    source: tcp:localhost:1\n",
        encoding="utf-8",
    )

    snapshot = load_native_project(path)

    assert snapshot.valid
    assert any("sync contains a non-text key" in warning for warning in snapshot.warnings)
    assert any("flushOnCreate is not a boolean" in warning for warning in snapshot.warnings)
    assert any(
        "sync.incomplete.beta is missing or not text" in warning for warning in snapshot.warnings
    )
    assert any(
        "forward.web.destination is missing or not text" in warning for warning in snapshot.warnings
    )


def test_native_project_import_warns_when_commands_section_is_not_a_mapping(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text("sync: {}\ncommands: []\n", encoding="utf-8")

    snapshot = load_native_project(path)

    assert snapshot.valid
    assert any("commands is not a YAML mapping" in warning for warning in snapshot.warnings)


def test_native_project_validation_accepts_defaults_and_well_formed_commands():
    valid, errors = validate_native_project_text(
        "sync:\n"
        "  defaults:\n    ignore:\n      paths: [cache/]\n"
        "commands:\n  logs: docker compose logs\n"
    )

    assert valid
    assert errors == ()


def test_native_project_validation_rejects_unencodable_text():
    valid, errors = validate_native_project_text("\ud800")

    assert not valid
    assert errors == ("Project content must be valid UTF-8 text.",)


def test_native_project_create_records_failed_link_without_replacing_file(tmp_path, monkeypatch):
    import mutaui.projects.native_project as native_project

    target = tmp_path / "mutagen.yml"
    audit = tmp_path / "audit.jsonl"

    def fail_link(_temporary, _target):
        raise FileExistsError("target appeared")

    monkeypatch.setattr(native_project.os, "link", fail_link)
    with pytest.raises(FileExistsError, match="target appeared"):
        create_native_project_file(
            target,
            "sync:\n  local:\n    alpha: ./src\n    beta: ./copy\n",
            audit_path=audit,
        )

    events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [event["phase"] for event in events] == ["prepared", "failed"]
    assert not target.exists()
    assert list(tmp_path.glob(".mutagen-project-*.tmp")) == []


def test_native_project_create_reports_completion_audit_failure(tmp_path, monkeypatch):
    import mutaui.projects.native_project as native_project

    target = tmp_path / "mutagen.yml"
    audit = tmp_path / "audit.jsonl"
    append = native_project._append_project_audit
    calls = 0

    def fail_completion(path, event):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("audit unavailable")
        append(path, event)

    monkeypatch.setattr(native_project, "_append_project_audit", fail_completion)
    with pytest.raises(ProjectStoreError, match="audit completion failed"):
        create_native_project_file(
            target,
            "sync:\n  local:\n    alpha: ./src\n    beta: ./copy\n",
            audit_path=audit,
        )

    assert target.exists()
    assert json.loads(audit.read_text(encoding="utf-8").splitlines()[0])["phase"] == "prepared"


def test_project_reference_loader_enforces_size_limit(tmp_path, monkeypatch):
    import mutaui.projects.native_project as native_project

    path = tmp_path / "projects.json"
    path.write_text('{"schema_version":1,"projects":[]}', encoding="utf-8")
    monkeypatch.setattr(native_project, "PROJECT_STORE_MAX_BYTES", 1)

    result = load_project_references(path)

    assert not result.valid
    assert any("size limit" in warning for warning in result.warnings)


def test_project_reference_store_refuses_invalid_existing_store(tmp_path):
    path = tmp_path / "projects.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(ProjectStoreError, match="Cannot edit invalid"):
        ProjectReferenceStore(path)


def test_project_reference_store_normalizes_blank_name_and_keeps_existing_backup(tmp_path):
    path = tmp_path / "projects.json"
    backup = path.with_suffix(".json.bak")
    store = ProjectReferenceStore(path)
    first = store.add(tmp_path / "demo" / "mutagen.yml", name="   ")
    assert first.name == "demo"
    backup.write_text("preserve existing backup", encoding="utf-8")

    reloaded = ProjectReferenceStore(path)
    reloaded.add(tmp_path / "other" / "mutagen.yml")

    assert backup.read_text(encoding="utf-8") == "preserve existing backup"
    assert len(list(tmp_path.glob("projects.json.*.bak"))) == 1
