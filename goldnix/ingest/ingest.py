"""Load and profile XAUUSD H1 bid/ask bars."""

from __future__ import annotations

import pandas as pd

SYNTHETIC_SPREAD_WARNING = (
    "Spread is synthetic. The vol ceiling is a volatility filter, not a spread filter. "
    "Live spread spikes are NOT modelled; rely on spread × 1.5 / × 2 stress."
)
SYNTHETIC_MODAL_SHARE = 0.95

_SPREAD_COLUMNS = {
    "entry": ("ask_open", "bid_open"),
    "ceiling": ("ask_close", "bid_close"),
}


def load_bars(path) -> pd.DataFrame:
    """Load bars with unique, strictly increasing UTC timestamps."""
    bars = pd.read_csv(path)
    bars["timestamp_utc"] = pd.to_datetime(bars["timestamp_utc"], utc=True, errors="raise")
    bars = (
        bars.drop_duplicates(subset="timestamp_utc", keep="first")
        .sort_values("timestamp_utc", kind="stable")
        .reset_index(drop=True)
    )
    timestamps = bars["timestamp_utc"]
    if not timestamps.is_unique or not timestamps.is_monotonic_increasing:
        raise ValueError("timestamps must be unique and strictly increasing")
    return bars


def spread_distribution_by_year(bars: pd.DataFrame) -> pd.DataFrame:
    """Summarise the approved entry and ceiling spread definitions by UTC year."""
    years = bars["timestamp_utc"].dt.year
    records = []
    for spread_kind, (ask_column, bid_column) in _SPREAD_COLUMNS.items():
        spreads = (bars[ask_column] - bars[bid_column]).round(10)
        for year, annual in spreads.groupby(years, sort=True):
            counts = annual.value_counts()
            records.append(
                {
                    "spread_kind": spread_kind,
                    "year": int(year),
                    "min": annual.min(),
                    "p5": annual.quantile(0.05),
                    "median": annual.median(),
                    "p95": annual.quantile(0.95),
                    "max": annual.max(),
                    "modal_share": counts.iloc[0] / len(annual),
                }
            )
    return pd.DataFrame.from_records(records)


def spread_issues(bars: pd.DataFrame) -> pd.DataFrame:
    """Return rows whose entry or ceiling spread is outside the declared envelope."""
    records = []
    for spread_kind, (ask_column, bid_column) in _SPREAD_COLUMNS.items():
        spreads = (bars[ask_column] - bars[bid_column]).round(10)
        for issue, mask in (
            ("non_positive", spreads <= 0),
            ("above_1_usd", spreads > 1.0),
        ):
            for index in bars.index[mask]:
                records.append(
                    {
                        "timestamp_utc": bars.at[index, "timestamp_utc"],
                        "spread_kind": spread_kind,
                        "spread": spreads.at[index],
                        "issue": issue,
                    }
                )
    return pd.DataFrame.from_records(
        records,
        columns=["timestamp_utc", "spread_kind", "spread", "issue"],
    )


def synthetic_spread_warning(bars: pd.DataFrame) -> str | None:
    """Return the required warning if either approved spread is essentially constant."""
    for ask_column, bid_column in _SPREAD_COLUMNS.values():
        spreads = (bars[ask_column] - bars[bid_column]).round(10)
        if spreads.value_counts(normalize=True).iloc[0] >= SYNTHETIC_MODAL_SHARE:
            return SYNTHETIC_SPREAD_WARNING
    return None
