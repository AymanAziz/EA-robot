# ATR parity result

- Run date: 2026-11-10
- Platform/server: MT5, MetaQuotes-Demo
- Symbol/timeframe: XAUUSD H1
- Export: 500 closed bars, including 300 warm-up and 200 comparison bars
- Export SHA-256: `5de872bdce17cac121854c68eaab4999ca5e3e00150657e5150854266595bc23`
- Server-time conversion: `Europe/Helsinki` EET/EEST table (UTC+2 winter,
  UTC+3 summer), supported by MetaQuotes' MQL5 forum statement:
  <https://www.mql5.com/en/forum/399066/page5>
- Converted UTC range: 2026-10-08 11:00 through 2026-11-10 00:00
- Historical offsets represented: UTC+3 through the pre-transition rows and
  UTC+2 from the first available bar after the European clock change
- Converted UTC grid: unique, increasing, exactly on the hour
- Simple ATR(14) maximum absolute difference: `0.000000004286` USD
- Wilder ATR(14) maximum absolute difference: `8.260764312148` USD
- Required tolerance: strictly less than `0.01` USD
- Selected method: simple average of true range
- Result: PASS

The exported price rows are parity evidence only. They are not part of the
strategy dataset and must not be used to evaluate signals or the holdout.
