# Data checks and reproduction

Three checks were run on QuantConnect after the recorded backtests. Two test assumptions about
the Morningstar fields the valuation reads; the third tests whether the code in this repository
reproduces the recorded base run. The files behind every number here are in
[`results/checks/data/`](../results/checks/data/) and
[`results/checks/reproduction/`](../results/checks/reproduction/), both written by
`analysis/build_results.py` from the exports in `results/raw/`.

None of the checks changes the published results.

## The probe backtests

The two field checks come from probe backtests that place no orders. The probe
([`probe_main.py`](../results/checks/data/code/probe_main.py)) holds the 100 largest primary
shares by `market_cap` with a price above USD 1 and reduces what it sees to one chart point per
month, because a free-tier backtest keeps few chart points. It ran once for 2012 and once for
2019.

| Backtest | Key | QuantConnect project / backtest | Created | LEAN | Period |
|---|---|---|---|---|---|
| Probe | `probe2__2012` | 36923739 / `843f4a7d9ac7d1d4fe5c23dea76eda92` | 2026-09-25 00:28:47 | v2.5.0.0.18126 | 2012 |
| Probe | `probe2__2019` | 36923739 / `7e0a587bfa6cb6d324391beb453792be` | 2026-09-25 00:29:33 | v2.5.0.0.18126 | 2019 |
| Cap probe | `capprobe2__2019` | 36924577 / `10bf1b25d6e517a9f7ddb811dba709d9` | 2026-09-25 00:36:08 | v2.5.0.0.18126 | 2 Jan to 15 Feb 2019 |

A first version of the probe had no once-per-day guard, so it counted repeat `on_data` calls on
the same day as day-to-day comparisons; it was discarded, and `probe2` is the corrected version.
Besides the three backtests above, QuantConnect's lists for the two probe projects hold the
discarded version's two backtests and one earlier run of the cap probe; none of those three was
exported ([`backtest_lists.csv`](../results/checks/backtest_lists.csv)).

## EBITDA growth is a decimal fraction

The valuation reads `operation_ratios.ebitda_growth.one_year` and bounds it to -0.05 and 0.15
([methodology](methodology.md#growth-and-forecast)). Those bounds mean -5% and +15% only if the
field is a decimal fraction, where 0.10 means 10%.

At the first data point of each month the probe took the field for every name it held, left out
missing, NaN and zero values, and recorded the median and the 90th percentile of the absolute
value ([`ebitda_growth_monthly.csv`](../results/checks/data/ebitda_growth_monthly.csv), one row
per month):

| Year | Monthly median, lowest to highest | 90th percentile of the absolute value |
|---|---|---|
| 2012 | 0.102 to 0.144 | 0.424 to 0.569 |
| 2019 | 0.088 to 0.100 | 0.431 to 0.468 |

Read as fractions, the median large company grew EBITDA by about 10% on the previous year, and
one in ten moved by more than 42% to 57% either way. Read as percentages, the median company
would have grown EBITDA by 0.10% and nine in ten would have moved by less than 0.57%, far too
flat for company earnings. The field is a decimal fraction, and the growth bounds apply as
intended.

## Market capitalisation is refreshed once a month

The valuation reads `market_cap` twice: the universe selection ranks companies by it, and the
upside ratio divides the implied equity value by it. At the first data point of each day the
probe compared every name's `market_cap` and price with the values it saw on the previous
trading day ([`market_cap_updates.csv`](../results/checks/data/market_cap_updates.csv), one row
per month):

- From February to December, 94.7% to 95.7% of the comparisons in a month found the cap
  unchanged. In January the share is exactly 100% in both years.
- In 66.5% to 84.5% of the comparisons in a month the price had moved and the cap had not.
- The cap moved in step with the price, as price times a share count would, in none of the
  comparisons in 23 of the 24 months; in June 2019 it did in 0.05%.

About one comparison in 21 finds a change, which is about one change per name per month (a month
has about 21 trading days). Both probes start on 1 January, and in January no name's cap changed
after the first day, so the refresh falls at the start of the month. Morningstar's
`market_cap` in QuantConnect is therefore a monthly value: refreshed at the start of each month
and then held, which is how a month-end snapshot behaves. It is not a daily price times shares.

### The cap probe's log

The cap probe ([`cap_probe_main.py`](../results/checks/data/code/cap_probe_main.py)) ties the
monthly value to a specific close and to the share count. At every universe selection call from
2 January to 15 February 2019 it logs, for AAPL, MSFT and XOM, the unadjusted and adjusted
price, `market_cap`, `company_profile.shares_outstanding` and unadjusted price times shares. Its
98 exported log lines are in [`cap_probe_2019.log`](../results/checks/data/cap_probe_2019.log),
and the 96 lines with values are parsed into
[`cap_probe_2019.csv`](../results/checks/data/cap_probe_2019.csv); the table in
[`results/checks/data/README.md`](../results/checks/data/README.md#cap-probe) is computed from
that file.

- Each line is dated by the selection call, at midnight, and carries the previous session's
  close: the line dated 2 January has AAPL at 157.74, MSFT at 101.57 and XOM at 68.19, their
  closes of 31 December 2018. There are lines on 32 dates, all on Tuesdays to Saturdays, and
  none on a Sunday, a Monday or Tuesday 22 January, after the Martin Luther King Day holiday:
  the selection runs at midnight after each trading session.
- AAPL's `market_cap` is 746.08 bn on every line from 2 to 31 January, while its unadjusted
  price moves every day (from 157.74 to 165.25). It changes to 784.81 bn on the line of
  1 February, which carries the 31 January close of 166.44. MSFT (780.36 to 801.21 bn) and XOM
  (288.92 to 310.33 bn) change on the same line.
- The value is the previous month's last close times the share count of the time. On the first
  line of each month, AAPL's `market_cap` divided by its price gives 4.7298 bn shares in January
  and 4.7153 bn in February.
- `shares_outstanding` is restated for later splits. AAPL logs 18.9192 bn, exactly four times
  the 4.7298 bn behind its cap (AAPL split four for one in August 2020), so price times shares
  gives 2,984.32 bn, four times the market value on 2 January. For MSFT and XOM, whose logged
  counts have no such restatement, price times shares equals `market_cap` on the first line of
  each month. The logged count also changes on its own dates (AAPL on 19 January, MSFT on
  26 January), while `market_cap` waits for the month end. Price times the logged shares is
  therefore not a usable capitalisation for past dates.
- Rolling January's value forward with the adjusted price, 746.08 x 39.41 / 37.35 for AAPL,
  gives 787.23 bn on 1 February against the reported 784.81 bn, 0.31% too high. For MSFT the
  roll-forward is 0.14% too high and for XOM 0.06%. Each error is close to the fall in the
  logged share count between the two lines (0.31%, 0.14% and 0.05%), which a price-only roll
  cannot see.

### Effect on the DCF

The strategy reads `market_cap` in two places: the universe selection ranks by it at its first
call of the month, and the rebalance, 30 minutes after the open on the first trading day,
divides each implied equity value by it. The two do not always come in that order. The
selection runs at midnight after a trading session, so the month's first call precedes the
rebalance only when the previous month ends on a trading day, which it does in 76 of the 108
months. In the other 32 it runs the night after the rebalance: that rebalance values and trades
last month's members, ranked on last month's snapshot, and the held names the new ranking drops
are sold at the next open. [Refresh and rebalance order](methodology.md#refresh-and-rebalance-order)
lists what this did in the base run (18 sales, three whole positions held for one session).
Which snapshot the rebalance's own read of `market_cap` returns in those 32 months was not
tested.

Apart from that lag, the strategy does not read the field inside the month, so the monthly
refresh itself does not change what it trades. The published runs contain the lag as it
happened, and their results stand as recorded. A strategy that ranks or trades on
capitalisation between month starts could not use this field as it is.

## Reproduction of the base run

The base run was recorded with a single `main.py`. That file was later split into
[`main.py`](../main.py) and [`dcf_model.py`](../dcf_model.py) with every expression kept, and two
more backtests test whether the split changed anything:

| Run | Key | QuantConnect project / backtest | Created | LEAN | Code that ran |
|---|---|---|---|---|---|
| Recorded base run | `dcf__base` | 36836412 / `54b5e0649da4a9cbf3f7dce6c409c7fe` | 2026-09-22 17:45:13 | v2.5.0.0.18116 | `main.py` `4f7f49ed...` |
| Refactored re-run | `rerun__dcf_base` | 36836412 / `4dbfbc74cea08eaceca427b01447a19d` | 2026-09-24 23:59:50 | v2.5.0.0.18126 | `main.py` `a567e72b...` and `dcf_model.py` `c9313f30...`, this repository's two files as run |
| Control | `control__dcf_recorded_code` | 36923806 / `48e014812a2a5dcdc8810e80d44d3637` | 2026-09-25 00:26:10 | v2.5.0.0.18126 | `main.py` `4f7f49ed...`, the recorded file |

Created is QuantConnect's timestamp for each backtest. The hashes are the SHA-256 of each file as
run on QuantConnect. In the published copies, in `results/raw/` and in this repository, one
docstring paragraph was rewritten to leave out the names of the other 2024 team members, so the
published `main.py` of the recorded run and the control is `c455f69d...` and the repository's
`main.py` and `dcf_model.py` are `56cadd09...` and `d21b127d...`;
[`results/provenance/code_hashes.json`](../results/provenance/code_hashes.json) records both
hashes of every file. All three ran the base parameters with the same dates and cash.

The refactored code on LEAN v2.5.0.0.18126 reproduced every order and every trade: all 1,340
orders (1,316 filled, 24 cancelled) match in time, symbol, quantity and status, and all 1,114
closed trades match in symbol, entry and exit time, quantity and profit. End equity is
USD 197,850.66 in all three runs. It also reproduced 24 of QuantConnect's 27 statistics. Three
moved:

| Statistic | Recorded run (v2.5.0.0.18116) | Refactored re-run (v2.5.0.0.18126) | Control (v2.5.0.0.18126) |
|---|---|---|---|
| Sharpe ratio | 0.279 | 0.28 | 0.28 |
| Sortino ratio | 0.279 | 0.28 | 0.28 |
| Probabilistic Sharpe ratio | 0.433% | 0.439% | 0.439% |

The control, the recorded code run on the same engine as the re-run, gave exactly the same 27
statistics as the refactored run. The refactor is therefore exact, and the difference comes from
QuantConnect's side, where the recorded change between the runs is the engine upgrade from
v2.5.0.0.18116 to v2.5.0.0.18126. At four decimals the Sharpe ratio moved from 0.2792 to 0.2804
and the Sortino ratio from 0.2792 to 0.2805, while return, volatility, drawdown and beta did not
move. Every statistic that moved is built on the return in excess of the risk-free rate, and the
exports do not show the rate each run used, so they cannot separate the engine upgrade from a
change in the rate data QuantConnect supplies.

The README and [`results/runs.csv`](../results/runs.csv) quote the recorded run. The
`lean_version` column of `runs.csv` gives the build of every run: the base run and three
sensitivity runs (margin of safety 0.15 and 0.35, cost of equity 0.08) ran on v2.5.0.0.18116,
and the other five sensitivity runs and the reference basket on v2.5.0.0.18126. The sensitivity
runs were not repeated on the other build.

Files: [`comparison.csv`](../results/checks/reproduction/comparison.csv) has one row per run with
the 27 statistics as QuantConnect gives them, the LEAN build, the code hashes and whether the
orders and trades match; its [`README.md`](../results/checks/reproduction/README.md) describes
every column.
