"""Unit tests for mdal.audit — AuditWriter (F4, NF5)."""

import json
from pathlib import Path

import pytest

from mdal.audit import AuditWriteError, AuditWriter, audit_writer_from_config
from mdal.config import AuditConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def file_writer(tmp_path: Path) -> AuditWriter:
    log_path = tmp_path / "audit" / "test.log"
    config = AuditConfig(target="file", path=str(log_path))
    return AuditWriter(config)


def read_entries(tmp_path: Path) -> list[dict]:
    log_path = tmp_path / "audit" / "test.log"
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

class TestWrite:
    def test_creates_file_on_first_write(self, tmp_path):
        writer = file_writer(tmp_path)
        writer.write("test.event", {"key": "value"})
        assert (tmp_path / "audit" / "test.log").exists()

    def test_creates_parent_directory(self, tmp_path):
        writer = file_writer(tmp_path)
        writer.write("test.event", {})
        assert (tmp_path / "audit").is_dir()

    def test_entry_contains_timestamp(self, tmp_path):
        writer = file_writer(tmp_path)
        writer.write("test.event", {})
        entries = read_entries(tmp_path)
        assert "timestamp" in entries[0]

    def test_entry_contains_event_type(self, tmp_path):
        writer = file_writer(tmp_path)
        writer.write("check.passed", {"output_id": "abc"})
        entries = read_entries(tmp_path)
        assert entries[0]["event"] == "check.passed"

    def test_entry_contains_custom_data(self, tmp_path):
        writer = file_writer(tmp_path)
        writer.write("retry.attempt", {"attempt": 2, "reason": "low score"})
        entries = read_entries(tmp_path)
        assert entries[0]["attempt"] == 2
        assert entries[0]["reason"] == "low score"

    def test_multiple_writes_append(self, tmp_path):
        writer = file_writer(tmp_path)
        writer.write("event.one", {"n": 1})
        writer.write("event.two", {"n": 2})
        writer.write("event.three", {"n": 3})
        entries = read_entries(tmp_path)
        assert len(entries) == 3
        assert [e["event"] for e in entries] == ["event.one", "event.two", "event.three"]

    def test_unicode_content_preserved(self, tmp_path):
        writer = file_writer(tmp_path)
        writer.write("test.event", {"message": "Ästhetik und Überzeugung — «Qualität»"})
        entries = read_entries(tmp_path)
        assert "Ästhetik" in entries[0]["message"]

    def test_each_entry_is_valid_json(self, tmp_path):
        writer = file_writer(tmp_path)
        for i in range(5):
            writer.write("test.event", {"i": i})
        log_path = tmp_path / "audit" / "test.log"
        for line in log_path.read_text(encoding="utf-8").splitlines():
            json.loads(line)   # raises if invalid


# ---------------------------------------------------------------------------
# Write-only: no reading, editing, or deleting
# ---------------------------------------------------------------------------

class TestWriteOnly:
    def test_no_read_method(self):
        config = AuditConfig(target="file", path="./test.log")
        writer = AuditWriter(config)
        assert not hasattr(writer, "read")
        assert not hasattr(writer, "get")
        assert not hasattr(writer, "query")
        assert not hasattr(writer, "delete")
        assert not hasattr(writer, "clear")


# ---------------------------------------------------------------------------
# Unimplemented targets
# ---------------------------------------------------------------------------

class TestUnimplementedTargets:
    def test_postgresql_raises_not_implemented(self, tmp_path):
        config = AuditConfig(
            target="postgresql",
            connection_string="postgresql://u:p@host/db",
        )
        writer = AuditWriter(config)
        with pytest.raises(NotImplementedError):
            writer.write("test.event", {})


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_write_to_unwritable_path_raises_audit_write_error(self, tmp_path):
        # Simulate an unwritable path by using a directory instead of a file
        log_path = tmp_path / "audit.log"
        log_path.mkdir()   # directory instead of file — write will fail
        config = AuditConfig(target="file", path=str(log_path))
        writer = AuditWriter(config)
        with pytest.raises(AuditWriteError):
            writer.write("test.event", {})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_audit_writer_from_config(self, tmp_path):
        config = AuditConfig(target="file", path=str(tmp_path / "audit.log"))
        writer = audit_writer_from_config(config)
        assert isinstance(writer, AuditWriter)
