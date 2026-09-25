"""Draw the README figures from the derived CSVs in results/ (never from the raw exports).

    python analysis/make_figures.py

Writes figures/equity_vs_spy.png, annual_returns.png, sensitivity.png and prototype_2023.png
at 150 dpi on an opaque white background, so they read the same on GitHub's light and dark
themes. Every number in a title or label is read from results/.
"""

from __future__ import annotations

from pathlib import Path

import logging

import matplotlib

matplotlib.use("Agg")
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results"
FIGURES = REPO / "figures"
DPI = 150

# Categorical slots 1 to 3 of the dataviz reference palette (validated all-pairs, light mode),
# plus its light-mode ink and chrome.
STRATEGY = "#2a78d6"
SPY = "#eb6834"
BASKET = "#1baf7a"
OTHER = "#b9b8b1"
SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.size": 10,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "grid.linestyle": "-",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2,
    "legend.frameon": False,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})

LINE = 1.6


def read(rel: str) -> pd.DataFrame:
    return pd.read_csv(RESULTS / rel)


def dates(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["date"])


def heading(fig, title: str, subtitle: str) -> None:
    fig.text(0.012, 0.975, title, ha="left", va="top", fontsize=13.5, fontweight="bold",
             color=INK)
    fig.text(0.012, 0.922, subtitle, ha="left", va="top", fontsize=9.5, color=INK_2)


def source_note(fig, text: str) -> None:
    fig.text(0.012, 0.012, text, ha="left", va="bottom", fontsize=8, color=MUTED)


def clean(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)


def dollars(x, _pos) -> str:
    return f"${x:,.0f}"


def percent(x, _pos) -> str:
    return f"{x:+.0f}%" if x else "0%"


def end_labels(ax, items: list[tuple], min_gap_pt: float = 13.0) -> None:
    """Dot at each series end and a label beside it. items are (x, y, text, color). Labels
    that would overlap are pushed apart vertically; the dots stay on the data."""
    ax.get_ylim()  # settle autoscaling before reading the transform
    px_per_pt = ax.figure.dpi / 72.0
    ys = [ax.transData.transform((0, y))[1] for _x, y, _t, _c in items]
    order = sorted(range(len(items)), key=lambda i: ys[i])
    placed: dict[int, float] = {}
    previous = None
    for i in order:
        pos = ys[i] if previous is None else max(ys[i], previous + min_gap_pt * px_per_pt)
        placed[i] = pos
        previous = pos
    shift = (sum(placed.values()) - sum(ys)) / len(items)  # re-centre the block on the data
    for i, (x, y, text, color) in enumerate(items):
        ax.plot([x], [y], "o", ms=5.5, color=color, mec=SURFACE, mew=1.5, zorder=5)
        dy = (placed[i] - shift - ys[i]) / px_per_pt
        ax.annotate(text, (x, y), xytext=(8, dy), textcoords="offset points", va="center",
                    ha="left", fontsize=9.5, color=INK)


def save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / name, dpi=DPI)
    plt.close(fig)
    print(f"wrote figures/{name}")


# ----------------------------------------------------------------------------- figures
def equity_vs_spy(runs: pd.DataFrame) -> None:
    eq = read("base_2016_2024/equity.csv")
    base = runs.set_index("key").loc["dcf__base"]
    t = dates(eq)
    start = eq["equity"].iloc[0]
    spy = eq["spy_benchmark"] / eq["spy_benchmark"].iloc[0] * start
    # Both drawdowns are measured the same way, from peaks among the chart samples. SPY is only
    # available at the samples; QuantConnect's own drawdown column takes its peaks from the full
    # daily record, so it is not comparable with SPY's.
    spy_dd = (eq["spy_benchmark"] / eq["spy_benchmark"].cummax() - 1.0) * 100.0
    dd = (eq["equity"] / eq["equity"].cummax() - 1.0) * 100.0
    worst = dd.idxmin()
    sampled = (eq["equity"].iloc[-1] / start - 1.0) * 100.0
    first_day, last_day = pd.Timestamp(eq["date"].iloc[0]), pd.Timestamp(eq["date"].iloc[-1])

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 6.4), sharex=True,
                                      gridspec_kw={"height_ratios": [3, 1.25], "hspace": 0.08})
    fig.subplots_adjust(left=0.085, right=0.86, top=0.84, bottom=0.1)
    top.plot(t, spy, color=SPY, lw=LINE, label="SPY, dividend-adjusted")
    top.plot(t, eq["equity"], color=STRATEGY, lw=LINE, label="DCF screen, base parameters")
    top.yaxis.set_major_formatter(FuncFormatter(dollars))
    top.set_ylabel("Value of $100,000")
    top.set_ylim(bottom=0)
    top.legend(loc="upper left", fontsize=9.5)
    end_labels(top, [(t.iloc[-1], spy.iloc[-1], "SPY", SPY),
                     (t.iloc[-1], eq["equity"].iloc[-1], "DCF screen", STRATEGY)])
    clean(top)

    bottom.fill_between(t, dd, 0, color=STRATEGY, alpha=0.10, lw=0)
    bottom.plot(t, spy_dd, color=SPY, lw=1.1)
    bottom.plot(t, dd, color=STRATEGY, lw=1.1)
    bottom.set_ylabel("Drawdown")
    bottom.yaxis.set_major_formatter(FuncFormatter(lambda x, _p: f"{x:.0f}%"))
    bottom.annotate(f"{dd.iloc[worst]:.1f}% ({pd.Timestamp(eq['date'].iloc[worst]):%b %Y})",
                    (t.iloc[worst], dd.iloc[worst]), xytext=(10, 2),
                    textcoords="offset points", fontsize=9, color=INK, va="center")
    bottom.xaxis.set_major_locator(mdates.YearLocator())
    bottom.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    clean(bottom)

    heading(fig,
            f"DCF screen {sampled:+.1f}% against SPY {base['spy_total_return']:+.1f}%, "
            f"{first_day.day} {first_day:%b %Y} to {last_day.day} {last_day:%b %Y}",
            f"Growth of $100,000 (top) and fall below the running peak (bottom), both at the same "
            f"chart samples.\nQuantConnect's statistics for the whole run: net profit "
            f"{base['net_profit']:+.1f}%, beta {base['beta']:.2f}, Sharpe {base['sharpe']:.2f}, "
            f"maximum drawdown {base['max_drawdown']:.1f}% on the daily record.")
    source_note(fig, "Source: results/base_2016_2024/equity.csv and results/runs.csv. QuantConnect "
                     "chart samples, about one every four days; the last sample is "
                     f"{pd.Timestamp(base['end']):%d %b %Y}.")
    save(fig, "equity_vs_spy.png")


def annual_returns() -> None:
    yr = read("base_2016_2024/yearly_returns.csv")
    orders = read("base_2016_2024/orders.csv")
    first_fill = pd.to_datetime(orders["last_fill_time"].dropna(), utc=True).min().tz_convert(
        "America/New_York")
    wins = yr.loc[yr["difference_sampled"] > 0, "year"].tolist()
    x = range(len(yr))
    width = 0.36

    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.8, bottom=0.14)
    ax.bar([i - width / 2 - 0.01 for i in x], yr["strategy_return_sampled"], width,
           color=STRATEGY, label="DCF screen")
    ax.bar([i + width / 2 + 0.01 for i in x], yr["spy_return"], width, color=SPY,
           label="SPY, dividend-adjusted")
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_xticks(list(x), [str(y) for y in yr["year"]])
    ax.yaxis.set_major_formatter(FuncFormatter(percent))
    ax.set_ylabel("Return in the year")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", ncols=2, fontsize=9.5)
    worst = yr["difference_sampled"].idxmin()
    ax.annotate(f"{yr.at[worst, 'difference_sampled']:+.1f} pts against SPY", (worst, min(
        yr.at[worst, "strategy_return_sampled"], yr.at[worst, "spy_return"])),
        xytext=(0, -14), textcoords="offset points", ha="center", fontsize=9, color=INK)
    clean(ax)

    won = " and ".join(str(y) for y in wins) if wins else "none"
    heading(fig,
            f"Between the same chart samples, the DCF screen beat SPY in {len(wins)} of {len(yr)} "
            f"years ({won})",
            f"Worst year against the index: {yr.at[worst, 'year']}, "
            f"{yr.at[worst, 'strategy_return_sampled']:+.1f}% against "
            f"{yr.at[worst, 'spy_return']:+.1f}%.\nThe book held only cash until its first fills "
            f"on {first_fill.day} {first_fill:%B %Y}, so {first_fill.year} includes that time "
            f"out of the market.")
    source_note(fig, "Source: results/base_2016_2024/yearly_returns.csv, columns "
                     "strategy_return_sampled and spy_return: both series between the same two "
                     "QuantConnect chart samples each year.")
    save(fig, "annual_returns.png")


def sensitivity(runs: pd.DataFrame) -> None:
    s = read("sensitivity/summary.csv")
    spy = runs.set_index("key").loc["dcf__base", "spy_total_return"]
    order = ["base", "mos015", "mos035", "mos050", "coe008", "coe010", "pos10", "pos40",
             "univ300"]
    s = s.set_index("variant").loc[order].reset_index()
    s.loc[s["variant"] == "base", "label"] = "Base parameters"
    colors = [STRATEGY if v == "base" else OTHER for v in s["variant"]]
    y = list(range(len(s)))[::-1]

    # Which parameter moves the net profit most (range within its group, base included).
    names = {"margin_of_safety": "the margin of safety", "cost_of_equity": "the cost of equity",
             "max_positions": "the number of positions", "universe_size": "the universe size"}
    base_net = s.loc[s["variant"] == "base", "net_profit"].iloc[0]
    spans = {}
    for param, group in s[s["variant"] != "base"].groupby("parameter"):
        values = list(group["net_profit"]) + [base_net]
        spans[param] = max(values) - min(values)
    top_param = max(spans, key=spans.get)

    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 5.8), sharey=True,
                                      gridspec_kw={"width_ratios": [1.6, 1], "wspace": 0.08})
    fig.subplots_adjust(left=0.265, right=0.97, top=0.8, bottom=0.13)
    left.barh(y, s["net_profit"], height=0.56, color=colors)
    left.axvline(spy, color=SPY, lw=1.4)
    left.annotate(f"SPY {spy:+.0f}%", (spy, y[0] + 0.45), xytext=(-4, 0),
                  textcoords="offset points", ha="right", va="center", fontsize=9, color=INK)
    for yi, v in zip(y, s["net_profit"]):
        left.annotate(f"{v:+.1f}%", (v, yi), xytext=(4, 0), textcoords="offset points",
                      va="center", fontsize=9, color=INK)
    left.set_xlim(0, spy * 1.12)
    left.set_xlabel("Total return, 2016 to 2024")
    left.xaxis.set_major_formatter(FuncFormatter(percent))
    left.set_yticks(y, s["label"])
    left.grid(axis="y", visible=False)
    clean(left)

    right.barh(y, s["max_drawdown"], height=0.56, color=colors)
    for yi, v in zip(y, s["max_drawdown"]):
        right.annotate(f"{v:.1f}%", (v, yi), xytext=(4, 0), textcoords="offset points",
                       va="center", fontsize=9, color=INK)
    right.set_xlim(0, s["max_drawdown"].max() * 1.25)
    right.set_xlabel("Maximum drawdown")
    right.xaxis.set_major_formatter(FuncFormatter(lambda x, _p: f"{x:.0f}%"))
    right.grid(axis="y", visible=False)
    clean(right)

    best = s.loc[s["net_profit"].idxmax()]
    p = dict(kv.split("=", 1) for kv in runs.set_index("key").loc["dcf__base", "parameters"]
             .split("; "))
    count = {8: "eight", 9: "nine", 10: "ten"}.get(len(s), str(len(s)))
    heading(fig,
            f"All {count} runs trail SPY; in these single runs {names.get(top_param, top_param)} "
            f"moved the result most",
            f"Base: universe {int(p['universe_size'])}, {int(p['max_positions'])} positions, "
            f"cost of equity {float(p['cost_of_equity']):.0%}, margin of safety "
            f"{float(p['margin_of_safety']):.0%}. One parameter changed per run.\n"
            f"Best: {best['label'].lower()}, {best['net_profit']:+.1f}%, against SPY "
            f"{spy:+.1f}% over the same years.")
    source_note(fig, "Source: results/sensitivity/summary.csv (QuantConnect statistics) and "
                     "results/runs.csv (SPY from the benchmark series). Base run in blue.")
    save(fig, "sensitivity.png")


def prototype_2023(runs: pd.DataFrame) -> None:
    proto_path = RESULTS / "prototype_2023" / "equity.csv"
    basket = read("reference/basket_2023/equity.csv")
    by_key = runs.set_index("key")
    p_net = by_key.loc["dcf__prototype_2023", "net_profit"]
    b_net = by_key.loc["audit__basket_2023", "net_profit"]

    fig, ax = plt.subplots(figsize=(10, 5.6))
    fig.subplots_adjust(left=0.1, right=0.83, top=0.8, bottom=0.14)
    bt = dates(basket)
    ax.plot(bt, basket["equity"], color=BASKET, lw=LINE,
            label="Equal-weight buy and hold of the same seven stocks")
    if proto_path.exists():
        proto = pd.read_csv(proto_path)
        pt = dates(proto)
        spy = proto["spy_benchmark"] / proto["spy_benchmark"].iloc[0] * proto["equity"].iloc[0]
        spy_ret = by_key.loc["dcf__prototype_2023", "spy_total_return"]
        ax.plot(pt, spy, color=SPY, lw=LINE, label="SPY, dividend-adjusted")
        ax.plot(pt, proto["equity"], color=STRATEGY, lw=LINE, label="2024 prototype")
        ends = [(pt.iloc[-1], proto["equity"].iloc[-1], "Prototype", STRATEGY),
                (pt.iloc[-1], spy.iloc[-1], "SPY", SPY),
                (bt.iloc[-1], basket["equity"].iloc[-1], "Seven-stock basket", BASKET)]
        subtitle = (f"Growth of $100,000 in calendar 2023. SPY {spy_ret:+.1f}% to the last chart "
                    f"sample ({pd.Timestamp(proto['date'].iloc[-1]):%d %b}).")
    else:
        spy = basket["spy_benchmark"] / basket["spy_benchmark"].iloc[0] * basket["equity"].iloc[0]
        ax.plot(bt, spy, color=SPY, lw=LINE, label="SPY, dividend-adjusted")
        ends = [(bt.iloc[-1], spy.iloc[-1], "SPY", SPY),
                (bt.iloc[-1], basket["equity"].iloc[-1], "Seven-stock basket", BASKET)]
        subtitle = "The prototype's equity series is not in the export; basket and SPY only."
    end_labels(ax, ends)
    ax.yaxis.set_major_formatter(FuncFormatter(dollars))
    ax.set_ylabel("Value of $100,000")
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 3, 5, 7, 9, 11]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(loc="upper left", fontsize=9.5)
    clean(ax)

    heading(fig,
            f"In 2023 the prototype made {p_net:+.1f}%, less than holding its seven stocks "
            f"({b_net:+.1f}%)",
            subtitle)
    source_note(fig, "Source: results/prototype_2023/equity.csv, results/reference/basket_2023/"
                     "equity.csv, results/runs.csv (net profit is QuantConnect's statistic to "
                     "31 Dec 2023).")
    save(fig, "prototype_2023.png")


def main() -> None:
    runs = read("runs.csv")
    equity_vs_spy(runs)
    annual_returns()
    sensitivity(runs)
    prototype_2023(runs)


if __name__ == "__main__":
    main()
