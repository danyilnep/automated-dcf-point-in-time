"""QuantConnect algorithm: a monthly point-in-time DCF screen on large US non-financial companies.

Files
    main.py       universe selection, reading Morningstar fields, schedule and orders (needs LEAN)
    dcf_model.py  the valuation arithmetic, pure Python, unit-tested in tests/

Project parameters (QuantConnect project parameters, or `parameters` in config.json for the LEAN
CLI), with the defaults used when a parameter is not set:
    universe_size     150   largest primary shares by market cap valued each month
    max_positions     20    equal-weight slots, 1 / max_positions of equity each
    cost_of_equity    0.09  one cost of equity for every company
    margin_of_safety  0.25  buy when market cap <= (1 - margin) * implied equity value

The recorded base run is QuantConnect project 36836412, backtest
54b5e0649da4a9cbf3f7dce6c409c7fe (1 Jan 2016 to 31 Dec 2024, $100,000). It ran this file
before the valuation arithmetic moved into dcf_model.py; the move kept every expression, loop
and container, so the decisions are meant to be the same to the last digit.
"""

# region imports
from AlgorithmImports import *
import math
from dcf_model import FundamentalInputs, ValuationParams, buy_threshold, exit_multiple_from, implied_upside
# endregion


class PointInTimeDcfValue(QCAlgorithm):
    """Automated fundamental analysis, rebuilt point-in-time.

    On the first trading day of each month the algorithm values the largest
    non-financial US companies with a five-year EBITDA-based discounted cash
    flow computed only from the fundamentals QuantConnect held on that day
    (Morningstar, point-in-time), and holds an equal-weight book of the names
    whose market capitalisation sits at least `margin_of_safety` below the
    implied equity value. A position is sold when the market capitalisation
    reaches the implied equity value, or when the name leaves the universe.

    Origin: a 2024 Mercury Capital Management quant-team project
    that computed seven fair values by hand from yfinance and traded
    them through 2023. This version keeps the valuation structure of that
    prototype (EBITDA forecast, FCF as a share of EBITDA, WACC, exit multiple)
    and fixes its defects: the inverted buy and sell bands, fair values that
    used year-end 2023 data inside a 2023 backtest, capital expenditure entering
    with the wrong sign, and a hand-picked seven-stock universe.
    """

    def initialize(self) -> None:
        self.set_start_date(2016, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Every assumption of the valuation is a named parameter.
        self.universe_size = int(self.get_parameter("universe_size", 150))
        self.max_positions = int(self.get_parameter("max_positions", 20))
        self.cost_of_equity = float(self.get_parameter("cost_of_equity", 0.09))
        self.margin_of_safety = float(self.get_parameter("margin_of_safety", 0.25))
        self.forecast_years = 5
        self.growth_floor, self.growth_cap = -0.05, 0.15
        self.default_growth = 0.03
        self.default_tax = 0.21
        self.multiple_floor, self.multiple_cap = 6.0, 14.0
        self.min_price = 5.0
        # The fixed bounds of the model (capex, working-capital, tax, cost-of-debt and WACC
        # limits) take their defaults in ValuationParams; dcf_model.py explains each one.
        self.valuation_params = ValuationParams(
            cost_of_equity=self.cost_of_equity,
            forecast_years=self.forecast_years,
            growth_floor=self.growth_floor,
            growth_cap=self.growth_cap,
            default_growth=self.default_growth,
            default_tax=self.default_tax,
        )

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select)
        self.last_selection_month = -1
        self.members: set = set()

        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance,
        )

    # ------------------------------------------------------------------ universe
    def select(self, fundamental: List[Fundamental]) -> List[Symbol]:
        """Largest `universe_size` primary shares by market cap, non-financial,
        refreshed once a month (the day before the rebalance)."""
        if self.time.month == self.last_selection_month:
            return Universe.UNCHANGED
        self.last_selection_month = self.time.month
        # Banks, insurers and property companies are excluded because EBITDA, capex and
        # working capital do not describe how they make or reinvest money, so an EBITDA DCF
        # has nothing to say about them.
        excluded = (MorningstarSectorCode.FINANCIAL_SERVICES, MorningstarSectorCode.REAL_ESTATE)
        candidates = [
            f for f in fundamental
            if f.has_fundamental_data
            and f.price > self.min_price
            and f.market_cap > 0
            and f.security_reference.is_primary_share
            and f.asset_classification.morningstar_sector_code not in excluded
        ]
        candidates.sort(key=lambda f: f.market_cap, reverse=True)
        return [f.symbol for f in candidates[: self.universe_size]]

    def on_securities_changed(self, changes: SecurityChanges) -> None:
        for security in changes.added_securities:
            if security.symbol != self.spy:
                self.members.add(security.symbol)
        for security in changes.removed_securities:
            self.members.discard(security.symbol)
            # A name that drops out of the top `universe_size` is no longer valued, so it is
            # sold at once rather than held without a view.
            if security.invested:
                self.liquidate(security.symbol, tag="left universe")

    # ------------------------------------------------------------------ valuation inputs
    @staticmethod
    def _period_value(field, periods) -> Optional[float]:
        """First available period of a Morningstar multi-period field, else None."""
        if field is None:
            return None
        for period in periods:
            try:
                value = getattr(field, period)
            except Exception:
                continue
            if value is None:
                continue
            try:
                value = float(value)
            except Exception:
                continue
            if not math.isnan(value):
                return value
        return None

    # Morningstar stores each statement line under several periods. A flow is wanted over the
    # trailing twelve months, which smooths seasonality. A balance is wanted at the latest
    # quarter-end, the freshest snapshot of debt and cash. A growth rate is wanted over one
    # year, with three years as the fallback. "value" is the field's default period.
    def _flow(self, field) -> Optional[float]:
        return self._period_value(field, ("twelve_months", "value"))

    def _balance(self, field) -> Optional[float]:
        return self._period_value(field, ("three_months", "twelve_months", "value"))

    def _growth(self, field) -> Optional[float]:
        return self._period_value(field, ("one_year", "three_years", "value"))

    def _valuation_inputs(self, f: Fundamental) -> FundamentalInputs:
        """Read one company's valuation inputs from the Morningstar record QuantConnect holds
        for the current day. Fields are passed through unchanged, with Morningstar's signs;
        dcf_model.implied_upside does all the arithmetic and the None handling."""
        inc = f.financial_statements.income_statement
        cf = f.financial_statements.cash_flow_statement
        bs = f.financial_statements.balance_sheet
        return FundamentalInputs(
            ebitda=self._flow(inc.ebitda),
            capex=self._flow(cf.capital_expenditure),
            change_in_wc=self._flow(cf.change_in_working_capital),
            pretax_income=self._flow(inc.pretax_income),
            tax_provision=self._flow(inc.tax_provision),
            current_debt=self._balance(bs.current_debt),
            long_term_debt=self._balance(bs.long_term_debt),
            cash=self._balance(bs.cash_and_cash_equivalents),
            interest_expense=self._flow(inc.interest_expense),
            ebitda_growth=self._growth(f.operation_ratios.ebitda_growth),
            market_cap=float(f.market_cap),
        )

    def upside(self, f: Fundamental, exit_multiple: float) -> Optional[float]:
        """Implied equity value divided by market capitalisation, from the
        point-in-time trailing-twelve-month statements. None when the inputs
        cannot support a valuation (negative EBITDA, missing statements).
        The formulas are in dcf_model.implied_upside."""
        return implied_upside(self._valuation_inputs(f), self.valuation_params, exit_multiple)

    # ------------------------------------------------------------------ trading
    def rebalance(self) -> None:
        multiples = []
        fundamentals = {}
        for symbol in list(self.members):
            security = self.securities[symbol]
            f = security.fundamentals
            if f is None or not security.has_data:
                continue
            fundamentals[symbol] = f
            m = f.valuation_ratios.ev_to_ebitda
            # EV/EBITDA is negative when EBITDA is negative and NaN when it is missing; only
            # positive multiples describe what the market pays for a unit of EBITDA.
            if m is not None and not math.isnan(m) and m > 0:
                multiples.append(m)
        if not fundamentals:
            return
        # Terminal multiple: the universe's median EV/EBITDA that day, bounded.
        exit_multiple = exit_multiple_from(multiples, self.multiple_floor, self.multiple_cap)

        upsides = {}
        for symbol, f in fundamentals.items():
            u = self.upside(f, exit_multiple)
            if u is not None:
                upsides[symbol] = u

        threshold = buy_threshold(self.margin_of_safety)
        # Sell side first. A holding is kept while its market cap is still below the implied
        # equity value (upside above 1). It is sold when the price has reached that value, or
        # when there is no valuation for it this month (no fundamentals, or a None from the
        # model), because the strategy does not hold names it cannot value.
        keep = set()
        for kvp in self.portfolio:
            symbol, holding = kvp.key, kvp.value
            if not holding.invested or symbol == self.spy:
                continue
            u = upsides.get(symbol)
            if u is not None and u > 1.0 and symbol in self.members:
                keep.add(symbol)
            else:
                self.liquidate(symbol, tag="reached implied value" if u is not None else "no valuation")

        # Buy side: the names with the highest upside above the buy threshold fill the free
        # slots. Every name, kept or new, is set back to 1 / max_positions of equity; unfilled
        # slots stay in cash rather than being spread over fewer names.
        candidates = sorted(
            ((s, u) for s, u in upsides.items() if u >= threshold and s not in keep),
            key=lambda item: item[1], reverse=True,
        )
        slots = max(0, self.max_positions - len(keep))
        new = [s for s, _ in candidates[:slots]]
        weight = 1.0 / self.max_positions
        targets = [PortfolioTarget(s, weight) for s in list(keep) + new]
        if targets:
            self.set_holdings(targets)
        self.log(f"{self.time.date()} multiple {exit_multiple:.1f} valued {len(upsides)} "
                 f"candidates {len(candidates)} keep {len(keep)} new {len(new)}")

    def on_end_of_algorithm(self) -> None:
        self.log(f"final equity {self.portfolio.total_portfolio_value:,.0f}")
