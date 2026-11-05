"""Typed market evidence and strictly bounded, non-executable AI opinion.

AI confidence is an uncalibrated opinion. Numeric market evidence belongs in the
trusted context only; provider prose may not introduce price/quantity claims.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from papertrade.domain import INSTRUMENTS, utcnow


class AIValidationError(ValueError):
    """Safe, non-secret reason why analysis cannot be used."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


def utc_stamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("A timezone-aware timestamp is required")
    return value.astimezone(timezone.utc)


class CandleEvidence(StrictModel):
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    _timestamp = field_validator("timestamp", mode="before")(utc_stamp)

    @model_validator(mode="after")
    def price_range(self):
        if self.timestamp.minute % 15 or self.timestamp.second or self.timestamp.microsecond:
            raise ValueError("Candle evidence requires fifteen-minute opening boundaries")
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("Invalid candle price range")
        return self


class QuantEvidence(StrictModel):
    probability: float = Field(ge=0, le=1)
    expected_return: float
    regime: Literal["range", "uptrend", "downtrend", "high_volatility", "unknown"]
    model_version: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")


class PositionEvidence(StrictModel):
    symbol: str
    qty: float = Field(ge=0)
    avg_entry: float = Field(gt=0)
    current_price: float = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def supported_symbol(cls, value):
        if value not in INSTRUMENTS:
            raise ValueError("Unsupported instrument")
        return value


class MarketContext(StrictModel):
    symbol: str
    asset_class: Literal["crypto", "equity", "forex"]
    data_timestamp: datetime
    current_price: float = Field(gt=0)
    recent_candles: list[CandleEvidence] = Field(min_length=1, max_length=32)
    trend_indicators: dict[str, float]
    momentum_indicators: dict[str, float]
    volatility: dict[str, float]
    volume: dict[str, float]
    support_resistance: dict[str, float]
    quant_prediction: QuantEvidence
    positions: list[PositionEvidence] = Field(max_length=20)
    macro_context: Literal["No verified macroeconomic context provided"] = "No verified macroeconomic context provided"
    news_context: Literal["No verified news context provided"] = "No verified news context provided"

    _timestamp = field_validator("data_timestamp", mode="before")(utc_stamp)

    @field_validator("trend_indicators", "momentum_indicators", "volatility", "volume", "support_resistance")
    @classmethod
    def bounded_indicators(cls, value):
        if len(value) > 32 or any(not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", name) for name in value):
            raise ValueError("Invalid indicator names")
        if any(not math.isfinite(number) for number in value.values()):
            raise ValueError("Non-finite market evidence")
        return value

    @model_validator(mode="after")
    def evidence_integrity(self):
        if self.symbol not in INSTRUMENTS or INSTRUMENTS[self.symbol].market != self.asset_class:
            raise ValueError("Unsupported or mismatched instrument")
        stamps = [c.timestamp for c in self.recent_candles]
        if stamps != sorted(set(stamps)):
            raise ValueError("Candle evidence must be unique and chronological")
        from datetime import timedelta
        if any(c.timestamp + timedelta(minutes=15) > self.data_timestamp for c in self.recent_candles):
            raise ValueError("Incomplete candle evidence")
        if stamps[-1] + timedelta(minutes=15) != self.data_timestamp:
            raise ValueError("Context timestamp must be the latest completed candle close")
        return self


_WRITTEN_NUMBERS = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million|billion|dollars?|cents?|percent|percentage)\b", re.IGNORECASE)


def bounded_prose(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 800:
        raise ValueError("Bounded natural-language analysis is required")
    if any(character.isnumeric() for character in text) or _WRITTEN_NUMBERS.search(text):
        raise ValueError("Numeric claims are forbidden in AI prose; use supplied evidence only")
    if any(character in text for character in "`<>{}[]\\$€£¥%") or any(ord(c) < 32 for c in text):
        raise ValueError("Code, markup, control characters and price claims are forbidden")
    if re.search(r"(?:https?://|\b(?:eval|exec|system|popen)\s*\(|__\w+__|\b(?:select|drop|insert)\s+\b(?:table|into|from)\b)", text, re.I):
        raise ValueError("External instructions and executable output are forbidden")
    return text.strip()


class AIAnalysis(StrictModel):
    symbol: str
    market_regime: Literal["bullish", "bearish", "ranging", "high_volatility", "uncertain"]
    direction_bias: Literal["long", "short", "neutral"]
    recommendation: Literal["BUY", "SELL", "CLOSE", "HOLD", "NO_TRADE"]
    confidence: float = Field(ge=0, le=1)
    risk_level: Literal["low", "medium", "high"]
    reasoning_summary: str = Field(min_length=10, max_length=800)
    supporting_factors: list[str] = Field(min_length=0, max_length=8)
    risk_factors: list[str] = Field(min_length=1, max_length=8)
    data_timestamp: datetime

    _timestamp = field_validator("data_timestamp", mode="before")(utc_stamp)
    _summary = field_validator("reasoning_summary")(bounded_prose)

    @field_validator("supporting_factors", "risk_factors")
    @classmethod
    def safe_prose(cls, values):
        return [bounded_prose(value) for value in values]

    @model_validator(mode="after")
    def consistent_opinion(self):
        if self.symbol not in INSTRUMENTS:
            raise ValueError("Unsupported instrument")
        if self.recommendation == "BUY" and (self.direction_bias != "long" or self.market_regime in {
            "bearish", "high_volatility", "uncertain"} or self.risk_level == "high"):
            raise ValueError("Contradictory entry opinion")
        if self.recommendation in {"SELL", "CLOSE"} and self.direction_bias == "long":
            raise ValueError("Contradictory exit opinion")
        if self.market_regime == "bullish" and self.direction_bias == "short":
            raise ValueError("Contradictory regime and direction")
        if self.market_regime == "bearish" and self.direction_bias == "long":
            raise ValueError("Contradictory regime and direction")
        return self


def validate_analysis(raw: str | dict, context: MarketContext, now: datetime | None = None,
                      max_age_seconds: int = 4500) -> AIAnalysis:
    try:
        if isinstance(raw, str):
            # JSON decoder rejects duplicate fields instead of silently trusting the last value.
            def unique_object(pairs):
                values = {}
                for key, value in pairs:
                    if key in values:
                        raise ValueError("Duplicate JSON field")
                    values[key] = value
                return values
            raw = json.loads(raw, object_pairs_hook=unique_object, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        analysis = AIAnalysis.model_validate(raw)
        clock = utc_stamp(now or utcnow())
        age = (clock - analysis.data_timestamp).total_seconds()
        if analysis.symbol != context.symbol or analysis.data_timestamp != context.data_timestamp:
            raise ValueError("AI output does not match market evidence")
        if not 0 <= age <= max_age_seconds:
            raise ValueError("AI analysis is stale or future-dated")
        if analysis.recommendation in {"SELL", "CLOSE"} and not any(
            position.symbol == context.symbol and position.qty > 0 for position in context.positions):
            raise ValueError("An exit opinion requires an existing long position")
        return analysis
    except (ValidationError, ValueError, TypeError, KeyError):
        raise AIValidationError("AI analysis failed strict evidence/response validation") from None
