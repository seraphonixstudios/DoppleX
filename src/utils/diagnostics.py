"""End-to-end diagnostics, health checks, and system information."""
from __future__ import annotations

import os
import sys
import platform
import traceback
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime

from utils.logger import get_logger
from utils.time_utils import utc_now

logger = get_logger("you2.diagnostics")


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    name: str
    status: str  # "ok", "warning", "error"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    latency_ms: Optional[float] = None
    timestamp: datetime = field(default_factory=utc_now)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class DiagnosticsReport:
    """Complete diagnostics report."""
    timestamp: datetime = field(default_factory=utc_now)
    version: str = "1.0.0"
    system: Dict[str, Any] = field(default_factory=dict)
    checks: List[HealthCheckResult] = field(default_factory=list)
    overall_status: str = "unknown"
    log_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "system": self.system,
            "checks": [c.to_dict() for c in self.checks],
            "overall_status": self.overall_status,
            "log_summary": self.log_summary,
        }

    def add_check(self, check: HealthCheckResult):
        self.checks.append(check)
        self._recalculate_status()

    def _recalculate_status(self):
        statuses = [c.status for c in self.checks]
        if any(s == "error" for s in statuses):
            self.overall_status = "error"
        elif any(s == "warning" for s in statuses):
            self.overall_status = "warning"
        elif statuses and all(s == "ok" for s in statuses):
            self.overall_status = "ok"
        else:
            self.overall_status = "unknown"


def get_system_info() -> Dict[str, Any]:
    """Collect system information."""
    info = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "cwd": os.getcwd(),
        "frozen": getattr(sys, "frozen", False),
    }
    
    # Memory info (best effort)
    try:
        import psutil
        mem = psutil.virtual_memory()
        info["memory_total_gb"] = round(mem.total / (1024**3), 2)
        info["memory_available_gb"] = round(mem.available / (1024**3), 2)
        info["memory_percent"] = mem.percent
    except Exception:
        info["memory"] = "psutil not available"
    
    return info


async def check_ollama(base_url: str = "http://localhost:11434") -> HealthCheckResult:
    """Check Ollama connectivity and available models."""
    import time
    start = time.time()
    try:
        from brain.ollama_bridge import OllamaBridge
        bridge = OllamaBridge(base_url=base_url)
        available = await bridge.is_available()
        latency = (time.time() - start) * 1000
        
        if not available:
            return HealthCheckResult(
                name="Ollama",
                status="error",
                message=f"Ollama not responding at {base_url}",
                latency_ms=round(latency, 2),
            )
        
        models = await bridge.list_models()
        model_names = [m.get("name", m.get("model", "unknown")) for m in models] if models else []
        
        return HealthCheckResult(
            name="Ollama",
            status="ok",
            message=f"Ollama online. {len(model_names)} models available.",
            details={"base_url": base_url, "models": model_names[:10]},
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        return HealthCheckResult(
            name="Ollama",
            status="error",
            message=f"Ollama check failed: {e}",
            details={"base_url": base_url, "error": str(e), "traceback": traceback.format_exc()},
        )


async def check_database() -> HealthCheckResult:
    """Check SQLite database connectivity and tables."""
    try:
        from db.database import SessionLocal, engine
        from sqlalchemy import inspect as sa_inspect
        
        with SessionLocal() as db:
            # Test connection
            db.execute("SELECT 1")
        
        # List tables
        inspector = sa_inspect(engine)
        tables = inspector.get_table_names()
        
        return HealthCheckResult(
            name="Database",
            status="ok",
            message=f"Database connected. {len(tables)} tables.",
            details={"tables": tables, "dialect": str(engine.dialect.name)},
        )
    except Exception as e:
        return HealthCheckResult(
            name="Database",
            status="error",
            message=f"Database check failed: {e}",
            details={"error": str(e), "traceback": traceback.format_exc()},
        )


async def check_accounts() -> HealthCheckResult:
    """Check configured accounts."""
    try:
        from db.database import SessionLocal
        from models import Account
        
        with SessionLocal() as db:
            accounts = db.query(Account).all()
            active = [a for a in accounts if a.is_active]
            platforms = {}
            for a in accounts:
                platforms[a.platform] = platforms.get(a.platform, 0) + 1
        
        if not accounts:
            return HealthCheckResult(
                name="Accounts",
                status="warning",
                message="No accounts configured.",
                details={"total": 0, "active": 0},
            )
        
        return HealthCheckResult(
            name="Accounts",
            status="ok",
            message=f"{len(accounts)} account(s) configured, {len(active)} active.",
            details={"total": len(accounts), "active": len(active), "platforms": platforms},
        )
    except Exception as e:
        return HealthCheckResult(
            name="Accounts",
            status="error",
            message=f"Account check failed: {e}",
            details={"error": str(e)},
        )


async def check_x_api() -> HealthCheckResult:
    """Test X API connectivity with stored credentials."""
    try:
        from db.database import SessionLocal
        from models import Account
        from encryption.crypto import decrypt
        from x_api.x_client import XClient
        import time
        
        with SessionLocal() as db:
            x_accounts = db.query(Account).filter(Account.platform == "X", Account.is_active == True).all()
        
        if not x_accounts:
            return HealthCheckResult(
                name="X API",
                status="warning",
                message="No active X accounts to test.",
            )
        
        account = x_accounts[0]
        token = decrypt(account.token_encrypted) if account.token_encrypted else None
        
        if not token:
            return HealthCheckResult(
                name="X API",
                status="warning",
                message=f"X account @{account.username} has no bearer token.",
            )
        
        start = time.time()
        client = XClient(account=account)
        user = await client.get_user_by_username(account.username or "x")
        latency = (time.time() - start) * 1000
        
        if user:
            return HealthCheckResult(
                name="X API",
                status="ok",
                message=f"X API connected as @{account.username}.",
                details={"user_id": user.get("id"), "latency_ms": round(latency, 2)},
                latency_ms=round(latency, 2),
            )
        else:
            return HealthCheckResult(
                name="X API",
                status="error",
                message="X API returned empty response. Token may be invalid.",
                latency_ms=round(latency, 2),
            )
    except Exception as e:
        return HealthCheckResult(
            name="X API",
            status="error",
            message=f"X API check failed: {e}",
            details={"error": str(e), "traceback": traceback.format_exc()},
        )


async def check_tiktok_browser() -> HealthCheckResult:
    """Check Playwright/browser availability for TikTok."""
    try:
        import asyncio
        from tiktok.tiktok_client import _get_browser_context
        
        # Try to launch browser (will fail quickly if not installed)
        ctx = await _get_browser_context(headless=True)
        await ctx.close()
        
        return HealthCheckResult(
            name="TikTok Browser",
            status="ok",
            message="Playwright browser is installed and launchable.",
        )
    except Exception as e:
        error_msg = str(e)
        if "executable doesn't exist" in error_msg:
            return HealthCheckResult(
                name="TikTok Browser",
                status="error",
                message="Playwright browser not installed. Run: python -m playwright install chromium",
                details={"error": error_msg},
            )
        return HealthCheckResult(
            name="TikTok Browser",
            status="error",
            message=f"TikTok browser check failed: {e}",
            details={"error": error_msg, "traceback": traceback.format_exc()},
        )


async def check_stable_diffusion(url: str = "http://127.0.0.1:7860") -> HealthCheckResult:
    """Check Stable Diffusion WebUI availability."""
    import time
    start = time.time()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/sdapi/v1/samplers", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                latency = (time.time() - start) * 1000
                if resp.status == 200:
                    return HealthCheckResult(
                        name="Stable Diffusion",
                        status="ok",
                        message=f"SD WebUI online at {url}.",
                        latency_ms=round(latency, 2),
                    )
                else:
                    return HealthCheckResult(
                        name="Stable Diffusion",
                        status="warning",
                        message=f"SD WebUI returned status {resp.status}.",
                        latency_ms=round(latency, 2),
                    )
    except Exception as e:
        return HealthCheckResult(
            name="Stable Diffusion",
            status="warning",
            message=f"SD WebUI not reachable at {url}. Image generation will be unavailable.",
            details={"error": str(e)},
        )


def get_log_summary(log_dir: str = "logs", max_lines: int = 100) -> Dict[str, Any]:
    """Summarize recent log entries."""
    summary = {
        "log_dir": log_dir,
        "files": [],
        "recent_errors": [],
        "recent_warnings": [],
    }
    
    if not os.path.isdir(log_dir):
        return summary
    
    log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
    summary["files"] = log_files
    
    if not log_files:
        return summary
    
    # Read most recent log file
    newest = max(log_files, key=lambda f: os.path.getmtime(os.path.join(log_dir, f)))
    log_path = os.path.join(log_dir, newest)
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        errors = [l.strip() for l in lines if "ERROR" in l][-max_lines:]
        warnings = [l.strip() for l in lines if "WARNING" in l][-max_lines:]
        summary["recent_errors"] = errors[-10:]
        summary["recent_warnings"] = warnings[-10:]
        summary["total_lines"] = len(lines)
        summary["error_count"] = len(errors)
        summary["warning_count"] = len(warnings)
    except Exception as e:
        summary["read_error"] = str(e)
    
    return summary


async def run_full_diagnostics(
    ollama_url: str = "http://localhost:11434",
    sd_url: str = "http://127.0.0.1:7860",
) -> DiagnosticsReport:
    """Run all diagnostic checks and return a complete report."""
    report = DiagnosticsReport(
        system=get_system_info(),
        log_summary=get_log_summary(),
    )
    
    report.add_check(await check_ollama(ollama_url))
    report.add_check(await check_database())
    report.add_check(await check_accounts())
    report.add_check(await check_x_api())
    report.add_check(await check_tiktok_browser())
    report.add_check(await check_stable_diffusion(sd_url))
    
    logger.info("Diagnostics complete: %s", report.overall_status)
    for check in report.checks:
        logger.info("  %s: %s - %s", check.name, check.status, check.message)
    
    return report


def format_report_text(report: DiagnosticsReport) -> str:
    """Format a diagnostics report as human-readable text."""
    lines = [
        "=" * 60,
        "You2.0 Social Brain - Diagnostics Report",
        f"Timestamp: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Version: {report.version}",
        f"Overall Status: {report.overall_status.upper()}",
        "=" * 60,
        "",
        "System Information:",
    ]
    for key, value in report.system.items():
        lines.append(f"  {key}: {value}")
    
    lines.extend(["", "Health Checks:"])
    for check in report.checks:
        icon = "✓" if check.status == "ok" else "⚠" if check.status == "warning" else "✗"
        lines.append(f"  {icon} {check.name}: {check.status.upper()}")
        lines.append(f"     {check.message}")
        if check.latency_ms:
            lines.append(f"     Latency: {check.latency_ms}ms")
        if check.details:
            for k, v in check.details.items():
                if k not in ("traceback",):
                    lines.append(f"     {k}: {v}")
    
    lines.extend(["", "Recent Log Summary:"])
    log = report.log_summary
    lines.append(f"  Log files: {', '.join(log.get('files', [])) or 'None'}")
    lines.append(f"  Recent errors: {log.get('error_count', 0)}")
    lines.append(f"  Recent warnings: {log.get('warning_count', 0)}")
    
    if log.get("recent_errors"):
        lines.extend(["", "  Last 3 Errors:"])
        for err in log["recent_errors"][-3:]:
            lines.append(f"    {err[:120]}")
    
    lines.append("=" * 60)
    return "\n".join(lines)
