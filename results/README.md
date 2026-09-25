# Results

Every QuantConnect backtest behind this repository, as exported from QuantConnect, plus the
tables derived from those exports. Nothing here is typed by hand: `analysis/build_results.py`
writes every file except this README, and `analysis/make_figures.py` draws `figures/` from the
derived CSVs.

## Layout

| Path | What it is |
|---|---|
| `runs.csv` | One row per strategy backtest: identifiers, LEAN version, parameters, headline statistics |
| `base_2016_2024/` | The rebuild with base parameters, 1 Jan 2016 to 31 Dec 2024 |
| `sensitivity/<variant>/` | The same code with one project parameter moved (eight runs) |
| `sensitivity/summary.csv` | The base run and the eight variants side by side |
| `prototype_2023/` | The 2024 prototype's final QuantConnect run (4 Apr 2024), calendar 2023 |
| `prototype_2023/code/main.py` | The code that run executed, from QuantConnect's project snapshot |
| `reference/basket_2023/` | Reference run: equal-weight buy and hold of the prototype's seven stocks through 2023 |
| `reference/basket_2023/code/main.py` | The reference algorithm (`mode` parameter `basket_2023`) |
| `checks/reproduction/` | The base run against a re-run of the refactored code and a re-run of the recorded code (`comparison.csv`, `README.md`) |
| `checks/data/` | Probe backtests on two Morningstar fields the DCF reads: EBITDA growth units and how often `market_cap` updates (`README.md`, CSVs, the cap probe's log, the probes' code) |
| `checks/backtest_lists.csv` | Every backtest QuantConnect lists in the projects behind this repository, with the published run it is or the reason it is not published |
| `raw/` | The QuantConnect exports, gzip-compressed, with `MANIFEST.json` |
| `provenance/code_hashes.json` | Not a QuantConnect export: the SHA-256 of every code file in the exports as run on QuantConnect and as published (see [Provenance](#provenance)) |

Variants in `sensitivity/`: `mos015`, `mos035`, `mos050` (margin of safety 0.15, 0.35, 0.50),
`coe008`, `coe010` (cost of equity 0.08, 0.10), `pos10`, `pos40` (maximum positions 10, 40) and
`univ300` (universe of 300). The base is margin of safety 0.25, cost of equity 0.09,
20 positions and a universe of 150.

Each run folder holds:

| File | Contents |
|---|---|
| `statistics.json` | QuantConnect's statistics, runtime statistics, trade and portfolio statistics, the parameters passed and in effect, the run's metadata, the SHA-256 of its `main.py` as run and as published, QuantConnect's analysis warnings, and notes on anything missing from the export |
| `equity.csv` | The equity curve against SPY, one row per stored chart sample |
| `orders.csv` | Every order QuantConnect recorded |
| `trades.csv` | Every closed round trip |
| `yearly_returns.csv`, `monthly_returns.csv` | Base and prototype runs only |
| `qc_report.html` | QuantConnect's own backtest report (base and prototype runs; the sensitivity runs have none) |

The reference basket export has no order or trade list, so its folder has no `orders.csv` or
`trades.csv`. The prototype export has no closed-trade list; its `trades.csv` is rebuilt from
the orders (first in, first out) and agrees with QuantConnect's own full-year trade statistics
on the count (181), the gross profit and loss (20,539.08) and the number of winners (106).

## Checks

`checks/` holds backtests run after the recorded ones to test them. Each folder's `README.md`
is written by the build, with every number read from the exports.

- `checks/reproduction/`: the base run re-run with the refactored code (`main.py` and
  `dcf_model.py`) and, as a control, with the recorded `main.py`. `comparison.csv` has one row
  per run with QuantConnect's 27 statistics, the LEAN version, the code hashes and whether the
  orders and closed trades match. The two re-runs also have a row in `runs.csv`, but no run
  folder: their orders and trades are identical to the base run's.
- `checks/data/`: probe backtests that place no orders. `ebitda_growth_monthly.csv` tests that
  `ebitda_growth.one_year` is a decimal fraction; `market_cap_updates.csv` measures how often
  `market_cap` changes from one day to the next. `cap_probe_2019.log` holds the cap probe's 98
  exported log lines and `cap_probe_2019.csv` the 96 lines with values, one row per name and
  selection date (AAPL, MSFT and XOM, 2 January to 15 February 2019). `code/` holds the probes'
  code as QuantConnect stored it.
- `checks/backtest_lists.csv`: QuantConnect's own list of the backtests in each project, used
  to account for every run (see [the section below](#backtest-lists)).

## Backtest lists

`raw/backtest_lists.json.gz` is QuantConnect's `backtests/list` endpoint, called with
`includeStatistics` for every project involved in this repository and in the stat-arb one, and
exported on 2026-09-25 (the file's own `exported` field says 2026-09-26; `MANIFEST.json` explains
the date). `checks/backtest_lists.csv` keeps the seven projects that concern this repository, one
row per backtest:

| Project | Backtests | Published here |
|---|---|---|
| 17552945, the 2024 prototype | 40 | 1, the final run (`dcf__prototype_2023`) |
| 17554026, the 2024 prototype's library | 0 | |
| 36836412, the rebuild | 10 | all 10 |
| 36922759, reference runs | 2 | 1 (`audit__basket_2023`); the other is the stat-arb repository's |
| 36923806, control re-run | 1 | 1 |
| 36923739, data probe | 4 | 2 (`probe2__2012`, `probe2__2019`); the other two are the discarded first version |
| 36924577, market cap probe | 2 | 1 (`capprobe2__2019`); the other is its first run, not exported |

Every backtest of the rebuild's project 36836412 is a row of `runs.csv`: the base run, the eight
sensitivity runs and the re-run of the refactored code. No other backtest was run in that
project. Of the prototype's 40 backtests, 15 stopped with an error and 25 completed; only the
final run was exported. The build fails if a listed backtest is neither published nor
explained, if a project's count disagrees with its list, if a published run is missing from
the list, or if a statistic in the list differs from the published export. The list returns no
statistics for `dcf__sens_coe008` (its cells are empty); the export of that run has them.

| Column | Meaning |
|---|---|
| `project_id`, `project_name` | QuantConnect project |
| `backtest_id`, `name`, `created` | QuantConnect's identifier, backtest name and creation time. Empty for a project with no backtests |
| `completed`, `status` | QuantConnect's completion flag and status text, as listed |
| `error` | First line of QuantConnect's error message, HTML entities decoded. Where that line is only QuantConnect's `FATAL UNHANDLED EXCEPTION` header, the first line of the stack trace |
| `parameters` | Project parameters passed to the backtest (empty: the code defaults) |
| `net_profit`, `sharpe`, `max_drawdown` | QuantConnect's net profit (percent), Sharpe ratio and drawdown (percent) as listed; zero for runs that stopped before trading |
| `orders` | The list's `trades` field, which holds QuantConnect's total order count (1,340 for the base run, as in `runs.csv`) |
| `published_as` | The key of the published run (the `key` in `runs.csv`, or the probe keys in `checks/data/`), or why the backtest is not published |

## Provenance

The exports were fetched through QuantConnect's web API on 2026-09-25 from Danyil Nepyivoda's
QuantConnect account: statistics, orders, closed trades, rolling windows, charts and the code
snapshot of each backtest. `raw/<key>.json.gz` is the export file for one backtest, compressed.
In the exports whose embedded code carried them, one docstring paragraph was rewritten to leave
out the names of the other 2024 team members; every other byte is as QuantConnect returned it,
and `provenance/code_hashes.json` records the SHA-256 of each code file as run on QuantConnect
and as published. `raw/charts.json.gz` holds the chart series of this repository's runs, cut from
the full chart export. The exports of the recorded runs do not include QuantConnect's server
statistics, so `raw/engines__original_runs.json.gz` holds them separately (for this
repository's runs and for the stat-arb repository's); it is the source of the LEAN version of
each recorded run. `raw/backtest_lists.json.gz` is QuantConnect's list of the backtests in each
project ([backtest lists](#backtest-lists)). `raw/MANIFEST.json` records the SHA-256 of every export file as published
(and of the two reports and the provenance file, with how that file was made), and every build
checks the decompressed raw files and the provenance file against it before reading them.

| Key | Folder | QuantConnect project / backtest |
|---|---|---|
| `dcf__base` | `base_2016_2024` | 36836412 / `54b5e0649da4a9cbf3f7dce6c409c7fe` |
| `dcf__sens_*` | `sensitivity/<variant>` | 36836412 / see `runs.csv` |
| `dcf__prototype_2023` | `prototype_2023` | 17552945 / `e472f920b9bb72dbb8024af7d95f1c04` |
| `audit__basket_2023` | `reference/basket_2023` | 36922759 / `d611b8a8fb19c48188e250a4c75a5297` |
| `rerun__dcf_base` | `checks/reproduction` | 36836412 / `4dbfbc74cea08eaceca427b01447a19d` |
| `control__dcf_recorded_code` | `checks/reproduction` | 36923806 / `48e014812a2a5dcdc8810e80d44d3637` |
| `probe2__2012`, `probe2__2019` | `checks/data` | 36923739 / see `checks/data/README.md` |
| `capprobe2__2019` | `checks/data` | 36924577 / `10bf1b25d6e517a9f7ddb811dba709d9` |
| `engines__original_runs` | `lean_version` in `runs.csv` | server statistics of the recorded runs |
| `backtest_lists` | `checks/backtest_lists.csv` | every backtest in each project involved |

`code_sha256_as_run` in `runs.csv` is the SHA-256 of the `main.py` as it ran on QuantConnect,
and `code_sha256_published` that of the published copy in `raw/`. For the base and sensitivity
runs they are `4f7f49ed...` as run, the rebuild's `main.py` as it stood when the runs were made,
and `c455f69d...` published. For the prototype both are `60ac793e...`, identical to
`received/main.py`. The control re-ran that same `4f7f49ed...` file; the refactored re-run's
`main.py` is `a567e72b...` as run and `56cadd09...` published, and it also ran `dcf_model.py`
(`checks/reproduction/comparison.csv` lists both hashes of every file). The code copies under
`**/code/` are written from the published code in `raw/`.

## Columns

Returns, rates and drawdowns are in percent. Money is in US dollars. Times ending in `Z` are UTC.

### runs.csv

| Column | Meaning |
|---|---|
| `key`, `label` | Run key (the raw file name) and a description |
| `project_id`, `backtest_id`, `created` | QuantConnect identifiers and the time the backtest was created |
| `lean_version` | LEAN build the backtest ran on: from the export's server statistics, or for the recorded runs from `raw/engines__original_runs.json.gz`. Empty for the 2024 prototype, which has no server statistics |
| `start` | Backtest start date |
| `end` | New York date of the last stored equity sample (see the note on chart samples) |
| `parameters` | Parameters in effect: the defaults in the code, overridden by the project parameters passed. Empty when the code has none |
| `net_profit`, `cagr`, `sharpe`, `psr`, `max_drawdown`, `beta` | QuantConnect's statistics: net profit, compounding annual return, Sharpe ratio, probabilistic Sharpe ratio, drawdown, beta to SPY |
| `orders` | QuantConnect's total order count (includes cancelled orders) |
| `closed_trades` | Closed round trips (empty when the export has none) |
| `win_rate`, `total_fees`, `end_equity` | QuantConnect's win rate, total fees and final equity |
| `spy_total_return`, `spy_cagr` | SPY over the same run, from QuantConnect's benchmark series between the first and last stored sample |
| `code_sha256_as_run` | SHA-256 of the `main.py` as it ran on QuantConnect, from `provenance/code_hashes.json` |
| `code_sha256_published` | SHA-256 of the published copy of that `main.py` in `raw/` |

The last two rows are the re-runs in `checks/reproduction/`. QuantConnect returned the
refactored re-run's equity, benchmark and drawdown charts empty, so its `end`, `spy_total_return`
and `spy_cagr` are empty. The control's chart samples fall at slightly different moments from the
base run's, so its SPY columns differ a little from the base run's (total return 238.9928
against 239.0297) although the backtest period is the same.

### sensitivity/summary.csv

`variant` is the folder name (`base` for the base run), `parameter` the project parameter that
differs from the base, `value` its value in this run and `base_value` its base value. The
remaining columns are as in `runs.csv`.

### equity.csv

| Column | Meaning |
|---|---|
| `date`, `time_utc` | Sample time, as a New York date and as the UTC timestamp QuantConnect stored |
| `equity` | Portfolio value at the sample (the close of QuantConnect's stored equity candle) |
| `spy_benchmark` | QuantConnect's SPY benchmark series, split- and dividend-adjusted, so its changes are total returns |
| `drawdown` | QuantConnect's equity drawdown chart: percent below the running peak, 0 at a new high. The peak comes from QuantConnect's full daily record, not from the samples, so a sample that is a new high among the samples can still show a drawdown |
| `exposure_long` | Long holdings as a fraction of equity (the short series is omitted where it is always zero) |
| `turnover` | QuantConnect's portfolio turnover chart, nearest point to the sample |

QuantConnect stores charts downsampled to about one point every 4.1 calendar days (794 points
over nine years, 88 over 2023). The statistics in `runs.csv` are computed by QuantConnect on the
full daily record, so they can differ slightly from what the samples show: the lowest value of
the base run's `drawdown` column is -42.3% (-42.0% when the peak is also taken from the
samples, as it has to be for SPY), and QuantConnect's statistic is 43.6%. The last sample of the
nine-year runs is taken early on 30 Dec 2024, before the last two sessions of the year.

### monthly_returns.csv

`month`, `start_equity`, `end_equity`, `return`. Built from QuantConnect's one-month rolling
windows. A window's start equity is the equity at the previous month's last close, so a month
ends where the next window starts, and the last month ends at the run's final equity. The chain
reproduces QuantConnect's net profit exactly. QuantConnect's own per-window net profit is not
used: a window's end equity leaves out the session on the month's last calendar day. In the
export, one window's end equity differs from the next window's start equity in exactly the
months whose last calendar day is a trading day.

### yearly_returns.csv

| Column | Meaning |
|---|---|
| `year`, `start_equity`, `end_equity`, `strategy_return` | Calendar-year strategy return from the month-end equity above (exact) |
| `sample_start`, `sample_end` | The two chart samples used for the comparison with SPY: the last sample before 2 January of the year and of the next year (New York time) |
| `strategy_return_sampled` | Strategy return between those two samples |
| `spy_start`, `spy_end`, `spy_return` | SPY benchmark series at those samples, and its return |
| `difference_sampled` | `strategy_return_sampled` minus `spy_return`, in percentage points |

1 January is a market holiday, so a sample taken before 2 January holds a December close.
Because samples fall every four days, in some years that close is one or two sessions before
the year's last session (2018, 2019 and 2024 in the base run). Compare the strategy with SPY
through the two `_sampled` columns, which cover identical dates; use `strategy_return` for the
strategy's own calendar-year figure.

### orders.csv

`id`, `time` (submitted), `last_fill_time`, `symbol`, `type` (QuantConnect order type),
`status` (`Filled` or `Canceled`; a cancelled order has no fill time and a zero price),
`direction` (buy or sell), `quantity` (negative for sells; in the same adjusted units as the
price), `price` (fill price, split- and dividend-adjusted as QuantConnect held the data when the
backtest ran), `value`, `fee`, `tag` (the reason the algorithm gave, if any; the base run's 24
cancelled midnight orders carry `no valuation`, which fits the tag of the call that cancelled
them rather than the one that placed them, see
[methodology](../docs/methodology.md#costs-and-execution)).

### trades.csv

`symbol`, `direction`, `quantity`, `entry_time`, `entry_price`, `exit_time`, `exit_price`,
`profit_loss` (gross of fees, as QuantConnect reports it), `total_fees`, `mae` and `mfe`
(maximum adverse and favourable excursion in dollars), `end_trade_drawdown`, `duration`
(days.hours:minutes:seconds), `is_win` (profit and loss above zero), `order_ids`.

## Rebuilding

From the repository root, with Python 3.11 or later and the pinned packages in
`requirements-dev.txt` (`pip install -r requirements-dev.txt`):

```
python analysis/build_results.py            # rebuild every derived file from results/raw
python analysis/build_results.py --check    # compare a fresh build with the files here
python analysis/make_figures.py             # redraw figures/ from the derived CSVs
```

`--check` exits with status 1 and lists every derived file that is missing, differs or is no
longer produced, and every raw file, report or provenance file whose hash does not match
`raw/MANIFEST.json`. The first build was run with `--import-from` pointing at the directory of
export files, which copies them into `raw/` and the provenance file into `provenance/`; later
builds never read anything outside `results/`.
