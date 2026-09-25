# Audit of the 2024 prototype

This is the audit of the April 2024 prototype that the rebuild replaces: the QuantConnect
algorithm [received/main.py](../received/main.py) and the yfinance valuation script
[received/dcf_valuation_yfinance.py](../received/dcf_valuation_yfinance.py). Both files are
verbatim; line links below point into them. Dollar amounts are written as USD because GitHub reads
a bare dollar sign as the start of a formula.

## Sources and method

- Code: the two files above. `received/main.py` is byte-identical to the `main.py` that
  QuantConnect stored with the prototype's final backtest (SHA-256 `60ac793e...`, compared against
  the backtest's code snapshot on 25 September 2026).
- Backtest: QuantConnect project 17552945, backtest `e472f920b9bb72dbb8024af7d95f1c04`
  ("Geeky Sky Blue Caterpillar", created 4 April 2024 17:28:14), exported through QuantConnect's
  web API on 25 September 2026 with all 363 orders and the headline statistics. Published as
  [`results/prototype_2023/`](../results/prototype_2023/) (`statistics.json`, `orders.csv`) and
  as the raw export [`results/raw/dcf__prototype_2023.json.gz`](../results/raw/dcf__prototype_2023.json.gz).
- Reference: backtest `d611b8a8fb19c48188e250a4c75a5297` in project 36922759, run on 24 September
  2026 for this audit. It buys the prototype's seven stocks in equal weights on the first day of
  2023 and holds them to the end of the year. Code and statistics:
  [`results/reference/basket_2023/`](../results/reference/basket_2023/), seven orders, nothing else.
- Run history: QuantConnect's list of all 40 backtests in project 17552945, with each run's
  status, first error line and headline statistics, exported through its web API on 25
  September 2026 ([`results/raw/backtest_lists.json.gz`](../results/raw/backtest_lists.json.gz),
  one row per backtest in
  [`results/checks/backtest_lists.csv`](../results/checks/backtest_lists.csv);
  [appendix A](#appendix-a-the-40-backtests-of-3-and-4-april-2024)).
- A first review of the same code, written on 22 September 2026, was the starting point. Every
  point below was checked again against the code and the exports; where the check disagreed with
  the first review, the correction is listed in [corrections](#corrections-to-the-first-review).

The yfinance script was not re-run. yfinance serves only the most recent annual statements, so
running it today would not reproduce the April 2024 inputs. The audit therefore works from the code
and from what the backtest did with the fair values it was given.

## What the prototype does

1. [dcf_valuation_yfinance.py](../received/dcf_valuation_yfinance.py) is run by hand, one ticker at
   a time ([L241](../received/dcf_valuation_yfinance.py#L241) sets `ticker = 'NKE'` and lists the
   other six in a comment). For the chosen year
   ([L242](../received/dcf_valuation_yfinance.py#L242), `year = 2023`) it computes a market value
   of equity, a WACC, capex and working-capital ratios, a five-year EBITDA forecast, a DCF value
   with an exit multiple of 10, and prints a fair price per share
   ([L260-L261](../received/dcf_valuation_yfinance.py#L260-L261)).
2. The seven printed fair prices are pasted into the algorithm as constants
   ([main.py L22-L32](../received/main.py#L22-L32)).
3. The algorithm trades those seven stocks on daily bars through calendar 2023
   ([L7-L8](../received/main.py#L7-L8)): buy 14% of equity when a rule on the close and the fair
   value holds, sell the whole position when another rule holds
   ([L50-L55](../received/main.py#L50-L55)).

The deck's slide 3 describes the same pipeline ("Algorithm takes data about companies from Yahoo
finance API ... This information goes to QC"), and slide 8 says the process is still manual.

## Headline numbers of the final run

From the export of backtest `e472f920`
([`results/prototype_2023/statistics.json`](../results/prototype_2023/statistics.json)):

| Statistic | Value |
|---|---|
| Net profit | +27.233% |
| Compounding annual return | 27.402% |
| Sharpe ratio | 1.878 |
| Probabilistic Sharpe ratio | 96.331% |
| Maximum drawdown | 2.6% |
| Beta to SPY | 0.386 |
| Annual standard deviation | 0.071 |
| Win rate | 58% |
| Total orders | 363 (183 buys, 180 sells) |
| Total fees | USD 363.04 |
| Portfolio turnover | 13.76% |
| End equity | USD 127,232.87 |

The results slide of the deck ([received/backtest-2023.png](../received/backtest-2023.png)) shows
QuantConnect's header row, not this table: its equity (USD 127,232.87), fees (USD 363.04), PSR
(96.331%) and return (27.23 %, the net profit row rounded) match the rows above. The other rows
are not on the slide.

## Findings

### 1. Inverted, overlapping trading bands

The rules, with $P$ the daily close and $F$ the pasted fair value:

- Buy, if not invested: `price * 0.95 < fair_value` ([L50](../received/main.py#L50))
- Sell, if invested: `price * 1.05 > fair_value` ([L54](../received/main.py#L54))

Solved for the price:

$$
\text{buy} \iff 0.95P < F \iff P < \frac{F}{0.95} \approx 1.0526F
$$

$$
\text{sell} \iff 1.05P > F \iff P > \frac{F}{1.05} \approx 0.9524F
$$

The buy threshold sits above the sell threshold. Every close in the interval
$0.9524F < P < 1.0526F$ satisfies both rules, so a stock in that range is bought on one bar and
sold on the next, then bought again, for as long as the price stays there. A stock bought below
$0.9524F$ is held only until it rises to 95% of fair value, and is sold before it reaches fair value.
The rule that was intended is a band with the buy threshold below the sell threshold:
$P < 0.95F$ to buy and $P > 1.05F$ to sell.

Evidence from the 363 orders (all market-on-open orders, filled at the next open after the signal
close, at QuantConnect's adjusted prices):

| Symbol | Orders | Buys | Sells | Lowest fill / F | Highest fill / F |
|---|---|---|---|---|---|
| UNH | 148 | 74 | 74 | 0.958 | 1.076 |
| AVGO | 94 | 47 | 47 | 0.627 | 1.052 |
| NKE | 77 | 39 | 38 | 0.947 | 1.076 |
| AAPL | 42 | 21 | 21 | 0.783 | 1.055 |
| NVO | 1 | 1 | 0 | 0.228 | 0.228 |
| XOM | 1 | 1 | 0 | 0.129 | 0.129 |
| PG | 0 | 0 | 0 | | |

- 109 of the 183 buys filled above the stock's own fair value.
- 61 of the 180 sells, all tagged `Reached fair value` by [L55](../received/main.py#L55), filled
  below it.
- 165 of the 181 round trips in [`trades.csv`](../results/prototype_2023/trades.csv) ended at
  the next weekday's fill or sooner. There is one more round trip than sells because NKE was
  bought a second time, for one share, while still held, and the next sale closed both lots.
- UNH alone produced 148 orders with every fill between 0.958 and 1.076 times its fair value, inside
  or next to the overlap.

The 363 orders on six traded names in 250 trading days are the churn the overlap produces.
Each order paid the USD 1 minimum fee or close to it, which is where the USD 363.04 in fees comes
from.

### 2. Look-ahead in the fair values

The fair values used to trade 2023 were computed from information that did not exist when the
backtest's January 2023 trades were made, the last close of 2023 and the fiscal-2023
statements:

- Market value of equity: the close in the window 31 December 2023 to 1 January 2024
  ([L26](../received/dcf_valuation_yfinance.py#L26)). 31 December 2023 was a Sunday, so the
  fallback on [L30-L31](../received/dcf_valuation_yfinance.py#L30-L31) takes the last close of
  2023. It sets the equity weight in the WACC ([L81-L82](../received/dcf_valuation_yfinance.py#L81-L82)).
- Tax rate, cost of debt and debt: the statements for the year 2023
  ([L54-L76](../received/dcf_valuation_yfinance.py#L54-L76)).
- Capex and working-capital ratios: 2023 ([L245](../received/dcf_valuation_yfinance.py#L245),
  through [L124-L126](../received/dcf_valuation_yfinance.py#L124-L126) and
  [L210-L211](../received/dcf_valuation_yfinance.py#L210-L211)).
- Net debt and diluted shares for the per-share value: 2023
  ([L248-L249](../received/dcf_valuation_yfinance.py#L248-L249),
  [L127-L128](../received/dcf_valuation_yfinance.py#L127-L128)).

`financials.loc['2023']` selects the annual statements whose period ends in 2023. For the three
companies with a December year end (UNH, XOM, NVO) those statements were published in early
2024. For the other four the fiscal year ended between May and October 2023 (NKE in May, PG in
June, AAPL in September, AVGO at the end of October), and the statements were published between
July and December 2023. The fair values were in the algorithm by 3 April 2024 (the first
completed backtest), and the deck was created on 4 April 2024. The 2023 backtest therefore
traded from January 2023 on fair values that already contained fiscal-2023 results and the last
close of 2023. Any return it reports is conditional on information nobody had when its trading
began.

The dates inside the valuation are also inconsistent with each other. The forecast starts from
fiscal 2022 EBITDA (next finding) and discounts 2023 as if it were the first future year, while the
market value, WACC, ratios and share count come from 2023.

### 3. Linear EBITDA extrapolation

[L246](../received/dcf_valuation_yfinance.py#L246) calls `create_forecasts(ticker, 2020, 2023)`.
The loop `range(start_year, end_year)` on [L154](../received/dcf_valuation_yfinance.py#L154) visits
2020, 2021 and 2022, so the forecast uses two year-on-year changes and the last known EBITDA is
2022's:

$$
\bar\Delta = \frac{(E_{2021} - E_{2020}) + (E_{2022} - E_{2021})}{2} = \frac{E_{2022} - E_{2020}}{2}
$$

$$
\hat E_{2022+k} = E_{2022} + k\,\bar\Delta, \qquad k = 1, \dots, 5
$$

([L162-L170](../received/dcf_valuation_yfinance.py#L162-L170),
[L178-L181](../received/dcf_valuation_yfinance.py#L178-L181)). The terminal value is
$10 \times \hat E_{2027}$ ([L230](../received/dcf_valuation_yfinance.py#L230),
[L247](../received/dcf_valuation_yfinance.py#L247)). For a company whose EBITDA collapsed in 2020
and recovered by 2022, the recovery is extended as a permanent trend: year five carries
$E_{2022} + 2.5\,(E_{2022} - E_{2020})$, and ten times that dominates the valuation.

The export shows the two names where the fair value was far from any traded price:

| Symbol | Pasted fair value | Only fill (first bar of 2023) | Fair value / fill | Sell rule needs a close above |
|---|---|---|---|---|
| XOM | 776.8739526 | 100.41 (136 shares) | 7.7 | 739.88 |
| NVO | 297.8334194 | 67.90 (208 shares) | 4.4 | 283.65 |

Both were bought on the first bar and never sold. They are the only positions open at the end of
the run; QuantConnect reports holdings of USD 34,835.56 on the final day. Fill prices are
QuantConnect's adjusted prices, restated for later splits and dividends, so they differ from the
prices quoted at the time, but no price adjustment explains a factor of 4 to 8. The audit could not recompute the
inputs behind these two fair values (see [sources](#sources-and-method)); the size of the gap and the
structure of the forecast are consistent with the extrapolation above, and nothing else in the
script can produce a factor of that size.

### 4. Capital-expenditure sign

yfinance reports `Capital Expenditure` as a negative cash flow. The script reads it as is
([L125](../received/dcf_valuation_yfinance.py#L125)), divides by EBITDA
([L210](../received/dcf_valuation_yfinance.py#L210)) and subtracts the ratio
([L223](../received/dcf_valuation_yfinance.py#L223)). With capex $K < 0$:

$$
\text{FCF} = E\left(1 - \frac{K}{E} - t - \frac{\Delta W}{E}\right) = E + \lvert K \rvert - tE - \Delta W
$$

Capital expenditure is added to free cash flow instead of deducted. For a capital-intensive
company this raises every forecast year's cash flow by twice its capex ratio times EBITDA. The
working-capital term has the same structure: `Change In Working Capital` on a cash-flow
statement is positive when working capital releases cash, and subtracting it turns a cash inflow
into a deduction. The rebuild uses $\lvert K \rvert$ and $-\Delta W$ (see
[methodology](methodology.md#cash-flow-ratios)).

### 5. Constant 8% cost of equity

[L80](../received/dcf_valuation_yfinance.py#L80) sets `cost_of_equity = 0.08` with the comment
"Assuming an 8% cost of equity as a placeholder". The WACC on
[L82](../received/dcf_valuation_yfinance.py#L82) is

$$
\text{WACC} = \frac{M}{M + D}\,0.08 + \frac{D}{M + D}\,r_d\,(1 - t)
$$

with $M$ the year-end 2023 market value of equity, $D$ total debt and $r_d$ the cost of debt,

so for the large, equity-financed companies in the list the discount rate is close to 8% for all
of them, and the ranking between them is decided by the forecast, not by risk. Two smaller
defects feed the same formula: the cost of debt is interest expense over total debt with no bounds
([L66](../received/dcf_valuation_yfinance.py#L66)), and the tax rate falls to 0 when pretax income
is not positive ([L73-L76](../received/dcf_valuation_yfinance.py#L73-L76)). The rebuild keeps the
cost of equity as a single constant, now a named parameter, and reports what moving it does
([limitations](limitations.md#one-cost-of-equity-constant)).

### 6. Hand-picked seven names

The universe is seven tickers written into the code
([L12](../received/main.py#L12)): AAPL, AVGO, NVO, XOM, UNH, PG, NKE. Neither the code nor the deck
gives a rule for choosing them, and the list was fixed in April 2024, after the backtest year had
ended.

The reference basket answers what the choice alone was worth. Buying the seven in equal weights on
the first day of 2023 and doing nothing else:

| | Prototype (e472f920) | Equal-weight basket, buy and hold (d611b8a8) |
|---|---|---|
| Net profit | +27.233% | +28.615% |
| Sharpe ratio | 1.878 | 1.312 |
| Maximum drawdown | 2.6% | 4.8% |
| Beta to SPY | 0.386 | 0.795 |
| Annual standard deviation | 0.071 | 0.112 |
| Orders | 363 | 7 |
| Fees | USD 363.04 | USD 7.50 |

The basket made more money than the strategy. The prototype's higher Sharpe ratio and lower beta
come from lower volatility, and the lower volatility comes from holding less: PG never met the buy
rule (its closes stayed above $F / 0.95$ all year, so it has no orders), which caps the book at
six positions of 14%, or 84% of equity, and the churning names spent many days in cash between
round trips. Over calendar 2023 SPY returned +26.18% on QuantConnect's benchmark series (the
base run's samples at the last closes of 2022 and 2023,
[`yearly_returns.csv`](../results/base_2016_2024/yearly_returns.csv)); the prototype run's own
benchmark series stops at a sample on 27 December, where it stands at +26.39%.

### 7. Forty backtests in two days

Project 17552945 holds 40 backtests, 31 on 3 April 2024 and 9 on 4 April 2024
([appendix A](#appendix-a-the-40-backtests-of-3-and-4-april-2024)). The first 14 all ended in
errors ([`backtest_lists.csv`](../results/checks/backtest_lists.csv), column `error`). Eleven
stopped at initialisation, ten of them while loading the fair values: no module `fairdata`
(1 run), an undefined `file_path` (2), no file `fair_data.txt` (5) and a table without the
expected `Symbol` or `Ticker` column (2); the eleventh on an undefined name `symbol` when the
algorithm module loaded. Three stopped during the backtest: two on
`'NoneType' object has no attribute 'Price'` after 32 orders each, one on
`'TradeBar' object has no attribute 'HasData'`. That fits the deck's account of fair values
moving from the script into QuantConnect, and the final code, which pastes them as constants,
still imports `pandas` and `os` without using them ([L2-L3](../received/main.py#L2-L3)). One more run failed
later (run 19, at initialisation, on a missing `benchmarkTicker` attribute), and 25 completed.
Their net profits range from +2.967% to +27.233%, and the published run is the highest of the
25. Runs 38, 39 and 40 all report +27.233%, a Sharpe ratio of 1.878, 363 orders and a 2.6%
drawdown; only run 40 was exported, so the list does not show whether the three ran the same
code.

QuantConnect's own research guide flags the project: the results screenshot in the deck shows
"Possible Overfitting" in its Research Guide panel
([received/backtest-2023.png](../received/backtest-2023.png)). Choosing the best of 25 variants of a
seven-stock, one-year backtest leaves no out-of-sample evidence at all. In the rebuild the base
run is the earliest of the nine published runs and all eight sensitivity runs are published
([results/sensitivity/summary.csv](../results/sensitivity/summary.csv)). The rebuild project's
own backtest list holds ten backtests, these nine and the re-run of the refactored code, and
all ten are in [`results/runs.csv`](../results/runs.csv); no other run was made in that project
([`backtest_lists.csv`](../results/checks/backtest_lists.csv)).

### Smaller points

- Tax is charged on EBITDA ([L223](../received/dcf_valuation_yfinance.py#L223)) rather than on
  operating profit, which ignores the depreciation tax shield. The rebuild keeps this
  simplification and says so.
- The exit multiple is fixed at 10 for every company ([L247](../received/dcf_valuation_yfinance.py#L247)).
- `calculate_wacc` returns a string when the year is missing
  ([L87](../received/dcf_valuation_yfinance.py#L87)), which the caller then tries to unpack into
  two numbers.
- `create_forecasts` calls `calculate_cap` and `calculate_wacc` for every year
  ([L155-L157](../received/dcf_valuation_yfinance.py#L155-L157)) and uses neither result.
- Position size is a constant 14% ([L51](../received/main.py#L51)) whatever the gap to fair value.

## What the 27.233% consists of

Most of it is the stock list. The basket of the same seven names, bought once, returned +28.615%.
The trading rule then removed PG, held XOM and NVO all year because their fair values were
unreachable, and churned AAPL, AVGO, NKE and UNH in and out around fair values that already
contained fiscal-2023 results. None of the return can be attributed to the valuation model.

## Corrections to the first review

The review of 22 September 2026 was re-checked point by point. Everything in the findings above
stands; these statements in it were wrong or imprecise:

| First review said | Export or code shows |
|---|---|
| "Seven × 14% is 98% invested from day one when all seven qualify." | PG never qualified and has no orders, so the book never exceeded six positions (84%). Four names were bought on the first bar of the year (AAPL, AVGO, NVO, XOM), UNH two days later and NKE not until May. |
| After the fair values were pasted in, results "ranged from 9% to 25.6%". | The 25 completed runs range from +2.967% to +27.233%. |
| NVO's fair value against "roughly USD 70 to 100". | NVO's only fill is 67.90, adjusted. |
| SPY returned "about 26% in 2023 (from memory)". | +26.18% for calendar 2023 on QuantConnect's benchmark series (+26.39% to the prototype run's last sample, on 27 December). |

## How the rebuild addresses each finding

| Finding | Rebuild |
|---|---|
| Inverted bands | Buy at $M \le 0.75V$, sell at $M \ge V$; the thresholds cannot overlap ([methodology](methodology.md#portfolio-construction)) |
| Look-ahead | Every input read on the rebalance day from QuantConnect's point-in-time Morningstar data |
| Linear extrapolation | One bounded growth rate, compounded ([methodology](methodology.md#growth-and-forecast)) |
| Capex sign | Absolute value of capex; working capital on the cash-flow convention |
| Cost of equity | Still one constant, now a parameter, with sensitivity runs at 8% and 10% |
| Seven names | The 150 largest eligible US companies, refreshed monthly |
| Forty runs | Base run is the earliest run in the project; every backtest in the project is published |

## Appendix A: the 40 backtests of 3 and 4 April 2024

From QuantConnect's backtest list for project 17552945, exported through its web API on 25
September 2026 ([`results/raw/backtest_lists.json.gz`](../results/raw/backtest_lists.json.gz)).
[`results/checks/backtest_lists.csv`](../results/checks/backtest_lists.csv) holds the same
rows with the backtest ids, the first line of each error and the reason each run is not
published. Times are as QuantConnect reports them. Backtest names are QuantConnect's automatic
names. Orders is QuantConnect's total order count. The list gives zeros as the statistics of
runs that stopped before placing an order; those cells are left empty here.

| # | Created | Backtest name | Orders | Net profit | Sharpe | Outcome |
|---|---|---|---|---|---|---|
| 1 | 2024-04-03 15:55:55 | Crying Blue Lion | 0 | | | error at initialisation |
| 2 | 2024-04-03 15:57:10 | Creative Violet Anguilline | 0 | | | error at initialisation |
| 3 | 2024-04-03 15:57:43 | Calculating Apricot Donkey | 0 | | | error at initialisation |
| 4 | 2024-04-03 15:59:17 | Virtual Asparagus Barracuda | 0 | | | error at initialisation |
| 5 | 2024-04-03 16:01:49 | Dancing Light Brown Pigeon | 0 | | | error at initialisation |
| 6 | 2024-04-03 18:19:47 | Measured Red Jackal | 0 | | | error at initialisation |
| 7 | 2024-04-03 18:21:54 | Crawling Black Koala | 0 | | | error at initialisation |
| 8 | 2024-04-03 18:52:00 | Crawling Fluorescent Yellow Dragonfly | 0 | | | error at initialisation |
| 9 | 2024-04-03 18:54:55 | Dancing Tan Chicken | 0 | | | error at initialisation |
| 10 | 2024-04-03 18:57:25 | Creative Blue Viper | 0 | | | error at initialisation |
| 11 | 2024-04-03 19:04:16 | Retrospective Tan Frog | 32 | 1.976% | 2.776 | error during the backtest |
| 12 | 2024-04-03 19:06:40 | Crawling Red Hornet | 0 | | | error during the backtest |
| 13 | 2024-04-03 19:12:12 | Virtual Black Buffalo | 32 | 1.976% | 2.776 | error during the backtest |
| 14 | 2024-04-03 19:14:40 | Formal Light Brown Shark | 0 | | | error at initialisation |
| 15 | 2024-04-03 19:17:35 | Jumping Tan Bee | 363 | 9.023% | 0.389 | completed |
| 16 | 2024-04-03 19:19:31 | Logical Sky Blue Lemur | 427 | 7.978% | 0.127 | completed |
| 17 | 2024-04-03 19:21:24 | Upgraded Light Brown Rat | 539 | 8.363% | 0.215 | completed |
| 18 | 2024-04-03 19:23:02 | Calm Yellow Green Anguilline | 6 | 10.360% | 0.53 | completed |
| 19 | 2024-04-03 20:04:44 | Emotional Light Brown Bear | 0 | | | error at initialisation |
| 20 | 2024-04-03 20:09:51 | Dancing Magenta Salamander | 6 | 10.360% | 0.53 | completed |
| 21 | 2024-04-03 20:13:24 | Focused Fluorescent Yellow Dog | 606 | 7.194% | -0.078 | completed |
| 22 | 2024-04-03 20:14:14 | Casual Light Brown Alligator | 427 | 7.978% | 0.127 | completed |
| 23 | 2024-04-03 20:15:39 | Calm Fluorescent Orange Jackal | 427 | 24.178% | 1.656 | completed |
| 24 | 2024-04-03 20:22:43 | Determined Orange Viper | 429 | 21.171% | 1.24 | completed |
| 25 | 2024-04-03 20:26:02 | Sleepy Green Horse | 8 | 25.635% | 1.278 | completed |
| 26 | 2024-04-03 20:28:45 | Adaptable Light Brown Owlet | 429 | 21.171% | 1.24 | completed |
| 27 | 2024-04-03 20:30:14 | Crawling Sky Blue Horse | 608 | 19.568% | 1.055 | completed |
| 28 | 2024-04-03 20:31:17 | Hipster Brown Penguin | 449 | 21.034% | 1.223 | completed |
| 29 | 2024-04-03 20:37:27 | Well Dressed Red Caterpillar | 1778 | 2.967% | -0.544 | completed |
| 30 | 2024-04-03 20:38:51 | Creative Yellow Green Dolphin | 1778 | 2.967% | -0.544 | completed |
| 31 | 2024-04-03 20:39:40 | Energetic Magenta Tapir | 8 | 25.635% | 1.278 | completed |
| 32 | 2024-04-04 01:07:38 | Creative Tan Gaur | 8 | 25.635% | 1.278 | completed |
| 33 | 2024-04-04 01:15:04 | Sleepy Violet Galago | 8 | 25.635% | 1.278 | completed |
| 34 | 2024-04-04 14:05:04 | Smooth Fluorescent Pink Shark | 8 | 25.635% | 1.278 | completed |
| 35 | 2024-04-04 14:10:20 | Swimming Sky Blue Gorilla | 449 | 21.034% | 1.223 | completed |
| 36 | 2024-04-04 14:18:12 | Upgraded Yellow Green Kangaroo | 447 | 16.637% | 1.236 | completed |
| 37 | 2024-04-04 14:19:29 | Fat Yellow Wolf | 363 | 18.985% | 1.505 | completed |
| 38 | 2024-04-04 14:20:19 | Virtual Asparagus Goshawk | 363 | 27.233% | 1.878 | completed |
| 39 | 2024-04-04 15:19:14 | Calm Sky Blue Gaur | 363 | 27.233% | 1.878 | completed |
| 40 | 2024-04-04 17:28:14 | Geeky Sky Blue Caterpillar | 363 | 27.233% | 1.878 | completed, published (`dcf__prototype_2023`) |

Only run 40 had its code and orders exported for this audit; the code of the other 39 runs was not
read. The runs with 6 or 8 orders barely traded after the first purchases; the runs with several
hundred orders churned.

## Appendix B: recomputing the order evidence

The figures in finding 1 come from the `orders` list of the backtest export and from the trade
list built from it, [`results/prototype_2023/trades.csv`](../results/prototype_2023/trades.csv).
Run from the repository root:

```python
import gzip
import json
import numpy as np
import pandas as pd

fair = {"AAPL": 161.188557, "AVGO": 874.5949946, "NVO": 297.8334194, "XOM": 776.8739526,
        "UNH": 466.6287323, "PG": 101.8037104, "NKE": 101.5209448}
with gzip.open("results/raw/dcf__prototype_2023.json.gz", "rt", encoding="utf-8") as fh:
    orders = json.load(fh)["orders"]

buys = [o for o in orders if o["quantity"] > 0]
sells = [o for o in orders if o["quantity"] < 0]
print(len(orders), len(buys), len(sells))                            # 363 183 180
print(sum(o["price"] > fair[o["symbol"]] for o in buys))             # 109 buys above F
print(sum(o["price"] < fair[o["symbol"]] for o in sells))            # 61 sells below F

trades = pd.read_csv("results/prototype_2023/trades.csv")
days = np.busday_count(trades["entry_time"].str[:10].to_numpy().astype("datetime64[D]"),
                       trades["exit_time"].str[:10].to_numpy().astype("datetime64[D]"))
print(len(trades), int((days <= 1).sum()))                           # 181 165
```
