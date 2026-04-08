"""Tests for NotebookStore."""

import json
import tempfile
from pathlib import Path

import pytest

from repo_transmute.txtai.notebook import (
    NotebookStore,
    NotebookEntry,
    PassRecord,
)


@pytest.fixture
def store(tmp_path):
    """Empty NotebookStore with a temporary directory."""
    return NotebookStore(store_dir=tmp_path)


def _make_entry(
    uid,
    repo="HKUDS/nanobot",
    chunk_id=0,
    final_code="function hello() { return 1; }",
    passes=None,
    **kwargs,
):
    if passes is None:
        passes = [
            PassRecord(
                pass_number=1,
                prompt="prompt",
                model="MiniMax-M2.7",
                raw_output=final_code,
            )
        ]
    return NotebookEntry(
        uid=uid,
        repo=repo,
        chunk_id=chunk_id,
        language="python",
        target_lang="typescript",
        blueprint_text="",
        passes=passes,
        final_code=final_code,
        **kwargs,
    )


class TestNotebookStore:
    def test_save_and_get(self, store):
        entry = _make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z")
        store.save(entry)

        retrieved = store.get("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z", repo="HKUDS/nanobot")
        assert retrieved is not None
        assert retrieved.uid == entry.uid
        assert retrieved.repo == entry.repo
        assert retrieved.final_code == entry.final_code

    def test_get_unknown_uid_returns_none(self, store):
        assert store.get("nonexistent") is None

    def test_list_by_repo_empty(self, store):
        assert store.list_by_repo("HKUDS/nanobot") == []

    def test_list_by_repo_multiple(self, store):
        e1 = _make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z", final_code="v1")
        e2 = _make_entry("HKUDS/nanobot:chunk0:2026-01-02T00:00:00Z", final_code="v2")
        store.save(e1)
        store.save(e2)

        entries = store.list_by_repo("HKUDS/nanobot")
        assert len(entries) == 2

    def test_list_by_chunk_id_filters_correctly(self, store):
        e0 = _make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z", chunk_id=0, final_code="chunk0-v1")
        e1 = _make_entry("HKUDS/nanobot:chunk1:2026-01-01T01:00:00Z", chunk_id=1, final_code="chunk1-v1")
        e0b = _make_entry("HKUDS/nanobot:chunk0:2026-01-02T00:00:00Z", chunk_id=0, final_code="chunk0-v2")
        store.save(e0)
        store.save(e1)
        store.save(e0b)

        chunk0_entries = store.list_by_chunk_id("HKUDS/nanobot", 0)
        assert len(chunk0_entries) == 2
        # oldest first
        assert chunk0_entries[0].final_code == "chunk0-v1"
        assert chunk0_entries[1].final_code == "chunk0-v2"

        chunk1_entries = store.list_by_chunk_id("HKUDS/nanobot", 1)
        assert len(chunk1_entries) == 1
        assert chunk1_entries[0].final_code == "chunk1-v1"

    def test_repos_lists_all(self, store):
        store.save(_make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z", repo="HKUDS/nanobot"))
        store.save(_make_entry("foo/bar:chunk0:2026-01-01T00:00:00Z", repo="foo/bar"))
        repos = store.repos()
        assert "HKUDS/nanobot" in repos
        assert "foo/bar" in repos

    def test_diff_entries_no_change(self, store):
        e1 = _make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z", final_code="function hello() { return 1; }")
        e2 = _make_entry("HKUDS/nanobot:chunk0:2026-01-02T00:00:00Z", final_code="function hello() { return 1; }")
        diff = store.diff_entries(e1, e2)
        assert diff == "(no code changes)"

    def test_diff_entries_with_changes(self, store):
        e1 = _make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z", final_code="function hello() {\n  return 1;\n}")
        e2 = _make_entry("HKUDS/nanobot:chunk0:2026-01-02T00:00:00Z", final_code="function hello() {\n  return 2;\n}")
        diff = store.diff_entries(e1, e2)
        assert "return 1;" in diff
        assert "return 2;" in diff

    def test_diff_entries_same_uid(self, store):
        e = _make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z")
        diff = store.diff_entries(e, e)
        assert "(same entry" in diff

    def test_diff_entries_reports_pass_count_difference(self, store):
        passes1 = [PassRecord(pass_number=1, prompt="p", model="MiniMax-M2.7", raw_output="v1")]
        passes2 = [
            PassRecord(pass_number=1, prompt="p", model="MiniMax-M2.7", raw_output="v1"),
            PassRecord(pass_number=2, prompt="p", model="MiniMax-M2.7", raw_output="v2"),
        ]
        e1 = _make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z", final_code="function f() {}", passes=passes1)
        e2 = _make_entry("HKUDS/nanobot:chunk0:2026-01-02T00:00:00Z", final_code="function f() {}", passes=passes2)
        diff = store.diff_entries(e1, e2)
        assert "Pass count: 1 → 2" in diff

    def test_diff_entries_multiline(self, store):
        old_code = "function add(a, b) {\n  return a + b;\n}\n"
        new_code = "function add(a: number, b: number): number {\n  return a + b;\n}\n"
        e1 = _make_entry("HKUDS/nanobot:chunk0:2026-01-01T00:00:00Z", final_code=old_code)
        e2 = _make_entry("HKUDS/nanobot:chunk0:2026-01-02T00:00:00Z", final_code=new_code)
        diff = store.diff_entries(e1, e2)
        assert "def add" not in diff  # unchanged function name
        assert "function add(a, b)" in diff and "function add(a: number, b: number): number" in diff
