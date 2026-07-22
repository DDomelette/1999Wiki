import json

import pytest

from src.huijiwiki.errors import SensitiveValueError
from src.huijiwiki.jsonl import JsonlWriter, write_json_file


def test_jsonl_writer_touches_empty_file_on_create(tmp_path):
    path = tmp_path / "data_pages.jsonl"
    JsonlWriter(path)

    assert path.exists()
    assert path.read_text(encoding="utf-8") == ""


def test_jsonl_writer_appends_utf8_records(tmp_path):
    path = tmp_path / "pages.jsonl"
    writer = JsonlWriter(path)
    writer.write({"title": "槲寄生", "pageid": 1})
    writer.write({"title": "Data:Example.json", "pageid": 2})

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"title": "槲寄生", "pageid": 1},
        {"title": "Data:Example.json", "pageid": 2},
    ]


def test_json_writer_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "siteinfo.json"
    write_json_file(path, {"query": {"general": {"sitename": "重返未来1999WIKI"}}})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["query"]["general"]["sitename"] == "重返未来1999WIKI"


def test_jsonl_writer_rejects_secret_like_keys(tmp_path):
    writer = JsonlWriter(tmp_path / "errors.jsonl")
    with pytest.raises(SensitiveValueError):
        writer.write({"cookie": "secret-cookie-value"})
    with pytest.raises(SensitiveValueError):
        writer.write({"nested": {"password": "secret-password"}})
