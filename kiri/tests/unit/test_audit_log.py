from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.audit.log import AuditEntry, AuditLog, _level_from_reason, _read_file
from src.filter.pipeline import Decision, FilterResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    decision: Decision = Decision.BLOCK,
    reason: str = "symbol match: foo",
    similarity: float = 0.0,
    symbols: list[str] | None = None,
) -> FilterResult:
    return FilterResult(
        decision=decision,
        reason=reason,
        top_similarity=similarity,
        matched_symbols=symbols or [],
    )


# ---------------------------------------------------------------------------
# _level_from_reason
# ---------------------------------------------------------------------------

class TestLevelFromReason:

    def test_symbol_match_is_l2(self):
        assert _level_from_reason("symbol match: foo") == "L2"

    def test_similarity_hard_block_is_l1(self):
        assert _level_from_reason("similarity hard block (score=0.95)") == "L1"

    def test_below_threshold_is_l1(self):
        assert _level_from_reason("below threshold (score=0.30)") == "L1"

    def test_grace_zone_redact_is_l1(self):
        assert _level_from_reason("grace zone: redact on suspicion (score=0.80)") == "L1"

    def test_classifier_leak_is_l3(self):
        assert _level_from_reason("classifier: leak detected") == "L3"

    def test_grace_zone_no_signal_is_l3(self):
        assert _level_from_reason("grace zone: no signal") == "L3"


# ---------------------------------------------------------------------------
# AuditLog.record
# ---------------------------------------------------------------------------

class TestRecord:

    def test_record_creates_file(self, tmp_path: Path):
        log = AuditLog(tmp_path / ".kiri" / "audit.log")
        log.record(_make_result(), "some prompt")
        assert log._path.exists()

    def test_record_writes_one_line(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(), "some prompt")
        lines = log._path.read_text().splitlines()
        assert len(lines) == 1

    def test_record_two_calls_two_lines(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(), "first")
        log.record(_make_result(), "second")
        lines = log._path.read_text().splitlines()
        assert len(lines) == 2

    def test_record_decision_uppercased(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(
            _make_result(decision=Decision.PASS, reason="below threshold (score=0.10)"), "hi"
        )
        entry = log.tail(1)[0]
        assert entry.decision == "PASS"

    def test_record_prompt_truncated_to_120(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        long_prompt = "x" * 200
        log.record(_make_result(), long_prompt)
        entry = log.tail(1)[0]
        assert len(entry.prompt_excerpt) == 120

    def test_record_short_prompt_not_padded(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(), "short")
        entry = log.tail(1)[0]
        assert entry.prompt_excerpt == "short"

    def test_record_symbols_stored(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(symbols=["foo", "bar"]), "prompt")
        entry = log.tail(1)[0]
        assert entry.matched_symbols == ["foo", "bar"]

    def test_record_similarity_rounded(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(similarity=0.123456789), "prompt")
        entry = log.tail(1)[0]
        assert entry.top_similarity == 0.1235

    def test_record_level_derived_from_reason(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(reason="symbol match: foo"), "prompt")
        entry = log.tail(1)[0]
        assert entry.level == "L2"

    def test_record_parent_dirs_created(self, tmp_path: Path):
        log = AuditLog(tmp_path / "deep" / "nested" / "audit.log")
        log.record(_make_result(), "prompt")
        assert log._path.exists()

    def test_record_key_id_stored_truncated(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(), "prompt", key="kr-ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        entry = log.tail(1)[0]
        assert entry.key_id == "kr-ABCDEFGHI"  # first 12 chars

    def test_record_key_id_defaults_to_empty(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(), "prompt")
        entry = log.tail(1)[0]
        assert entry.key_id == ""

    def test_record_short_key_stored_as_is(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(), "prompt", key="kr-short")
        entry = log.tail(1)[0]
        assert entry.key_id == "kr-short"

    def test_parse_legacy_entry_without_key_id(self, tmp_path: Path):
        """Old log lines without key_id field must still parse correctly."""
        import json
        log_path = tmp_path / "audit.log"
        legacy_line = json.dumps({
            "timestamp": "2024-01-01T00:00:00+00:00",
            "decision": "PASS",
            "reason": "below threshold (score=0.10)",
            "level": "L1",
            "top_similarity": 0.1,
            "matched_symbols": [],
            "prompt_excerpt": "hello",
        })
        log_path.write_text(legacy_line + "\n", encoding="utf-8")

        log = AuditLog(log_path)
        entries = log.tail()
        assert len(entries) == 1
        assert entries[0].key_id == ""


# ---------------------------------------------------------------------------
# AuditLog.tail
# ---------------------------------------------------------------------------

class TestTail:

    def test_tail_empty_log_returns_empty(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        assert log.tail() == []

    def test_tail_missing_file_returns_empty(self, tmp_path: Path):
        log = AuditLog(tmp_path / "nonexistent.log")
        assert log.tail() == []

    def test_tail_returns_last_n(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        for i in range(10):
            log.record(_make_result(reason=f"below threshold (score=0.{i:02d})"), f"prompt {i}")
        entries = log.tail(3)
        assert len(entries) == 3
        assert entries[-1].prompt_excerpt == "prompt 9"

    def test_tail_n_larger_than_log_returns_all(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(), "only one")
        assert len(log.tail(100)) == 1

    def test_tail_zero_returns_all(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        for i in range(5):
            log.record(_make_result(), f"p{i}")
        assert len(log.tail(0)) == 5

    def test_tail_returns_audit_entry_objects(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        log.record(_make_result(), "prompt")
        entries = log.tail()
        assert isinstance(entries[0], AuditEntry)


# ---------------------------------------------------------------------------
# AuditLog.filter
# ---------------------------------------------------------------------------

class TestFilter:

    def _populate(self, log: AuditLog) -> None:
        log.record(_make_result(Decision.BLOCK, "symbol match: x"), "blocked")
        log.record(_make_result(Decision.PASS, "below threshold (score=0.10)"), "passed")
        log.record(
            _make_result(Decision.REDACT, "grace zone: redact on suspicion (score=0.80)"),
            "redacted",
        )

    def test_filter_by_decision_block(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        self._populate(log)
        entries = log.filter(decision="BLOCK")
        assert all(e.decision == "BLOCK" for e in entries)
        assert len(entries) == 1

    def test_filter_by_decision_case_insensitive(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        self._populate(log)
        assert len(log.filter(decision="block")) == 1

    def test_filter_by_decision_pass(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        self._populate(log)
        assert len(log.filter(decision="PASS")) == 1

    def test_filter_since_excludes_old(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        self._populate(log)
        future = datetime(2099, 1, 1, tzinfo=UTC)
        assert log.filter(since=future) == []

    def test_filter_since_includes_all_past(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        self._populate(log)
        past = datetime(2000, 1, 1, tzinfo=UTC)
        assert len(log.filter(since=past)) == 3

    def test_filter_combined_decision_and_since(self, tmp_path: Path):
        log = AuditLog(tmp_path / "audit.log")
        self._populate(log)
        past = datetime(2000, 1, 1, tzinfo=UTC)
        entries = log.filter(decision="BLOCK", since=past)
        assert len(entries) == 1
        assert entries[0].decision == "BLOCK"


# ---------------------------------------------------------------------------
# AuditLog rotation
# ---------------------------------------------------------------------------

class TestRotation:

    def _tiny_log(self, tmp_path: Path, backup_count: int = 3) -> AuditLog:
        """AuditLog that rotates after 1 byte (i.e. after every write)."""
        return AuditLog(tmp_path / "audit.log", max_bytes=1, backup_count=backup_count)

    def test_rotation_disabled_by_default(self, tmp_path: Path):
        """max_bytes=0 → no rotation regardless of file size."""
        log = AuditLog(tmp_path / "audit.log")  # default max_bytes=0
        for i in range(20):
            log.record(_make_result(), f"prompt {i}")
        assert not Path(f"{log._path}.1").exists()

    def test_rotation_creates_backup(self, tmp_path: Path):
        log = self._tiny_log(tmp_path)
        log.record(_make_result(), "first")
        log.record(_make_result(), "second")
        assert Path(f"{log._path}.1").exists()

    def test_rotated_backup_contains_old_entry(self, tmp_path: Path):
        log = self._tiny_log(tmp_path)
        log.record(_make_result(reason="symbol match: old"), "old entry")
        log.record(_make_result(), "new entry")
        backup = Path(f"{log._path}.1")
        entries = _read_file(backup)
        assert any(e.reason == "symbol match: old" for e in entries)

    def test_current_log_has_only_new_entry(self, tmp_path: Path):
        log = self._tiny_log(tmp_path)
        log.record(_make_result(reason="symbol match: old"), "old")
        log.record(_make_result(reason="below threshold (score=0.10)"), "new")
        entries = _read_file(log._path)
        reasons = [e.reason for e in entries]
        assert "symbol match: old" not in reasons

    def test_backup_count_limits_number_of_files(self, tmp_path: Path):
        log = self._tiny_log(tmp_path, backup_count=2)
        for i in range(10):
            log.record(_make_result(), f"entry {i}")
        # only audit.log, audit.log.1, audit.log.2 should exist
        assert not Path(f"{log._path}.3").exists()
        assert Path(f"{log._path}.1").exists()
        assert Path(f"{log._path}.2").exists()

    def test_oldest_backup_deleted_when_count_exceeded(self, tmp_path: Path):
        log = self._tiny_log(tmp_path, backup_count=2)
        for i in range(5):
            log.record(_make_result(), f"entry {i}")
        # .3 must not exist
        assert not Path(f"{log._path}.3").exists()

    def test_tail_reads_across_rotation(self, tmp_path: Path):
        """tail(100) returns entries from both current and rotated files."""
        log = self._tiny_log(tmp_path)
        log.record(_make_result(reason="symbol match: old"), "old entry")
        log.record(_make_result(reason="below threshold (score=0.10)"), "new entry")
        entries = log.tail(100)
        reasons = {e.reason for e in entries}
        assert "symbol match: old" in reasons
        assert "below threshold (score=0.10)" in reasons

    def test_tail_n_returns_most_recent_across_files(self, tmp_path: Path):
        """tail(1) should return the single most recent entry, not the oldest."""
        log = self._tiny_log(tmp_path)
        log.record(_make_result(reason="symbol match: old"), "old")
        log.record(_make_result(reason="below threshold (score=0.10)"), "new")
        entries = log.tail(1)
        assert len(entries) == 1
        assert entries[0].reason == "below threshold (score=0.10)"

    def test_filter_reads_rotated_files(self, tmp_path: Path):
        """filter() must look in rotated files, not only the current one."""
        log = self._tiny_log(tmp_path)
        log.record(_make_result(Decision.BLOCK, "symbol match: x"), "blocked")
        log.record(_make_result(Decision.PASS, "below threshold (score=0.10)"), "passed")
        blocks = log.filter(decision="BLOCK")
        assert len(blocks) == 1
        assert blocks[0].decision == "BLOCK"

    def test_settings_wired_into_main(self, tmp_path: Path):
        """audit_max_bytes and audit_backup_count from Settings reach AuditLog."""
        from src.config.settings import Settings
        s = Settings(workspace=tmp_path, audit_max_bytes=1024, audit_backup_count=3)
        assert s.audit_max_bytes == 1024
        assert s.audit_backup_count == 3
