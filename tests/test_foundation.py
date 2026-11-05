import pytest
from pydantic import ValidationError
from sqlalchemy import select

from papertrade.config import Settings
from papertrade.domain import INSTRUMENTS
from papertrade.models import InstrumentRow


def test_live_mode_cannot_be_configured():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mode="live")


def test_database_initialization_is_idempotent_and_controls_persist(db):
    db.initialize()
    with db.session() as session:
        assert {x.symbol for x in session.scalars(select(InstrumentRow))} == set(INSTRUMENTS)
    db.set_control("killed", True)
    db.initialize()
    assert db.control("killed") is True
