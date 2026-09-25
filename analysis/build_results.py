"""Build the published results tree from the raw QuantConnect exports.

First run, which copies the exports into results/raw and then builds:

    python analysis/build_results.py --import-from ../_qc-export

Every later run reads only results/raw:

    python analysis/build_results.py

Check that the derived files in results/ match a fresh build (exit 1 on any difference):

    python analysis/build_results.py --check

The raw exports are QuantConnect backtest results fetched through its web API on 2026-09-25,
and QuantConnect's list of every backtest in each project involved (backtest_lists.json). In the
exports whose code carried them, one docstring paragraph of the embedded code was rewritten to
leave out the names of the other 2024 team members; results/provenance/code_hashes.json records,
for every code file, the SHA-256 as run on QuantConnect and as published.
results/raw/MANIFEST.json holds the SHA-256 of every export file as imported and of the
provenance file; each build checks the decompressed raw files and the provenance file against
it before reading them.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import io
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results"
RAW = RESULTS / "raw"
MANIFEST = RAW / "MANIFEST.json"
CODE_HASHES_REL = "provenance/code_hashes.json"
CODE_HASHES = RESULTS / CODE_HASHES_REL
CODE_HASHES_HOW = (
    "Not a QuantConnect export. Written on 2026-09-25 when the exports were prepared for "
    "publication, by hashing each code file in each export before and after the rewrite. Per "
    "export key and code file: as_run is the SHA-256 of the file as QuantConnect stored and ran "
    "it, published the SHA-256 of the copy in the export as imported here, and names_removed "
    "whether one docstring paragraph was rewritten to leave out the names of the other 2024 "
    "team members. It covers the exports of this repository and of the stat-arb repository.")
EXPORT_DATE = "2026-09-25"
NY = "America/New_York"
BASE_KEY = "dcf__base"

# One entry per QuantConnect backtest that belongs to this repository.
RUNS = [
    {"key": "dcf__base", "folder": "base_2016_2024",
     "label": "Base parameters, 2016 to 2024", "calendar": True},
    {"key": "dcf__sens_mos015", "folder": "sensitivity/mos015", "label": "Margin of safety 15%"},
    {"key": "dcf__sens_mos035", "folder": "sensitivity/mos035", "label": "Margin of safety 35%"},
    {"key": "dcf__sens_mos050", "folder": "sensitivity/mos050", "label": "Margin of safety 50%"},
    {"key": "dcf__sens_coe008", "folder": "sensitivity/coe008", "label": "Cost of equity 8%"},
    {"key": "dcf__sens_coe010", "folder": "sensitivity/coe010", "label": "Cost of equity 10%"},
    {"key": "dcf__sens_pos10", "folder": "sensitivity/pos10", "label": "10 positions"},
    {"key": "dcf__sens_pos40", "folder": "sensitivity/pos40", "label": "40 positions"},
    {"key": "dcf__sens_univ300", "folder": "sensitivity/univ300", "label": "Universe of 300"},
    {"key": "dcf__prototype_2023", "folder": "prototype_2023",
     "label": "2024 prototype, calendar 2023", "calendar": True, "write_code": True},
    {"key": "audit__basket_2023", "folder": "reference/basket_2023",
     "label": "Reference: equal-weight buy and hold of the prototype's seven stocks, 2023",
     "write_code": True},
]

# Backtests that check the recorded ones (results/checks/). The two re-runs get a row in
# runs.csv; the probes place no orders and appear only under checks/data.
RERUN_KEY = "rerun__dcf_base"
CONTROL_KEY = "control__dcf_recorded_code"
CHECK_RUNS = [
    {"key": RERUN_KEY,
     "label": "Check: base parameters re-run with the refactored code (main.py and dcf_model.py)"},
    {"key": CONTROL_KEY,
     "label": "Check: the base run's recorded main.py re-run, as a control for the re-run"},
]
REPRODUCTION = [
    (BASE_KEY, "Recorded base run"),
    (RERUN_KEY, "Refactored re-run"),
    (CONTROL_KEY, "Control: recorded code re-run"),
]
PROBE_KEYS = ["probe2__2012", "probe2__2019"]
CAP_PROBE_KEY = "capprobe2__2019"
ENGINES_KEY = "engines__original_runs"
LISTS_KEY = "backtest_lists"
EXTRA_RAW = [RERUN_KEY, CONTROL_KEY, *PROBE_KEYS, CAP_PROBE_KEY, ENGINES_KEY, LISTS_KEY]

# backtest_lists.json is a separate export: QuantConnect's backtests/list endpoint with
# includeStatistics, one entry per backtest in every project involved in either strategy
# repository. LISTS_NOTE, stored in the manifest, explains the export date.
LISTS_EXPORTED = "2026-09-25"
LISTS_HOW = "QuantConnect web API, backtests/list with includeStatistics, every backtest of each project"
LISTS_NOTE = ("The file's own exported field reads 2026-09-26. The file was written on 2026-09-25 "
              "at 03:24 UTC, about two hours after the last backtest it lists was created "
              "(2026-09-25 01:00:28), so the export date is 2026-09-25.")

# The projects in backtest_lists.json that concern this repository, in the order of
# checks/backtest_lists.csv. The file also lists the stat-arb repository's projects.
LIST_PROJECTS = [17552945, 17554026, 36836412, 36922759, 36923806, 36923739, 36924577]
PROTOTYPE_PROJECT = 17552945
# Backtests in those projects that are neither published here nor runs of the 2024 prototype
# (which are explained by rule in list_reason), with the reason.
NOT_PUBLISHED = {
    "59188fbb663a9156f0a91ef329d1a6e0":
        "not in this repository: the SPY reference run of the stat-arb repository "
        "(audit__spy_2015_2019)",
    "d8437e5465b8ac3e0e57c1793df5a2ca":
        "not published: first probe version, without a once-per-day guard (it counted repeat "
        "calls on the same day); discarded and replaced by probe2__2012",
    "783c48a6748f1768dc417308cc432b26":
        "not published: first probe version, without a once-per-day guard (it counted repeat "
        "calls on the same day); discarded and replaced by probe2__2019",
    "3ea271f9598e34f6872c7aa6911fa3c8":
        "not published: first run of the cap probe, replaced by capprobe2__2019; not exported",
}

ORDER_TYPES = {
    0: "Market", 1: "Limit", 2: "StopMarket", 3: "StopLimit", 4: "MarketOnOpen",
    5: "MarketOnClose", 6: "OptionExercise", 7: "LimitIfTouched", 8: "ComboMarket",
    9: "ComboLimit", 10: "ComboLegLimit", 11: "TrailingStop",
}
ORDER_STATUS = {
    0: "New", 1: "Submitted", 2: "PartiallyFilled", 3: "Filled", 5: "Canceled", 6: "None",
    7: "Invalid", 8: "CancelPending", 9: "UpdateSubmitted",
}
ORDER_DIRECTION = {0: "buy", 1: "sell", 2: "hold"}
TRADE_DIRECTION = {0: "long", 1: "short"}

DERIVED_NAMES = {
    "runs.csv", "summary.csv", "statistics.json", "equity.csv", "orders.csv", "trades.csv",
    "yearly_returns.csv", "monthly_returns.csv",
}


# ----------------------------------------------------------------------------- helpers
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gzip_bytes(data: bytes) -> bytes:
    """Deterministic gzip: no file name and a zero timestamp in the header."""
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as gz:
        gz.write(data)
    return buf.getvalue()


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.replace("\r\n", "\n").encode("utf-8"))


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_csv(path: Path, df: pd.DataFrame) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, lineterminator="\n")
    write_text(path, buf.getvalue())


def num(value) -> float | None:
    """QuantConnect statistic string ("97.851%", "$1388.79", "1,340") to a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "").replace("%", "").strip()
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def pct(fraction: float | None) -> float | None:
    """Fraction to percent, rounded to 4 decimal places."""
    return None if fraction is None else round(fraction * 100.0, 4)


def camel(obj):
    """Lower the first letter of every key (the 2024 export uses PascalCase keys)."""
    if isinstance(obj, dict):
        return {k[:1].lower() + k[1:]: camel(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [camel(v) for v in obj]
    return obj


def snake(name: str) -> str:
    """QuantConnect statistic name to a column name: "Profit-Loss Ratio" -> profit_loss_ratio."""
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")


def ny_time(seconds: pd.Series) -> pd.Series:
    return pd.to_datetime(seconds, unit="s", utc=True).dt.tz_convert(NY)


# ----------------------------------------------------------------------------- import
def import_exports(src: Path) -> None:
    """Copy this repository's exports into results/raw (gzip) and the QuantConnect reports
    into the run folders, and write the manifest of source hashes."""
    src = src.resolve()
    files: dict[str, dict] = {}

    def add(key: str) -> None:
        data = (src / f"{key}.json").read_bytes()
        name = f"{key}.json.gz"
        write_bytes(RAW / name, gzip_bytes(data))
        files[name] = {"source_file": f"{key}.json", "sha256": sha256(data), "bytes": len(data)}
        if key == LISTS_KEY:
            files[name].update({"exported": LISTS_EXPORTED, "how": LISTS_HOW,
                                "note": LISTS_NOTE})

    for run in RUNS:
        add(run["key"])

    all_bytes = (src / "charts__all.json").read_bytes()
    all_charts = json.loads(all_bytes)
    keys = [run["key"] for run in RUNS if run["key"] in all_charts]
    sliced = json.dumps({k: all_charts[k] for k in keys}, separators=(",", ":")).encode("utf-8")
    write_bytes(RAW / "charts.json.gz", gzip_bytes(sliced))
    files["charts.json.gz"] = {
        "source_file": "charts__all.json", "source_sha256": sha256(all_bytes),
        "source_bytes": len(all_bytes), "keys": keys, "sha256": sha256(sliced),
        "bytes": len(sliced),
    }

    for key in EXTRA_RAW:
        add(key)

    reports: dict[str, dict] = {}
    for run in RUNS:
        report = src / f"{run['key']}__report.html"
        if report.exists():
            data = report.read_bytes()
            rel = f"{run['folder']}/qc_report.html"
            write_bytes(RESULTS / rel, data)
            reports[rel] = {"source_file": report.name, "sha256": sha256(data), "bytes": len(data)}

    hashes = (src / "code_hashes.json").read_bytes()
    write_bytes(CODE_HASHES, hashes)
    provenance = {CODE_HASHES_REL: {"source_file": "code_hashes.json", "sha256": sha256(hashes),
                                    "bytes": len(hashes), "how": CODE_HASHES_HOW}}

    manifest = {
        "exported": EXPORT_DATE,
        "how": "QuantConnect web API, backtest read endpoints, from Danyil Nepyivoda's account",
        "note": ("sha256 is the hash of the export file as imported, which is also the hash of "
                 "the decompressed .json.gz. In the exports whose code carried them, one "
                 "docstring paragraph of the embedded code was rewritten to leave out the names "
                 "of the other 2024 team members; every other byte is as QuantConnect returned "
                 "it, and provenance/code_hashes.json gives each code file's SHA-256 as run and "
                 "as published. charts.json.gz is the slice of charts__all.json for the keys "
                 "listed; its sha256 is that of the slice, source_sha256 that of the full file."),
        "files": files,
        "reports": reports,
        "provenance": provenance,
    }
    write_json(MANIFEST, manifest)
    print(f"imported {len(files)} raw files and {len(reports)} reports from {src}")


# ----------------------------------------------------------------------------- load
def load_raw() -> tuple[dict[str, dict], dict[str, dict], dict]:
    """Every raw export by key (engines__original_runs included), the chart slice and the
    manifest."""
    if not MANIFEST.exists():
        raise SystemExit("results/raw/MANIFEST.json is missing; run with --import-from first")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    decoded: dict[str, bytes] = {}
    for name, entry in manifest["files"].items():
        data = gzip.decompress((RAW / name).read_bytes())
        if sha256(data) != entry["sha256"]:
            raise SystemExit(f"hash mismatch in results/raw/{name}")
        decoded[name] = data
    exports = {name.removesuffix(".json.gz"): json.loads(data)
               for name, data in decoded.items() if name != "charts.json.gz"}
    missing = [k for k in [run["key"] for run in RUNS] + EXTRA_RAW if k not in exports]
    if missing:
        raise SystemExit(f"results/raw lacks {', '.join(missing)}; run with --import-from")
    charts = json.loads(decoded["charts.json.gz"])
    return exports, charts, manifest


def load_code_hashes(manifest: dict, exports: dict[str, dict]) -> dict:
    """provenance/code_hashes.json, checked against the manifest. Every code file of every raw
    export must have an entry whose published hash is the hash of the file in results/raw."""
    entry = (manifest.get("provenance") or {}).get(CODE_HASHES_REL)
    if entry is None or not CODE_HASHES.exists():
        raise SystemExit(f"results/{CODE_HASHES_REL} or its manifest entry is missing; run with "
                         f"--import-from")
    data = CODE_HASHES.read_bytes().replace(b"\r\n", b"\n")
    if sha256(data) != entry["sha256"]:
        raise SystemExit(f"hash mismatch in results/{CODE_HASHES_REL}")
    hashes = json.loads(data)
    for key, export in exports.items():
        code = export.get("code") if isinstance(export, dict) else None
        if not code:
            continue
        recorded = hashes.get(key) or {}
        if set(recorded) != set(code):
            raise SystemExit(f"{CODE_HASHES_REL}: {key} lists {sorted(recorded)}, the export "
                             f"holds {sorted(code)}")
        for name, text in code.items():
            item = recorded[name]
            if item["published"] != sha256(text.encode("utf-8")):
                raise SystemExit(f"{CODE_HASHES_REL}: published hash of {key}/{name} differs "
                                 f"from the code in results/raw")
            if (item["as_run"] != item["published"]) != bool(item["names_removed"]):
                raise SystemExit(f"{CODE_HASHES_REL}: {key}/{name} names_removed disagrees "
                                 f"with its two hashes")
    return hashes


def code_hash(hashes: dict, key: str, name: str = "main.py") -> dict:
    """The provenance entry (as_run, published, names_removed) of one code file."""
    return hashes[key][name]


# ----------------------------------------------------------------------------- per-run data
def run_charts(key: str, export: dict, all_charts: dict) -> dict:
    """charts__all.json is the complete chart export; the per-run file is the fallback
    (the reference basket run is only there)."""
    return all_charts.get(key) or export.get("charts") or {}


def code_of(export: dict) -> str:
    return (export.get("code") or {}).get("main.py", "")


def python_files(export: dict) -> dict[str, str]:
    """The Python files QuantConnect stored with a backtest. research.ipynb, the default
    notebook every QuantConnect project carries, does not run in a backtest."""
    return {name: text for name, text in (export.get("code") or {}).items()
            if name.endswith(".py")}


def lean_version(export: dict, engines: dict) -> str:
    """LEAN version from the export's server statistics; for the original runs, whose exports
    lack them, from engines__original_runs. Empty when neither has one."""
    server = export.get("serverStatistics") or {}
    if server.get("LEAN Version"):
        return server["LEAN Version"]
    entry = engines.get(export["meta"]["backtestId"]) or {}
    return (entry.get("serverStatistics") or {}).get("LEAN Version", "")


def effective_parameters(export: dict) -> dict[str, str]:
    """Defaults from the get_parameter calls in the code that ran, overlaid with the
    project parameters QuantConnect passed."""
    params: dict[str, str] = {}
    pattern = r'get_parameter\(\s*"(\w+)"\s*,\s*([^)]+?)\s*\)'
    for name, default in re.findall(pattern, code_of(export)):
        params[name] = default.strip().strip('"').strip("'")
    passed = export.get("parameterSet") or {}
    if isinstance(passed, dict):
        params.update({k: str(v) for k, v in passed.items()})
    return params


def has_equity(charts: dict) -> bool:
    return bool((charts.get("Strategy Equity") or {}).get("Equity"))


def equity_frame(charts: dict) -> pd.DataFrame:
    """QuantConnect's stored chart samples (about one every 4.1 calendar days), aligned on
    the Strategy Equity timestamps. equity is the close of each sample."""
    points = charts["Strategy Equity"]["Equity"]
    df = pd.DataFrame({
        "t": [int(p[0]) for p in points],
        "equity": [float(p[4] if len(p) >= 5 else p[1]) for p in points],
    }).drop_duplicates("t").sort_values("t").reset_index(drop=True)

    def attach(column: str, chart: str, series: str, keep_zero: bool = True) -> None:
        pts = (charts.get(chart) or {}).get(series)
        if not pts:
            return
        s = pd.DataFrame({"t": [int(p[0]) for p in pts],
                          column: [None if p[1] is None else float(p[1]) for p in pts]})
        s = s.drop_duplicates("t").sort_values("t")
        if not keep_zero and not (s[column].fillna(0) != 0).any():
            return
        merged = pd.merge_asof(df[["t"]], s, on="t", direction="nearest", tolerance=172800)
        df[column] = merged[column].to_numpy()

    attach("spy_benchmark", "Benchmark", "Benchmark")
    attach("drawdown", "Drawdown", "Equity Drawdown")
    attach("exposure_long", "Exposure", "Equity - Long Ratio", keep_zero=False)
    attach("exposure_short", "Exposure", "Equity - Short Ratio", keep_zero=False)
    attach("turnover", "Portfolio Turnover", "Portfolio Turnover")

    times = pd.to_datetime(df["t"], unit="s", utc=True)
    df.insert(0, "time_utc", times.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    df.insert(0, "date", ny_time(df["t"]).dt.strftime("%Y-%m-%d"))
    df["equity"] = df["equity"].round(2)
    return df


def month_end_equity(export: dict) -> pd.DataFrame | None:
    """Monthly returns from QuantConnect's one-month rolling windows.

    A window's startEquity is the equity at the previous month's last close. Its endEquity
    misses the month's last session when that session falls on the last calendar day, so
    the windows are chained through their start equities: a month ends where the next
    window starts, and the last month ends at the last window's endEquity."""
    windows = []
    for key, window in (export.get("rollingWindow") or {}).items():
        span, _, end = key.partition("_")
        if span != "M1":
            continue
        stats = camel(window).get("portfolioStatistics") or {}
        windows.append((end, float(stats["startEquity"]), float(stats["endEquity"])))
    if not windows:
        return None
    windows.sort()
    last_month = export["meta"]["backtestEnd"][:7]
    rows = []
    for i, (end, start_eq, end_eq) in enumerate(windows):
        month = f"{end[:4]}-{end[4:6]}"
        if month > last_month:
            continue
        month_end = windows[i + 1][1] if i + 1 < len(windows) else end_eq
        rows.append({"month": month, "start_equity": round(start_eq, 2),
                     "end_equity": round(month_end, 2),
                     "return": pct(month_end / start_eq - 1.0)})
    return pd.DataFrame(rows)


def yearly_returns(monthly: pd.DataFrame, eq: pd.DataFrame) -> pd.DataFrame:
    """Calendar-year strategy return from the month-end equity, and strategy against SPY
    between the same two chart samples: the last sample before 2 January (New York time)
    of the year and of the next year. 1 January is a market holiday, so such a sample holds
    the last close of December or earlier."""
    times = ny_time(eq["t"])
    rows = []
    for year, group in monthly.groupby(monthly["month"].str[:4], sort=True):
        y = int(year)
        before_start = eq.index[times < pd.Timestamp(f"{y}-01-02", tz=NY)]
        before_end = eq.index[times < pd.Timestamp(f"{y + 1}-01-02", tz=NY)]
        i0 = before_start[-1] if len(before_start) else eq.index[0]
        i1 = before_end[-1]
        s0, s1 = float(group["start_equity"].iloc[0]), float(group["end_equity"].iloc[-1])
        e0, e1 = eq.at[i0, "equity"], eq.at[i1, "equity"]
        b0, b1 = eq.at[i0, "spy_benchmark"], eq.at[i1, "spy_benchmark"]
        strategy_sampled = e1 / e0 - 1.0
        spy = b1 / b0 - 1.0
        rows.append({
            "year": y,
            "start_equity": round(s0, 2),
            "end_equity": round(s1, 2),
            "strategy_return": pct(s1 / s0 - 1.0),
            "sample_start": eq.at[i0, "date"],
            "sample_end": eq.at[i1, "date"],
            "strategy_return_sampled": pct(strategy_sampled),
            "spy_start": b0,
            "spy_end": b1,
            "spy_return": pct(spy),
            "difference_sampled": pct(strategy_sampled - spy),
        })
    return pd.DataFrame(rows)


def orders_frame(export: dict) -> pd.DataFrame | None:
    orders = export.get("orders")
    if not orders:
        return None
    rows = [{
        "id": o["id"],
        "time": o["time"],
        "last_fill_time": o.get("lastFillTime"),
        "symbol": o["symbol"],
        "type": ORDER_TYPES.get(o["type"], str(o["type"])),
        "status": ORDER_STATUS.get(o["status"], str(o["status"])),
        "direction": ORDER_DIRECTION.get(o["direction"], str(o["direction"])),
        "quantity": o["quantity"],
        "price": o["price"],
        "value": o["value"],
        "fee": o.get("fee"),
        "tag": o.get("tag", ""),
    } for o in sorted(orders, key=lambda o: o["id"])]
    return pd.DataFrame(rows)


TRADE_COLUMNS = [
    "symbol", "direction", "quantity", "entry_time", "entry_price", "exit_time", "exit_price",
    "profit_loss", "total_fees", "mae", "mfe", "end_trade_drawdown", "duration", "is_win",
    "order_ids",
]


def trades_from_export(export: dict) -> pd.DataFrame | None:
    trades = export.get("closedTrades")
    if not trades:
        return None
    rows = [{
        "symbol": t["symbol"],
        "direction": TRADE_DIRECTION.get(t["direction"], str(t["direction"])),
        "quantity": t["quantity"],
        "entry_time": t["entryTime"],
        "entry_price": t["entryPrice"],
        "exit_time": t["exitTime"],
        "exit_price": t["exitPrice"],
        "profit_loss": t["profitLoss"],
        "total_fees": t["totalFees"],
        "mae": t.get("mae"),
        "mfe": t.get("mfe"),
        "end_trade_drawdown": t.get("endTradeDrawdown"),
        "duration": t.get("duration"),
        "is_win": bool(t["isWin"]),
        "order_ids": " ".join(str(i) for i in t.get("orderIds") or []),
    } for t in trades]
    return pd.DataFrame(rows, columns=TRADE_COLUMNS)


def qc_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{days}.{hours:02d}:{minutes:02d}:{secs:02d}"


def trades_from_orders(export: dict) -> pd.DataFrame | None:
    """Round trips rebuilt from filled orders, first in first out, long only. Used only when
    the export has no closed-trade list. profit_loss is gross of fees (as QuantConnect's is);
    fees are the entry and exit order fees pro rata to quantity; MAE and MFE are unknown."""
    orders = [o for o in export.get("orders") or [] if o["status"] == 3]
    if not orders:
        return None
    orders.sort(key=lambda o: (o["lastFillTime"], o["id"]))
    lots: dict[str, list[list]] = {}
    rows = []
    for o in orders:
        qty = o["quantity"]
        if qty > 0:
            lots.setdefault(o["symbol"], []).append([qty, qty, o])
            continue
        remaining = -qty
        while remaining > 0:
            queue = lots.get(o["symbol"]) or []
            if not queue:
                raise SystemExit(f"cannot rebuild trades: short sale in {o['symbol']}")
            lot = queue[0]
            take = min(remaining, lot[0])
            entry = lot[2]
            fees = entry["fee"] * take / lot[1] + o["fee"] * take / -qty
            pnl = round(take * (o["price"] - entry["price"]), 2)
            held = (pd.Timestamp(o["lastFillTime"]) - pd.Timestamp(entry["lastFillTime"]))
            rows.append({
                "symbol": o["symbol"], "direction": "long", "quantity": take,
                "entry_time": entry["lastFillTime"], "entry_price": entry["price"],
                "exit_time": o["lastFillTime"], "exit_price": o["price"],
                "profit_loss": pnl, "total_fees": round(fees, 4),
                "mae": None, "mfe": None, "end_trade_drawdown": None,
                "duration": qc_duration(held.total_seconds()), "is_win": pnl > 0,
                "order_ids": f"{entry['id']} {o['id']}",
            })
            lot[0] -= take
            remaining -= take
            if lot[0] == 0:
                queue.pop(0)
    return pd.DataFrame(rows, columns=TRADE_COLUMNS)


def full_period_window(export: dict) -> tuple[str, dict] | None:
    """For a backtest of at most a year, the last twelve-month rolling window, which spans
    all of it. Checked against the run's start and end equity."""
    meta = export["meta"]
    span = pd.Timestamp(meta["backtestEnd"]) - pd.Timestamp(meta["backtestStart"])
    keys = sorted(k for k in export.get("rollingWindow") or {} if k.startswith("M12_"))
    if span.days > 366 or not keys:
        return None
    window = camel(export["rollingWindow"][keys[-1]])
    portfolio = window.get("portfolioStatistics") or {}
    stats = export.get("statistics") or {}
    same_start = num(portfolio.get("startEquity")) == num(stats.get("Start Equity"))
    same_end = abs((num(portfolio.get("endEquity")) or 0) - (num(stats.get("End Equity")) or 0))
    if not same_start or same_end > 0.01:
        return None
    return keys[-1], window


def run_row(key: str, label: str, export: dict, eq: pd.DataFrame | None,
            params: dict[str, str], closed_trades: int | None, engines: dict,
            hashes: dict) -> dict:
    """One row of runs.csv. Without an equity series (eq is None) the end date and the SPY
    columns stay empty."""
    meta = export["meta"]
    stats = export.get("statistics") or {}
    code = code_of(export)
    end = spy_total_return = spy_cagr = None
    if eq is not None:
        span_years = (eq["t"].iloc[-1] - eq["t"].iloc[0]) / (365.25 * 86400)
        spy_total = eq["spy_benchmark"].iloc[-1] / eq["spy_benchmark"].iloc[0] - 1.0
        end = eq["date"].iloc[-1]
        spy_total_return = pct(spy_total)
        spy_cagr = pct((1.0 + spy_total) ** (1.0 / span_years) - 1.0)
    return {
        "key": key,
        "label": label,
        "project_id": meta.get("projectId"),
        "backtest_id": meta.get("backtestId"),
        "created": meta.get("created"),
        "lean_version": lean_version(export, engines),
        "start": meta["backtestStart"][:10],
        "end": end,
        "parameters": "; ".join(f"{k}={v}" for k, v in params.items()),
        "net_profit": num(stats.get("Net Profit")),
        "cagr": num(stats.get("Compounding Annual Return")),
        "sharpe": num(stats.get("Sharpe Ratio")),
        "psr": num(stats.get("Probabilistic Sharpe Ratio")),
        "max_drawdown": num(stats.get("Drawdown")),
        "beta": num(stats.get("Beta")),
        "orders": int(num(stats.get("Total Orders")) or 0),
        "closed_trades": closed_trades,
        "win_rate": num(stats.get("Win Rate")),
        "total_fees": num(stats.get("Total Fees")),
        "end_equity": num(stats.get("End Equity")),
        "spy_total_return": spy_total_return,
        "spy_cagr": spy_cagr,
        "code_sha256_as_run": code_hash(hashes, key)["as_run"],
        "code_sha256_published": sha256(code.encode("utf-8")),
    }


# ----------------------------------------------------------------------------- build
def build(out: Path) -> list[str]:
    """Write every derived file under `out` (same layout as results/). Returns the paths
    written, relative to `out`."""
    exports, all_charts, manifest = load_raw()
    hashes = load_code_hashes(manifest, exports)
    engines = exports[ENGINES_KEY]
    written: list[str] = []

    def emit(rel: str, writer, obj) -> None:
        writer(out / rel, obj)
        written.append(rel)

    base_params = effective_parameters(exports[BASE_KEY])
    run_rows = []
    summary_rows = []
    for run in RUNS:
        key, folder = run["key"], run["folder"]
        export = exports[key]
        meta = export["meta"]
        stats = export.get("statistics") or {}
        charts = run_charts(key, export, all_charts)
        eq = equity_frame(charts)
        code = code_of(export)
        params = effective_parameters(export)
        notes: list[str] = []

        trade_stats = export.get("tradeStatistics")
        portfolio_stats = export.get("portfolioStatistics")
        stats_source = "run" if trade_stats else None
        if not trade_stats:
            window = full_period_window(export)
            if window:
                trade_stats = window[1].get("tradeStatistics")
                portfolio_stats = window[1].get("portfolioStatistics")
                stats_source = f"rollingWindow {window[0]}"
                notes.append(
                    f"The export has no run-level trade or portfolio statistics; the ones here "
                    f"are QuantConnect's rolling window {window[0]}, which spans the backtest.")

        orders = orders_frame(export)
        trades = trades_from_export(export)
        if trades is None and orders is not None:
            trades = trades_from_orders(export)
            if trades is not None:
                check = ""
                if trade_stats:
                    n_ok = len(trades) == int(trade_stats["totalNumberOfTrades"])
                    pl_ok = abs(trades["profit_loss"].sum() - num(trade_stats["totalProfitLoss"])) < 0.01
                    w_ok = int(trades["is_win"].sum()) == int(trade_stats["numberOfWinningTrades"])
                    if not (n_ok and pl_ok and w_ok):
                        raise SystemExit(f"{key}: rebuilt trades disagree with {stats_source}")
                    check = f" All three match QuantConnect's {stats_source}."
                notes.append(
                    f"The export has no closed-trade list. trades.csv is rebuilt from the filled "
                    f"orders (first in, first out): {len(trades)} round trips, gross profit and "
                    f"loss {trades['profit_loss'].sum():,.2f}, {int(trades['is_win'].sum())} "
                    f"winners.{check} MAE, MFE and end-trade drawdown are not available.")
        if orders is None:
            notes.append("The export has no order list or closed trades for this run, so "
                         "orders.csv and trades.csv are not written.")

        closed_trades = None
        if export.get("closedTrades"):
            closed_trades = len(export["closedTrades"])
        elif trade_stats:
            closed_trades = int(trade_stats["totalNumberOfTrades"])

        analysis = [{"name": a.get("name"), "issue": a.get("issue"), "sample": a.get("sample")}
                    for a in export.get("analysis") or []]
        statistics = {
            "key": key,
            "label": run["label"],
            "meta": meta,
            "parameters_passed": export.get("parameterSet") or {},
            "parameters_effective": params,
            "code": {"file": "main.py",
                     "sha256_as_run": code_hash(hashes, key)["as_run"],
                     "sha256_published": sha256(code.encode("utf-8")),
                     "bytes_published": len(code.encode("utf-8")),
                     "names_removed": code_hash(hashes, key)["names_removed"]},
            "statistics": stats,
            "runtime_statistics": export.get("runtimeStatistics"),
            "trade_statistics": camel(trade_stats) if trade_stats else None,
            "portfolio_statistics": camel(portfolio_stats) if portfolio_stats else None,
            "trade_and_portfolio_statistics_source": stats_source,
            "analysis_warnings": analysis,
            "notes": notes,
        }
        emit(f"{folder}/statistics.json", write_json, statistics)
        emit(f"{folder}/equity.csv", write_csv, eq.drop(columns=["t"]))
        if orders is not None:
            emit(f"{folder}/orders.csv", write_csv, orders)
        if trades is not None:
            emit(f"{folder}/trades.csv", write_csv, trades)
        if run.get("calendar"):
            monthly = month_end_equity(export)
            if monthly is None:
                monthly = equity_month_ends(eq)
            final = num(stats.get("End Equity"))
            if final is not None and abs(monthly["end_equity"].iloc[-1] - final) > 0.01:
                raise SystemExit(f"{key}: month-end chain ends at {monthly['end_equity'].iloc[-1]}"
                                 f", statistics say {final}")
            emit(f"{folder}/monthly_returns.csv", write_csv, monthly)
            emit(f"{folder}/yearly_returns.csv", write_csv, yearly_returns(monthly, eq))
        if run.get("write_code") and code:
            emit(f"{folder}/code/main.py", write_text, code)

        row = run_row(key, run["label"], export, eq, params, closed_trades, engines, hashes)
        run_rows.append(row)

        if key == BASE_KEY or folder.startswith("sensitivity/"):
            changed = [k for k, v in params.items()
                       if k in base_params and num(v) != num(base_params[k])]
            summary_rows.append({
                "variant": "base" if key == BASE_KEY else folder.split("/", 1)[1],
                "label": run["label"],
                "parameter": "; ".join(changed),
                "value": "; ".join(params[k] for k in changed),
                "base_value": "; ".join(base_params[k] for k in changed),
                **{c: row[c] for c in (
                    "net_profit", "cagr", "sharpe", "psr", "max_drawdown", "beta", "orders",
                    "closed_trades", "win_rate", "total_fees", "end_equity", "backtest_id")},
            })

    for run in CHECK_RUNS:
        key = run["key"]
        export = exports[key]
        charts = run_charts(key, export, all_charts)
        eq = equity_frame(charts) if has_equity(charts) else None
        closed = len(export["closedTrades"]) if export.get("closedTrades") else None
        run_rows.append(run_row(key, run["label"], export, eq, effective_parameters(export),
                                closed, engines, hashes))

    runs = pd.DataFrame(run_rows)
    runs["closed_trades"] = runs["closed_trades"].astype("Int64")
    emit("runs.csv", write_csv, runs)
    summary = pd.DataFrame(summary_rows)
    summary["closed_trades"] = summary["closed_trades"].astype("Int64")
    emit("sensitivity/summary.csv", write_csv, summary)

    build_reproduction(emit, exports, engines, runs, hashes)
    build_data_checks(emit, exports, engines)
    build_backtest_lists(emit, exports)
    return written


def equity_month_ends(eq: pd.DataFrame) -> pd.DataFrame:
    """Fallback when a run has no rolling windows: month ends from the equity samples."""
    months = eq["date"].str[:7]
    last = eq.groupby(months, sort=True)["equity"].last()
    start = [float(eq["equity"].iloc[0])] + list(last.iloc[:-1])
    return pd.DataFrame({"month": last.index, "start_equity": [round(s, 2) for s in start],
                         "end_equity": last.round(2).to_numpy(),
                         "return": [pct(e / s - 1.0) for s, e in zip(start, last)]})


# ----------------------------------------------------------------------------- checks: reproduction
def trade_keys(export: dict) -> list[tuple]:
    """Closed trades as (symbol, entry time, exit time, quantity, profit), sorted."""
    return sorted((t["symbol"], t["entryTime"], t["exitTime"], t["quantity"], t["profitLoss"])
                  for t in export.get("closedTrades") or [])


def order_keys(export: dict) -> list[tuple]:
    """Orders as (time, symbol, quantity, status), in order-id order."""
    return [(o["time"], o["symbol"], o["quantity"], o["status"])
            for o in sorted(export.get("orders") or [], key=lambda o: o["id"])]


def unmatched(a: list[tuple], b: list[tuple]) -> int:
    """Entries of either list without a counterpart in the other."""
    ca, cb = Counter(a), Counter(b)
    return sum((ca - cb).values()) + sum((cb - ca).values())


def short_hash(text: str) -> str:
    return sha256(text.encode("utf-8"))[:8] + "..."


def code_cell(key: str, export: dict, hashes: dict) -> str:
    """Each Python file of a run with the first eight characters of its SHA-256 as run."""
    return ", ".join(f"`{name}` (`{code_hash(hashes, key, name)['as_run'][:8]}...`)"
                     for name in python_files(export))


def build_reproduction(emit, exports: dict, engines: dict, runs: pd.DataFrame,
                       hashes: dict) -> None:
    """results/checks/reproduction: the recorded base run against the refactored re-run and
    the control (the recorded code re-run on the re-run's engine)."""
    rows_in = [(key, name, exports[key]) for key, name in REPRODUCTION]
    stat_names = list(exports[BASE_KEY]["statistics"])
    for key, _, export in rows_in:
        if list(export["statistics"]) != stat_names:
            raise SystemExit(f"{key}: statistics differ in name or order from {BASE_KEY}")
    trades = {key: trade_keys(export) for key, _, export in rows_in}
    orders = {key: order_keys(export) for key, _, export in rows_in}

    def identical(a: str, b: str) -> bool:
        return trades[a] == trades[b] and orders[a] == orders[b]

    rows = []
    for key, name, export in rows_in:
        code = python_files(export)
        row = {
            "key": key,
            "run": name,
            "project_id": export["meta"]["projectId"],
            "backtest_id": export["meta"]["backtestId"],
            "created": export["meta"]["created"],
            "lean_version": lean_version(export, engines),
            "code_files": "; ".join(code),
            "code_sha256_as_run": "; ".join(f"{n}:{code_hash(hashes, key, n)['as_run']}"
                                            for n in code),
            "code_sha256_published": "; ".join(f"{n}:{sha256(t.encode('utf-8'))}"
                                               for n, t in code.items()),
        }
        row.update({snake(s): export["statistics"][s] for s in stat_names})
        row["closed_trades"] = len(export.get("closedTrades") or [])
        row["orders"] = len(export.get("orders") or [])
        row["trades_identical_to_recorded"] = identical(key, BASE_KEY)
        row["trades_identical_to_rerun"] = identical(key, RERUN_KEY)
        rows.append(row)
    emit("checks/reproduction/comparison.csv", write_csv, pd.DataFrame(rows))
    emit("checks/reproduction/README.md", write_text,
         reproduction_readme(rows_in, stat_names, trades, orders, engines, runs, hashes))


def reproduction_readme(rows_in, stat_names, trades, orders, engines, runs, hashes) -> str:
    ex = {key: export for key, _, export in rows_in}
    base, rerun, control = ex[BASE_KEY], ex[RERUN_KEY], ex[CONTROL_KEY]
    v = {key: lean_version(export, engines) for key, export in ex.items()}
    n_stats = len(stat_names)
    lines = [
        "# Reproduction of the base run",
        "",
        "Written by `analysis/build_results.py` from the exports in `results/raw/`; a rebuild "
        "overwrites it. `comparison.csv` holds the full comparison, one row per run.",
        "",
        "The base run in `base_2016_2024/` was recorded before the strategy code was split into "
        "`main.py` and `dcf_model.py`. Two later backtests test whether the split changed "
        "anything:",
        "",
        "| Run | Key | QuantConnect project / backtest | Created | LEAN | Code that ran |",
        "|---|---|---|---|---|---|",
    ]
    for key, name, export in rows_in:
        meta = export["meta"]
        lines.append(f"| {name} | `{key}` | {meta['projectId']} / `{meta['backtestId']}` | "
                     f"{meta['created']} | {v[key] or 'not recorded'} | "
                     f"{code_cell(key, export, hashes)} |")
    same_code = (code_hash(hashes, CONTROL_KEY)["as_run"] == code_hash(hashes, BASE_KEY)["as_run"])
    rewritten = any(code_hash(hashes, key, name)["names_removed"]
                    for key, _, export in rows_in for name in python_files(export))
    lines += [
        "",
        "- The refactored re-run ran this repository's `main.py` and `dcf_model.py` with the base "
        "parameters (the code defaults; no project parameters were passed). The hashes above are "
        "the SHA-256 of each file as it ran on QuantConnect, from "
        "`results/provenance/code_hashes.json`."
        + (" In the published copies in `results/raw/` and in this repository, one docstring "
           "paragraph was rewritten to leave out the names of the other 2024 team members; "
           "`comparison.csv` gives both hashes of each file." if rewritten else ""),
        "- The control ran the recorded run's `main.py` "
        + ("(the same SHA-256) " if same_code else "")
        + "again, in a separate QuantConnect project, on the same engine build as the re-run. A "
        "difference that appears in both the re-run and the control comes from QuantConnect's "
        "side, not from the code.",
        "- Created is the creation time QuantConnect records for each backtest.",
        "",
        "## LEAN versions",
        "",
    ]
    if v[BASE_KEY] and v[RERUN_KEY] and v[BASE_KEY] != v[RERUN_KEY]:
        lines.append(f"QuantConnect upgraded LEAN between the recorded run ({v[BASE_KEY]}) and the "
                     f"re-runs ({v[RERUN_KEY]}).")
    lines += [
        "The re-runs' exports carry the version in their server statistics. The exports of the "
        "original runs do not; their versions come from `raw/engines__original_runs.json.gz`, a "
        "separate export of the server statistics of each original backtest. `runs.csv` gives "
        "the version of every run:",
        "",
        "| LEAN | Runs | Created |",
        "|---|---|---|",
    ]
    for version, group in runs.groupby(runs["lean_version"].fillna(""), sort=True):
        created = sorted(str(c)[:10] for c in group["created"])
        span = created[0] if created[0] == created[-1] else f"{created[0]} to {created[-1]}"
        keys = ", ".join(f"`{k}`" for k in group["key"])
        lines.append(f"| {version or 'not recorded'} | {keys} | {span} |")
    sens = runs[runs["key"].str.startswith("dcf__sens_")]
    counts = sens.groupby("lean_version").size()
    if len(counts) > 1:
        parts = [f"{n} {'ran ' if i == 0 else ''}on {version}"
                 for i, (version, n) in enumerate(counts.items())]
        lines += ["", f"Of the {len(sens)} sensitivity runs, {' and '.join(parts)}; none was "
                  f"re-run on another build."]

    n_orders, n_trades = len(orders[BASE_KEY]), len(trades[BASE_KEY])
    status = Counter(o["status"] for o in base.get("orders") or [])
    status_text = ", ".join(
        f"{n:,} {'cancelled' if s == 5 else ORDER_STATUS.get(s, str(s)).lower()}"
        for s, n in sorted(status.items()))
    lines += ["", "## Result", ""]
    all_same = all(trades[k] == trades[BASE_KEY] and orders[k] == orders[BASE_KEY] for k in ex)
    if all_same:
        lines.append(
            f"Orders and trades are identical in the three runs: all {n_orders:,} orders "
            f"({status_text}) match in time, symbol, quantity and status, in order-id order, "
            f"and all {n_trades:,} closed trades match in symbol, entry time, exit time, quantity "
            f"and profit.")
    else:
        for key, name, _ in rows_in[1:]:
            lines.append(
                f"- {name} against the recorded run: {unmatched(trades[key], trades[BASE_KEY]):,} "
                f"closed trades and {unmatched(orders[key], orders[BASE_KEY]):,} orders without "
                f"a match ({len(trades[key]):,} against {n_trades:,} trades, {len(orders[key]):,} "
                f"against {n_orders:,} orders).")

    def stat(export: dict, name: str) -> str:
        return export["statistics"][name]

    differ = [s for s in stat_names if len({stat(e, s) for e in ex.values()}) > 1]
    rerun_vs_control = [s for s in stat_names if stat(rerun, s) != stat(control, s)]
    lines.append("")
    if not rerun_vs_control:
        first = f"The re-run and the control agree on all {n_stats} QuantConnect statistics."
    else:
        first = (f"The re-run and the control differ on {len(rerun_vs_control)} of the "
                 f"{n_stats} statistics: {', '.join(rerun_vs_control)}.")
    if differ:
        lines += [
            f"{first} Across the three runs, {n_stats - len(differ)} of the {n_stats} are the "
            f"same and {len(differ)} differ:",
            "",
            f"| Statistic | Recorded ({v[BASE_KEY]}) | Re-run ({v[RERUN_KEY]}) | "
            f"Control ({v[CONTROL_KEY]}) |",
            "|---|---|---|---|",
        ]
        for s in differ:
            lines.append(f"| {s} | {stat(base, s)} | {stat(rerun, s)} | {stat(control, s)} |")
    else:
        lines.append(f"{first} All {n_stats} are the same in the three runs.")

    if all_same and not rerun_vs_control:
        lines += [
            "",
            "The refactor changed nothing: the refactored code and the recorded code produce the "
            "same orders, trades and statistics on the same engine build."
            + (f" The control shows the same new values for the {len(differ)} statistics that "
               f"changed, so the change comes from QuantConnect's side between the recorded run "
               f"and the re-runs, not from the code." if differ else ""),
        ]
    pb, pr = base.get("portfolioStatistics") or {}, rerun.get("portfolioStatistics") or {}
    moved = [k for k in pb if pb.get(k) != pr.get(k)]
    if differ and moved:
        text = ", ".join(f"`{k}` {pb[k]} to {pr[k]}" for k in moved)
        lines += ["", f"At four decimals, QuantConnect's portfolio statistics show the same "
                      f"shift: {text}."]
        rf_based = {"sharpeRatio", "sortinoRatio", "probabilisticSharpeRatio", "treynorRatio"}
        if set(moved) <= rf_based:
            lines[-1] += (
                " Return, volatility, drawdown and beta are unchanged, and every statistic that "
                "moved is built on the return in excess of the risk-free rate (the probabilistic "
                "Sharpe ratio through the Sharpe ratio). That suggests the risk-free rate the "
                "statistics use differs between the two builds; the exports do not show that "
                "rate, so this is not confirmed.")
    lines += [
        "",
        "## comparison.csv",
        "",
        "| Column | Meaning |",
        "|---|---|",
        "| `key`, `run` | Raw export key and the run's role |",
        "| `project_id`, `backtest_id`, `created` | QuantConnect identifiers and creation time |",
        "| `lean_version` | LEAN build the backtest ran on |",
        "| `code_files` | The Python files QuantConnect stored with the backtest "
        "(`research.ipynb`, QuantConnect's default notebook, does not run in a backtest and is "
        "left out) |",
        "| `code_sha256_as_run`, `code_sha256_published` | SHA-256 of each file as it ran on "
        "QuantConnect (from `results/provenance/code_hashes.json`) and of the published copy in "
        "`results/raw/` |",
        f"| `total_orders` to `drawdown_recovery` | QuantConnect's {n_stats} statistics, exactly "
        "as the export gives them (text, with QuantConnect's rounding and units) |",
        "| `closed_trades`, `orders` | Length of the exported closed-trade and order lists |",
        "| `trades_identical_to_recorded`, `trades_identical_to_rerun` | True when both the "
        "closed trades (symbol, entry time, exit time, quantity, profit; compared as sorted "
        "lists) and the orders (time, symbol, quantity, status; in order-id order) equal those "
        "of the recorded run or of the re-run |",
        "",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- checks: data
CAP_LINE = re.compile(
    r"(\d{4}-\d{2}-\d{2}) (\S+) px (-?[\d.]+) adj (-?[\d.]+) mcap (-?[\d.]+) "
    r"sh (-?[\d.]+) pxsh (-?[\d.]+)")
CAP_COLUMNS = ["date", "ticker", "price_unadjusted", "price_adjusted", "market_cap_bn",
               "shares_outstanding_bn", "price_x_shares_bn"]


def log_lines(logs) -> list[str]:
    """The export's log field as a list of lines (it may be a list or one string)."""
    if not logs:
        return []
    if isinstance(logs, str):
        return [line for line in logs.splitlines() if line.strip()]
    return [item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
            for item in logs]


def parse_cap_log(lines: list[str]) -> pd.DataFrame:
    """The cap probe's log lines (see results/checks/data/code/cap_probe_main.py) as a table.
    Lines that do not match the probe's format are ignored."""
    rows = []
    for line in lines:
        match = CAP_LINE.search(line)
        if match:
            date, ticker, *values = match.groups()
            rows.append([date, ticker, *(float(x) for x in values)])
    return pd.DataFrame(rows, columns=CAP_COLUMNS)


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def cap_probe_summary(table: pd.DataFrame) -> list[str]:
    """Markdown lines on the cap probe's table: on which weekdays the lines fall, and per name
    the first market_cap, when it first changed, how close rolling the first value forward
    with the adjusted price comes to the new one, and how the logged share count compares
    with the one implied by the first line (market_cap / unadjusted price)."""
    if table.empty:
        return []
    dates = pd.to_datetime(pd.Series(sorted(table["date"].unique())))
    present = set(dates.dt.day_name())
    days = [d for d in WEEKDAYS if d in present]
    day_text = days[0] if len(days) == 1 else f"{', '.join(days[:-1])} or {days[-1]}"
    lines = [
        f"The lines fall on {len(dates)} dates, each a {day_text}; a line is dated by the "
        f"selection call that wrote it.",
        "",
        "| Ticker | `market_cap` on the first line, bn | Held until | Changed on | Changed to, bn "
        "| First value rolled forward with the adjusted price, bn | Rolled value against the new "
        "one | Logged shares, change over the same lines | Logged shares / (`market_cap` / price) "
        "on the first line |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    restated = []
    for ticker, group in table.groupby("ticker", sort=False):
        group = group.sort_values("date").reset_index(drop=True)
        first = group.iloc[0]
        same = group[group["market_cap_bn"] == first["market_cap_bn"]]
        changed = group[group["market_cap_bn"] != first["market_cap_bn"]]
        ratio = first["shares_outstanding_bn"] / (first["market_cap_bn"] / first["price_unadjusted"])
        cells = [ticker, f"{first['market_cap_bn']:.2f}", same["date"].iloc[-1]]
        if changed.empty:
            cells += ["not in the log", "", "", "", ""]
        else:
            new = changed.iloc[0]
            rolled = first["market_cap_bn"] * new["price_adjusted"] / first["price_adjusted"]
            shares = new["shares_outstanding_bn"] / first["shares_outstanding_bn"] - 1.0
            cells += [new["date"], f"{new['market_cap_bn']:.2f}", f"{rolled:.2f}",
                      f"{(rolled / new['market_cap_bn'] - 1.0) * 100:+.2f}%", f"{shares * 100:+.2f}%"]
        cells.append(f"{ratio:.4f}")
        lines.append("| " + " | ".join(cells) + " |")
        if round(ratio, 3) > 1 and round(ratio, 3) == round(ratio):
            restated.append(f"{ticker} ({round(ratio)} times)")
    if restated:
        lines += [
            "",
            f"A whole-number ratio above 1 means the logged share count is that multiple of the "
            f"one behind `market_cap`, which is what a share count restated for a later split "
            f"looks like: {', '.join(restated)}.",
        ]
    return lines


def probe_month(seconds: int, previous: bool) -> tuple[int, int]:
    """(year, month) of a probe chart point. The monthly Caps and Calls points are plotted
    when the next month starts (the last one at the end of the backtest), so they belong to
    the month before their New York timestamp; the EBITDA growth points are plotted at the
    first data point of their own month."""
    ts = pd.Timestamp(seconds, unit="s", tz="UTC").tz_convert(NY)
    year, month = ts.year, ts.month
    if previous:
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return year, month


def probe_rows(export: dict, points: dict[str, list], previous: bool) -> list[dict]:
    """Rows (year, month, one column per series) from probe chart series. Every series must
    share the same timestamps, and every month must fall in the probe's year exactly once."""
    key = export["meta"]["key"]
    times = [[int(p[0]) for p in pts] for pts in points.values()]
    if any(t != times[0] for t in times):
        raise SystemExit(f"{key}: probe series do not share timestamps")
    year = int((export.get("parameterSet") or {}).get("year"))
    rows = []
    for i, t in enumerate(times[0]):
        y, m = probe_month(t, previous)
        row = {"year": y, "month": m}
        row.update({column: float(pts[i][1]) for column, pts in points.items()})
        rows.append(row)
    months = [(r["year"], r["month"]) for r in rows]
    if len(set(months)) != len(months) or any(y != year for y, _ in months):
        raise SystemExit(f"{key}: probe months {months} do not fit the year {year}")
    return rows


def fmt_share(x: float) -> str:
    return f"{x * 100:.1f}%"


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def build_data_checks(emit, exports: dict, engines: dict) -> None:
    """results/checks/data: what the probe backtests show about two Morningstar fields."""
    probes = [exports[k] for k in PROBE_KEYS]
    cap = exports[CAP_PROBE_KEY]

    growth, caps = [], []
    for export in probes:
        charts = export["charts"]
        growth += probe_rows(export, {
            "median_one_year": charts["EBITDA growth"]["median one_year"],
            "p90_abs_one_year": charts["EBITDA growth"]["p90 of absolute value"],
        }, previous=False)
        caps += probe_rows(export, {
            "cap_unchanged_share": charts["Caps"]["cap unchanged share"],
            "cap_moved_with_price_share": charts["Caps"]["cap moved with price share"],
            "price_moved_cap_unchanged_share": charts["Caps"]["price moved, cap unchanged share"],
            "calls_per_day": charts["Calls"]["on_data calls per day"],
            "hour_of_first_call": charts["Calls"]["hour of first call"],
        }, previous=True)
    growth_df = pd.DataFrame(growth).sort_values(["year", "month"]).reset_index(drop=True)
    caps_df = pd.DataFrame(caps).sort_values(["year", "month"]).reset_index(drop=True)
    emit("checks/data/ebitda_growth_monthly.csv", write_csv, growth_df)
    emit("checks/data/market_cap_updates.csv", write_csv, caps_df)

    probe_code = {code_of(e) for e in probes}
    if len(probe_code) != 1:
        raise SystemExit("the two probe exports ran different code")
    emit("checks/data/code/probe_main.py", write_text, probe_code.pop())
    emit("checks/data/code/cap_probe_main.py", write_text, code_of(cap))

    lines = log_lines(cap.get("logs"))
    cap_table = parse_cap_log(lines)
    if lines:
        emit("checks/data/cap_probe_2019.log", write_text, "\n".join(lines) + "\n")
        emit("checks/data/cap_probe_2019.csv", write_csv, cap_table)

    emit("checks/data/README.md", write_text,
         data_readme(probes, cap, engines, growth_df, caps_df, lines, cap_table))


def data_readme(probes, cap, engines, growth, caps, lines, cap_table) -> str:
    out = [
        "# Data checks",
        "",
        "Written by `analysis/build_results.py` from the exports in `results/raw/`; a rebuild "
        "overwrites it.",
        "",
        "Two assumptions about the Morningstar fields the DCF reads were tested with probe "
        "backtests on QuantConnect that place no orders:",
        "",
        "1. `operation_ratios.ebitda_growth.one_year` is a decimal fraction (0.10 means 10%). "
        "The DCF bounds its growth rate to -0.05 and 0.15 on that assumption.",
        "2. `market_cap` is a capitalisation for the day it is read. The DCF ranks its universe "
        "by this field and divides the equity value by it.",
        "",
        "| Backtest | Key | QuantConnect project / backtest | Created | LEAN | Period |",
        "|---|---|---|---|---|---|",
    ]
    for export, name in [(probes[0], "Probe"), (probes[1], "Probe"), (cap, "Cap probe")]:
        meta = export["meta"]
        out.append(f"| {name} | `{meta['key']}` | {meta['projectId']} / `{meta['backtestId']}` | "
                   f"{meta['created']} | {lean_version(export, engines)} | "
                   f"{meta['backtestStart'][:10]} to {meta['backtestEnd'][:10]} |")
    out += [
        "",
        "The probe (`code/probe_main.py`, one backtest per year through its `year` parameter) "
        "holds the 100 largest primary shares by `market_cap` with a price above $1 and "
        "aggregates what it sees to one chart point per month, because a free-tier backtest "
        "keeps few chart points. A first version of the probe had no once-per-day guard and "
        "counted repeat calls on the same day; it was discarded, and `probe2` is the corrected "
        "version. `../backtest_lists.csv` lists its two backtests and an earlier run of the cap "
        "probe, none of them exported.",
        "",
        "| File | Contents |",
        "|---|---|",
        "| `ebitda_growth_monthly.csv` | Median and 90th percentile of the absolute value of "
        "`ebitda_growth.one_year` across the probe's names, per month |",
        "| `market_cap_updates.csv` | How often `market_cap` changed from one day to the next, "
        "per month |",
    ]
    if lines:
        out += [
            "| `cap_probe_2019.csv` | The cap probe's log, one row per name and day |",
            "| `cap_probe_2019.log` | The cap probe's log lines as exported |",
        ]
    out += [
        "| `code/probe_main.py` | The probe's code as QuantConnect stored it (identical in both "
        "probe backtests) |",
        "| `code/cap_probe_main.py` | The cap probe's code as QuantConnect stored it |",
        "",
        "## EBITDA growth",
        "",
        "`ebitda_growth_monthly.csv`: `year`, `month`, `median_one_year`, `p90_abs_one_year`. At "
        "the first data point of each month the probe takes `ebitda_growth.one_year` of every name it "
        "holds (missing, NaN and zero values left out) and plots the median and the 90th "
        "percentile of the absolute value.",
        "",
    ]
    parts = []
    for year, g in growth.groupby("year", sort=True):
        parts.append(f"between {g['median_one_year'].min():.3f} and "
                     f"{g['median_one_year'].max():.3f} in {year}")
    med = growth["median_one_year"].median()
    p90_max = growth["p90_abs_one_year"].max()
    out.append(
        f"The monthly median lies {' and '.join(parts)}; the 90th percentile of the absolute "
        f"value lies between {growth['p90_abs_one_year'].min():.3f} and {p90_max:.3f}. Read as "
        f"fractions, the median company grew EBITDA by about {med * 100:.0f}% over the previous "
        f"year. Read as percentages, it would have grown by {med:.2f}% and nine in ten would have "
        f"moved by less than {p90_max:.2f}% either way, far too flat for company earnings. The "
        f"field is a decimal fraction, and the DCF's growth bounds apply as intended.")

    later = caps[caps["month"] > 1]
    january = caps[caps["month"] == 1]
    moved = caps[caps["cap_moved_with_price_share"] > 0]
    if moved.empty:
        moved_text = "The cap never moved in step with the price."
    else:
        where = ", ".join(f"{MONTHS[int(r.month) - 1]} {int(r.year)} "
                          f"({r.cap_moved_with_price_share * 100:.2f}% of comparisons)"
                          for r in moved.itertuples())
        moved_text = (f"The cap moved in step with the price in no comparison in "
                      f"{len(caps) - len(moved)} of the {len(caps)} months; the exception is "
                      f"{where}.")
    if (january["cap_unchanged_share"] == 1.0).all():
        january_text = (f"In January the share unchanged is exactly 1.0 in "
                        f"{'both years' if len(january) == 2 else 'every year'}.")
    else:
        january_text = "In January the share unchanged is " + ", ".join(
            f"{r.cap_unchanged_share:.4f} in {int(r.year)}" for r in january.itertuples()) + "."
    out += [
        "",
        "## Market cap updates",
        "",
        "`market_cap_updates.csv`: one row per month. At the first data point of each day the probe "
        "compares every name's `market_cap` and price with the values it saw on the previous "
        "day.",
        "",
        "| Column | Meaning |",
        "|---|---|",
        "| `year`, `month` | The month the comparisons fall in |",
        "| `cap_unchanged_share` | Share of comparisons in which the cap did not change |",
        "| `cap_moved_with_price_share` | Share in which the cap changed by the same ratio as the "
        "price (within 1e-6), as price times shares would |",
        "| `price_moved_cap_unchanged_share` | Share in which the price changed and the cap did "
        "not |",
        "| `calls_per_day` | Mean number of `on_data` calls per day |",
        "| `hour_of_first_call` | Mean New York hour of the day's first `on_data` call |",
        "",
        "QuantConnect stores each monthly point when the next month starts (the last one at the "
        "end of the backtest), so the build assigns each point to the month before its "
        "timestamp.",
        "",
        f"From February to December, between {fmt_share(later['cap_unchanged_share'].min())} and "
        f"{fmt_share(later['cap_unchanged_share'].max())} of the comparisons in a month found the "
        f"cap unchanged, while in {fmt_share(later['price_moved_cap_unchanged_share'].min())} to "
        f"{fmt_share(later['price_moved_cap_unchanged_share'].max())} the price had moved and the "
        f"cap had not. {moved_text} {january_text} That pattern fits a value that changes once "
        f"a month, at the start of the month: the probe starts on 1 January, so January's "
        f"comparisons contain no such change, and in later months about one comparison in "
        f"{round(1.0 / (1.0 - later['cap_unchanged_share'].mean()))} finds a change, roughly one "
        f"per name per month (a month has about 21 trading days).",
        "",
        f"`on_data` ran {caps['calls_per_day'].min():.2f} to {caps['calls_per_day'].max():.2f} "
        f"times a day on average in a month, which is why the probe compares only at the first "
        f"call of each day.",
        "",
        "So `market_cap` is not price times shares on each day: it holds a value that is "
        "refreshed about once a month. The DCF reads it for its universe ranking, at the first "
        "universe selection of each month, and for the upside ratio, at the rebalance on the "
        "first trading day; `docs/data-checks.md` describes when those two reads fall on "
        "different sides of the refresh.",
        "",
        "## Cap probe",
        "",
        "The cap probe (`code/cap_probe_main.py`) logs, for AAPL, MSFT and XOM at every universe "
        "selection call of its run, the unadjusted price, the adjusted price, `market_cap`, "
        "`company_profile.shares_outstanding` and unadjusted price times shares.",
        "",
    ]
    if lines:
        out.append(
            f"`cap_probe_2019.log` holds the {len(lines)} exported log lines; `cap_probe_2019.csv` "
            f"parses the {len(cap_table)} that match the probe's format into `date`, `ticker`, "
            f"`price_unadjusted`, `price_adjusted`, `market_cap_bn`, `shares_outstanding_bn` and "
            f"`price_x_shares_bn` (billions, as logged).")
        out += ["", *cap_probe_summary(cap_table)]
    else:
        out.append(
            "The export of this backtest holds no log lines (its `logs` list is empty), so "
            "`cap_probe_2019.csv` and `cap_probe_2019.log` are not written. The build writes them "
            "once an export that contains the log lines is imported.")
    out.append("")
    return "\n".join(out)


# ----------------------------------------------------------------------------- checks: backtest lists
LIST_COLUMNS = [
    "project_id", "project_name", "backtest_id", "name", "created", "completed", "status",
    "error", "parameters", "net_profit", "sharpe", "max_drawdown", "orders", "published_as",
]
FATAL_HEADER = "[ERROR] FATAL UNHANDLED EXCEPTION"


def first_line(text: str | None) -> str:
    """First non-empty line of a QuantConnect message, HTML entities decoded, whitespace
    collapsed."""
    for line in html.unescape(text or "").splitlines():
        if line.strip():
            return " ".join(line.split())
    return ""


def error_line(bt: dict) -> str:
    """First line of the backtest's error. When that line is only QuantConnect's fatal-error
    header followed by a fragment of the trace, the first line of the stack trace instead."""
    line = first_line(bt.get("error"))
    if line.startswith(FATAL_HEADER):
        return first_line(bt.get("stacktrace")) or line
    return line


def list_reason(project_id: int, bt: dict, final: dict | None) -> str | None:
    """Why a listed backtest is not published: from NOT_PUBLISHED, or for the 2024 prototype
    by rule (`final` is the prototype's published run). None when there is no reason."""
    if bt["backtestId"] in NOT_PUBLISHED:
        return NOT_PUBLISHED[bt["backtestId"]]
    if project_id != PROTOTYPE_PROJECT:
        return None
    if bt.get("error") or bt.get("status") != "Completed.":
        stage = ("at initialisation" if "initiali" in (bt.get("error") or "").lower()
                 else "during the backtest")
        after = f" after {bt['trades']} orders" if bt.get("trades") else ""
        return f"not published: 2024 prototype run that stopped with an error {stage}{after}"
    text = "not published: earlier completed run of the 2024 prototype"
    headline = ("netProfit", "sharpeRatio", "drawdown", "trades")
    if final and all(bt.get(k) == final.get(k) for k in headline):
        text += ", same headline statistics as the published final run"
    return text + "; not exported, so its code and orders are not in the repository"


def build_backtest_lists(emit, exports: dict) -> None:
    """results/checks/backtest_lists.csv: every backtest QuantConnect lists in the projects
    that concern this repository, with the published key or the reason it is not published.
    Fails when a project's list is incomplete, when a listed statistic disagrees with the
    published export, when a published backtest is missing from the list, or when a backtest
    is neither published nor explained."""
    projects = exports[LISTS_KEY]["projects"]
    published = {e["meta"]["backtestId"]: e for k, e in exports.items()
                 if isinstance(e, dict) and "meta" in e and k != ENGINES_KEY}
    listed = set()
    rows = []
    for pid in LIST_PROJECTS:
        project = projects.get(str(pid))
        if project is None:
            raise SystemExit(f"backtest list: project {pid} is missing")
        backtests = sorted(project["backtests"], key=lambda b: (b["created"], b["backtestId"]))
        if project.get("count") != len(backtests):
            raise SystemExit(f"backtest list: project {pid} counts {project.get('count')} "
                             f"backtests and lists {len(backtests)}")
        if not backtests:
            rows.append({"project_id": pid, "project_name": project["name"],
                         "published_as": "no backtests: QuantConnect lists none in this project"})
            continue
        final = next((b for b in backtests if b["backtestId"] in published), None)
        for bt in backtests:
            bid = bt["backtestId"]
            listed.add(bid)
            if bt.get("projectId") != pid:
                raise SystemExit(f"backtest list: {bid} is filed under {pid} but names "
                                 f"project {bt.get('projectId')}")
            export = published.get(bid)
            if export is not None:
                meta, stats = export["meta"], export.get("statistics") or {}
                if meta["created"] != bt["created"] or meta["projectId"] != pid:
                    raise SystemExit(f"backtest list: {bid} disagrees with {meta['key']} on "
                                     f"creation time or project")
                pairs = [("netProfit", "Net Profit"), ("sharpeRatio", "Sharpe Ratio"),
                         ("drawdown", "Drawdown"), ("trades", "Total Orders")]
                for list_name, stat_name in pairs:
                    a, b = bt.get(list_name), num(stats.get(stat_name))
                    if a is not None and b is not None and abs(float(a) - b) > 1e-9:
                        raise SystemExit(f"backtest list: {bid} {list_name} {a} against "
                                         f"{meta['key']} {stat_name} {b}")
                published_as = meta["key"]
            else:
                published_as = list_reason(pid, bt, final)
                if published_as is None:
                    raise SystemExit(f"backtest list: {bid} ({bt['name']}) in project {pid} "
                                     f"is neither published nor explained")
            passed = bt.get("parameterSet") or {}
            params = "; ".join(f"{k}={v}" for k, v in passed.items()) if isinstance(passed, dict) else ""
            rows.append({
                "project_id": pid,
                "project_name": project["name"],
                "backtest_id": bid,
                "name": bt["name"],
                "created": bt["created"],
                "completed": bt.get("completed"),
                "status": bt.get("status"),
                "error": error_line(bt),
                "parameters": params,
                "net_profit": bt.get("netProfit"),
                "sharpe": bt.get("sharpeRatio"),
                "max_drawdown": bt.get("drawdown"),
                "orders": bt.get("trades"),
                "published_as": published_as,
            })
    missing = sorted(e["meta"]["key"] for bid, e in published.items()
                     if e["meta"]["projectId"] in LIST_PROJECTS and bid not in listed)
    if missing:
        raise SystemExit(f"backtest list: published runs not in the list: {', '.join(missing)}")
    table = pd.DataFrame(rows, columns=LIST_COLUMNS)
    for column in ("net_profit", "sharpe", "max_drawdown"):
        table[column] = table[column].astype("Float64")
    table["orders"] = table["orders"].astype("Int64")
    emit("checks/backtest_lists.csv", write_csv, table)


# ----------------------------------------------------------------------------- check
def is_derived(rel: Path) -> bool:
    if rel.parts and rel.parts[0] == "raw":
        return False
    if rel.parts and rel.parts[0] == "checks":
        return True
    return rel.name in DERIVED_NAMES or (rel.name == "main.py" and rel.parent.name == "code")


def normalised(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def check() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        built = build(fresh)
        for rel in sorted(built):
            committed = RESULTS / rel
            if not committed.exists():
                problems.append(f"missing: results/{rel}")
                continue
            new, old = normalised(fresh / rel), normalised(committed)
            if new != old:
                new_lines, old_lines = new.split(b"\n"), old.split(b"\n")
                line = next((i + 1 for i, (a, b) in enumerate(zip(new_lines, old_lines))
                             if a != b), min(len(new_lines), len(old_lines)) + 1)
                problems.append(f"differs: results/{rel} (first difference at line {line})")
        built_set = set(built)
        for path in sorted(RESULTS.rglob("*")):
            rel = path.relative_to(RESULTS)
            if path.is_file() and is_derived(rel) and rel.as_posix() not in built_set:
                problems.append(f"not produced by the build: results/{rel.as_posix()}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for rel, entry in manifest.get("reports", {}).items():
        path = RESULTS / rel
        if not path.exists():
            problems.append(f"missing: results/{rel}")
        elif sha256(normalised(path)) != entry["sha256"]:
            problems.append(f"hash mismatch: results/{rel}")
    for rel, entry in manifest.get("provenance", {}).items():
        path = RESULTS / rel
        if not path.exists():
            problems.append(f"missing: results/{rel}")
        elif sha256(normalised(path)) != entry["sha256"]:
            problems.append(f"hash mismatch: results/{rel}")
    if problems:
        print("results/ does not match a fresh build:")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"OK: {len(built)} derived files match a fresh build from results/raw; "
          f"{len(manifest['files'])} raw files, {len(manifest.get('reports', {}))} "
          f"reports and {len(manifest.get('provenance', {}))} provenance file match MANIFEST.json")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--import-from", type=Path,
                        help="directory holding the raw QuantConnect exports (first run only)")
    parser.add_argument("--check", action="store_true",
                        help="rebuild into a temporary directory and compare with results/")
    args = parser.parse_args()
    if args.check:
        return check()
    if args.import_from:
        import_exports(args.import_from)
    written = build(RESULTS)
    print(f"wrote {len(written)} derived files under {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
