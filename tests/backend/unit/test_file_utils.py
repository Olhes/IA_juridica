"""Pruebas del hashing SHA-256 y la detección de archivos duplicados."""

import hashlib

import pytest

from utils.file_utils import FileUtils


@pytest.mark.parametrize(
    "content", [b"", b"abc", bytes(range(256)) * 40], ids=["empty", "text", "multiple_chunks"]
)
def test_get_file_hash_returns_sha256_for_complete_content(tmp_path, content):
    file_path = tmp_path / "document.bin"
    file_path.write_bytes(content)

    digest = FileUtils().get_file_hash(str(file_path))

    assert digest == hashlib.sha256(content).hexdigest()
    assert len(digest) == 64


def test_get_file_hash_preserves_empty_result_for_missing_file(tmp_path):
    assert FileUtils().get_file_hash(str(tmp_path / "missing.txt")) == ""


def test_find_duplicate_files_groups_content_with_sha256_keys(tmp_path):
    first = tmp_path / "first.txt"
    nested = tmp_path / "nested"
    nested.mkdir()
    second = nested / "second.txt"
    unique = tmp_path / "unique.txt"
    first.write_bytes(b"same content")
    second.write_bytes(b"same content")
    unique.write_bytes(b"other text!!")

    duplicates = FileUtils().find_duplicate_files(str(tmp_path))

    expected_digest = hashlib.sha256(b"same content").hexdigest()
    assert set(duplicates) == {expected_digest}
    assert set(duplicates[expected_digest]) == {str(first), str(second)}


def test_find_duplicate_files_returns_empty_for_empty_directory(tmp_path):
    assert FileUtils().find_duplicate_files(str(tmp_path)) == {}
