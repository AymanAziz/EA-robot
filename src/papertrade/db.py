from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import sessionmaker

from papertrade.config import Settings
from papertrade.domain import INSTRUMENTS, utcnow
from papertrade.models import Base, Candle, Control, Health, InstrumentRow


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        filename = settings.database_url.removeprefix("sqlite:///")
        if filename != ":memory:":
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(self.engine, "connect")
        def pragmas(conn, _):
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        with self.sessions.begin() as session:
            yield session

    def initialize(self):
        """Tests use this; production initializes via Alembic then seed()."""
        Base.metadata.create_all(self.engine)
        self.seed()

    def seed(self):
        with self.session() as session:
            for item in INSTRUMENTS.values():
                session.execute(insert(InstrumentRow).values(symbol=item.symbol, market=item.market,
                    broker=item.broker, enabled=True).on_conflict_do_nothing())
            for key, value in {"paused": False, "killed": False, "close_requested": False}.items():
                session.execute(insert(Control).values(key=key, value=value).on_conflict_do_nothing())

    def control(self, key: str, default=None):
        with self.session() as session:
            row = session.get(Control, key)
            return row.value if row else default

    def set_control(self, key: str, value):
        with self.session() as session:
            session.execute(insert(Control).values(key=key, value=value).on_conflict_do_update(
                index_elements=[Control.key], set_={"value": value}))

    def health(self, name: str, status: str, detail: str, now: datetime | None = None):
        with self.session() as session:
            session.merge(Health(name=name, status=status, detail=detail, timestamp=now or utcnow()))

    def store_candles(self, symbol: str, candles: pd.DataFrame, source: str):
        with self.session() as session:
            prior_sources = set(session.scalars(select(Candle.source).where(Candle.symbol == symbol).distinct()))
            if prior_sources and prior_sources != {source}:
                from papertrade.data import DataError
                raise DataError("Historical provider changed; use a separate database and retrain on that feed")
            for timestamp, row in candles.iterrows():
                values = {name: float(row[name]) for name in ("open", "high", "low", "close", "volume")}
                session.execute(insert(Candle).values(symbol=symbol, timestamp=timestamp.to_pydatetime(),
                    source=source, **values).on_conflict_do_nothing(index_elements=["symbol", "timestamp"]))

    def load_candles(self, symbol: str, limit: int | None = None) -> pd.DataFrame:
        with self.session() as session:
            query = select(Candle).where(Candle.symbol == symbol).order_by(Candle.timestamp.desc())
            if limit:
                query = query.limit(limit)
            rows = list(reversed(session.scalars(query).all()))
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                                index=pd.DatetimeIndex([], tz="UTC", name="timestamp"))
        return pd.DataFrame([{"timestamp": aware(r.timestamp), "open": r.open, "high": r.high,
                              "low": r.low, "close": r.close, "volume": r.volume} for r in rows]
                            ).set_index("timestamp")
