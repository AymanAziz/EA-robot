from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from filelock import FileLock

from papertrade.engine import TradingEngine


def test_schedule_runs_twenty_seconds_after_each_quarter_hour():
    trigger = CronTrigger(minute="0,15,30,45", second=20, timezone=timezone.utc)
    now = datetime(2026, 11, 5, 10, 14, 59, tzinfo=timezone.utc)
    first = trigger.get_next_fire_time(None, now)
    assert first == datetime(2026, 11, 5, 10, 15, 20, tzinfo=timezone.utc)
    assert trigger.get_next_fire_time(first, first).minute == 30


def test_overlapping_worker_skips_without_creating_a_run(settings, db):
    engine = TradingEngine(settings, db, {}, {})
    with FileLock(settings.state_dir / "engine.lock"):
        assert engine.run_once()["reason"] == "another_execution_is_running"
