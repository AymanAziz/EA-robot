import pytest

from papertrade.config import Settings
from papertrade.db import Database


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, state_dir=tmp_path, models_dir=tmp_path / "models",
                    database_url=f"sqlite:///{tmp_path / 'test.db'}", strategy_execution_enabled=True)


@pytest.fixture
def db(settings):
    result = Database(settings)
    result.initialize()
    yield result
    result.engine.dispose()
