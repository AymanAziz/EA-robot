# GOLDNIX: access to a matching small-contract gold demo

Checked 2026-11-12 against official provider pages. This investigation submitted no registration forms, created no accounts, sent no messages, installed no software, deposited no funds and placed no orders. Previously frozen research files were left unchanged.

The target is an actual demo/practice gold contract whose minimum economic exposure is at most **0.023712 oz**, the conditional S11 sizing ceiling from [the local qualification calculation](../goldnix_round3/venue/QUALIFICATION.json). This is an exposure screen, not proof of sufficient costs, margin, independent evidence, or Step 6 approval.

## Finding

**JustMarkets Standard Cent is a more concrete demo-access lead than the earlier HFM lead:** its own account page expressly includes Standard Cent among the account types available in demo and lists MT4/MT5 support. However, the retrieved public gold specification does not establish the Cent account's minimum gold exposure. No account in this investigation satisfies the complete chain of matching demo type, verified gold exposure, eligible user access, and actual account export. No anonymous/no-registration route to such an account was established.

| Provider and type | Matching demo evidence | Gold sizing evidence | Status |
| --- | --- | --- | --- |
| JustMarkets Standard Cent | Explicitly included in official demo account list; MT4/MT5 | Cent-specific gold ounces not established | Strongest next account-access lead; qualify the actual symbol |
| HFM Cent | General MT4/MT5 demo available; Cent demo not established | 1 oz per lot × 0.01 lot = 0.01 oz | Small contract documented; matching demo access unresolved |
| FBS Oceania Cent | Explicit Demo Cent in PDS and `demoSecCent` registration link | Cent-specific gold ounces not established | Demo route exists, but Australian-resident restriction applies |
| Ultima Markets Cent | Retrieved public demo form lists Standard/STP and RAW/ECN, not Cent | Published Cent gold guide gives 1 oz × 0.01 lot = 0.01 oz | Small contract documented; matching demo not established |
| RoboForex ProCent | Current beginner guide offers Demo Pro and Demo ECN, describing ProCent separately as real | Gold card and general MT5 minimum differ; actual export needed | No matching ProCent demo established |
| Exness Standard Cent | Explicitly excluded from demo availability | No new sizing qualification attempted | Not a matching demo route |

## JustMarkets: concrete access path, unresolved gold contract

The official Standard account page lists Standard Cent with MT4/MT5, USC account units and a 0.01 cent-lot minimum. Its Demo FAQ explicitly includes Standard Cent. These facts establish that a matching account-type demo is advertised; they do not establish how many ounces its gold order represents. The provider also distinguishes simulated demo liquidity from live execution.
[Official account comparison and Demo FAQ](https://justmarkets.com/trading/standard-accounts).

The official instructions require a Personal Area login or signup. The documented path is **My accounts → Demo → Open new account → select platform and type → Try demo**. The user then selects currency, leverage, password and virtual balance. Funding is not part of this demo path. If USC is available, 2,000 USC represents the project's $20 budget; do not substitute a larger virtual balance to pass risk limits.
[Official demo setup](https://justmarkets.com/education/practice-account-opening).

The registration instructions request country of residence, active email and a password, and note that a trading account is created automatically. Thus even reaching the account-selection screen can involve personal registration; this research did not submit it. Existing account access avoids inventing identity information. No claim is made that document verification is or is not required for a particular user's demo eligibility.
[Official registration instructions](https://justmarkets.com/ru/landing/quick-start).

The public unsuffixed XAUUSD page shows contract size 100 and minimum volume 0.01 lot, with no Cent selection visible in the retrieved page. It even labels the profit currency XAU, which should not be silently corrected into an account specification. This generic web table cannot prove a 0.01 oz Cent gold minimum. The next decisive evidence is the actual Standard Cent demo symbol and hypothetical adverse-move P/L in account currency.
[Official XAUUSD specification](https://justmarkets.com/markets/commodities/xauusd).

### Public HTML and quote-interface follow-up

The XAUUSD HTML makes the table's units more explicit: its contract-size tooltip says **“Volume of the asset in one standard lot.”** The displayed value is 100. The header identifies the unsuffixed symbol `XAUUSD`; the retrieved HTML contains no `XAUUSDc` or Standard Cent entry. This does not establish which gold contract applies to Standard Cent or justify dividing its exposure by 100.
[Official XAUUSD HTML](https://justmarkets.com/markets/commodities/xauusd).

The commodity table has exactly three advertised account selector values: `standard`, `pro` and `raw-spread`. No Cent selector or Cent gold row appears in the retrieved HTML. Its linked table JavaScript implements those displayed tabs; it contains no account-specific fetch endpoint or Cent entry. Thus switching the public account table did not reveal the missing gold contract.
[Official commodities table](https://justmarkets.com/markets/commodities), [page-linked table script](https://justmarketsmy.net/app/themes/sage/public/js/blocks/table-instruments/app.1794224628384.js).

The gold page's linked script requests `app/v1/trading/symbol/info?symbols=XAUUSD` under the site's public REST root. The inspected consumer updates bid, daily change, sentiment and spread; it does not expose a Cent account selector or gold contract conversion. A read-only GET to that exact discovered URL returned HTTP **401 Unauthorized**. Research stopped at that response: no authentication, nonce replay, alternate-symbol enumeration or access workaround was attempted, and no API contract data was obtained.
[Page-linked quote script](https://justmarketsmy.net/app/themes/sage/public/js/pages/trading_instruments/app.1794224628384.js), [attempted quote URL](https://justmarketsmy.net/j-api/app/v1/trading/symbol/info?symbols=XAUUSD).

The separate quick-start page limits its 100-fold reduction claim to **some instruments** and lists Standard Cent under MT4 only. This differs from the current Standard account comparison's MT4/MT5 listing. Neither statement supplies gold-specific Cent ounces; platform availability must be confirmed in the actual eligible account selector. An MT4-only result would require adapting the current MT5 collection workflow. The `.com` pages redirected to provider-linked regional domains during retrieval; no account was opened on any domain.
[Official quick-start page](https://justmarkets.com/ru/landing/quick-start), [current account comparison](https://justmarkets.com/trading/standard-accounts).

## HFM: small exposure remains documented, Cent demo unresolved

The gold table's Cent column explicitly gives one ounce per lot and a 0.01-lot minimum, implying 0.01 oz. This remains a product specification, not an exported account property.
[Official HFM gold specification](https://www.hfm.com/int/en/trading-instruments/single-product?symbol=XAUUSD).

The official demo page supports MT4/MT5 and requires a myHF profile: new clients register first; existing clients log in. It does not establish that the available demo types include Cent. A generic HFM demo must not be treated as a Cent demo merely because Cent appears elsewhere in the navigation.
[Official HFM demo page](https://www.hfm.com/int/en/trading-accounts/demo-account).

## Other checks that prevent false matches

FBS Oceania's Cent page links directly to a demo registration route identifying `account=demoSecCent&type=demo`. Its PDS, revised 26 February 2024 and still served by the provider, explicitly lists Demo Cent. The Cent page lists MT5 and states that the website is not intended for residents outside Australia. The retrieved contract table did not expose a gold-specific Cent row, so neither exposure nor user eligibility is qualified. The existence of this page is not permission to select a different residence.
[Cent account and jurisdiction statement](https://fbsaustralia.com/en/trading/cent), [Demo Cent registration route](https://fbsaustralia.com/cabinet/registration?account=demoSecCent&lang=en&type=demo), [PDS, page 11](https://fbsaustralia.com/docs/en/fbs_oceania_pds_en.pdf).

Ultima's Cent STP product guide gives XAUUSD.sc a one-ounce contract and 0.01 minimum volume. The retrieved official demo form lists only Standard/STP and RAW/ECN account types, standard currency choices and virtual balances starting at $1,000. It requests email, name, country, phone and a password. Current regional redirects complicate retrieval. This is insufficient evidence for a matching $20-equivalent Cent demo; a menu link to Cent elsewhere on the site does not fill the gap.
[Official Cent STP guide, page 12](https://www.ultimamarkets.com/pdf/Product_Guide_Cent_STP_ENG.pdf), [Official demo form](https://www.ultimamarkets.com/nl/accounts/open-demo-account/).

RoboForex's beginner guide offers Demo Pro and Demo ECN on MT4/MT5, then describes ProCent as an additional real-account alternative. Its gold-specific ProCent card lists a 0.10 minimum, while its general Cent educational page lists a 0.01 MT5 minimum; the account's actual gold properties are required to resolve that difference. None of these pages establishes Demo ProCent access.
[Official account-opening guide](https://roboforex.com/beginners/start/beginner/), [ProCent XAUUSD card](https://roboforex.com/forex-trading/trading/specifications/card/pro-cent/xauusd/), [General Cent account explanation](https://roboforex.com/blog/education/what-are-forex-cent-accounts-needed-for/).

Exness's current account-creation guide explicitly excludes Standard Cent from demo availability. A Standard demo is not an adequate replacement for Standard Cent economics.
[Official Exness account-creation guide](https://get.exness.help/hc/en-us/articles/4408633634322-How-to-create-trading-accounts).

## Next evidence to collect

If an accessible Standard Cent demo is available, first collect its actual server, gold symbol, account currency, minimum volume/step, BUY and SELL hypothetical loss for a $1/oz adverse move, and margin. Convert cent-denominated money exactly once. Reject it if its actual minimum dollar exposure exceeds the sizing ceiling or margin exceeds the unchanged $20 budget. Broker-specific history and fees remain separate requirements; an account snapshot cannot manufacture them.

The user’s residency, existing provider account access and personal registration details are not available in this research. No replacement account has been connected. The existing MetaQuotes account and S11’s lack of independent validation therefore remain unresolved. This note supplies a concrete access lead and exclusions; it does not change Step 6 to PASS.
