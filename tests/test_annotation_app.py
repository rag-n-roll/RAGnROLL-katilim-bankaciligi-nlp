import sys
import types

import pytest

from src.annotation.app import DEFAULT_DATASET, _query_dataset, _save
from src.annotation.store import ConcurrentUpdateError


class _FakeStreamlit:
    def __init__(self):
        self.query_params = {}
        self.errors = []
        self.stopped = False

    def error(self, message):
        self.errors.append(message)

    def stop(self):
        self.stopped = True
        raise _StopException


class _StopException(Exception):
    pass


@pytest.fixture()
def fake_streamlit(monkeypatch):
    st = _FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", types.SimpleNamespace(**{
        "query_params": st.query_params,
        "error": st.error,
        "stop": st.stop,
    }))
    return st


def test_query_dataset_defaults_to_repository_dataset(fake_streamlit):
    assert _query_dataset() == DEFAULT_DATASET


def test_query_dataset_reads_query_param_override(fake_streamlit, tmp_path):
    fake_streamlit.query_params["dataset"] = str(tmp_path / "custom.jsonl")
    assert _query_dataset() == tmp_path / "custom.jsonl"


def test_save_returns_new_digest_on_success(tmp_path):
    import hashlib
    import json

    path = tmp_path / "annotations.jsonl"
    records = [{"id": "1", "text": "metin"}]
    path.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    stale = [{"id": "1", "text": "güncellenmiş metin"}]
    current_digest = hashlib.sha256(path.read_bytes()).hexdigest()

    digest = _save(path, stale, digest=current_digest)

    assert isinstance(digest, str) and len(digest) == 64
    saved = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert saved == stale


def test_save_reports_conflict_and_stops(tmp_path, fake_streamlit):
    path = tmp_path / "annotations.jsonl"
    path.write_text('{"id": "1"}\n', encoding="utf-8")

    with pytest.raises(_StopException):
        _save(path, [{"id": "2"}], digest="eski-digest")

    assert fake_streamlit.stopped is True
    assert "Annotation file changed" in fake_streamlit.errors[0]


def test_save_conflict_raises_concurrent_update_error_directly():
    with pytest.raises(ConcurrentUpdateError):
        raise ConcurrentUpdateError("test")
