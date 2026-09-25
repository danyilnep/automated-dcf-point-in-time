"""Valuation arithmetic of the point-in-time DCF strategy, with no QuantConnect dependency.

The model values one company from its trailing-twelve-month statements on the valuation day:

    capex ratio      c        = |capex| / EBITDA                   bounded to [0, 0.8]
    working capital  w        = -change_in_wc / EBITDA             bounded to [-0.3, 0.3]
    tax rate         t        = tax_provision / pretax_income      bounded to [0, 0.35], else 0.21
    FCF margin       m        = 1 - t - c - w
    forecast         EBITDA_k = EBITDA * (1 + g)^k,  k = 1..N      g bounded to [-0.05, 0.15]
    discount rate    r        = max(E/(E+D) * r_e + D/(E+D) * r_d * (1 - t), 0.05)
    equity value     V        = sum_k EBITDA_k * m / (1 + r)^k + EBITDA_N * X / (1 + r)^N - D + C
    upside           U        = V / E

where E is market capitalisation, D is current plus long-term debt, C is cash, r_e the cost of
equity parameter, r_d the interest-derived cost of debt, N = 5 forecast years and X the exit
multiple (the universe's median EV/EBITDA that day, see exit_multiple_from). The algorithm buys
when U >= 1 / (1 - margin_of_safety) (see buy_threshold) and holds while U > 1.

Provenance. The structure (free cash flow as a fixed share of EBITDA, a WACC with a single cost
of equity, an EBITDA exit multiple) comes from the 2024 Mercury Capital Management quant team's
prototype, `received/dcf_valuation_yfinance.py`. The bounds, the sign handling
and the point-in-time inputs are the 2026 rebuild's corrections of that prototype. This module
was then extracted from `main.py` as it ran on QuantConnect (project 36836412, backtest
54b5e0649da4a9cbf3f7dce6c409c7fe, 2016 to 2024) with every expression kept: same operands, same
operator order, same None handling. Floating-point addition is not associative, so reordering a
sum could flip a borderline buy decision and change the backtest; the arithmetic below must not
be "tidied". `tests/test_dcf_model.py` holds a copy of the original code and requires exact
equality with it on thousands of random inputs.

Standard library only, so the model runs and is tested without LEAN.
"""

import statistics
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class FundamentalInputs:
    """One company's valuation inputs as `main.py` reads them from Morningstar on the day.

    Flows (ebitda, capex, change_in_wc, pretax_income, tax_provision, interest_expense) are
    trailing twelve months. Balances (current_debt, long_term_debt, cash) are the latest
    quarter-end values, annual when the quarter is missing. ebitda_growth is a fraction (0.05
    means 5%). None means Morningstar had no usable value that day; NaN never arrives here
    because `main.py` turns it into None.

    Signs are Morningstar's cash-flow-statement signs, not the textbook FCF formula's:
    capex is a cash outflow and so normally negative, and change_in_wc is the cash effect of
    working capital, negative when working capital absorbed cash.
    """

    ebitda: Optional[float]
    capex: Optional[float]
    change_in_wc: Optional[float]
    pretax_income: Optional[float]
    tax_provision: Optional[float]
    current_debt: Optional[float]
    long_term_debt: Optional[float]
    cash: Optional[float]
    interest_expense: Optional[float]
    ebitda_growth: Optional[float]
    market_cap: float


@dataclass(frozen=True)
class ValuationParams:
    """Assumptions of the valuation.

    The first six mirror attributes set in `PointInTimeDcfValue.initialize`; cost_of_equity is
    a QuantConnect project parameter. The rest are the fixed bounds of the model, named here so
    the tests can refer to them; the reasons for each bound are given where it is applied in
    implied_upside.
    """

    cost_of_equity: float = 0.09
    forecast_years: int = 5
    growth_floor: float = -0.05
    growth_cap: float = 0.15
    default_growth: float = 0.03
    default_tax: float = 0.21
    capex_ratio_cap: float = 0.8
    wc_ratio_floor: float = -0.3
    wc_ratio_cap: float = 0.3
    tax_cap: float = 0.35
    cost_of_debt_floor: float = 0.01
    cost_of_debt_cap: float = 0.12
    wacc_floor: float = 0.05


def clamp(x: float, lo: float, hi: float) -> float:
    """Limit x to the interval [lo, hi], computed as max(lo, min(hi, x)).

    The nesting order is the recorded code's. It decides which argument comes back on a tie
    between 0.0 and -0.0 and what a NaN turns into, so it is kept.
    """
    return max(lo, min(hi, x))


def implied_upside(
    inputs: FundamentalInputs, params: ValuationParams, exit_multiple: float
) -> Optional[float]:
    """Implied equity value divided by market capitalisation, U = V / E in the module formulas.

    Returns None when the inputs cannot support this model: EBITDA missing or <= 0, market cap
    <= 0, FCF margin m <= 0, or equity value V <= 0. `main.py` never buys a name without a
    valuation and sells a holding whose valuation disappears.

    Missing debt, cash, capex, working-capital and interest lines count as zero. A missing tax
    line, or pretax income that is missing or <= 0, gives the default tax rate. A missing growth
    rate gives the default growth rate.

    Raises ZeroDivisionError when market cap plus debt is exactly zero, which needs negative
    reported debt equal to the market cap. The recorded code had no guard either, and the
    recorded backtest completed, so the case did not occur there.
    """
    ebitda = inputs.ebitda
    if ebitda is None or ebitda <= 0:
        return None
    market_cap = inputs.market_cap
    if market_cap <= 0:
        return None

    # Both ratios are shares of trailing EBITDA. The 2024 prototype subtracted yfinance's
    # negative capex as a percentage, which added capex back to free cash flow; taking the
    # absolute value makes capex a deduction whichever sign the filer used. A capex share above
    # 80% of EBITDA is treated as 80%, so one heavy investment year cannot remove the margin.
    capex = inputs.capex or 0.0
    # change_in_wc is negative when working capital absorbed cash, so its negation is the share
    # of EBITDA consumed by working capital (positive = drag). One year's swing is mostly
    # timing, and the forecast repeats it for five years, hence the +/-30% bound.
    dwc = inputs.change_in_wc or 0.0
    capex_ratio = clamp(abs(capex) / ebitda, 0.0, params.capex_ratio_cap)
    wc_ratio = clamp(-dwc / ebitda, params.wc_ratio_floor, params.wc_ratio_cap)

    # Effective tax rate from the statements. Deferred-tax movements, credits and write-downs
    # push provision / pretax far outside any plausible rate, hence [0, 35%]. With no positive
    # pretax income the ratio means nothing and the US federal rate since 2018, 21%, is used.
    # As in the prototype, the rate is later applied to EBITDA rather than EBIT; that
    # overstates cash tax (depreciation is deductible) and so errs towards lower valuations.
    pretax = inputs.pretax_income
    tax_provision = inputs.tax_provision
    if pretax and pretax > 0 and tax_provision is not None:
        tax = clamp(tax_provision / pretax, 0.0, params.tax_cap)
    else:
        tax = params.default_tax

    # Free cash flow as a share of EBITDA, the prototype's structure. A margin at or below zero
    # forecasts no free cash flow at all, which this model cannot value.
    fcf_margin = 1.0 - tax - capex_ratio - wc_ratio
    if fcf_margin <= 0:
        return None

    # Capital structure: book debt, market equity. Cost of debt is trailing interest over
    # quarter-end debt; debt raised or repaid during the year distorts that ratio, hence the
    # [1%, 12%] band. interest_expense is used as a magnitude, so its sign does not matter.
    # The cost of equity is one parameter for every company, as in the prototype.
    debt = (inputs.current_debt or 0.0) + (inputs.long_term_debt or 0.0)
    cash = inputs.cash or 0.0
    interest = abs(inputs.interest_expense or 0.0)
    if debt > 0:
        cost_of_debt = clamp(interest / debt, params.cost_of_debt_floor, params.cost_of_debt_cap)
    else:
        cost_of_debt = 0.0
    total_capital = market_cap + debt
    wacc = ((market_cap / total_capital) * params.cost_of_equity
            + (debt / total_capital) * cost_of_debt * (1.0 - tax))
    # A heavily indebted company with cheap debt can blend to a rate well below 5%, and the
    # valuation rises steeply as the discount rate falls; 5% is the floor.
    wacc = max(wacc, params.wacc_floor)

    # One year's EBITDA growth is noisy (a rebound year can show tens of percent) and is
    # compounded for five years and then capitalised at the exit multiple, so an unbounded rate
    # would decide the ranking on its own. The prototype's straight-line extrapolation had that
    # failure: Exxon's post-2020 rebound became a $777 fair value against a share price near
    # $100. Morningstar's one-year rate is used, its three-year rate when one year is missing.
    growth = inputs.ebitda_growth
    if growth is None:
        growth = params.default_growth
    else:
        growth = clamp(growth, params.growth_floor, params.growth_cap)

    present_value = 0.0
    level = ebitda
    for year in range(1, params.forecast_years + 1):
        level *= (1.0 + growth)
        present_value += level * fcf_margin / (1.0 + wacc) ** year
    # Terminal value: final-year EBITDA at the exit multiple, discounted over the same N years.
    terminal = level * exit_multiple / (1.0 + wacc) ** params.forecast_years

    # Enterprise value to equity value: take off debt, add back cash.
    equity_value = present_value + terminal - debt + cash
    if equity_value <= 0:
        return None
    return equity_value / market_cap


def exit_multiple_from(
    multiples: Sequence[float], floor: float, cap: float, default: float = 10.0
) -> float:
    """Terminal EV/EBITDA multiple: clamp(median(multiples), floor, cap), or default if empty.

    `multiples` are the positive EV/EBITDA ratios of the universe members on the valuation day.
    A company's own multiple already contains its share price, so exiting at it would value
    every company close to where it trades; the cross-section asks instead what the company
    would be worth at a typical large-cap multiple. The median, not the mean, because
    EV/EBITDA is skewed to the right by high-growth names. The [6, 14] band in `main.py` limits
    how far a market-wide re-rating moves every valuation at once. The default 10 is the
    prototype's fixed multiple and is used only when no member has a usable multiple.
    """
    return clamp(statistics.median(multiples), floor, cap) if multiples else default


def buy_threshold(margin_of_safety: float) -> float:
    """Smallest upside that opens a position: 1 / (1 - margin_of_safety).

    Market cap at least margin_of_safety below implied equity value means
    E <= (1 - mos) * V, that is V / E >= 1 / (1 - mos). The base 0.25 gives 1.333..., an
    implied value one third above the market cap. Positions are sold at V / E <= 1, so the gap
    between the two thresholds is what keeps a name from being bought and sold in alternate
    months, the churn of the prototype's overlapping bands.
    """
    return 1.0 / (1.0 - margin_of_safety)
