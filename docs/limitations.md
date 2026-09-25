# Limitations

What the rebuild does not do, and what each gap means for the result. Figures come from
[`results/runs.csv`](../results/runs.csv), the base run's files in
[`results/base_2016_2024/`](../results/base_2016_2024/) and
[`results/sensitivity/summary.csv`](../results/sensitivity/summary.csv) unless stated otherwise.
The model itself is described in [methodology.md](methodology.md), and the checks on its data in
[data-checks.md](data-checks.md).

## Value tilt and market beta

Most of the screen's movement is the market's. It is long only with most of its capital
invested, and its beta to SPY is 0.916 in the base run and between 0.867 and 0.935 in every
variant. Against SPY it lost: it fell 15.98% in calendar 2020 while SPY gained 17.97% (between
the same two chart samples the strategy lost 16.00%), and over the nine years it returned
+97.851% against +239.03% for SPY. QuantConnect's information ratio against SPY is -0.567, with
a tracking error of 7.6% a year and an alpha of -0.036.

The shortfall is not decomposed. The book differs from SPY in several ways that could each
explain part of it, and no run separates them:

- Weighting: 20 equal slots against SPY's capitalisation weights, over years in which the
  largest companies led the index.
- Sectors: financial services and real estate are excluded by construction.
- Concentration: 20 names and no sector limit. After the January 2020 rebalance 9 of the 20
  holdings were energy companies (COP, CVX, EOG, MPC, OXY, PSX, SLB, VLO, XOM), and after the
  March 2020 rebalance 7 were; both times the book also held DAL and LVS (holdings rebuilt from
  [`orders.csv`](../results/base_2016_2024/orders.csv)).
- Style: the screen buys companies that are cheap against an EBITDA valuation, a value tilt, in
  years when large-cap value stocks lagged growth stocks.

The style effect fits the result but was not measured: there is no factor regression, and no
equal-weight run of the 150-name universe to serve as the benchmark for the ranking. The
backtest is not evidence that the valuation model picks winners, within the value style or
otherwise.

## One cost-of-equity constant

Every company on every date is discounted with the same 9% cost of equity; there is no beta, no
size or debt premium, and no link to interest rates. Because the constant is shared, it mostly
shifts all upsides together, but it also changes the ranking between low-debt and high-debt
companies through the WACC weights. Moving it to 8% or 10% gives +92.1% and +111.2%, so the
conclusion does not depend on it, but the model has no view on which companies are riskier.

## Trailing-twelve-month data and Morningstar coverage gaps

The valuation starts from one trailing-twelve-month EBITDA and one year of EBITDA growth, so a
peak or trough year is carried forward for five years, and the growth bounds are the only guard.

Missing fields fall back to defaults. Capital expenditure becomes 0, which raises the
valuation. Debt becomes 0, which usually raises it too: the debt deduction goes, although the
discount rate rises to the full cost of equity. Cash becomes 0, which lowers it. The change in
working capital becomes 0, which raises the valuation of a company that invests in working
capital and lowers it for one that releases cash. Growth becomes 3% and tax 21%. The runs do
not record how often each default was used, so part of the signal may come from data gaps
rather than from cheapness.

Only the one-year period of the growth field was checked on QuantConnect: it is a decimal
fraction, as the bounds require
([data checks](data-checks.md#ebitda-growth-is-a-decimal-fraction)). When it is missing the code
falls back to the three-year period and then to the field's default period. Their units and
meaning (an annual rate or a change over three years) were not checked, and the runs do not
record how often the fallback was used.

A company that enters the universe is first valued about a month later: when the new list
arrives before the rebalance the newcomer has no daily bar yet at 10:00, and when it arrives
after, that month's rebalance has already run.

## Default fee model and no slippage model

Costs are small. QuantConnect's default per-share fee model (USD 0.005 per share, USD 1 minimum
per order, as the base run's orders show) charged USD 1,388.79 over nine years. It charges on
QuantConnect's split- and dividend-adjusted share counts, which for a company that split later
are larger than the shares that traded at the time, so the fee is overstated for those names;
at this size that does not matter. Orders fill at the closing price with no spread, market
impact or slippage, which is reasonable for USD 100,000 in the largest US companies but says
nothing about a larger book. Since turnover is low (0.53% of the portfolio per day), realistic
slippage would lower the return a little and would not change the comparison with the index.

## Monthly rebalance

The portfolio is valued and traded once a month, 30 minutes after the open on the first trading
day, with the fill at that day's close. Statements change quarterly, so monthly valuation does not
miss new fundamental data, but the book cannot react to prices inside the month: in the 2020 fall
the rebalances on the first trading days of March and April were the only chances to act. Kept
positions are resized to equal weight every month, which adds turnover that a drift band would
avoid. A faster rebalance would also need a new source for the market capitalisation:
QuantConnect's Morningstar `market_cap` is refreshed once a month, at the start of the month
([data checks](data-checks.md#market-capitalisation-is-refreshed-once-a-month)), which suits a
monthly rebalance and nothing faster.

The schedule has a defect. The universe refresh runs at midnight after a trading session, so in
the 32 of 108 months whose previous month ends on a weekend or holiday it comes the night after
the rebalance. That rebalance trades on last month's list, and the names the new list drops are
sold at the next open: 18 of the base run's 1,340 orders, and three whole positions bought at
one close and sold the next day
([methodology](methodology.md#refresh-and-rebalance-order)). Removing it needs a new version of
the code and new runs, which this repository does not contain.

## No sector or factor neutrality

There are no sector caps, no factor constraints and no hedge. The book can fill up with whatever
sector the model scores as cheap, and the result mixes the valuation signal with sector, size and
value-factor returns. No factor regression was run, so how much of the return, or of the 2020
drawdown, belongs to each of these is not measured.

## Parameter sensitivity

Breadth moved the result most in these runs. Holding 10 names returned +29.9% and 40 names
+148.2%; valuing the largest 300 companies instead of 150 returned +157.4%; a margin of safety of
15% gives exactly the base run, so the names between the 15% and 25% hurdles never reached a
free slot. Each figure is a single backtest path, with no subperiod split or bootstrap, so the
differences describe these runs: with a tracking error of about 7.6% a year, and more
stock-specific risk in a 10-name book, one path cannot show that breadth matters more than the
valuation settings. The growth, multiple, capex and tax bounds were never varied.

One nine-year path with no holdout period supports the statement that the pipeline works and
did not beat the index over this period, and nothing stronger. Even the shortfall is not
statistically firm: an information ratio of -0.567 over nine years is about 1.7 standard errors
below zero (the ratio times the square root of the number of years). The probabilistic Sharpe
ratio of 0.433% does not bear on the comparison with SPY. It is QuantConnect's estimate of the
probability that the true Sharpe ratio exceeds a positive reference value, not a test against
the index.

## EBITDA-based cash flow and a market-relative exit multiple

Free cash flow is EBITDA times a margin, with tax charged on EBITDA rather than on operating profit,
and EBITDA adds back all amortisation, so companies whose main cost is amortised (content,
capitalised software) can look cheaper than their cash flow justifies. The exit multiple is the
universe median EV/EBITDA on the day, so the terminal value follows the market's own pricing: the
model measures cheapness relative to other large companies, not against an absolute value, and in
a market-wide fall every terminal value falls with it.

The terminal term dominates. In the hand-worked example in
[`tests/test_dcf_model.py`](../tests/test_dcf_model.py) the discounted terminal value is
8,815.85 of an enterprise value of 11,367.18, or 78%. The upside ratio therefore mostly compares
the universe's median multiple, applied to EBITDA grown for five years at a bounded rate, with
the company's own market value. It behaves much like a growth-adjusted relative EV/EBITDA
screen, in which a company's own multiple against the median decides much of its rank.
