from papertrade.config import Settings
from .alpaca import AlpacaPaper
from .oanda import OandaPractice
from .simulator import LocalPaperSimulator


def build_brokers(settings: Settings, *, quote_provider=None, data_provider=None):
    """Construct configured adapters without claiming a successful connection."""
    disabled, brokers = {}, {}
    if settings.execution == "simulator":
        brokers["simulator"] = LocalPaperSimulator(settings.state_dir / "simulator.db", settings.capital,
                                                  quote_provider=quote_provider, data_provider=data_provider)
        return brokers, disabled
    key = settings.alpaca_key.get_secret_value()
    secret = settings.alpaca_secret.get_secret_value()
    if key and secret:
        brokers["alpaca"] = AlpacaPaper(key, secret)
    else:
        disabled["alpaca"] = "Alpaca paper API key and secret are missing"
    token = settings.oanda_token.get_secret_value()
    account = settings.oanda_account_id.get_secret_value()
    if token and account:
        brokers["oanda"] = OandaPractice(token, account)
    else:
        disabled["oanda"] = "OANDA practice token and eligible USD v20 account are missing"
    return brokers, disabled
