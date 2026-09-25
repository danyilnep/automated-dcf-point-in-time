# Data checks

Written by `analysis/build_results.py` from the exports in `results/raw/`; a rebuild overwrites it.

Two assumptions about the Morningstar fields the DCF reads were tested with probe backtests on QuantConnect that place no orders:

1. `operation_ratios.ebitda_growth.one_year` is a decimal fraction (0.10 means 10%). The DCF bounds its growth rate to -0.05 and 0.15 on that assumption.
2. `market_cap` is a capitalisation for the day it is read. The DCF ranks its universe by this field and divides the equity value by it.

| Backtest | Key | QuantConnect project / backtest | Created | LEAN | Period |
|---|---|---|---|---|---|
| Probe | `probe2__2012` | 36923739 / `843f4a7d9ac7d1d4fe5c23dea76eda92` | 2026-09-25 00:28:47 | v2.5.0.0.18126 | 2012-01-01 to 2012-12-31 |
| Probe | `probe2__2019` | 36923739 / `7e0a587bfa6cb6d324391beb453792be` | 2026-09-25 00:29:33 | v2.5.0.0.18126 | 2019-01-01 to 2019-12-31 |
| Cap probe | `capprobe2__2019` | 36924577 / `10bf1b25d6e517a9f7ddb811dba709d9` | 2026-09-25 00:36:08 | v2.5.0.0.18126 | 2019-01-02 to 2019-02-15 |

The probe (`code/probe_main.py`, one backtest per year through its `year` parameter) holds the 100 largest primary shares by `market_cap` with a price above $1 and aggregates what it sees to one chart point per month, because a free-tier backtest keeps few chart points. A first version of the probe had no once-per-day guard and counted repeat calls on the same day; it was discarded, and `probe2` is the corrected version. `../backtest_lists.csv` lists its two backtests and an earlier run of the cap probe, none of them exported.

| File | Contents |
|---|---|
| `ebitda_growth_monthly.csv` | Median and 90th percentile of the absolute value of `ebitda_growth.one_year` across the probe's names, per month |
| `market_cap_updates.csv` | How often `market_cap` changed from one day to the next, per month |
| `cap_probe_2019.csv` | The cap probe's log, one row per name and day |
| `cap_probe_2019.log` | The cap probe's log lines as exported |
| `code/probe_main.py` | The probe's code as QuantConnect stored it (identical in both probe backtests) |
| `code/cap_probe_main.py` | The cap probe's code as QuantConnect stored it |

## EBITDA growth

`ebitda_growth_monthly.csv`: `year`, `month`, `median_one_year`, `p90_abs_one_year`. At the first data point of each month the probe takes `ebitda_growth.one_year` of every name it holds (missing, NaN and zero values left out) and plots the median and the 90th percentile of the absolute value.

The monthly median lies between 0.102 and 0.144 in 2012 and between 0.088 and 0.100 in 2019; the 90th percentile of the absolute value lies between 0.424 and 0.569. Read as fractions, the median company grew EBITDA by about 10% over the previous year. Read as percentages, it would have grown by 0.10% and nine in ten would have moved by less than 0.57% either way, far too flat for company earnings. The field is a decimal fraction, and the DCF's growth bounds apply as intended.

## Market cap updates

`market_cap_updates.csv`: one row per month. At the first data point of each day the probe compares every name's `market_cap` and price with the values it saw on the previous day.

| Column | Meaning |
|---|---|
| `year`, `month` | The month the comparisons fall in |
| `cap_unchanged_share` | Share of comparisons in which the cap did not change |
| `cap_moved_with_price_share` | Share in which the cap changed by the same ratio as the price (within 1e-6), as price times shares would |
| `price_moved_cap_unchanged_share` | Share in which the price changed and the cap did not |
| `calls_per_day` | Mean number of `on_data` calls per day |
| `hour_of_first_call` | Mean New York hour of the day's first `on_data` call |

QuantConnect stores each monthly point when the next month starts (the last one at the end of the backtest), so the build assigns each point to the month before its timestamp.

From February to December, between 94.7% and 95.7% of the comparisons in a month found the cap unchanged, while in 66.5% to 84.5% the price had moved and the cap had not. The cap moved in step with the price in no comparison in 23 of the 24 months; the exception is June 2019 (0.05% of comparisons). In January the share unchanged is exactly 1.0 in both years. That pattern fits a value that changes once a month, at the start of the month: the probe starts on 1 January, so January's comparisons contain no such change, and in later months about one comparison in 21 finds a change, roughly one per name per month (a month has about 21 trading days).

`on_data` ran 1.52 to 1.90 times a day on average in a month, which is why the probe compares only at the first call of each day.

So `market_cap` is not price times shares on each day: it holds a value that is refreshed about once a month. The DCF reads it for its universe ranking, at the first universe selection of each month, and for the upside ratio, at the rebalance on the first trading day; `docs/data-checks.md` describes when those two reads fall on different sides of the refresh.

## Cap probe

The cap probe (`code/cap_probe_main.py`) logs, for AAPL, MSFT and XOM at every universe selection call of its run, the unadjusted price, the adjusted price, `market_cap`, `company_profile.shares_outstanding` and unadjusted price times shares.

`cap_probe_2019.log` holds the 98 exported log lines; `cap_probe_2019.csv` parses the 96 that match the probe's format into `date`, `ticker`, `price_unadjusted`, `price_adjusted`, `market_cap_bn`, `shares_outstanding_bn` and `price_x_shares_bn` (billions, as logged).

The lines fall on 32 dates, each a Tuesday, Wednesday, Thursday, Friday or Saturday; a line is dated by the selection call that wrote it.

| Ticker | `market_cap` on the first line, bn | Held until | Changed on | Changed to, bn | First value rolled forward with the adjusted price, bn | Rolled value against the new one | Logged shares, change over the same lines | Logged shares / (`market_cap` / price) on the first line |
|---|---|---|---|---|---|---|---|---|
| AAPL | 746.08 | 2019-01-31 | 2019-02-01 | 784.81 | 787.23 | +0.31% | -0.31% | 4.0000 |
| MSFT | 780.36 | 2019-01-31 | 2019-02-01 | 801.21 | 802.34 | +0.14% | -0.14% | 1.0000 |
| XOM | 288.92 | 2019-01-31 | 2019-02-01 | 310.33 | 310.52 | +0.06% | -0.05% | 1.0000 |

A whole-number ratio above 1 means the logged share count is that multiple of the one behind `market_cap`, which is what a share count restated for a later split looks like: AAPL (4 times).
