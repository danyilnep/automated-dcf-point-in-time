# Reproduction of the base run

Written by `analysis/build_results.py` from the exports in `results/raw/`; a rebuild overwrites it. `comparison.csv` holds the full comparison, one row per run.

The base run in `base_2016_2024/` was recorded before the strategy code was split into `main.py` and `dcf_model.py`. Two later backtests test whether the split changed anything:

| Run | Key | QuantConnect project / backtest | Created | LEAN | Code that ran |
|---|---|---|---|---|---|
| Recorded base run | `dcf__base` | 36836412 / `54b5e0649da4a9cbf3f7dce6c409c7fe` | 2026-09-22 17:45:13 | v2.5.0.0.18116 | `main.py` (`4f7f49ed...`) |
| Refactored re-run | `rerun__dcf_base` | 36836412 / `4dbfbc74cea08eaceca427b01447a19d` | 2026-09-24 23:59:50 | v2.5.0.0.18126 | `main.py` (`a567e72b...`), `dcf_model.py` (`c9313f30...`) |
| Control: recorded code re-run | `control__dcf_recorded_code` | 36923806 / `48e014812a2a5dcdc8810e80d44d3637` | 2026-09-25 00:26:10 | v2.5.0.0.18126 | `main.py` (`4f7f49ed...`) |

- The refactored re-run ran this repository's `main.py` and `dcf_model.py` with the base parameters (the code defaults; no project parameters were passed). The hashes above are the SHA-256 of each file as it ran on QuantConnect, from `results/provenance/code_hashes.json`. In the published copies in `results/raw/` and in this repository, one docstring paragraph was rewritten to leave out the names of the other 2024 team members; `comparison.csv` gives both hashes of each file.
- The control ran the recorded run's `main.py` (the same SHA-256) again, in a separate QuantConnect project, on the same engine build as the re-run. A difference that appears in both the re-run and the control comes from QuantConnect's side, not from the code.
- Created is the creation time QuantConnect records for each backtest.

## LEAN versions

QuantConnect upgraded LEAN between the recorded run (v2.5.0.0.18116) and the re-runs (v2.5.0.0.18126).
The re-runs' exports carry the version in their server statistics. The exports of the original runs do not; their versions come from `raw/engines__original_runs.json.gz`, a separate export of the server statistics of each original backtest. `runs.csv` gives the version of every run:

| LEAN | Runs | Created |
|---|---|---|
| not recorded | `dcf__prototype_2023` | 2024-04-04 |
| v2.5.0.0.18116 | `dcf__base`, `dcf__sens_mos015`, `dcf__sens_mos035`, `dcf__sens_coe008` | 2026-09-22 |
| v2.5.0.0.18126 | `dcf__sens_mos050`, `dcf__sens_coe010`, `dcf__sens_pos10`, `dcf__sens_pos40`, `dcf__sens_univ300`, `audit__basket_2023`, `rerun__dcf_base`, `control__dcf_recorded_code` | 2026-09-24 to 2026-09-25 |

Of the 8 sensitivity runs, 3 ran on v2.5.0.0.18116 and 5 on v2.5.0.0.18126; none was re-run on another build.

## Result

Orders and trades are identical in the three runs: all 1,340 orders (1,316 filled, 24 cancelled) match in time, symbol, quantity and status, in order-id order, and all 1,114 closed trades match in symbol, entry time, exit time, quantity and profit.

The re-run and the control agree on all 27 QuantConnect statistics. Across the three runs, 24 of the 27 are the same and 3 differ:

| Statistic | Recorded (v2.5.0.0.18116) | Re-run (v2.5.0.0.18126) | Control (v2.5.0.0.18126) |
|---|---|---|---|
| Sharpe Ratio | 0.279 | 0.28 | 0.28 |
| Sortino Ratio | 0.279 | 0.28 | 0.28 |
| Probabilistic Sharpe Ratio | 0.433% | 0.439% | 0.439% |

The refactor changed nothing: the refactored code and the recorded code produce the same orders, trades and statistics on the same engine build. The control shows the same new values for the 3 statistics that changed, so the change comes from QuantConnect's side between the recorded run and the re-runs, not from the code.

At four decimals, QuantConnect's portfolio statistics show the same shift: `sharpeRatio` 0.2792 to 0.2804, `probabilisticSharpeRatio` 0.0043 to 0.0044, `sortinoRatio` 0.2792 to 0.2805, `treynorRatio` 0.0472 to 0.0474. Return, volatility, drawdown and beta are unchanged, and every statistic that moved is built on the return in excess of the risk-free rate (the probabilistic Sharpe ratio through the Sharpe ratio). That suggests the risk-free rate the statistics use differs between the two builds; the exports do not show that rate, so this is not confirmed.

## comparison.csv

| Column | Meaning |
|---|---|
| `key`, `run` | Raw export key and the run's role |
| `project_id`, `backtest_id`, `created` | QuantConnect identifiers and creation time |
| `lean_version` | LEAN build the backtest ran on |
| `code_files` | The Python files QuantConnect stored with the backtest (`research.ipynb`, QuantConnect's default notebook, does not run in a backtest and is left out) |
| `code_sha256_as_run`, `code_sha256_published` | SHA-256 of each file as it ran on QuantConnect (from `results/provenance/code_hashes.json`) and of the published copy in `results/raw/` |
| `total_orders` to `drawdown_recovery` | QuantConnect's 27 statistics, exactly as the export gives them (text, with QuantConnect's rounding and units) |
| `closed_trades`, `orders` | Length of the exported closed-trade and order lists |
| `trades_identical_to_recorded`, `trades_identical_to_rerun` | True when both the closed trades (symbol, entry time, exit time, quantity, profit; compared as sorted lists) and the orders (time, symbol, quantity, status; in order-id order) equal those of the recorded run or of the re-run |
