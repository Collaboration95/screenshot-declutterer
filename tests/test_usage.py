import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ss_dcl import usage

CREATED = datetime(2026, 10, 8, 9, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("opened_seconds", "scan_seconds", "eligible"),
    [
        (120, 780, True),
        (300, 960, True),
        (120, 720, False),
        (120, 720.001, True),
        (360, 1800, False),
        (10800, 12600, False),
        (0, 780, False),
        (-1, 780, False),
        (0.9, 780, False),  # indistinguishable at mdls second precision
        (1, 780, True),
        (300.001, 960, False),
        (900, 780, False),  # future open
    ],
)
def test_fixed_timing_boundaries(opened_seconds, scan_seconds, eligible):
    record = usage.UsageMetadata(CREATED, CREATED + timedelta(seconds=opened_seconds))
    result = usage.cleanup_result(record, CREATED + timedelta(seconds=scan_seconds))
    assert result["eligible"] is eligible
    assert result["timing_match"] is eligible
    assert result["reason"] == (usage.CLEANUP_REASON if eligible else None)


def test_timezone_normalization_and_explicit_decisions():
    local = timezone(timedelta(hours=8))
    record = usage.UsageMetadata(CREATED.astimezone(local), CREATED + timedelta(minutes=2))
    now = (CREATED + timedelta(minutes=13)).astimezone(local)
    result = usage.cleanup_result(record, now, unsorted=False)
    assert result["timing_match"] is True
    assert result["eligible"] is False
    assert result["opened_after_capture_seconds"] == 120
    assert result["last_opened_ago_seconds"] == 660


@pytest.mark.parametrize(
    ("created", "opened", "now"),
    [
        (None, CREATED, CREATED),
        (CREATED, None, CREATED),
        (CREATED.replace(tzinfo=None), CREATED, CREATED),
        (CREATED, CREATED.replace(tzinfo=None), CREATED),
        (CREATED, CREATED, CREATED.replace(tzinfo=None)),
        (CREATED + timedelta(hours=1), CREATED + timedelta(hours=1, minutes=2), CREATED),
    ],
)
def test_unavailable_ambiguous_and_future_timestamps(created, opened, now):
    assert not usage.cleanup_result(usage.UsageMetadata(created, opened), now)["eligible"]


@pytest.mark.parametrize("value", ["", "(null)", "broken", "2026-10-08 09:02:00", "inf"])
def test_invalid_mdls_output(value):
    assert usage.parse_last_used(value) is None


def test_mdls_timezone_and_nul_parsing():
    assert usage.parse_last_used("2026-10-08 17:02:00 +0800\x00") == CREATED + timedelta(minutes=2)


@pytest.mark.parametrize("birth", [None, float("nan"), float("inf"), 1e100])
def test_missing_or_invalid_birth_time_never_uses_access_or_modification(birth):
    path = Mock(spec=Path)
    path.stat.return_value = SimpleNamespace(st_birthtime=birth, st_atime=1, st_mtime=1)
    assert usage._birth_time(path) is None


def test_unavailable_birth_attribute_and_stat_failure():
    path = Mock(spec=Path)
    path.stat.return_value = SimpleNamespace(st_atime=1, st_mtime=1)
    assert usage._birth_time(path) is None
    path.stat.side_effect = PermissionError
    assert usage._birth_time(path) is None


def test_birth_time_uses_utc(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "stat", lambda p: SimpleNamespace(st_birthtime=CREATED.timestamp()))
    assert usage._birth_time(tmp_path) == CREATED


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError(),
        FileNotFoundError(),
        subprocess.TimeoutExpired("mdls", 0.75),
        UnicodeError(),
    ],
)
def test_query_failures_are_optional(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(usage, "_birth_time", lambda path: CREATED)
    query = Mock(side_effect=failure)
    monkeypatch.setattr(usage.subprocess, "run", query)
    result = usage._read_file(tmp_path / "Screenshot test.png", usage.time.monotonic() + 3)
    assert result == usage.UsageMetadata(CREATED)
    assert query.call_args.kwargs["timeout"] <= usage.METADATA_TIMEOUT_SECONDS
    assert query.call_args.args[0][0] == "/usr/bin/mdls"


@pytest.mark.parametrize(
    ("code", "output", "opened"),
    [(0, "2026-10-08 09:02:00 +0000", True), (0, "(null)", False), (1, "denied", False)],
)
def test_query_results(tmp_path, monkeypatch, code, output, opened):
    monkeypatch.setattr(usage, "_birth_time", lambda path: CREATED)
    monkeypatch.setattr(
        usage.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=code, stdout=output))
    )
    result = usage._read_file(tmp_path, usage.time.monotonic() + 3)
    assert bool(result.last_opened_at) is opened


def test_missing_birth_or_exhausted_scan_budget_skips_query(tmp_path, monkeypatch):
    query = Mock()
    monkeypatch.setattr(usage.subprocess, "run", query)
    monkeypatch.setattr(usage, "_birth_time", lambda path: None)
    usage._read_file(tmp_path, usage.time.monotonic() + 3)
    monkeypatch.setattr(usage, "_birth_time", lambda path: CREATED)
    usage._read_file(tmp_path, usage.time.monotonic() - 1)
    query.assert_not_called()


def test_platform_and_fresh_per_scan_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(usage.sys, "platform", "linux")
    assert usage.read_usage([tmp_path]) == {}
    monkeypatch.setattr(usage.sys, "platform", "darwin")
    assert usage.read_usage([]) == {}
    reader = Mock(side_effect=[usage.UsageMetadata(CREATED), usage.UsageMetadata(CREATED, CREATED)])
    monkeypatch.setattr(usage, "_read_file", reader)
    assert usage.read_usage([tmp_path])[tmp_path].last_opened_at is None
    assert usage.read_usage([tmp_path])[tmp_path].last_opened_at == CREATED


def test_usage_payload_is_optional_and_timezone_aware():
    assert usage.usage_payload(usage.UsageMetadata()) == {
        "created_at": None,
        "last_opened_at": None,
    }
    assert usage.usage_payload(usage.UsageMetadata(CREATED, CREATED))["created_at"].endswith(
        "+00:00"
    )
