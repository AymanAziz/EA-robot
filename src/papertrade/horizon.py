"""One definition of the strategy holding and outcome horizons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


BAR_MINUTES = 15


@dataclass(frozen=True)
class HorizonPolicy:
    """Translate a holding period in bars into every dependent time boundary."""

    bars: int

    def __post_init__(self) -> None:
        if isinstance(self.bars, bool) or not isinstance(self.bars, int) or self.bars < 1:
            raise ValueError("Positive integer holding horizon required")

    @property
    def hold_delta(self) -> timedelta:
        return timedelta(minutes=BAR_MINUTES * self.bars)

    @property
    def outcome_delta(self) -> timedelta:
        # The signal is observed at a candle close and enters at the next open.
        return timedelta(minutes=BAR_MINUTES * (self.bars + 1))

    @property
    def purge_bars(self) -> int:
        return self.bars + 1

    def permits_market(self, market: str) -> bool:
        """The registered twelve-hour hypothesis is crypto-only."""
        return self.bars != 48 or market == "crypto"
