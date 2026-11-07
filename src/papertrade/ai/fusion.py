"""Conservative, validated strategy gates; LLM opinions never become order authority.

The quantitative decision and independent risk engine retain their existing roles.
AI strategies can remove a quantitative entry. They cannot create an entry or veto
an existing risk-reducing exit. Certificates are local administrator-reviewed facts,
not a field accepted from any AI response.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from papertrade.config import Settings
from papertrade.decisions import Decision

STRATEGIES = ("quant_only", "ai_filtered_quant", "hybrid", "ai_only_research")


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Timezone-aware timestamp required")
    if parsed.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc)


def strategy_policy(settings: Settings) -> dict:
    """Non-secret policy fingerprint; upgrades invalidate approval, never old quant artifacts."""
    root = Path(__file__).resolve().parents[1]
    sources = ("ai/fusion.py", "ai/evaluation.py", "ai/schema.py", "ai/providers.py", "ai/service.py",
               "decisions.py", "risk.py", "features.py", "backtest.py", "calendars.py", "ml.py", "data.py",
               "engine.py", "horizon.py")
    keys = ("execution", "capital", "risk_per_trade", "daily_loss_limit", "max_drawdown", "max_positions",
            "max_total_exposure", "max_instrument_exposure", "max_correlated_exposure", "min_probability",
            "min_net_edge_bps", "max_data_age_seconds", "max_quote_age_seconds", "holding_horizon_bars",
            "allow_unhosted_protection",
            "ai_max_age_minutes", "ai_analysis_interval_minutes", "ai_recent_candles",
            "ai_event_probability_delta", "ai_event_price_change", "ai_event_min_interval_minutes",
            "ai_response_format", "ai_max_output_tokens", "ai_max_attempts", "ai_timeout_seconds",
            "ai_max_daily_requests", "ai_max_daily_tokens", "strategy_min_validation_trades",
            "strategy_min_observations", "strategy_certificate_max_age_days")
    value = {"version": "ai_entry_veto_v2", "settings": {k: getattr(settings, k, None) for k in keys},
             "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                               if (root / name).is_file() else "absent" for name in sources},
             "rules": {"ai_filtered_quant": "quant BUY and timely AI BUY/long, non-high risk, non-bearish regime",
                       "hybrid": "quant BUY and timely AI BUY/long, low risk, bullish regime",
                       "ai_only_research": "no automatic entries", "confidence": "never weighted or calibrated"}}
    value["sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return value


def seal_certificate(value: dict) -> dict:
    """Integrity checksum, not a signature or a replacement for server authorization."""
    result = {k: v for k, v in value.items() if k != "content_sha256"}
    result["content_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return result


def validate_certificate(certificate: dict | None, *, strategy: str, symbol: str,
                         quant_model_version: str, ai_provider: str, ai_model: str,
                         settings: Settings, now: datetime) -> bool:
    try:
        cert = certificate or {}
        if cert.get("content_sha256") != seal_certificate(cert)["content_sha256"]:
            return False
        expected = {"schema_version": 1, "strategy": strategy, "symbol": symbol,
                    "quant_model_version": quant_model_version, "ai_provider": ai_provider,
                    "ai_model": ai_model, "policy_sha256": strategy_policy(settings)["sha256"],
                    "accepted": True, "approved": True, "source": "forward_replay"}
        if any(cert.get(key) != value for key, value in expected.items()):
            return False
        criteria = cert.get("criteria")
        if not isinstance(criteria, dict) or not criteria or not all(v is True for v in criteria.values()):
            return False
        created, approved, expires = (_timestamp(cert[k]) for k in ("created_at", "approved_at", "expires_at"))
        maximum = timedelta(days=getattr(settings, "strategy_certificate_max_age_days", 30))
        return bool(created <= approved <= now < expires <= created + maximum and cert.get("report_sha256"))
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def ai_entry_agrees(ai: Any, *, strategy: str, symbol: str, candle_at: datetime,
                    decision_at: datetime, ai_created_at: datetime | str | None,
                    max_age_minutes: int = 75) -> tuple[bool, str]:
    """Only stored observations available at the decision time can gate an entry."""
    try:
        value = ai.model_dump(mode="json") if hasattr(ai, "model_dump") else ai
        if not isinstance(value, dict) or value.get("symbol") != symbol:
            return False, "ai_missing_or_wrong_symbol"
        timestamp = _timestamp(value["data_timestamp"])
        created = _timestamp(ai_created_at)
        now = _timestamp(decision_at)
        candle_close = _timestamp(candle_at) + timedelta(minutes=15)
        if timestamp > candle_close or timestamp > created or created > now:
            return False, "ai_future_or_hindsight_analysis"
        if not 0 <= (now - timestamp).total_seconds() <= max_age_minutes * 60:
            return False, "ai_analysis_stale"
        confidence = value.get("confidence")
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            return False, "ai_invalid_opinion"
        if value.get("recommendation") != "BUY" or value.get("direction_bias") != "long":
            return False, "ai_quant_disagreement"
        if value.get("risk_level") not in {"low", "medium"}:
            return False, "ai_risk_veto"
        if value.get("market_regime") not in {"bullish", "ranging"}:
            return False, "ai_regime_veto"
        if strategy == "hybrid" and (value["risk_level"] != "low" or value["market_regime"] != "bullish"):
            return False, "hybrid_evidence_veto"
        return True, "ai_quant_agreement"
    except (ValueError, TypeError, KeyError, OverflowError):
        return False, "ai_invalid_or_missing_provenance"


def fuse_decision(quant: Decision, *, strategy: str, symbol: str, candle_at: datetime,
                  now: datetime, quant_model_version: str, ai: Any = None,
                  ai_provider: str = "", ai_model: str = "", ai_created_at: datetime | str | None = None,
                  certificate: dict | None = None, settings: Settings) -> Decision:
    if quant.action in {"CLOSE", "SELL"}:
        return quant
    if quant.action != "BUY":
        return quant

    def hold(reason):
        return Decision("HOLD", reason, quant.cost_bps)

    if strategy not in STRATEGIES:
        return hold("unsupported_strategy")
    if strategy == "ai_only_research":
        return hold("ai_only_research_no_execution")
    if not getattr(settings, "strategy_execution_enabled", False):
        return hold("strategy_execution_disabled")
    if not quant_model_version:
        return hold("quant_model_not_validated")
    if strategy == "quant_only":
        return quant
    if not validate_certificate(certificate, strategy=strategy, symbol=symbol,
        quant_model_version=quant_model_version, ai_provider=ai_provider, ai_model=ai_model,
        settings=settings, now=now):
        return hold("ai_strategy_not_validated_and_approved")
    agrees, reason = ai_entry_agrees(ai, strategy=strategy, symbol=symbol, candle_at=candle_at,
                                   decision_at=now, ai_created_at=ai_created_at,
                                   max_age_minutes=getattr(settings, "ai_max_age_minutes", 75))
    return Decision("BUY", reason, quant.cost_bps) if agrees else hold(reason)
