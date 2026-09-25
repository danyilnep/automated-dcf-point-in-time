import yfinance as yf
import pandas as pd


def calculate_cap(ticker, year):
    stock = yf.Ticker(ticker)

    # Transpose financial statements to have years as rows
    financials = stock.financials.T

    year_str = str(year)

    # Ensure year is in the DataFrame index for financials
    if year_str in financials.index:
        financials_year = financials.loc[year_str]

        # Check and fetch 'Diluted Average Shares' from financials
        if 'Diluted Average Shares' in financials_year:
            diluted_average_shares = financials_year['Diluted Average Shares']
        else:
            print(f"'Diluted Average Shares' data not available for {year}.")
            return

        # Attempt to fetch the year-end price
        try:
            history = stock.history(period="1d", start=f"{year}-12-31", end=f"{year + 1}-01-01")
            if not history.empty:
                year_end_price = history['Close'].iloc[0]
            else:
                history = stock.history(start=f"{year}-01-01", end=f"{year + 1}-01-01")
                year_end_price = history['Close'].iloc[-1]
        except Exception as e:
            print(f"Error fetching year-end price: {e}")
            return
        # Calculate Market Value of Equity (E)
        market_value_equity = year_end_price * diluted_average_shares

        return market_value_equity.values[0]
    else:
        print(f"Financial data for {year} is not available.")
        return


def calculate_wacc(ticker, year, cap):
    stock = yf.Ticker(ticker)

    # Transpose financial statements to have years as rows
    financials = stock.financials.T
    balance_sheet = stock.balance_sheet.T
    cash_flow = stock.cashflow.T
    year_str = str(year)

    # Check if the year is available in the financials
    if year_str in financials.index:
        # Extract data for the year
        financials_year = financials.loc[year_str]
        balance_sheet_year = balance_sheet.loc[year_str]
        cash_flow_year = cash_flow.loc[year_str]

        # Estimate Market Value of Debt (D)
        total_debt = balance_sheet_year.get('Total Debt', pd.Series([0])).iloc[0]

        # Approximate Cost of Debt (Rd)
        interest_expense = financials_year.get('Interest Expense', pd.Series([0])).iloc[0]
        if total_debt > 0:
            cost_of_debt = interest_expense / total_debt
        else:
            cost_of_debt = 0

        # Tax Rate Calculation (Tc)
        tax_expense = financials_year.get('Tax Provision', pd.Series([0])).iloc[0]
        pretax_income = financials_year.get('Pretax Income', pd.Series([0])).iloc[0]
        if pretax_income > 0:
            tax_rate = tax_expense / pretax_income
        else:
            tax_rate = 0

        # WACC Calculation Placeholder
        # Placeholder for Re, as real calculation requires external data
        cost_of_equity = 0.08  # Assuming an 8% cost of equity as a placeholder
        v = cap + total_debt
        wacc = (cap / v) * cost_of_equity + (total_debt / v) * cost_of_debt * (1 - tax_rate)

        return wacc, tax_rate

    else:
        return f"Data not available for year {year}"


def fetch_financial_metrics_for_years(ticker, year, wacc, tax_rate):
    """
    Fetches financial data for a given ticker and a range of years,
    and calculates various financial metrics.

    Parameters:
    ticker (str): The ticker symbol of the company
    start_year (int): The start year for the financial data
    end_year (int): The end year for the financial data

    Returns:
    dict: A dictionary containing the financial metrics for each year
    """

    # Initialize dictionary to store the results
    results = {}

    # Fetch stock data
    stock = yf.Ticker(ticker)

    # Transpose financial statements to have years as rows
    financials = stock.financials.T
    balance_sheet = stock.balance_sheet.T
    cash_flow = stock.cashflow.T
    year_str = str(year)

    # Ensure year is in the DataFrame index
    if year_str in financials.index:
        # Extract data for the year
        financials_year = financials.loc[year_str]
        balance_sheet_year = balance_sheet.loc[year_str]
        cash_flow_year = cash_flow.loc[year_str]

        # Fetch metrics
        ebitda = financials_year['EBITDA']
        capex = cash_flow_year['Capital Expenditure']
        change_in_working_capital = cash_flow_year['Change In Working Capital']
        net_debt = balance_sheet_year['Net Debt']
        diluted_average_shares = financials_year['Diluted Average Shares']

        # Store results
        results = {
            'EBITDA': ebitda.values[0],
            'CAPEX': capex.values[0],
            'Tax Rate': tax_rate,
            'Change in Working Capital': change_in_working_capital.values[0],
            'WACC': wacc,
            'Net Debt': net_debt.values[0],
            'Shares': diluted_average_shares.values[0]
        }
    else:
        results[year] = f"Data not available for year {year}"

    return results


def create_forecasts(ticker, start_year, end_year):
    total_change = 0
    num_changes = 0

    # Initialize to store first year's EBITDA for growth rate calculation
    previous_ebitda = None

    # Loop over each year to calculate the change in EBITDA
    for year in range(start_year, end_year):
        cap = calculate_cap(ticker, year)
        wacc, tax_rate = calculate_wacc(ticker, year, cap)  # Assuming calculate_wacc returns a tuple (wacc, tax_rate)
        fetched_data = fetch_financial_metrics_for_years(ticker, year, wacc, tax_rate)

        ebitda = fetched_data['EBITDA']

        if previous_ebitda is not None:
            change = ebitda - previous_ebitda
            total_change += change
            num_changes += 1

        previous_ebitda = ebitda

    # Calculate average yearly EBITDA change
    if num_changes > 0:
        average_change = total_change / num_changes
    else:
        print("Not enough data to calculate average EBITDA change.")
        return

    # Forecast future EBITDA using the average change
    forecasts = []
    last_known_ebitda = previous_ebitda
    for year in range(end_year, end_year + 5):  # Forecasting for 5 years beyond end_date
        forecasted_ebitda = last_known_ebitda + average_change
        forecasts.append(forecasted_ebitda)
        last_known_ebitda = forecasted_ebitda

    return forecasts


def calculate_percentage_metrics(ticker, year, wacc, tax_rate):
    """
    Fetches financial metrics for a given year and calculates CAPEX percent of EBITDA and
    change in working capital percent of EBITDA.

    Parameters:
    ticker (str): The ticker symbol of the company.
    year (int): The year for which to calculate the metrics.
    wacc (float): Weighted average cost of capital.
    tax_rate (float): Tax rate applicable to the company.

    Returns:
    capex_percent_of_ebitda (float): CAPEX as a percentage of EBITDA.
    change_in_working_capital_percent_of_ebitda (float): Change in working capital as a percentage of EBITDA.
    """

    financial_metrics = fetch_financial_metrics_for_years(ticker, year, wacc, tax_rate)

    ebitda = financial_metrics['EBITDA']
    capex = financial_metrics['CAPEX']
    change_in_working_capital = financial_metrics['Change in Working Capital']

    # Prevent division by zero
    if ebitda != 0:
        capex_percent_of_ebitda = capex / ebitda
        change_in_working_capital_percent_of_ebitda = change_in_working_capital / ebitda
    else:
        # Return None or some form of indication that calculation couldn't be performed
        return None, None

    return capex_percent_of_ebitda, change_in_working_capital_percent_of_ebitda


def calculate_ebitda_value(ebitda_forecasts, capex_percent_of_ebitda, tax_rate,
                           change_in_working_capital_percent_of_ebitda, wacc, ebitda_exit_multiple):
    years = range(1, len(ebitda_forecasts) + 1)  # Adjusting years dynamically based on forecasts length
    # Calculating Free Cash Flows (FCFs)
    fcfs = [(ebitda * (1 - capex_percent_of_ebitda - tax_rate - change_in_working_capital_percent_of_ebitda)) for
            ebitda in ebitda_forecasts]

    # Discounting FCFs to Present Value (PV)
    pv_fcfs = [fcf / ((1 + wacc) ** year) for fcf, year in zip(fcfs, years)]

    # Calculating the Terminal Value (TV) using EBITDA Exit Multiple
    terminal_value = ebitda_forecasts[-1] * ebitda_exit_multiple

    # Discounting Terminal Value to Present Value
    pv_terminal_value = terminal_value / ((1 + wacc) ** len(years))

    # Summing PVs to get the Total DCF Value
    total_dcf_value = sum(pv_fcfs) + pv_terminal_value

    return total_dcf_value


ticker = 'NKE' #AAPL, AVGO, NVO, XOM, UNH, PG, NKE
year = 2023
cap_value = calculate_cap(ticker, year)
wacc, tax_rate = calculate_wacc(ticker, year, cap_value)
capex_percent, change_in_wc_percent = calculate_percentage_metrics(ticker, year, wacc, tax_rate)
forecasts = create_forecasts(ticker, 2020, 2023)
ebxm = 10
shares = fetch_financial_metrics_for_years(ticker, year, wacc, tax_rate)['Shares']
net_debt = fetch_financial_metrics_for_years(ticker, year, wacc, tax_rate)['Net Debt']
dcf_value = calculate_ebitda_value(
    forecasts,
    capex_percent,
    tax_rate,
    change_in_wc_percent,
    wacc,
    ebxm
)
print(tax_rate)
print(f"The calculated DCF value is: {dcf_value}")
fair_price = (dcf_value - net_debt) / shares
print(f"fair price =  {fair_price} .")
