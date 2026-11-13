# Small gold contracts for the $20 Goldnix research account

Checked 2026-11-12 against first-party product documentation. This investigation
created no accounts, made no deposits, sent no messages to brokers and placed
no orders. The current terminal remains the existing MetaQuotes demo.

## Result

There is a concrete published product route to **0.01 oz minimum gold exposure**:
HFM's international XAUUSD specification explicitly lists a 1 oz contract per
Cent lot and a 0.01-lot minimum. This is gold-specific evidence, not a conversion
from a generic FX cent-lot description. However, no HFM account has been
connected or qualified here, and a Cent demo account was not established from
the public documentation. The result is **documented candidate, account and
execution evidence pending**, not a broker-approved Step 6 pass.
[HFM XAUUSD contract specification](https://www.hfm.com/int/en/trading-instruments/single-product?symbol=XAUUSD).

## Exact published product facts

The HFM gold instrument table's **CENT** column gives:

| Field | Published value |
| --- | ---: |
| Gold per 1 lot | 1 ounce |
| Minimum lot | 0.01 |
| Minimum price increment | 0.01 |
| Tick value per 1 lot | USD 0.01 |
| Spread advertised as low as | 0.32 |
| Margin requirement shown | 0.05% |

Arithmetic inference: `1 oz/lot × 0.01 lot = 0.01 oz`, hence USD 0.01 per
USD 1/oz price move, before costs. The listed margin percentage and spread
are public conditions, not observations of an actual account or a historical
cost series. The page has regional variants; the intended account/server
must resolve any difference.
[HFM gold table](https://www.hfm.com/int/en/trading-instruments/single-product?symbol=XAUUSD).

The Cent account page separately lists MT5 support, currency USC, a 0.01-lot
volume increment, no commission, no minimum opening deposit, and the
`XAUUSDc` symbol suffix. Its generic 1,000-unit lot description should not be
used for the gold calculation above.
[HFM Cent account](https://www.hfm.com/int/en/trading-accounts/cent-account).

HFM's public demo page offers free MT4/MT5 demos through its client area. It
does **not** say that its Cent contract is available in demo. General demo
availability therefore cannot establish a no-deposit Cent demo route. The
next account-specific check is whether the available demo configuration
actually exposes `XAUUSDc` with the documented economic exposure.
[HFM demo accounts](https://www.hfm.com/int/en/trading-accounts/demo-account).

Swap-free wording is conditional. HFM's swap page limits the feature to
selected accounts/instruments and a number of days; it also describes
possible carry charges in some circumstances. The linked regional rollover
policy could not be retrieved successfully in this check. No unlimited
zero-financing assumption is justified from the retrieved pages.
[HFM swap-free terms overview](https://www.hfm.com/int/en/funding/swap-free-trading).

## Other lead: Exness

Exness lists MT5 and `XAUUSDc` for Standard Cent. Its cent-lot account page
does not provide an equally explicit gold-ounces table, so it was not used to
certify a gold exposure value here.
[Exness Standard Cent](https://get.exness.help/hc/en-us/articles/17537782786588-Standard-Cent-account).

The official account-creation guide explicitly excludes Standard Cent from
demo availability. A free Standard demo is therefore not evidence of Standard
Cent execution or costs. No account opening or funding is proposed by this
research result.
[Exness account creation and demo exception](https://get.exness.help/hc/en-us/articles/4408633634322-How-to-create-trading-accounts).

## How to qualify the candidate without placing orders

The existing [ExportQualification.mq5](../goldnix_checks/ExportQualification.mq5)
already records minimum volume, volume step, contract size, tick value,
quotes, account currency and hypothetical profit/margin. It makes no
`OrderSend` call. Retain that read-only workflow on an already available
candidate account, with automated trading disabled.

Read the actual server's symbol identity and currency fields, volume limits,
tick size/value, and contract size. These are available through MT5 symbol
properties; a display name containing GOLD is insufficient because it can
refer to an equity.
[Official MT5 symbol properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants).

The strongest exposure check is the hypothetical loss from a USD 1/oz adverse
move at the minimum valid volume. `OrderCalcProfit` returns account currency,
so a USC result must be divided by 100 before comparing with USD risk limits.
Confirm a loss no greater than USD 0.01 for this specific target. Also check
both trade directions instead of assuming their economics are identical.
[OrderCalcProfit](https://www.mql5.com/en/docs/trading/ordercalcprofit).

Use `OrderCalcMargin` in both directions and compare the converted maximum
against the actual USD free margin. It reports hypothetical margin in account
currency and does not incorporate current pending orders or positions. A
printed product percentage cannot replace this check.
[OrderCalcMargin](https://www.mql5.com/en/docs/trading/ordercalcmargin).

Code review caveat: the current exporter skips any instrument whose
`SYMBOL_CURRENCY_PROFIT` is not exactly `USD`. If a candidate reports a cent
profit currency, it would be omitted even though the Python evaluator accepts
USC account units. That is a conditional integration limitation, not an
observation of how HFM encodes its symbols. Inspect/report the actual currency
fields before interpreting an empty export; do not broaden currency acceptance
without an explicit conversion rule and tests. The current exporter also does
not capture commissions, swap policy or a bid/ask history.

For venue-specific costs, retrieve available bid/ask ticks and construct bars
from that source. `CopyTicksRange` supplies a bounded tick history; its return
count, errors and actual temporal coverage must be recorded. It does not
promise a complete 2005–2025 archive. H1 bid bars plus one spread snapshot do
not reconstruct actual historical ask OHLC or intrabar spreads.
[CopyTicksRange](https://www.mql5.com/en/docs/series/copyticksrange).

## Effect on the research result

Changing from 1 oz to 0.01 oz scales dollar P/L by 0.01 only if trade outcomes
and proportional costs are unchanged. This conditional calculation can help
screen G7, but it leaves R-based profitability, consistency and basket count
unchanged. Actual venue costs can also change eligibility and fills, so the
final evaluation must use that venue's evidence rather than a fixed spread
discount. The existing corrected Step 6 and completed Step 7 artifacts remain
the authoritative results for V1 and V2.

The remaining evidence is a matching account/server export, actual historical
bid/ask costs and applicable fee terms, verified access to the account type,
and a revised validation protocol. No source inspected here demonstrates that
the user's account is eligible for the product or that all Step 6 gates pass.

## Follow-up on 2026-11-12: exposure below 0.01 oz

The subsequent strategy screen raised a stricter sizing question: is there
primary product evidence for an MT5 gold minimum no greater than **0.001 oz**?
This follow-up searched cent, micro and nano gold offerings. **No credible
official product specification establishing that minimum was found in this
search.** This is a bounded research result, not proof that such a product
cannot exist.

Two additional first-party checks illustrate why an account label is not
enough:

| Product checked | Official gold sizing evidence | Meets 0.001 oz target? |
| --- | --- | --- |
| Titan FX Zero Micro | Contract size 10; minimum 0.01 lot, implying 0.1 oz | No |
| Born2trade Nano (Cent) | Explicitly 1 oz per lot and 0.01 oz minimum trade | No |

Titan FX explicitly offers a Micro demo account with virtual funds, but that
does not solve the smaller-exposure requirement. Its published gold contract
is larger than HFM Cent's documented minimum.
[Titan FX Micro specification and demo FAQ](https://www.titanfx.com/trading-accounts/zero-micro).

Born2trade's own gold guide specifies MT5 and the Nano contract calculation
directly. Its use of the word Nano therefore does not imply a thousandth of
an ounce. The retrieved guide encourages demos generally but does not verify
a matching Nano demo configuration. Account-specific access, spreads and
financing remain unqualified here as well.
[Born2trade gold specification explanation](https://born2trade.com/news-articles/how-to-trade-gold).

Search hits using `0.001` often referred to price increments, dollar tick
values, or fractions of a **100 oz** standard lot. None of those alone proves
0.001 oz minimum exposure. A different account balance display unit also does
not justify multiplying a verified economic exposure by another cent factor.

HFM's 0.01 oz product evidence remains the smallest direct gold-specific
specification established in this investigation. There is still no connected,
account-qualified alternative venue, and no authority to substitute 0.001 oz
as an executable size in a final approval. A hypothetical size can be reported
as a sensitivity only. No account signup, deposit, trade, or communication
with a broker was performed during this follow-up.
