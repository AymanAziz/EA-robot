"""Session filters; provider tradeability checks remain authoritative for forex holidays."""
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd


@lru_cache(maxsize=1)
def _nyse():
    return xcals.get_calendar("XNYS", start="2000-01-01", end="2035-12-31")


def is_market_open(market: str, now: datetime) -> bool:
    stamp = pd.Timestamp(now)
    if stamp.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    if market == "crypto":
        return True
    if market == "equity":
        return bool(_nyse().is_open_on_minute(stamp.floor("min"), ignore_breaks=True))
    if market == "forex":
        local = stamp.tz_convert(ZoneInfo("America/New_York"))
        return local.weekday() < 4 or (local.weekday() == 4 and local.hour < 17) or (local.weekday() == 6 and local.hour >= 17)
    raise ValueError("Unknown market")


def session_mask(index: pd.DatetimeIndex, market: str) -> pd.Series:
    if market == "crypto":
        return pd.Series(True, index=index)
    # Both ends of the complete candle must fit inside a regular trading session.
    return pd.Series([is_market_open(market, x.to_pydatetime()) and
                      is_market_open(market, (x + pd.Timedelta(minutes=14)).to_pydatetime())
                      for x in index], index=index)
