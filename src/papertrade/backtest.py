"""Deterministic long-only, next-bar execution with finite cash and conservative OHLC stops.

Historical bid/ask is generally unavailable on free feeds. Reported spread/slippage
are explicit estimates, not observed fills. Tick volume is not forex notional liquidity.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from papertrade.calendars import is_market_open
from papertrade.config import Settings
from papertrade.data import validate_candles
from papertrade.decisions import decide
from papertrade.domain import Instrument, Quote, utcnow
from papertrade.features import build_features, feature_regime
from papertrade.horizon import HorizonPolicy
from papertrade.risk import Portfolio, RiskContext, approve_entry


def performance_metrics(equity: pd.Series, trades: list[dict], turnover: float = 0,
                        exposure_bars: int = 0, transaction_costs: float = 0) -> dict:
    if equity.empty:
        return {}
    returns = equity.pct_change(fill_method=None).dropna()
    elapsed_days = max((equity.index[-1] - equity.index[0]).total_seconds() / 86400, 0)
    periods_year = len(returns) / (elapsed_days / 365.25) if elapsed_days > 0 else 0
    deviation = float(returns.std(ddof=1)) if len(returns) > 1 else 0
    downside = float(np.sqrt(np.mean(np.minimum(returns.to_numpy(), 0) ** 2))) if len(returns) else 0
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1)
    profits = [float(t["net_pl"]) for t in trades]
    gains = sum(x for x in profits if x > 0)
    losses = -sum(x for x in profits if x < 0)
    return {
        "total_return": total_return,
        "cagr": float((equity.iloc[-1] / equity.iloc[0]) ** (365.25 / elapsed_days) - 1) if elapsed_days >= 365 else None,
        "sharpe": float(returns.mean() / deviation * math.sqrt(periods_year)) if deviation > 1e-12 else 0.0,
        "sortino": float(returns.mean() / downside * math.sqrt(periods_year)) if downside > 1e-12 else 0.0,
        "max_drawdown": float((equity / equity.cummax() - 1).min()),
        "profit_factor": float(gains / losses) if losses > 0 else (None if gains > 0 else 0.0),
        "win_rate": sum(x > 0 for x in profits) / len(profits) if profits else 0.0,
        "trade_count": len(trades),
        "trades_per_day": len(trades) / elapsed_days if elapsed_days > 0 else 0.0,
        "turnover": float(turnover / equity.iloc[0]),
        "exposure": float(exposure_bars / max(len(equity) - 1, 1)),
        "transaction_costs": float(transaction_costs),
    }


def run_backtest(candles: pd.DataFrame, probabilities: pd.Series, instrument: Instrument,
                 threshold: float = .6, expected_returns: pd.Series | None = None,
                 horizon: int | None = None, initial_cash: float = 10000,
                 spread_bps: float | None = None, min_edge_bps: float = 5,
                 start: pd.Timestamp | None = None, end: pd.Timestamp | None = None,
                 risk_per_trade: float = .005, daily_loss_limit: float = .02,
                 max_drawdown: float = .10, now=None, settings: Settings | None = None) -> dict:
    if not 0.5 <= threshold <= 1 or initial_cash <= 0:
        raise ValueError("Invalid backtest configuration")
    frame = validate_candles(candles, now or utcnow(), instrument.market)
    policy = settings or Settings(_env_file=None, capital=initial_cash, risk_per_trade=risk_per_trade,
                                  daily_loss_limit=daily_loss_limit, max_drawdown=max_drawdown,
                                  min_net_edge_bps=min_edge_bps)
    holding = HorizonPolicy(policy.holding_horizon_bars)
    if horizon is not None and horizon != holding.bars:
        raise ValueError("Backtest holding horizon conflicts with the strategy policy")
    horizon = holding.bars
    decision_policy = policy.model_copy(update={"min_probability": max(policy.min_probability, threshold)})
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None or frame.index.has_duplicates:
        raise ValueError("Unique timezone-aware candles required")
    features = build_features(frame)
    probs = probabilities.reindex(frame.index)
    spread = instrument.max_spread_bps / 2 if spread_bps is None else spread_bps
    if spread < 0:
        raise ValueError("Spread must be nonnegative")
    execution_fraction = instrument.slippage_bps / 10000
    fee_fraction = instrument.fee_bps / 10000
    cash = initial_cash
    peak = initial_cash
    daily_start = initial_cash
    current_day = None
    daily_latched = drawdown_latched = False
    position = None
    trades = []
    points = []
    turnover = total_costs = 0.
    exposure = 0
    indices = np.arange(len(frame))
    if start is not None:
        indices = indices[frame.index[indices] >= start]
    if end is not None:
        indices = indices[frame.index[indices] <= end]
    if len(indices) < 2:
        raise ValueError("Insufficient backtest interval")
    points.append((frame.index[indices[0]], initial_cash))

    def close_trade(price, i, reason, quoted_bid=False):
        nonlocal cash, turnover, total_costs, position
        bid = price if quoted_bid else price * (1 - spread / 20000)
        execution_price = bid * (1 - execution_fraction)
        notional = position["qty"] * execution_price
        fee = notional * fee_fraction
        cash += notional - fee
        reference_mid = bid / (1 - spread / 20000)
        total_costs += fee + position["qty"] * (reference_mid - execution_price)
        turnover += notional
        trades.append({"signal_time": position["signal_time"], "entry_time": position["entry_time"],
                       "exit_time": frame.index[i].isoformat(), "entry_price": position["entry_price"],
                       "exit_price": execution_price, "qty": position["qty"],
                       "fees": position["fee"] + fee,
                       "net_pl": notional - fee - position["entry_notional"] - position["fee"],
                       "regime": position["regime"], "exit_reason": reason})
        position = None

    for i in indices[1:]:
        stamp = frame.index[i]
        previous = frame.index[i - 1]
        bar = frame.iloc[i]
        quote = Quote(float(bar.open) * (1 - spread / 20000), float(bar.open) * (1 + spread / 20000), stamp.to_pydatetime())
        equity_open = cash + (position["qty"] * quote.bid if position else 0)
        peak = max(peak, equity_open)
        if current_day != stamp.date():
            current_day, daily_start = stamp.date(), points[-1][1]
            daily_latched = False
        daily_latched = daily_latched or equity_open <= daily_start * (1 - policy.daily_loss_limit)
        drawdown_latched = drawdown_latched or equity_open <= peak * (1 - policy.max_drawdown)
        circuit = daily_latched or drawdown_latched
        feature = features.loc[previous] if previous in features.index else None
        expected = np.nan if expected_returns is None else expected_returns.get(previous, np.nan)
        decision = decide(float(probs.iloc[i - 1]), float(expected), feature_regime(feature) if feature is not None else "unknown",
                          instrument, quote, float(frame.volume.iloc[i - 1]), position["qty"] if position else 0, decision_policy)
        closed_this_bar = False
        if position:
            exposure += 1
            if quote.bid <= position["stop"]:
                close_trade(float(bar.open), i, "stop_gap")
            elif quote.bid >= position["target"]:
                close_trade(position["target"], i, "take_profit_gap", quoted_bid=True)
            elif circuit or (stamp - pd.Timestamp(position["entry_time"])).total_seconds() >= horizon * 900 or decision.action == "CLOSE":
                close_trade(float(bar.open), i, "risk_exit" if circuit else "scheduled_exit")
            elif bar.low * (1 - spread / 20000) <= position["stop"]:
                close_trade(position["stop"], i, "stop", quoted_bid=True)
            elif bar.high * (1 - spread / 20000) >= position["target"]:
                close_trade(position["target"], i, "take_profit", quoted_bid=True)
            closed_this_bar = position is None
        if (position is None and not closed_this_bar and not circuit and previous in features.index
                and stamp - previous == pd.Timedelta(minutes=15) and is_market_open(instrument.market, stamp.to_pydatetime())
                and decision.action == "BUY"):
            portfolio = Portfolio(equity_open, cash, daily_start, peak, [], reconciled=True)
            context = RiskContext(stamp.to_pydatetime(), previous.to_pydatetime(), quote, True, True, True,
                                  float(frame.volume.iloc[i - 1]), float(feature.atr), daily_circuit=daily_latched,
                                  session_remaining_ok=(holding.permits_market(instrument.market)
                                      and is_market_open(instrument.market,
                                          (stamp + holding.hold_delta).to_pydatetime())))
            approval = approve_entry(instrument, portfolio, context, policy)
            if approval.approved:
                raw_price = float(bar.open)
                price = quote.ask * (1 + execution_fraction)
                qty = approval.qty
                if qty >= instrument.min_qty:
                    notional = qty * price
                    fee = notional * fee_fraction
                    cash -= notional + fee
                    turnover += notional
                    total_costs += fee + qty * (price - raw_price)
                    position = {"qty": qty, "entry_price": price, "entry_notional": notional,
                                "fee": fee, "stop": approval.stop_loss,
                                "target": approval.take_profit,
                                "entry_bar": i, "signal_time": previous.isoformat(), "entry_time": stamp.isoformat(),
                                "regime": feature_regime(feature)}
                    # A protective stop is active immediately after entry; worst path first.
                    if bar.low * (1 - spread / 20000) <= position["stop"]:
                        close_trade(position["stop"], i, "entry_bar_stop", quoted_bid=True)
                    elif bar.high * (1 - spread / 20000) >= position["target"]:
                        close_trade(position["target"], i, "entry_bar_take_profit", quoted_bid=True)
        mark = cash + (position["qty"] * float(bar.close) * (1 - spread / 20000) if position else 0)
        peak = max(peak, mark)
        daily_latched = daily_latched or mark <= daily_start * (1 - policy.daily_loss_limit)
        drawdown_latched = drawdown_latched or mark <= peak * (1 - policy.max_drawdown)
        points.append((stamp, mark))
    if position:
        close_trade(float(frame.close.iloc[indices[-1]]), indices[-1], "end_of_test")
        points[-1] = (points[-1][0], cash)
    equity = pd.Series([x[1] for x in points], index=pd.DatetimeIndex([x[0] for x in points]))
    by_regime = {}
    for regime in ("uptrend", "downtrend", "range", "high_volatility"):
        selected = [t for t in trades if t["regime"] == regime]
        by_regime[regime] = {"trade_count": len(selected), "net_pl": sum(t["net_pl"] for t in selected)}
    return {"metrics": performance_metrics(equity, trades, turnover, exposure, total_costs),
            "trades": trades, "equity": [{"timestamp": stamp.isoformat(), "equity": float(value)} for stamp, value in equity.items()],
            "by_regime": by_regime,
            "assumptions": {"market": instrument.market, "spread_bps": spread, "fee_bps_per_side": instrument.fee_bps,
                            "slippage_bps_per_side": instrument.slippage_bps, "entry": "next_bar_open",
                            "ohlc_ambiguity": "stop_first", "shorts": False, "cash_leverage": 1,
                            "volume_participation": "1% prior candle volume; forex tick volume only filters missing activity",
                            "portfolio": "single symbol isolation; operational portfolio may further reject correlated/combined exposure",
                            "decision_and_sizing": "shared production decide() and approve_entry()",
                            "horizon_bars": horizon, "survivorship": "fixed current universe; no delisted asset study"}}
