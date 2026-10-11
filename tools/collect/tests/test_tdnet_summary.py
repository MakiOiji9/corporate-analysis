import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tdnet_summary import parse_facts, parse_meta, to_rows, upsert_rows  # noqa: E402

SAMPLE = """
<ix:nonNumeric name="tse-ed-t:DocumentName" contextRef="c" escape="false"><p>2027年３月期 第１四半期決算短信</p></ix:nonNumeric>
<ix:nonNumeric name="tse-ed-t:FilingDate" contextRef="c">2026年8月12日</ix:nonNumeric>
<ix:nonNumeric name="tse-ed-t:FiscalYearEnd" contextRef="c">2027-03-31</ix:nonNumeric>
<ix:nonFraction name="tse-ed-t:NetSales" contextRef="CurrentAccumulatedQ1Duration_ConsolidatedMember_ResultMember" unitRef="JPY" decimals="-6" scale="6">4,304</ix:nonFraction>
<ix:nonFraction name="tse-ed-t:ChangeInNetSales" contextRef="CurrentAccumulatedQ1Duration_ConsolidatedMember_ResultMember" unitRef="Pure" decimals="3" scale="-2">13.1</ix:nonFraction>
<ix:nonFraction name="tse-ed-t:CashFlowsFromInvestingActivities" contextRef="CurrentYearDuration_ConsolidatedMember_ResultMember" unitRef="JPY" scale="6" sign="-"><span>△</span>531</ix:nonFraction>
<ix:nonFraction name="tse-ed-t:NetIncomePerShare" contextRef="NextYearDuration_ConsolidatedMember_ForecastMember" unitRef="JPYPerShares" scale="0">40.65</ix:nonFraction>
<ix:nonFraction name="tse-ed-t:DividendPerShare" contextRef="X" unitRef="JPYPerShares" xsi:nil="true" />
"""


def test_parse_facts_normalises_units_and_sign():
    facts = {f.element: f for f in parse_facts(SAMPLE)}
    assert facts["NetSales"].value == 4304 and facts["NetSales"].unit == "百万円"
    assert facts["ChangeInNetSales"].value == 13.1 and facts["ChangeInNetSales"].unit == "%"
    assert facts["CashFlowsFromInvestingActivities"].value == -531
    assert facts["NetIncomePerShare"].value == 40.65
    assert facts["DividendPerShare"].value is None


def test_parse_meta_strips_markup():
    meta = parse_meta(SAMPLE)
    assert meta["DocumentName"] == "2027年３月期 第１四半期決算短信"
    assert meta["FiscalYearEnd"] == "2027-03-31"


def test_meta_found_when_nested_inside_other_nonnumeric():
    nested = ('<ix:nonNumeric name="tse-ed-t:DocumentName" escape="false"><p>短信</p>'
              '<ix:nonNumeric name="tse-ed-t:FiscalYearEnd" contextRef="c">2027-03-31</ix:nonNumeric>'
              '</ix:nonNumeric>')
    meta = parse_meta(nested)
    assert meta["FiscalYearEnd"] == "2027-03-31"
    assert meta["DocumentName"] == "短信"


def test_large_values_are_not_in_scientific_notation():
    src = ('<ix:nonFraction name="tse-ed-t:NumberOfTreasuryStockAtTheEndOfFiscalYear" '
           'contextRef="c" unitRef="Shares" scale="0">7,276,620</ix:nonFraction>')
    rows = to_rows(parse_facts(src), {}, "D")
    assert rows[0]["value"] == "7276620"


def test_upsert_replaces_same_doc(tmp_path):
    out = tmp_path / "facts.csv"
    rows = to_rows(parse_facts(SAMPLE), parse_meta(SAMPLE), "D1")
    assert upsert_rows(out, rows) == 4  # nil value dropped
    upsert_rows(out, rows)
    assert len(out.read_text(encoding="utf-8").strip().splitlines()) == 1 + 4
