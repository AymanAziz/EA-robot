# Paper broker interfaces and operational limits

The adapters use `httpx` against fixed HTTPS origins with redirects disabled:
`https://paper-api.alpaca.markets`, `https://data.alpaca.markets`, and
`https://api-fxpractice.oanda.com`. There is no live origin configuration or
withdrawal interface. Supplying live credentials cannot change these origins.
POST/PUT/DELETE requests are never automatically retried. A timeout, malformed
submission response, or server error produces an uncertain state which requires
lookup by deterministic client order identifier before any further action.

Official documentation consulted during implementation (2026-11-05):

- [Alpaca order workflow](https://docs.alpaca.markets/us/docs/working-with-orders):
  client identifiers and order lifecycle, equity bracket orders, supported
  execution combinations. Whole-share SPY/QQQ opening orders attach a stop and
  target. Crypto does not support these bracket combinations and requires the
  application’s explicitly enabled additional monitoring gate.
  Capability alone is not proof of current coverage: the minute monitor checks
  actual active stop/target orders against the held quantity. Partially filled
  bracket entries have inactive exit legs until entry completion, so the monitor
  cancels the remainder and closes the exposed partial holding. Missing or
  manually canceled protection also triggers a monitored exit attempt.
- [Alpaca asset capabilities](https://docs.alpaca.markets/us/reference/get-v2-assets-symbol_or_asset_id):
  each submission verifies current tradability and reported minimum size and
  quantity increment. The configured risk quantity is never rounded upward to
  satisfy a provider minimum. If the configured quantity increment is finer
  than the provider’s current increment, the order is rejected safely; update
  the instrument configuration and rerun relevant validation before enabling it.
  The single-asset lookup uses the documented legacy `BTCUSD`/`ETHUSD` symbol;
  orders and market data use slash-separated pairs.
- [Alpaca lookup by client identifier](https://docs.alpaca.markets/us/reference/getorderbyclientorderid):
  reconciliation uses the paper `/v2/orders:by_client_order_id` endpoint.
- [Alpaca crypto historical bars](https://docs.alpaca.markets/us/reference/cryptobars-1)
  and [stock bars](https://docs.alpaca.markets/us/reference/stockbars): paginated
  15-minute bars; stock data requests explicitly use the free IEX feed. IEX does
  not represent the consolidated US market, so volume and spread estimates are
  feed specific. Raw stock prices are used; corporate actions need research
  handling before long-horizon stock comparisons are interpreted.
- [Alpaca account activities](https://docs.alpaca.markets/us/docs/account-activities)
  and [crypto fees](https://docs.alpaca.markets/us/docs/crypto-fees): fills are
  actual execution activities, paginated without silent truncation. A missing
  commission is provisional (`fees_final=False`), not evidence of a zero fee.
  Crypto fees can appear later as separate `CFEE`/`FEE` activity without an order
  identifier. This release does not allocate those fees across individual fills;
  account cash/equity remain authoritative and research subtracts estimated costs.
- [OANDA practice development guide](https://developer.oanda.com/rest-live-v20/development-guide/):
  practice-only REST endpoint and persistent connections.
- [OANDA orders](https://developer.oanda.com/rest-live-v20/order-ep/)
  and [order definitions](https://developer.oanda.com/rest-live-v20/order-df/):
  opening longs use `OPEN_ONLY` market/FOK orders with `stopLossOnFill` and
  `takeProfitOnFill`; sells use `REDUCE_ONLY` so they cannot open shorts. Client
  extensions enable lookup using `@client-id`. Stops are not guaranteed fills.
- [OANDA account definitions](https://developer.oanda.com/rest-live-v20/account-df/):
  the accounts list identifies MT4-linked accounts. This implementation rejects
  those accounts because the required client extensions cannot be used safely.
  USD-denominated, accessible, eligible v20 practice accounts are required.
- [OANDA instrument candles](https://developer.oanda.com/rest-live-v20/instrument-ep/),
  [pricing](https://developer.oanda.com/rest-live-v20/pricing-ep/), and
  [transactions](https://developer.oanda.com/rest-live-v20/transaction-ep/):
  completed M15 midpoint candles, executable bid/ask quotes with tradeability,
  instrument precision/minimum quantities, and paginated execution transactions.
  Forex candle volume is tick count, not centralized traded volume. Fill
  commission and realized P/L are recorded from execution transactions; financing
  is reflected in account balance/NAV and is not assigned to individual fills.

## Local simulator

The fallback is a distinct local paper ledger at `PT_STATE_DIR/simulator.db`, not
a broker-hosted account. It uses SQLite WAL, a unique client order identifier,
and one immediate transaction for cash, position, order, and fill changes. New
market orders fill only against real supplied fresh bid/ask quotes, with adverse
slippage and instrument-specific estimated fees. It never creates random quotes
or fills at a stale reference candle price. Missing quotes disable execution.
Partial fills, order book depth, corporate actions, dividends, financing and
exchange outages are not simulated. No leverage, shorts, or position additions
are allowed. Whole-share increments apply to equity simulation.

Simulator stop/target protection is software emulation. The dedicated monitor
must observe current quotes; stops fill at the next observed executable price
with adverse slippage, so gaps can exceed the planned risk. Host downtime stops
monitoring. Configure an external heartbeat to detect those outages; it cannot
execute orders during downtime. Alpaca crypto additionally requires a recently
acknowledged external heartbeat before any new unhosted position is approved.

Each local ledger has a persistent random account identity. A SHA-256 digest is
exposed to the main application, which binds historical state to that account.
Broker-hosted account identifiers are likewise hashed. Changing credentials to a
different account or resetting a simulator ledger requires fresh application
state; the platform must not join unrelated account balances and performance.
Older local simulator ledgers migrate the identity column transactionally while
preserving cash and positions, with schema version recorded in SQLite.

## Verification

`pytest tests/test_brokers.py` uses mocked HTTP responses and actual temporary
SQLite ledgers. It does not establish a successful external broker connection.

`PT_RUN_PAPER_INTEGRATION=true pytest tests/integration/test_paper_brokers.py -m integration`
explicitly opts into read-only real paper account, position, quote, and historical
data checks. Missing credentials skip the relevant checks. Real order/fill
verification requires eligible paper accounts, market availability and the
normal risk-approved engine path with an explicitly validated/promoted model.
Neither integration-test success nor a local simulated fill proves a profitable
strategy or guarantees broker execution.
