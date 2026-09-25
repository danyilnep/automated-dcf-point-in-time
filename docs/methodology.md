# Methodology

This document describes what the algorithm does, rule by rule, as it ran in the base backtest
`54b5e0649da4a9cbf3f7dce6c409c7fe` (QuantConnect project 36836412, `main.py` SHA-256
`4f7f49ed...` as run on QuantConnect; the published copy is the code in
[`results/raw/dcf__base.json.gz`](../results/raw/dcf__base.json.gz)). It describes behaviour, not
file layout: the repository's
`main.py` and `dcf_model.py` split that file in two, and a re-run of them on QuantConnect
reproduced every order and trade of the base run
([data checks](data-checks.md#reproduction-of-the-base-run)), so the rules below are what every
published run executed.

Statements below about what the base run did (first order dates, order types, fees) come from its
order log, [`results/base_2016_2024/orders.csv`](../results/base_2016_2024/orders.csv).
Dollar amounts are written as USD in this file because GitHub reads a bare dollar sign as the
start of a formula.

## Pipeline in one paragraph

On the first trading day of each month the algorithm takes the 150 largest non-financial US
primary shares by market capitalisation, values each one with a five-year discounted cash flow
built from the trailing-twelve-month Morningstar statements QuantConnect held on that day, and
compares the implied equity value with the market capitalisation. It holds up to 20 names in
equal 5% slots. A name is bought when its market capitalisation is at most 75% of the implied
equity value and sold when the market capitalisation reaches the implied equity value, when it
can no longer be valued, or when it leaves the universe.

## Universe

A fundamental universe selection runs at midnight after each trading session, Tuesday to
Saturday in a week without holidays. It returns a new list only at its first call in each
calendar month and `Universe.UNCHANGED` at every other call, so membership changes once a month;
[Refresh and rebalance order](#refresh-and-rebalance-order) shows when that first call falls. A
company is eligible when all of the following hold on the selection date:

| Filter | Rule | Reason |
|---|---|---|
| Fundamental coverage | `has_fundamental_data` is true | The valuation needs Morningstar statements. |
| Price | Price in the fundamental record above USD 5 | Removes low-priced shares where per-share fees and data errors dominate. |
| Size | `market_cap` above zero | Needed to rank and to compute the upside ratio. |
| Share class | `security_reference.is_primary_share` | One line per company; avoids holding two share classes of the same firm. |
| Sector | Morningstar sector is neither Financial Services nor Real Estate | EBITDA, capital expenditure and debt do not describe banks, insurers or REITs in the way this model assumes. |

Eligible companies are sorted by `market_cap`, largest first, and the first `universe_size`
(default 150) form the universe. QuantConnect's US equity universe includes companies that were
later delisted, so the selection has no survivorship filter built in.

When a company leaves the universe at a monthly refresh and the portfolio holds it,
`on_securities_changed` liquidates the position at once with the order tag `left universe`. The
order is submitted at midnight, outside market hours, so it is a market-on-open order; what
happens to it next depends on the order of refresh and rebalance (below). The SPY benchmark
subscription is never a member.

## Timing

| Event | When |
|---|---|
| Universe refresh | First universe selection of each calendar month, at midnight after a trading session |
| Valuation and rebalance | First trading day of the month, 30 minutes after the open (10:00 New York time), scheduled on SPY's trading calendar |
| Fill of rebalance orders | The close of the same day (see [Costs and execution](#costs-and-execution)) |
| Backtest window | 1 January 2016 to 31 December 2024, USD 100,000 starting cash |

Securities are subscribed at daily resolution. A security that joined the universe at the
refresh has no daily bar yet at 10:00 on its first day, and the rebalance skips any member
without data (`security.has_data` false) or without a `Fundamentals` object. Such a name is
first valued at the next monthly rebalance. The base run shows this at the start: its first
orders are dated 1 February 2016, not January 2016, because every member was new in January.

### Refresh and rebalance order

The refresh does not always come before the rebalance. The selection runs only at midnight
after a trading session: the cap probe's log has selection lines on 32 dates from 2 January to
15 February 2019, all on Tuesdays to Saturdays, and none on Tuesday 22 January, the day after the
Martin Luther King Day holiday ([data checks](data-checks.md#the-cap-probes-log)). So the first
selection of a month comes before the month's first trading day only when the previous month
ends on a trading day; it then runs at midnight at the start of the 1st.

| Previous month ends on | Months, of the 108 | First selection of the month | The rebalance trades on |
|---|---|---|---|
| A trading day | 76 | Midnight at the start of the 1st, before the rebalance | The new list, ranked on the new month-end snapshot |
| A weekend or holiday | 32 | Midnight after the rebalance day | Last month's list, ranked on last month's snapshot |

In the second case the rebalance values and trades last month's members, and the new list
arrives that night. The held names it drops are sold with the tag `left universe` by
market-on-open orders submitted at midnight, which fill that day. The base run has 18 such
sales, in 17 of the 32 months (for example on 2 February 2016, and on 2 June 2021 after the
Memorial Day holiday on 31 May). In 16 of the 18 the rebalance had bought or resized the same
name at the close the day before, and three were whole positions bought at one close and sold
the next day: HLT (98 shares) and HPQ (741) on 1 and 2 February 2016, and AEP (107) on 1 and
2 June 2021. Which snapshot the rebalance's own read of `market_cap` returns in these months
was not tested.

In the first case the dropped names get the same midnight market-on-open orders, but the
rebalance runs before they fill: it finds those names outside the universe and so without a
valuation, and sells them at the close with the tag `no valuation`, cancelling the pending
orders ([Costs and execution](#costs-and-execution)).

The docstring of `select` in `main.py` says the refresh comes the day before the rebalance,
which holds only in the first case. It is left as it is because `main.py` must stay
byte-identical to the published copy of the file the re-run executed. Running the rebalance on
the second trading day of the month, or after the refresh, would remove the lag; that is a new
version of the strategy and needs new backtests.

## Inputs from Morningstar

All inputs come from `security.fundamentals`, the Morningstar record QuantConnect holds for the
security on the rebalance day. Morningstar stores most items as multi-period fields. The code reads
the first period in the listed order that exists and converts to a number other than NaN;
`None`, missing attributes and NaN are skipped. The check is for NaN only, so an infinite value
would be used.

| Model input | Symbol | Morningstar field | Period order | If missing |
|---|---|---|---|---|
| EBITDA | $E_0$ | `financial_statements.income_statement.ebitda` | twelve months, then default value | Company not valued |
| Capital expenditure | $K$ | `financial_statements.cash_flow_statement.capital_expenditure` | twelve months, then default | Treated as 0 |
| Change in working capital | $\Delta W$ | `financial_statements.cash_flow_statement.change_in_working_capital` | twelve months, then default | Treated as 0 |
| Pretax income | $I$ | `financial_statements.income_statement.pretax_income` | twelve months, then default | Default tax rate used |
| Tax provision | $T$ | `financial_statements.income_statement.tax_provision` | twelve months, then default | Default tax rate used |
| Interest expense | $R$ | `financial_statements.income_statement.interest_expense` | twelve months, then default | Treated as 0 |
| Current debt | $D_c$ | `financial_statements.balance_sheet.current_debt` | three months, twelve months, default | Treated as 0 |
| Long-term debt | $D_l$ | `financial_statements.balance_sheet.long_term_debt` | three months, twelve months, default | Treated as 0 |
| Cash and equivalents | $C$ | `financial_statements.balance_sheet.cash_and_cash_equivalents` | three months, twelve months, default | Treated as 0 |
| EBITDA growth | $g_{\text{raw}}$ | `operation_ratios.ebitda_growth` | one year, three years, default | Default growth used |
| EV/EBITDA | | `valuation_ratios.ev_to_ebitda` | single value | Excluded from the median |
| Market capitalisation | $M$ | `market_cap` | single value | Company not valued |

Flows (income and cash-flow items) are trailing twelve months. Balance-sheet items take the latest
quarter first because a balance sheet is a snapshot, not a flow. Growth takes the one-year figure
first because the forecast horizon starts next year.

`market_cap` is not a daily price times shares. In QuantConnect's Morningstar data it is a
month-end snapshot, in force from the start of the month and then held
([data checks](data-checks.md#market-capitalisation-is-refreshed-once-a-month)). The universe
ranking reads it at the first selection of the month and the rebalance reads it again for the
upside ratio. In 76 of the 108 months the ranking behind the rebalance's universe used the new
snapshot; in the other 32 it used the previous month's
([Refresh and rebalance order](#refresh-and-rebalance-order)).

Sign conventions follow Morningstar's cash-flow statement: capital expenditure is reported as a
negative cash flow, and the change in working capital is its cash effect, positive when working
capital releases cash.

## Valuation

Write $\operatorname{clamp}(x, a, b) = \max(a, \min(b, x))$. All steps below are per company and
per rebalance day.

### Eligibility

The company is valued only if $E_0 > 0$ and $M > 0$. A negative or zero EBITDA has no meaningful
multiple or cash-flow margin in this model, so those companies get no valuation (and a held
position in one is sold with the tag `no valuation`).

### Cash-flow ratios

$$
c = \operatorname{clamp}\left(\frac{\lvert K \rvert}{E_0},\ 0,\ 0.8\right),
\qquad
w = \operatorname{clamp}\left(\frac{-\Delta W}{E_0},\ -0.3,\ 0.3\right)
$$

$c$ is capital expenditure as a share of EBITDA; the absolute value removes the sign
convention. $w$ is investment in working capital as a share of EBITDA: a cash outflow into working
capital ($\Delta W < 0$) makes $w$ positive and lowers free cash flow. The bounds stop one unusual
year (a large acquisition booked as capex, a one-off working-capital swing) from dominating a
five-year forecast.

### Tax rate

$$
t =
\begin{cases}
\operatorname{clamp}(T / I,\ 0,\ 0.35) & \text{if } I > 0 \text{ and } T \text{ is available} \\
0.21 & \text{otherwise}
\end{cases}
$$

The effective rate is bounded at 35%, the US federal statutory rate before 2018, so a one-off tax
charge cannot produce a rate above what any firm in the sample normally paid. The default 21% is
the federal statutory rate from 2018 onward, used when pretax income is negative or missing.

### Free-cash-flow margin

$$
m = 1 - t - c - w
$$

Free cash flow in year $k$ is modelled as $m \cdot E_k$. If $m \le 0$ the company is not valued.
This keeps the prototype's simplification: tax is charged on EBITDA rather than on operating
profit after depreciation, which understates free cash flow for asset-heavy companies and makes
the model conservative for them.

### Capital structure and discount rate

$$
D = D_c + D_l,
\qquad
r_d =
\begin{cases}
\operatorname{clamp}(\lvert R \rvert / D,\ 0.01,\ 0.12) & D > 0 \\
0 & D = 0
\end{cases}
$$

$$
\text{WACC} = \max\left( \frac{M}{M + D}\, k_e + \frac{D}{M + D}\, r_d\, (1 - t),\ 0.05 \right)
$$

$k_e$ is the `cost_of_equity` parameter, one constant for every company and every date (default
0.09). The cost of debt is the interest expense over period-end debt; the bounds catch cases where
debt was refinanced during the year and the ratio of a flow to a snapshot is meaningless. Equity
is weighted at market value, debt at book value. The 5% floor prevents a heavily indebted
company with cheap debt from being discounted at a rate below any plausible required return.

### Growth and forecast

$$
g =
\begin{cases}
\operatorname{clamp}(g_{\text{raw}},\ -0.05,\ 0.15) & \text{if available} \\
0.03 & \text{otherwise}
\end{cases}
$$

$$
E_k = E_0 (1 + g)^k, \qquad k = 1, \dots, 5
$$

The one-year growth field is a decimal fraction (0.05 means 5%), which a probe backtest on
QuantConnect confirmed ([data checks](data-checks.md#ebitda-growth-is-a-decimal-fraction)); the
three-year and default periods read when it is missing were not checked. EBITDA compounds at one
bounded rate for five years. This replaces the prototype's straight-line extrapolation of
absolute changes, which turned post-2020 rebounds into very large terminal values (see
[audit-2024-prototype.md](audit-2024-prototype.md#3-linear-ebitda-extrapolation)). The upper
bound of 15% limits the value a single strong year can create; the lower bound of -5% keeps a
temporary decline from valuing a company as if it were in permanent run-off. Missing growth
defaults to a modest 3%, so a company with no growth record is neither rewarded nor punished much.

### Terminal value and equity value

$$
\text{PV} = \sum_{k=1}^{5} \frac{m\, E_k}{(1 + \text{WACC})^k},
\qquad
\text{TV} = \frac{X\, E_5}{(1 + \text{WACC})^5}
$$

$$
V = \text{PV} + \text{TV} - D + C,
\qquad
u = \frac{V}{M}
$$

$X$ is the exit multiple (next section). $V$ is the implied equity value: enterprise value from
the forecast and the terminal multiple, minus debt, plus cash. If $V \le 0$ the company is not
valued. The signal is the upside ratio $u$; $u = 1.5$ means the model values the equity at 1.5
times its market capitalisation.

## Exit multiple

On each rebalance day the algorithm collects `valuation_ratios.ev_to_ebitda` for every universe
member that has data, keeps the positive values that are not NaN, and takes the median:

$$
X = \operatorname{clamp}\left(\operatorname{median}\lbrace \text{EV/EBITDA}_i \rbrace,\ 6,\ 14\right),
\qquad X = 10 \text{ if no member has a valid multiple}
$$

The same $X$ applies to every company that day. Using the market's own median ties the terminal
value to how the market prices large companies at the time, so the model measures cheapness
relative to the universe rather than against a fixed number. The bounds of 6 and 14 keep a
market-wide bubble or crash from moving every terminal value with it; 10 is the prototype's fixed
multiple, kept as the fallback.

## Portfolio construction

Let $s$ be the `margin_of_safety` parameter (default 0.25) and $N$ the `max_positions` parameter
(default 20). The buy threshold is

$$
u^{\text{buy}} = \frac{1}{1 - s}
$$

so a name qualifies when $M \le (1 - s) V$. With $s = 0.25$ that is $u \ge 4/3$.

| margin_of_safety | Buy threshold $u^{\text{buy}}$ |
|---|---|
| 0.15 | 1.176 |
| 0.25 | 1.333 |
| 0.35 | 1.538 |
| 0.50 | 2.000 |

At each rebalance, in this order:

1. Every current holding is checked. It is kept if it is still a universe member and $u > 1$.
   Otherwise it is sold: with the tag `reached implied value` if it was valued and $u \le 1$,
   or `no valuation` if no valuation could be computed. Only members are valued, so a holding
   that has just left the universe also gets `no valuation`.
2. Candidates are all valued names with $u \ge u^{\text{buy}}$ that are not already kept, sorted
   by $u$ from highest to lowest.
3. The free slots are $N$ minus the number of kept names. The top candidates fill them.
4. Kept and new names all get the target weight $1/N$ (5% with the default), set in one
   `set_holdings` call. Kept positions are therefore resized back to $1/N$ every month.

The buy rule ($M \le (1-s)V$) and the sell rule ($M \ge V$) are separated by the margin of safety,
so a name cannot be bought and sold on the same condition. Weights are fixed at $1/N$ and do not
scale up when fewer than $N$ names qualify: the rest of the book stays in cash. The portfolio is
long only and the targets sum to at most 100% of equity at each rebalance. Orders fill at the
close, after the targets are set, so long exposure can end slightly above 100%: at most 100.3%
of equity in the base run's chart samples, and 101.3% with 10 positions.

## Costs and execution

- Fees: QuantConnect's default fee model for US equities, which follows Interactive Brokers'
  per-share schedule. The base run's orders show USD 0.005 per share with a USD 1 minimum per
  order (for example 543 shares of NFLX paid USD 2.715; 87 shares of GILD paid USD 1.00). Total
  fees in the base run: USD 1,388.79. Share counts are in QuantConnect's split- and
  dividend-adjusted units, like the prices, so the fee is charged on adjusted counts. For a
  company that split later these are larger than the shares that traded at the time (the 543
  NFLX shares were bought at an adjusted USD 9.41), so the fee is overstated for such names. At
  USD 1,388.79 over nine years this does not change the comparison with the index.
- Fills: the rebalance submits market orders at 10:00 New York time. With daily data, LEAN
  executes these as market-on-close orders, so they fill at that day's closing price. In the base
  run 1,298 of the 1,340 orders are market-on-close.
- Midnight orders: the other 42 orders are market-on-open sales submitted at midnight. The
  rebalance runs only at 10:00, so they can only come from `on_securities_changed` selling a
  held name that had just left the universe
  ([Refresh and rebalance order](#refresh-and-rebalance-order)). Eighteen of them, tagged
  `left universe`, were submitted the night after a rebalance and filled that day. The other 24
  were submitted at midnight at the start of the 1st, in 18 months whose previous month ended
  on a trading day, and never filled: each was followed by a filled market-on-close sale of the
  same quantity tagged `no valuation`, at the rebalance on the same date in 21 cases and on the
  next trading day in the three whose 1st was a Saturday (GLW in April 2017, CRH in September
  2018, PSX in August 2020). The export shows these 24 cancelled orders with the
  tag `no valuation`, not `left universe`, which fits the rebalance's `liquidate` call having
  cancelled them and written its own tag onto them; that step is inferred from the order log
  and was not checked in LEAN's code.
- Exits by cause: counting those 24 as universe exits, the base run sold 42 positions because
  they left the universe, 24 because they could no longer be valued and 57 because they
  reached implied value. The other 488 filled sales carry no tag; they are the monthly resizes
  of kept positions back to $1/N$.
- Slippage: none modelled. LEAN's default slippage model for equities adds nothing, and a fill
  at the official close has no spread cost in the backtest.
- The algorithm does not model interest on uninvested cash.

The decision uses only the Morningstar record and prices available before the open of the
rebalance day; the fill happens at the close of that day, after the decision, so execution does
not look ahead.

## Parameters

The first four are QuantConnect project parameters, so a sensitivity run changes no code. The
rest are constants in the algorithm. The base values are those of the earliest published run,
the base run (named `run1` in QuantConnect), and the sensitivity runs in
[`results/sensitivity/summary.csv`](../results/sensitivity/summary.csv) came after it and move
only the four project parameters. QuantConnect's backtest list for the project holds these nine
runs and the re-run of the refactored code and nothing else
([`results/checks/backtest_lists.csv`](../results/checks/backtest_lists.csv)), so no other
parameter values were run in it.

| Name | Default | Project parameter | Meaning |
|---|---|---|---|
| `universe_size` | 150 | yes | Number of largest eligible companies valued each month |
| `max_positions` | 20 | yes | Number of equal-weight slots; target weight is 1 / max_positions |
| `cost_of_equity` | 0.09 | yes | $k_e$ in the WACC, same for every company and date |
| `margin_of_safety` | 0.25 | yes | $s$; buy when market cap is at most $(1-s)$ times implied equity value |
| `forecast_years` | 5 | no | Explicit forecast horizon in years |
| `growth_floor`, `growth_cap` | -0.05, 0.15 | no | Bounds on the EBITDA growth rate |
| `default_growth` | 0.03 | no | Growth used when Morningstar has none |
| `default_tax` | 0.21 | no | Tax rate used when pretax income is not positive or data is missing |
| tax bounds | 0, 0.35 | no | Bounds on the effective tax rate |
| capex ratio bounds | 0, 0.8 | no | Bounds on capex as a share of EBITDA |
| working-capital ratio bounds | -0.3, 0.3 | no | Bounds on working-capital investment as a share of EBITDA |
| cost-of-debt bounds | 0.01, 0.12 | no | Bounds on interest expense over debt |
| WACC floor | 0.05 | no | Minimum discount rate |
| `multiple_floor`, `multiple_cap` | 6, 14 | no | Bounds on the exit multiple |
| fallback exit multiple | 10 | no | Used when no member has a valid EV/EBITDA |
| `min_price` | 5 | no | Minimum price in USD for universe eligibility |
| rebalance offset | 30 minutes | no | Minutes after the open when the rebalance runs |
| start, end, cash | 2016-01-01, 2024-12-31, 100,000 | no | Backtest window and starting cash in USD |

## What is point-in-time and what is not

Point-in-time:

- Every accounting input, the market capitalisation, the EV/EBITDA median and the growth rate are
  read from the Morningstar record QuantConnect holds for that date. Nothing published after the
  rebalance day enters the valuation.
- Universe membership is decided each month from that month's market capitalisations, and the
  underlying US equity universe includes companies that were later delisted. In 32 of the 108
  months the new list arrives the day after the rebalance, so that rebalance trades on the
  previous month's list ([Refresh and rebalance order](#refresh-and-rebalance-order)); that is
  a delay, not a look-ahead.
- Orders fill after the decision, at the close of the rebalance day.

Not point-in-time, or not verified:

- The model design. The bounds, the defaults, the 150-name universe and the base parameters were
  chosen in September 2026 by people who knew how 2016 to 2024 turned out, including that value
  stocks lagged growth stocks from 2020. They are the values of the earliest run in the
  rebuild's QuantConnect project, whose backtest list holds no run that is not published
  ([`backtest_lists.csv`](../results/checks/backtest_lists.csv)), but they are not free of
  hindsight: the list covers backtests, not choices made before the first one.
- The cost of equity. One constant (9%) is applied to every company for nine years of very
  different interest-rate conditions. It is an assumption fixed in 2026, not a rate an investor
  would have estimated on each date.
- Restatements. The rebuild relies on QuantConnect's statement that its Morningstar data is
  point-in-time. It does not check whether any value was later restated, or whether the sector
  classification used on a date is the one Morningstar assigned at the time.
- Prices. Backtest prices are QuantConnect's split- and dividend-adjusted series. This is correct
  for returns; absolute price levels in the order log differ from the prices quoted at the time.
