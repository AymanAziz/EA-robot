"""Community Cloud entrypoint for the existing dashboard; no trading engine runs here."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from papertrade.dashboard import main  # noqa: E402

main(cloud=True)
