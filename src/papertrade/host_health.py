"""Observed backend resources; never infer Oracle availability from the dashboard host."""
import platform
import time
from datetime import datetime, timezone

import psutil
from sqlalchemy import text


def observe_host(db):
    start = time.monotonic()
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            journal = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        database = {"reachable": True, "journal_mode": journal,
                    "latency_ms": round((time.monotonic() - start) * 1000, 2),
                    "integrity_verified": False}
    except Exception:
        database = {"reachable": False, "integrity_verified": False}
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(db.settings.state_dir.resolve())
        host = {"os": platform.system(), "architecture": platform.machine(),
                "cpu_percent_sample": psutil.cpu_percent(interval=0.02),
                "memory_percent": memory.percent, "memory_available_bytes": memory.available,
                "disk_free_bytes": disk.free, "disk_percent": disk.percent,
                "boot_time": datetime.fromtimestamp(psutil.boot_time(), timezone.utc).isoformat()}
    except Exception:
        host = {"status": "unavailable"}
    return {"observed_at": datetime.now(timezone.utc).isoformat(),
            "deployment_declared": db.settings.deployment_environment, "host": host, "database": database,
            "note": "Resources measured on the backend; deployment label is operator configuration, not cloud attestation"}
