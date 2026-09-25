"""Tests for dcf_model: a hand-worked valuation, every None path, every bound, and an exact
equivalence check against the valuation code QuantConnect ran for the recorded backtest."""

import ast
import dataclasses
import math
import random
import sys
from pathlib import Path
from statistics import median
from types import SimpleNamespace

import pytest

from dcf_model import (
    FundamentalInputs,
    ValuationParams,
    buy_threshold,
    clamp,
    exit_multiple_from,
    implied_upside,
)

BASE = ValuationParams()


def inputs(**overrides) -> FundamentalInputs:
    """A plain, valuable company (the hand-worked example below); overrides change fields."""
    fields = dict(
        ebitda=1000.0,
        capex=-200.0,
        change_in_wc=-50.0,
        pretax_income=600.0,
        tax_provision=120.0,
        current_debt=100.0,
        long_term_debt=400.0,
        cash=300.0,
        interest_expense=25.0,
        ebitda_growth=0.06,
        market_cap=8000.0,
    )
    fields.update(overrides)
    return FundamentalInputs(**fields)


def upside(params: ValuationParams = BASE, exit_multiple: float = 10.0, **overrides):
    return implied_upside(inputs(**overrides), params, exit_multiple)


# --------------------------------------------------------------------------- hand-worked example


def test_hand_worked_valuation():
    # Ratios to trailing EBITDA of 1,000.
    capex_ratio = 200.0 / 1000.0  # |capex| / EBITDA = 0.20, inside [0, 0.8]
    wc_ratio = 50.0 / 1000.0  # -(-50) / EBITDA = 0.05: working capital absorbed 50 of cash
    tax = 120.0 / 600.0  # provision / pretax = 0.20, inside [0, 0.35]
    fcf_margin = 1.0 - tax - capex_ratio - wc_ratio  # 0.55
    assert fcf_margin == pytest.approx(0.55)

    # Capital structure: D = 100 + 400, C = 300, E = 8,000.
    debt, cash, equity = 500.0, 300.0, 8000.0
    cost_of_debt = 25.0 / debt  # 5%, inside [1%, 12%]
    wacc = equity / (equity + debt) * 0.09 + debt / (equity + debt) * cost_of_debt * (1 - tax)
    assert wacc == pytest.approx(0.0870588, abs=1e-7)  # above the 5% floor

    # Five years of 6% growth (inside [-5%, +15%]), then a 10x exit multiple.
    ebitda_path = [1000.0 * 1.06**k for k in range(1, 6)]
    pv_fcf = sum(e * fcf_margin / (1 + wacc) ** k for k, e in enumerate(ebitda_path, start=1))
    terminal = ebitda_path[-1] * 10.0 / (1 + wacc) ** 5
    assert pv_fcf == pytest.approx(2551.33, abs=0.01)
    assert terminal == pytest.approx(8815.85, abs=0.01)

    equity_value = pv_fcf + terminal - debt + cash
    expected = equity_value / equity
    assert expected == pytest.approx(1.395898, abs=1e-6)

    result = upside()
    assert result == pytest.approx(expected, rel=1e-12)
    # At the base margin of safety (25%) this company is a buy: 1.396 >= 1 / 0.75.
    assert result >= buy_threshold(0.25)


def test_hand_worked_valuation_on_defaults():
    # No debt, no cash, no tax line, no growth rate: default tax 21%, default growth 3%, and
    # WACC equals the cost of equity because there is no debt.
    result = upside(
        capex=None, change_in_wc=None, pretax_income=None, tax_provision=None,
        current_debt=None, long_term_debt=None, cash=None, interest_expense=None,
        ebitda_growth=None, market_cap=10000.0,
    )
    margin, wacc, growth = 1.0 - 0.21, 0.09, 0.03
    level, pv = 1000.0, 0.0
    for k in range(1, 6):
        level *= 1 + growth
        pv += level * margin / (1 + wacc) ** k
    expected = (pv + level * 10.0 / (1 + wacc) ** 5) / 10000.0
    assert result == pytest.approx(expected, rel=1e-12)


# --------------------------------------------------------------------------- None paths


@pytest.mark.parametrize("ebitda", [None, 0.0, -0.0, -1.0, -5000.0])
def test_no_valuation_without_positive_ebitda(ebitda):
    assert upside(ebitda=ebitda) is None


@pytest.mark.parametrize("market_cap", [0.0, -0.0, -1.0, -8000.0])
def test_no_valuation_without_positive_market_cap(market_cap):
    assert upside(market_cap=market_cap) is None


def test_no_valuation_when_fcf_margin_is_negative():
    # capex 90% of EBITDA (bounded to 80%) and working capital 40% (bounded to 30%) leave
    # 1 - 0.2 - 0.8 - 0.3 < 0.
    assert upside(capex=-900.0, change_in_wc=-400.0) is None


def test_no_valuation_when_fcf_margin_is_exactly_zero():
    # 0.25, 0.5 and 0.25 are exact in binary, so 1 - 0.25 - 0.5 - 0.25 is exactly 0.0.
    assert upside(tax_provision=150.0, capex=-500.0, change_in_wc=-250.0) is None
    # One unit less capex leaves a positive margin and a valuation.
    assert upside(tax_provision=150.0, capex=-499.0, change_in_wc=-250.0) is not None


def test_no_valuation_when_equity_value_is_negative():
    # Debt of 50,000 against an enterprise value near 11,000.
    assert upside(long_term_debt=50000.0) is None


def test_no_valuation_when_equity_value_is_exactly_zero():
    # With a zero cost of equity and no interest, the blended rate is below 5% for any debt
    # level, so the floor holds WACC at exactly 5% and the enterprise value does not depend
    # on debt. Debt equal to that enterprise value leaves an equity value of exactly zero.
    params = ValuationParams(cost_of_equity=0.0)
    fields = dict(
        capex=None, change_in_wc=None, pretax_income=None, tax_provision=None,
        current_debt=None, cash=None, interest_expense=None, ebitda_growth=None,
    )
    margin = 1.0 - 0.21  # default tax; the capex and working-capital ratios are zero
    present_value, level = 0.0, 1000.0
    for year in range(1, 6):
        level *= (1.0 + 0.03)
        present_value += level * margin / (1.0 + 0.05) ** year
    enterprise_value = present_value + level * 10.0 / (1.0 + 0.05) ** 5

    assert upside(params, long_term_debt=enterprise_value, **fields) is None
    positive = upside(params, long_term_debt=enterprise_value - 80.0, **fields)
    assert positive == pytest.approx(80.0 / 8000.0, rel=1e-6)


# --------------------------------------------------------------------------- bounds


def test_tax_rate_bounds_and_default():
    at_cap = upside(tax_provision=210.0)  # 210 / 600 = 0.35 exactly
    assert upside(tax_provision=360.0) == at_cap  # 0.60 is bounded to 0.35
    assert upside(tax_provision=204.0) != at_cap  # 0.34 is not bounded
    at_zero = upside(tax_provision=0.0)
    assert upside(tax_provision=-60.0) == at_zero  # a tax credit is bounded to 0
    default = upside(pretax_income=100.0, tax_provision=21.0)  # 21 / 100 = 0.21 exactly
    assert upside(tax_provision=None) == default
    assert upside(pretax_income=None) == default
    assert upside(pretax_income=0.0) == default
    assert upside(pretax_income=-600.0) == default
    assert upside(pretax_income=-0.0) == default


def test_capex_ratio_bound():
    # No tax and a working-capital release keep the margin positive at the capex bound.
    base = dict(tax_provision=0.0, change_in_wc=300.0)
    at_cap = upside(capex=-800.0, **base)  # 800 / 1000 = 0.8 exactly
    assert at_cap is not None
    assert upside(capex=-900.0, **base) == at_cap
    assert upside(capex=-5000.0, **base) == at_cap
    assert upside(capex=-700.0, **base) != at_cap


def test_capex_sign_does_not_matter():
    assert upside(capex=200.0) == upside(capex=-200.0)
    assert upside(capex=None) == upside(capex=0.0)
    # Capex is a deduction: more capex, lower valuation.
    assert upside(capex=-300.0) < upside(capex=-200.0) < upside(capex=0.0)


def test_working_capital_bounds_and_sign():
    at_cap = upside(change_in_wc=-300.0)  # absorbed 30% of EBITDA, the bound
    assert upside(change_in_wc=-500.0) == at_cap
    at_floor = upside(change_in_wc=300.0)  # released 30% of EBITDA, the bound
    assert upside(change_in_wc=500.0) == at_floor
    assert upside(change_in_wc=-200.0) != at_cap
    # Cash released by working capital raises the valuation; cash absorbed lowers it.
    assert upside(change_in_wc=50.0) > upside(change_in_wc=None) > upside(change_in_wc=-50.0)
    assert upside(change_in_wc=None) == upside(change_in_wc=0.0)


def test_cost_of_debt_bounds():
    # Debt is 500 in the example.
    at_cap = upside(interest_expense=60.0)  # 60 / 500 = 0.12 exactly
    assert upside(interest_expense=100.0) == at_cap
    assert upside(interest_expense=50.0) != at_cap
    at_floor = upside(interest_expense=5.0)  # 5 / 500 = 0.01 exactly
    assert upside(interest_expense=1.0) == at_floor
    assert upside(interest_expense=0.0) == at_floor
    assert upside(interest_expense=None) == at_floor
    # Interest is used as a magnitude.
    assert upside(interest_expense=-25.0) == upside(interest_expense=25.0)


def test_cost_of_debt_is_zero_without_debt():
    no_debt = dict(current_debt=None, long_term_debt=0.0)
    assert upside(interest_expense=100.0, **no_debt) == upside(interest_expense=0.0, **no_debt)
    negative_debt = dict(current_debt=-10.0, long_term_debt=None)
    assert upside(interest_expense=100.0, **negative_debt) == upside(
        interest_expense=0.0, **negative_debt
    )


def test_growth_bounds_and_default():
    assert upside(ebitda_growth=0.40) == upside(ebitda_growth=0.15)
    assert upside(ebitda_growth=0.10) != upside(ebitda_growth=0.15)
    assert upside(ebitda_growth=-0.50) == upside(ebitda_growth=-0.05)
    assert upside(ebitda_growth=-0.02) != upside(ebitda_growth=-0.05)
    assert upside(ebitda_growth=None) == upside(ebitda_growth=0.03)


def test_wacc_floor():
    # Without debt WACC equals the cost of equity, so a cost of equity below 5% is floored.
    no_debt = dict(current_debt=None, long_term_debt=None)
    floor = upside(ValuationParams(cost_of_equity=0.05), **no_debt)
    assert upside(ValuationParams(cost_of_equity=0.01), **no_debt) == floor
    assert upside(ValuationParams(cost_of_equity=0.0), **no_debt) == floor
    assert upside(ValuationParams(cost_of_equity=0.06), **no_debt) < floor


def test_valuation_moves_the_right_way():
    assert upside(exit_multiple=12.0) > upside(exit_multiple=10.0)
    assert upside(ValuationParams(cost_of_equity=0.10)) < upside(ValuationParams(cost_of_equity=0.08))
    assert upside(cash=1000.0) > upside(cash=300.0)
    assert upside(market_cap=4000.0) > upside(market_cap=8000.0)


# --------------------------------------------------------------------------- helpers


def test_clamp():
    assert clamp(0.5, 0.0, 1.0) == 0.5
    assert clamp(-1.0, 0.0, 1.0) == 0.0
    assert clamp(2.0, 0.0, 1.0) == 1.0
    assert clamp(0.0, 0.0, 1.0) == 0.0
    assert clamp(1.0, 0.0, 1.0) == 1.0
    # max(lo, min(hi, x)) returns lo, not x, on a 0.0 / -0.0 tie.
    assert math.copysign(1.0, clamp(-0.0, 0.0, 0.8)) == 1.0


def test_exit_multiple_is_bounded_median():
    assert exit_multiple_from([8.0, 12.0, 10.0], 6.0, 14.0) == 10.0
    assert exit_multiple_from([8.0, 9.0, 11.0, 13.0], 6.0, 14.0) == 10.0
    assert exit_multiple_from([7.0, 30.0, 45.0, 60.0, 9.0], 6.0, 14.0) == 14.0
    assert exit_multiple_from([2.0, 3.0, 4.0], 6.0, 14.0) == 6.0
    assert exit_multiple_from([6.0], 6.0, 14.0) == 6.0


def test_exit_multiple_default():
    assert exit_multiple_from([], 6.0, 14.0) == 10.0
    assert exit_multiple_from([], 6.0, 14.0, default=12.5) == 12.5


def test_buy_threshold():
    assert buy_threshold(0.25) == 1.0 / 0.75
    assert buy_threshold(0.0) == 1.0
    assert buy_threshold(0.5) == 2.0
    assert buy_threshold(0.15) == pytest.approx(1.17647, abs=1e-5)


def test_params_defaults_are_the_models_constants():
    assert dataclasses.asdict(BASE) == dict(
        cost_of_equity=0.09, forecast_years=5, growth_floor=-0.05, growth_cap=0.15,
        default_growth=0.03, default_tax=0.21, capex_ratio_cap=0.8, wc_ratio_floor=-0.3,
        wc_ratio_cap=0.3, tax_cap=0.35, cost_of_debt_floor=0.01, cost_of_debt_cap=0.12,
        wacc_floor=0.05,
    )


def test_model_uses_the_standard_library_only():
    source = (Path(__file__).resolve().parents[1] / "dcf_model.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names)


# --------------------------------------------------------------------------- equivalence
#
# RecordedAlgorithm is the valuation code of main.py exactly as QuantConnect ran it for the
# recorded base run (project 36836412, backtest 54b5e0649da4a9cbf3f7dce6c409c7fe, main.py
# sha256 4f7f49ed7adf30b3e57d0cbc4a754d47fd365cfa9d62e52d8ea7497a30ffa599 as run on QuantConnect;
# the published copy in results/raw/dcf__base.json.gz differs only in one rewritten docstring
# paragraph). The body of upside() and the two expressions from rebalance() are copied from the
# code stored with that backtest. The only change is at the edges: the Morningstar readers (_flow, _balance,
# _growth) return their argument, because the fake record below already holds the floats the
# real readers would have returned.


class RecordedAlgorithm:
    def __init__(self, params: ValuationParams, margin_of_safety: float = 0.25):
        self.cost_of_equity = params.cost_of_equity
        self.margin_of_safety = margin_of_safety
        self.forecast_years = params.forecast_years
        self.growth_floor, self.growth_cap = params.growth_floor, params.growth_cap
        self.default_growth = params.default_growth
        self.default_tax = params.default_tax
        self.multiple_floor, self.multiple_cap = 6.0, 14.0

    @staticmethod
    def _flow(value):
        return value

    @staticmethod
    def _balance(value):
        return value

    @staticmethod
    def _growth(value):
        return value

    @staticmethod
    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    def upside(self, f, exit_multiple: float):
        inc = f.financial_statements.income_statement
        cf = f.financial_statements.cash_flow_statement
        bs = f.financial_statements.balance_sheet

        ebitda = self._flow(inc.ebitda)
        if ebitda is None or ebitda <= 0:
            return None
        market_cap = float(f.market_cap)
        if market_cap <= 0:
            return None

        capex = self._flow(cf.capital_expenditure) or 0.0
        dwc = self._flow(cf.change_in_working_capital) or 0.0
        capex_ratio = self._clamp(abs(capex) / ebitda, 0.0, 0.8)
        wc_ratio = self._clamp(-dwc / ebitda, -0.3, 0.3)

        pretax = self._flow(inc.pretax_income)
        tax_provision = self._flow(inc.tax_provision)
        if pretax and pretax > 0 and tax_provision is not None:
            tax = self._clamp(tax_provision / pretax, 0.0, 0.35)
        else:
            tax = self.default_tax

        fcf_margin = 1.0 - tax - capex_ratio - wc_ratio
        if fcf_margin <= 0:
            return None

        debt = (self._balance(bs.current_debt) or 0.0) + (self._balance(bs.long_term_debt) or 0.0)
        cash = self._balance(bs.cash_and_cash_equivalents) or 0.0
        interest = abs(self._flow(inc.interest_expense) or 0.0)
        cost_of_debt = self._clamp(interest / debt, 0.01, 0.12) if debt > 0 else 0.0
        total_capital = market_cap + debt
        wacc = (market_cap / total_capital) * self.cost_of_equity \
            + (debt / total_capital) * cost_of_debt * (1.0 - tax)
        wacc = max(wacc, 0.05)

        growth = self._growth(f.operation_ratios.ebitda_growth)
        growth = self.default_growth if growth is None else self._clamp(growth, self.growth_floor, self.growth_cap)

        present_value = 0.0
        level = ebitda
        for year in range(1, self.forecast_years + 1):
            level *= (1.0 + growth)
            present_value += level * fcf_margin / (1.0 + wacc) ** year
        terminal = level * exit_multiple / (1.0 + wacc) ** self.forecast_years

        equity_value = present_value + terminal - debt + cash
        if equity_value <= 0:
            return None
        return equity_value / market_cap

    def exit_multiple(self, multiples):
        return self._clamp(median(multiples), self.multiple_floor, self.multiple_cap) if multiples else 10.0

    def buy_threshold(self):
        return 1.0 / (1.0 - self.margin_of_safety)


def fake_fundamental(x: FundamentalInputs) -> SimpleNamespace:
    """The shape of a QuantConnect Fundamental object, holding the already-read floats."""
    return SimpleNamespace(
        market_cap=x.market_cap,
        financial_statements=SimpleNamespace(
            income_statement=SimpleNamespace(
                ebitda=x.ebitda,
                pretax_income=x.pretax_income,
                tax_provision=x.tax_provision,
                interest_expense=x.interest_expense,
            ),
            cash_flow_statement=SimpleNamespace(
                capital_expenditure=x.capex,
                change_in_working_capital=x.change_in_wc,
            ),
            balance_sheet=SimpleNamespace(
                current_debt=x.current_debt,
                long_term_debt=x.long_term_debt,
                cash_and_cash_equivalents=x.cash,
            ),
        ),
        operation_ratios=SimpleNamespace(ebitda_growth=x.ebitda_growth),
    )


def outcome(fn, *args):
    """The value a call returns, or the type of arithmetic error it raises."""
    try:
        return ("value", fn(*args))
    except ArithmeticError as exc:
        return ("raised", type(exc))


def draw(rng: random.Random, scale: float, lo: float, hi: float, optional: bool = True):
    """A statement value: sometimes None, 0.0 or -0.0, otherwise uniform on [lo, hi] * scale."""
    r = rng.random()
    if r < 0.12:
        return rng.choice((None, 0.0, -0.0) if optional else (0.0, -0.0))
    return rng.uniform(lo, hi) * scale


def random_case(rng: random.Random):
    scale = 10.0 ** rng.uniform(5.0, 11.0)
    r = rng.random()
    if r < 0.08:
        ebitda = rng.choice((None, 0.0, -0.0))
    elif r < 0.16:
        ebitda = -rng.uniform(0.0, 1.0) * scale
    else:
        ebitda = rng.uniform(0.001, 1.0) * scale
    r = rng.random()
    if r < 0.04:
        market_cap = rng.choice((0.0, -0.0))
    elif r < 0.08:
        market_cap = -rng.uniform(0.1, 20.0) * scale
    else:
        market_cap = rng.uniform(0.1, 40.0) * scale
    growth_roll = rng.random()
    x = FundamentalInputs(
        ebitda=ebitda,
        capex=draw(rng, scale, -1.5, 0.3),
        change_in_wc=draw(rng, scale, -0.8, 0.8),
        pretax_income=draw(rng, scale, -0.5, 1.0),
        tax_provision=draw(rng, scale, -0.2, 0.6),
        current_debt=draw(rng, scale, -0.05, 1.0),
        long_term_debt=draw(rng, scale, 0.0, 5.0),
        cash=draw(rng, scale, 0.0, 1.5),
        interest_expense=draw(rng, scale, -0.3, 0.3),
        ebitda_growth=None if growth_roll < 0.1 else (0.0 if growth_roll < 0.13 else rng.uniform(-0.8, 0.8)),
        market_cap=market_cap,
    )
    params = ValuationParams(
        cost_of_equity=rng.choice((0.09, 0.08, 0.10, rng.uniform(0.0, 0.2))),
        forecast_years=rng.choice((5, 5, 5, rng.randint(1, 10))),
        default_growth=rng.choice((0.03, rng.uniform(-0.05, 0.1))),
        default_tax=rng.choice((0.21, rng.uniform(0.0, 0.4))),
    )
    exit_multiple = rng.choice((6.0, 10.0, 14.0, rng.uniform(4.0, 20.0)))
    return x, params, exit_multiple


def test_implied_upside_equals_recorded_code_on_random_inputs():
    rng = random.Random(20260925)
    n_cases = 5000
    values = nones = 0
    for _ in range(n_cases):
        x, params, exit_multiple = random_case(rng)
        new = outcome(implied_upside, x, params, exit_multiple)
        old = outcome(RecordedAlgorithm(params).upside, fake_fundamental(x), exit_multiple)
        assert new == old, (x, params, exit_multiple, new, old)
        if new[0] == "value":
            assert type(new[1]) is type(old[1])
            if new[1] is None:
                nones += 1
            else:
                values += 1
    # The draws must exercise both outcomes, or the comparison above proves little.
    assert values >= 1000
    assert nones >= 1000


def test_implied_upside_equals_recorded_code_on_edge_cases():
    # Market cap plus debt of exactly zero divides by zero in both versions.
    x = inputs(current_debt=-8000.0, long_term_debt=None, market_cap=8000.0)
    assert outcome(implied_upside, x, BASE, 10.0) == ("raised", ZeroDivisionError)
    assert outcome(RecordedAlgorithm(BASE).upside, fake_fundamental(x), 10.0) == (
        "raised", ZeroDivisionError
    )
    for x in (inputs(), inputs(capex=-0.0, change_in_wc=-0.0), inputs(pretax_income=-0.0)):
        assert implied_upside(x, BASE, 10.0) == RecordedAlgorithm(BASE).upside(fake_fundamental(x), 10.0)


def test_exit_multiple_and_threshold_equal_recorded_code():
    rng = random.Random(20260926)
    recorded = RecordedAlgorithm(BASE)
    for _ in range(2000):
        multiples = [rng.uniform(0.5, 60.0) for _ in range(rng.randint(0, 300))]
        assert exit_multiple_from(multiples, 6.0, 14.0) == recorded.exit_multiple(multiples)
        mos = rng.uniform(0.0, 0.9)
        assert buy_threshold(mos) == RecordedAlgorithm(BASE, margin_of_safety=mos).buy_threshold()
