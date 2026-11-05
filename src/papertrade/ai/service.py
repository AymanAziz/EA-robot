"""AI work runs outside the execution lock. Trading reads validated, durable observations only."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from filelock import FileLock, Timeout
from sqlalchemy import select

from papertrade.ai.budget import BudgetExceeded, UsageBudget
from papertrade.ai.schema import MarketContext, validate_analysis
from papertrade.config import Settings
from papertrade.db import Database, aware
from papertrade.domain import INSTRUMENTS, utcnow
from papertrade.features import build_features
from papertrade.models import AIAnalysisRow, PositionRow, PredictionRow, StrategyValidation


class AIDisabled(RuntimeError):
    pass


def model_for(settings: Settings) -> str:
    return settings.groq_model if settings.ai_provider == "groq" else settings.hermes_model


def provider_disabled_reason(settings: Settings, *, discovery=False):
    if (not settings.ai_enabled and not discovery) or settings.ai_provider == "none":
        return "Cloud AI analysis is disabled"
    if settings.ai_account_tier == "unverified":
        return "Declare a confirmed free account or explicitly authorize paid usage"
    if settings.ai_account_tier == "paid" and not settings.ai_allow_paid:
        return "Paid AI usage is not authorized"
    if settings.ai_provider == "hermes" and not settings.ai_allow_paid:
        return "Hermes requires explicit paid-access authorization; no fallback is configured"
    key = settings.groq_api_key if settings.ai_provider == "groq" else settings.hermes_api_key
    if not key.get_secret_value():
        return "Selected AI provider credentials are missing"
    model = model_for(settings)
    if not model and not discovery:
        return "Select an available provider model explicitly using ai-models"
    return None


def make_provider(settings: Settings, budget: UsageBudget, symbol=None, *, discovery=False, transport=None):
    from papertrade.ai.providers import GroqProvider, HermesProvider
    reason = provider_disabled_reason(settings, discovery=discovery)
    if reason:
        raise AIDisabled(reason)
    key = settings.groq_api_key if settings.ai_provider == "groq" else settings.hermes_api_key
    model = model_for(settings)
    before, after = budget.callbacks(settings.ai_provider, model, symbol)
    options = dict(timeout=settings.ai_timeout_seconds, max_attempts=settings.ai_max_attempts,
                   max_output_tokens=settings.ai_max_output_tokens, response_format=settings.ai_response_format,
                   before_attempt=before, after_attempt=after, transport=transport,
                   max_response_age_seconds=settings.ai_max_age_minutes * 60)
    if settings.ai_provider == "groq":
        return GroqProvider(key.get_secret_value(), model, **options)
    return HermesProvider(key.get_secret_value(), model, base_url=settings.hermes_base_url,
                          paid_authorized=settings.ai_allow_paid, **options)


def context_hash(context: MarketContext) -> str:
    return hashlib.sha256(context.model_dump_json().encode()).hexdigest()


def state_hash(context: MarketContext) -> str:
    """Qualitative state for caching; material numeric changes are checked separately."""
    facts = {"symbol": context.symbol, "regime": context.quant_prediction.regime,
             "quant_model": context.quant_prediction.model_version,
             "positions": [{"symbol": p.symbol, "qty": p.qty, "avg_entry": p.avg_entry} for p in context.positions]}
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()


def build_context(db: Database, symbol: str, *, now=None) -> MarketContext:
    from papertrade.data import validate_candles
    now = now or utcnow()
    instrument = INSTRUMENTS[symbol]
    candles = validate_candles(db.load_candles(symbol, limit=600), now, instrument.market,
                              require_fresh=True, max_age_seconds=db.settings.max_data_age_seconds)
    with db.session() as session:
        prediction = session.scalar(select(PredictionRow).where(PredictionRow.symbol == symbol,
                PredictionRow.candle_at == candles.index[-1].to_pydatetime()).order_by(PredictionRow.id.desc()))
        positions = session.scalars(select(PositionRow).where(PositionRow.closed_at.is_(None))).all()
    if prediction is None:
        raise AIDisabled("A current genuine quantitative prediction is required for AI context")
    feature = build_features(candles)
    if feature.empty or feature.index[-1] != candles.index[-1]:
        raise AIDisabled("Insufficient causal market features")
    row = feature.iloc[-1]
    def pick(names):
        return {key: float(row[key]) for key in names}
    recent = candles.tail(db.settings.ai_recent_candles)
    return MarketContext(symbol=symbol, asset_class=instrument.market,
        data_timestamp=candles.index[-1].to_pydatetime() + timedelta(minutes=15),
        current_price=float(candles.iloc[-1].close),
        recent_candles=[dict(timestamp=index.to_pydatetime(), **{k: float(value[k]) for k in
            ("open", "high", "low", "close", "volume")}) for index, value in recent.iterrows()],
        trend_indicators=pick(("sma20_gap", "sma50_gap", "trend_strength")),
        momentum_indicators=pick(("return_1", "return_4", "return_16", "rsi14", "macd", "macd_signal", "momentum8")),
        volatility=pick(("atr", "atr_pct", "volatility", "price_range")),
        volume={"last": float(candles.iloc[-1].volume), **pick(("volume_change", "volume_ratio"))},
        support_resistance={"rolling_low": float(recent.low.min()), "rolling_high": float(recent.high.max())},
        quant_prediction={"probability": prediction.probability, "expected_return": prediction.expected_return,
                          "regime": prediction.regime, "model_version": prediction.model_version},
        positions=[{"symbol": p.symbol, "qty": p.qty, "avg_entry": p.avg_entry,
                    "current_price": p.current_price} for p in positions if p.symbol in INSTRUMENTS and p.qty > 0])


def materially_changed(previous: AIAnalysisRow, context: MarketContext, settings: Settings) -> bool:
    if previous.state_hash != state_hash(context):
        return True
    try:
        old = previous.context
        probability_delta = abs(old["quant_prediction"]["probability"] - context.quant_prediction.probability)
        price_delta = abs(context.current_price / old["current_price"] - 1)
        old_vol = old["volatility"]["volatility"]
        vol_change = old_vol > 0 and context.volatility["volatility"] / old_vol > 2
        return probability_delta >= settings.ai_event_probability_delta or price_delta >= settings.ai_event_price_change or vol_change
    except (KeyError, TypeError, ZeroDivisionError):
        return True


class AIService:
    def __init__(self, settings: Settings, db: Database, *, provider_factory=None, clock=utcnow):
        self.settings, self.db, self.clock = settings, db, clock
        self.budget = UsageBudget(db, clock)
        self.provider_factory = provider_factory or make_provider
        settings.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(settings.state_dir / "ai.lock")

    def _latest(self, symbol, *, valid_only=False):
        with self.db.session() as session:
            query = select(AIAnalysisRow).where(AIAnalysisRow.symbol == symbol,
                AIAnalysisRow.provider == self.settings.ai_provider, AIAnalysisRow.model == model_for(self.settings))
            if valid_only:
                query = query.where(AIAnalysisRow.status == "valid")
            return session.scalar(query.order_by(AIAnalysisRow.id.desc()))

    def cached(self, symbol, *, now=None, context=None):
        now = now or self.clock()
        if provider_disabled_reason(self.settings):
            return None
        row = self._latest(symbol, valid_only=True)
        if row is None or row.response is None or now >= aware(row.expires_at) or aware(row.created_at) > now:
            return None
        latest = self._latest(symbol)
        if latest and latest.status == "error" and latest.id > row.id:
            return None
        try:
            current = context or build_context(self.db, symbol, now=now)
            original = MarketContext.model_validate(row.context)
            if row.context_hash != context_hash(original) or materially_changed(row, current, self.settings):
                return None
            if row.quant_model_version != current.quant_prediction.model_version or aware(row.data_timestamp) > current.data_timestamp:
                return None
            validate_analysis(row.response, original, now, max_age_seconds=self.settings.ai_max_age_minutes * 60)
            return row
        except (ValueError, TypeError, KeyError, AIDisabled):
            return None

    def analyze(self, symbol, *, now=None):
        try:
            with self.lock.acquire(timeout=0):
                return self._analyze(symbol, now=now)
        except Timeout:
            return {"symbol": symbol, "status": "skipped", "reason": "AI worker already running"}

    def _analyze(self, symbol, *, now=None):
        now = now or self.clock()
        reason = provider_disabled_reason(self.settings)
        if reason:
            self.db.health(f"ai:{self.settings.ai_provider}", "disabled", reason, now)
            return {"symbol": symbol, "status": "disabled", "reason": reason}
        context = build_context(self.db, symbol, now=now)
        cached = self.cached(symbol, now=now, context=context)
        latest = self._latest(symbol)
        if latest:
            elapsed = (now - aware(latest.created_at)).total_seconds()
            interval = self.settings.ai_analysis_interval_minutes * 60
            event = materially_changed(latest, context, self.settings)
            if elapsed < interval and (not event or elapsed < self.settings.ai_event_min_interval_minutes * 60):
                return {"symbol": symbol, "status": "cached" if cached else "waiting", "reason": "frequency_gate"}
        try:
            provider = self.provider_factory(self.settings, self.budget, symbol)
        except AIDisabled as exc:
            self.db.health(f"ai:{self.settings.ai_provider}", "disabled", str(exc), now)
            return {"symbol": symbol, "status": "disabled", "reason": str(exc)}
        created = self.clock()
        row = AIAnalysisRow(symbol=symbol, provider=self.settings.ai_provider, model=model_for(self.settings),
            context_hash=context_hash(context), state_hash=state_hash(context),
            quant_model_version=context.quant_prediction.model_version, data_timestamp=context.data_timestamp,
            created_at=created, expires_at=context.data_timestamp + timedelta(minutes=self.settings.ai_max_age_minutes),
            status="pending", context=context.model_dump(mode="json"))
        with self.db.session() as session:
            session.add(row)
            session.flush()
            row_id = row.id
        try:
            result = provider.analyze_market(context, now=now)
            finished = self.clock()
            validate_analysis(result.analysis.model_dump(mode="json"), context, finished,
                              max_age_seconds=self.settings.ai_max_age_minutes * 60)
            with self.db.session() as session:
                saved = session.get(AIAnalysisRow, row_id)
                saved.status, saved.response, saved.created_at = "valid", result.analysis.model_dump(mode="json"), finished
                saved.latency_ms = result.latency_ms
                saved.prompt_tokens, saved.completion_tokens, saved.total_tokens = result.prompt_tokens, result.completion_tokens, result.total_tokens
            self.db.health(f"ai:{self.settings.ai_provider}", "ok", "Validated provider analysis stored", finished)
            return {"symbol": symbol, "status": "valid", "analysis_id": row_id}
        except Exception as exc:
            reason = "Daily AI budget exhausted" if isinstance(exc, BudgetExceeded) else f"AI analysis unavailable: {type(exc).__name__}"
            with self.db.session() as session:
                saved = session.get(AIAnalysisRow, row_id)
                saved.status, saved.error = "error", reason
            self.db.health(f"ai:{self.settings.ai_provider}", "error", reason, self.clock())
            return {"symbol": symbol, "status": "error", "reason": reason}

    def run_once(self):
        try:
            with self.lock.acquire(timeout=0):
                if not self.settings.ai_enabled or self.settings.ai_provider == "none":
                    self.db.health(f"ai:{self.settings.ai_provider}", "disabled", "Cloud AI is disabled", self.clock())
                    return {"status": "disabled", "outcomes": []}
                outcomes = []
                for symbol in INSTRUMENTS:
                    try:
                        outcomes.append(self.analyze(symbol))
                    except Exception as exc:
                        outcomes.append({"symbol": symbol, "status": "skipped", "reason": type(exc).__name__})
                self.db.health("ai_worker", "ok", "AI frequency/event cycle finished", self.clock())
                return {"status": "complete", "outcomes": outcomes}
        except Timeout:
            return {"status": "skipped", "reason": "AI worker already running"}

    def certificate(self, symbol, quant_model_version):
        from papertrade.ai.fusion import validate_certificate
        with self.db.session() as session:
            rows = session.scalars(select(StrategyValidation).where(StrategyValidation.symbol == symbol,
                StrategyValidation.strategy == self.settings.strategy, StrategyValidation.approved.is_(True),
                StrategyValidation.accepted.is_(True)).order_by(StrategyValidation.id.desc())).all()
        for row in rows:
            report_hash = hashlib.sha256(json.dumps(row.report, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if row.certificate.get("report_sha256") != report_hash:
                continue
            if validate_certificate(row.certificate, strategy=self.settings.strategy, symbol=symbol,
                quant_model_version=quant_model_version, ai_provider=self.settings.ai_provider,
                ai_model=model_for(self.settings), settings=self.settings, now=self.clock()):
                return row.certificate
        return None
