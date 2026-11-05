"""APScheduler is optional; never run alongside the deployment systemd timer."""
from datetime import timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from papertrade.engine import TradingEngine


def run_scheduler(engine: TradingEngine):
    scheduler = BlockingScheduler(timezone=timezone.utc)
    scheduler.add_job(engine.run_once, CronTrigger(minute="0,15,30,45", second=20, timezone=timezone.utc),
                      id="analysis", max_instances=1, coalesce=True, misfire_grace_time=60)
    scheduler.add_job(engine.monitor_once, CronTrigger(second=10, timezone=timezone.utc),
                      id="protection", max_instances=1, coalesce=True, misfire_grace_time=20)
    scheduler.add_job(engine.ai_service.run_once,
                      CronTrigger(minute="0,15,30,45", second=40, timezone=timezone.utc),
                      id="ai_analysis", max_instances=1, coalesce=True, misfire_grace_time=60)
    # A restart first reconciles and monitors; missed candles are not replayed as present opportunities.
    engine.monitor_once()
    scheduler.start()
