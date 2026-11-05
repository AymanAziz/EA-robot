import json
import logging
import re
from datetime import datetime, timezone

from papertrade.config import Settings


def redact(value: str, settings: Settings | None = None) -> str:
    if settings:
        for name in ("alpaca_key", "alpaca_secret", "oanda_token", "oanda_account_id",
                     "admin_password_hash", "api_token", "watchdog_url", "groq_api_key", "hermes_api_key"):
            secret = getattr(settings, name).get_secret_value()
            if secret:
                value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1[REDACTED]", value)
    return re.sub(r"(?i)((?:password|secret|token|api_key)\s*[=:]\s*)[^\s,]+", r"\1[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def format(self, record):
        return json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname,
                           "logger": record.name, "message": redact(record.getMessage(), self.settings)})


def configure_logging(settings: Settings):
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(settings))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.captureWarnings(True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
