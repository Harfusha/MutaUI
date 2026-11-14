import mutaui.adapters.yaml_config as yaml_config
from mutaui.adapters.yaml_config import (
    YAML_MAX_BYTES,
    load_yaml_file,
    parse_yaml_bytes,
    render_yaml_preview,
)


def test_round_trip_preview_preserves_comments_order_quotes_and_unknown_values():
    source = (
        b"# global comment\r\n"
        b"sync:\r\n"
        b"  defaults:\r\n"
        b"    # custom comment\r\n"
        b'    watchMode: "portable"\r\n'
        b"    unknownFutureOption: [one, two]\r\n"
        b"customSection:\r\n"
        b"  value: true\r\n"
    )

    result = parse_yaml_bytes(source)
    preview = render_yaml_preview(result.document)

    assert result.valid
    assert result.raw_bytes == source
    assert result.sha256
    assert result.newline == "\r\n"
    assert "# global comment" in preview
    assert "# custom comment" in preview
    assert 'watchMode: "portable"' in preview
    assert "unknownFutureOption" in preview
    assert preview.index("sync:") < preview.index("customSection:")


def test_invalid_yaml_retains_exact_source_and_reports_parse_error(tmp_path):
    source = b"sync:\n  defaults: [unterminated\n"
    path = tmp_path / "mutagen.yml"
    path.write_bytes(source)

    result = load_yaml_file(path)

    assert not result.valid
    assert result.raw_bytes == source
    assert result.document is None
    assert result.error
    assert path.read_bytes() == source


def test_duplicate_keys_and_non_mapping_roots_are_rejected():
    duplicate = parse_yaml_bytes(b"sync: {}\nsync: {}\n")
    sequence = parse_yaml_bytes(b"- one\n- two\n")

    assert not duplicate.valid
    assert "duplicate" in duplicate.error.lower()
    assert not sequence.valid
    assert "mapping" in sequence.error.lower()


def test_python_object_tags_are_not_constructed():
    result = parse_yaml_bytes(b"!!python/object/apply:os.system ['echo should-not-run']\n")

    assert not result.valid
    assert result.raw_bytes.startswith(b"!!python/object/apply:")


def test_empty_yaml_is_a_valid_empty_mapping_and_bom_is_detected():
    empty = parse_yaml_bytes(b"# empty config\n")
    bom = parse_yaml_bytes(b"\xef\xbb\xbfsync: {}\n")

    assert empty.valid
    assert len(empty.document) == 0
    assert bom.valid
    assert bom.encoding == "utf-8-sig"


def test_yaml_size_limit_rejects_oversized_source_without_parsing():
    result = parse_yaml_bytes(b"a" * (YAML_MAX_BYTES + 1))

    assert not result.valid
    assert "size limit" in result.error.lower()
    assert result.raw_bytes == b"a" * (YAML_MAX_BYTES + 1)


def test_yaml_parser_preserves_invalid_encoding_and_rejects_excessive_indentation():
    invalid_utf8 = parse_yaml_bytes(b"sync: \xff\n")
    over_indented = parse_yaml_bytes(b"sync:\n" + b" " * 129 + b"value: true\n")

    assert not invalid_utf8.valid
    assert "not valid UTF-8" in invalid_utf8.error
    assert invalid_utf8.raw_bytes == b"sync: \xff\n"
    assert not over_indented.valid
    assert "indentation exceeds" in over_indented.error


def test_yaml_file_read_error_is_returned_as_invalid_snapshot(tmp_path):
    result = load_yaml_file(tmp_path / "missing.yml")

    assert not result.valid
    assert result.raw_bytes == b""
    assert "Could not read YAML source" in result.error


def test_yaml_parser_future_depth_guard_and_type_contract(monkeypatch):
    class FutureParser:
        def __init__(self, *, typ):
            self.typ = typ
            self.max_depth = None

    monkeypatch.setattr(yaml_config, "YAML", FutureParser)
    parser = yaml_config._parser()

    assert parser.typ == "rt"
    assert parser.max_depth == 64
    try:
        parse_yaml_bytes("sync: {}")
    except TypeError as exc:
        assert str(exc) == "YAML source must be bytes."
    else:
        raise AssertionError("string YAML source must be rejected")
