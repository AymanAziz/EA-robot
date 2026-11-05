"""A backup must include committed WAL state without copying credentials."""
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_backup_captures_wal_database_and_models_without_secrets(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    models = state / "models"
    models.mkdir()
    (models / "metadata.json").write_text('{"fixture": true}')
    (state / ".env").write_text("DO_NOT_BACKUP=test-value")
    connection = sqlite3.connect(state / "papertrade.db")
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE observations (value INTEGER)")
        connection.executemany("INSERT INTO observations VALUES (?)", [(7,), (11,)])
        connection.commit()
        script = Path(__file__).resolve().parents[1] / "scripts/backup.py"
        subprocess.run([sys.executable, str(script), "--state-dir", str(state),
                        "--destination", str(tmp_path / "backups")], check=True, capture_output=True)
        destinations = list((tmp_path / "backups").iterdir())
        assert len(destinations) == 1
        with sqlite3.connect(destinations[0] / "papertrade.db") as restored:
            assert restored.execute("SELECT value FROM observations ORDER BY value").fetchall() == [(7,), (11,)]
        assert (destinations[0] / "models/metadata.json").exists()
        assert not (destinations[0] / ".env").exists()
    finally:
        connection.close()
