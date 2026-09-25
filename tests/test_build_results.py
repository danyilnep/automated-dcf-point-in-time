"""Checks of the helpers in analysis/build_results.py that the committed exports do not
exercise on their own."""

from analysis.build_results import (
    PROTOTYPE_PROJECT,
    cap_probe_summary,
    error_line,
    list_reason,
    log_lines,
    parse_cap_log,
    probe_month,
    snake,
)


def test_error_line_decodes_entities_and_skips_the_fatal_header():
    assert error_line({"error": "\n Runtime Error: &#039;x&#039;  failed\nat trade"}) == \
        "Runtime Error: 'x' failed"
    fatal = {"error": "[ERROR] FATAL UNHANDLED EXCEPTION: ^^^, in a.py", "stacktrace": "No file\nat b"}
    assert error_line(fatal) == "No file"
    assert error_line({"error": None}) == ""


def test_unlisted_prototype_runs_get_a_reason_and_other_projects_do_not():
    final = {"netProfit": 27.233, "sharpeRatio": 1.878, "drawdown": 2.6, "trades": 363}
    same = {"backtestId": "a", "status": "Completed.", "error": None, **final}
    assert "same headline statistics" in list_reason(PROTOTYPE_PROJECT, same, final)
    crashed = {"backtestId": "b", "status": "Runtime Error", "trades": 32,
               "error": "Runtime Error: 'NoneType' object has no attribute 'Price'"}
    assert list_reason(PROTOTYPE_PROJECT, crashed, final).endswith("during the backtest after 32 orders")
    assert list_reason(36836412, same, final) is None


def test_cap_probe_summary_rolls_the_first_value_forward():
    # Synthetic: the cap steps from 100 to 110 on the third line while the adjusted price
    # rises 12%, so the rolled value is 112 and 1.82% above the new cap. The share count on
    # the first line is twice the one behind the cap (100 / 20 = 5 against 10 logged).
    lines = [
        "2019-01-02 00:00:00 2019-01-02 ABC px 20.00 adj 10.00 mcap 100.00 sh 10.0000 pxsh 200.00",
        "2019-01-03 00:00:00 2019-01-03 ABC px 21.00 adj 10.50 mcap 100.00 sh 10.0000 pxsh 210.00",
        "2019-02-01 00:00:00 2019-02-01 ABC px 22.40 adj 11.20 mcap 110.00 sh 9.9000 pxsh 221.76",
    ]
    text = "\n".join(cap_probe_summary(parse_cap_log(lines)))
    assert "The lines fall on 3 dates, each a Wednesday, Thursday or Friday" in text
    assert "| ABC | 100.00 | 2019-01-03 | 2019-02-01 | 110.00 | 112.00 | +1.82% | -1.00% | 2.0000 |" in text
    assert "ABC (2 times)" in text
    assert cap_probe_summary(parse_cap_log([])) == []


def test_cap_log_line_in_the_probe_format_is_parsed():
    # Synthetic values in the exact format of cap_probe_main.py's self.log call, behind the
    # timestamp prefix QuantConnect adds to each log line.
    lines = [
        "2019-01-03 00:00:00 2019-01-03 AAPL px 100.00 adj 99.50 mcap 500.25 sh 5.0000 pxsh 500.00",
        "2019-01-03 00:00:00 Algorithm starting",
        "2019-01-04 XOM px 70.10 adj 65.00 mcap 300.00 sh 4.2338 pxsh 296.79",
    ]
    table = parse_cap_log(lines)
    assert list(table.columns) == [
        "date", "ticker", "price_unadjusted", "price_adjusted", "market_cap_bn",
        "shares_outstanding_bn", "price_x_shares_bn"]
    assert table["ticker"].tolist() == ["AAPL", "XOM"]
    assert table.iloc[0].tolist() == ["2019-01-03", "AAPL", 100.0, 99.5, 500.25, 5.0, 500.0]


def test_log_field_as_one_string_or_empty():
    assert log_lines("a\n\nb\n") == ["a", "b"]
    assert log_lines([]) == []
    assert log_lines(None) == []


def test_probe_points_are_assigned_to_their_month():
    # 2012-02-01 00:00 New York: the January point of Caps and Calls.
    assert probe_month(1328072400, previous=True) == (2012, 1)
    # 2013-01-01 00:00 New York, end of the 2012 backtest: the December point.
    assert probe_month(1357016400, previous=True) == (2012, 12)
    # 2012-01-03 16:00 New York: the January point of EBITDA growth.
    assert probe_month(1325624400, previous=False) == (2012, 1)


def test_statistic_names_to_columns():
    assert snake("Profit-Loss Ratio") == "profit_loss_ratio"
    assert snake("Probabilistic Sharpe Ratio") == "probabilistic_sharpe_ratio"
