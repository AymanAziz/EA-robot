"""SQLite-serialized reservations shared by all processes/providers and retained after crashes."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, text

from papertrade.db import Database
from papertrade.domain import utcnow
from papertrade.logging import redact
from papertrade.models import AIRequest


class BudgetExceeded(RuntimeError):
    pass


class UsageBudget:
    def __init__(self, db: Database, clock=utcnow):
        self.db, self.clock = db, clock

    def reserve(self, tokens: int, *, provider: str, model: str, symbol: str | None = None) -> int:
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise ValueError("Invalid AI token reservation")
        now = self.clock()
        day = now.date().isoformat()
        with self.db.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            count, used = session.execute(select(func.count(AIRequest.id), func.coalesce(func.sum(AIRequest.charged_tokens), 0)
                                                ).where(AIRequest.day == day)).one()
            settings = self.db.settings
            if count >= settings.ai_max_daily_requests or used + tokens > settings.ai_max_daily_tokens:
                raise BudgetExceeded("Daily AI request or conservative token budget exhausted")
            row = AIRequest(provider=provider, model=model, symbol=symbol, day=day,
                kind="models" if tokens == 0 else "analysis", status="reserved", reserved_tokens=tokens,
                charged_tokens=tokens, created_at=now)
            session.add(row)
            session.flush()
            return row.id

    def finish(self, request_id: int, usage):
        with self.db.session() as session:
            row = session.get(AIRequest, request_id)
            if row is None or row.finished_at is not None:
                return
            row.status, row.kind = usage.status, usage.request_kind
            row.http_status, row.latency_ms = usage.http_status, usage.latency_ms
            row.error = redact(usage.error, self.db.settings)[:250] if usage.error else None
            row.prompt_tokens, row.completion_tokens, row.total_tokens = usage.prompt_tokens, usage.completion_tokens, usage.total_tokens
            if usage.usage_known and usage.total_tokens is not None:
                row.charged_tokens = max(0, usage.total_tokens)
            # Unknown usage (including timeouts/crashes) consumes the entire original reservation.
            row.rate_limits, row.finished_at = usage.rate_limits, self.clock()

    def callbacks(self, provider: str, model: str, symbol: str | None):
        active = None

        def before(tokens):
            nonlocal active
            active = self.reserve(tokens, provider=provider, model=model, symbol=symbol)

        def after(usage):
            nonlocal active
            if active is not None:
                self.finish(active, usage)
                active = None

        return before, after

    def metrics(self, now: datetime | None = None):
        day = (now or self.clock()).date().isoformat()
        with self.db.session() as session:
            rows = session.scalars(select(AIRequest).where(AIRequest.day == day)).all()
        providers = {}
        for row in rows:
            value = providers.setdefault(row.provider, {"requests": 0, "tokens_charged": 0, "tokens_reported": 0,
                "failures": 0, "rate_limits": 0, "unknown_usage_requests": 0, "last_latency_ms": None})
            value["requests"] += 1
            value["tokens_charged"] += row.charged_tokens
            value["tokens_reported"] += row.total_tokens or 0
            value["failures"] += row.status not in {"success", "reserved"}
            value["rate_limits"] += row.status == "rate_limited"
            value["unknown_usage_requests"] += row.total_tokens is None and row.kind == "analysis"
            value["last_latency_ms"] = row.latency_ms
        return {"day_utc": day, "requests": len(rows), "tokens_charged": sum(r.charged_tokens for r in rows),
                "tokens_reported": sum(r.total_tokens or 0 for r in rows), "providers": providers,
                "request_limit": self.db.settings.ai_max_daily_requests, "token_limit": self.db.settings.ai_max_daily_tokens,
                "billing_tier_verified_by_api": False,
                "account_tier_declared": self.db.settings.ai_account_tier,
                "note": "Local conservative limits; organization-wide provider limits/billing are separate"}
