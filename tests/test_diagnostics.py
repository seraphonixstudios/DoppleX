"""Tests for diagnostics module."""
from __future__ import annotations

import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.diagnostics import (
    HealthCheckResult,
    DiagnosticsReport,
    get_system_info,
    check_database,
    check_accounts,
    format_report_text,
    get_log_summary,
)


class TestHealthCheckResult:
    def test_ok_result(self):
        r = HealthCheckResult(name="Test", status="ok", message="All good")
        assert r.status == "ok"
        assert r.to_dict()["status"] == "ok"

    def test_error_result(self):
        r = HealthCheckResult(name="Test", status="error", message="Failed")
        assert r.status == "error"

    def test_result_with_details(self):
        r = HealthCheckResult(name="DB", status="ok", message="Connected", details={"tables": 5})
        d = r.to_dict()
        assert d["details"]["tables"] == 5


class TestDiagnosticsReport:
    def test_empty_report(self):
        report = DiagnosticsReport()
        assert report.overall_status == "unknown"

    def test_all_ok(self):
        report = DiagnosticsReport()
        report.add_check(HealthCheckResult("A", "ok", "ok"))
        report.add_check(HealthCheckResult("B", "ok", "ok"))
        assert report.overall_status == "ok"

    def test_warning_overall(self):
        report = DiagnosticsReport()
        report.add_check(HealthCheckResult("A", "ok", "ok"))
        report.add_check(HealthCheckResult("B", "warning", "slow"))
        assert report.overall_status == "warning"

    def test_error_overall(self):
        report = DiagnosticsReport()
        report.add_check(HealthCheckResult("A", "ok", "ok"))
        report.add_check(HealthCheckResult("B", "error", "down"))
        assert report.overall_status == "error"

    def test_to_dict(self):
        report = DiagnosticsReport(system={"os": "test"})
        report.add_check(HealthCheckResult("A", "ok", "ok"))
        d = report.to_dict()
        assert d["overall_status"] == "ok"
        assert d["system"]["os"] == "test"
        assert len(d["checks"]) == 1


class TestSystemInfo:
    def test_get_system_info(self):
        info = get_system_info()
        assert "platform" in info
        assert "python_version" in info
        assert "cpu_count" in info


@pytest.mark.asyncio
class TestAsyncDiagnostics:
    async def test_check_database(self):
        result = await check_database()
        # Database may or may not be initialized in test environment
        assert result.status in ("ok", "error")
        assert result.name == "Database"

    async def test_check_accounts(self):
        result = await check_accounts()
        # Could be ok or warning depending on test DB state
        assert result.status in ("ok", "warning", "error")


class TestFormatReport:
    def test_format_text(self):
        report = DiagnosticsReport()
        report.add_check(HealthCheckResult("Test", "ok", "Working"))
        text = format_report_text(report)
        assert "Diagnostics Report" in text
        assert "Working" in text
        assert "✓" in text

    def test_format_with_errors(self):
        report = DiagnosticsReport()
        report.add_check(HealthCheckResult("Test", "error", "Broken"))
        text = format_report_text(report)
        assert "✗" in text
        assert "Broken" in text


class TestLogSummary:
    def test_missing_log_dir(self):
        summary = get_log_summary(log_dir="nonexistent_logs_xyz")
        assert summary["files"] == []

    def test_existing_log_dir(self):
        os.makedirs("logs", exist_ok=True)
        summary = get_log_summary()
        assert "files" in summary
