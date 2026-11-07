"""Tests for edgar_rev. All parsing/reshaping is tested against recorded
fixtures — no network. The live command is exercised by hand."""

import csv
import io
import sys

import pytest

import edgar_rev as er


TICKER_MAP = {
    "AAPL": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "AMZN": {"cik_str": 1018724, "ticker": "AMZN", "title": "Amazon.com, Inc."},
    "AMC": {"cik_str": 1411579, "ticker": "AMC", "title": "AMC Entertainment Holdings, Inc."},
}


def entry(fy, val, form="10-K", fp="FY", filed="2024-02-01", days=365):
    start = f"{fy - 1}-10-01" if days == 365 else f"{fy}-02-01"
    end = f"{fy}-09-30" if days == 365 else f"{fy}-05-01"
    return {"start": start, "end": end, "val": val, "form": form, "fp": fp, "filed": filed}


def test_find_cik_hit():
    assert er.find_cik("aapl", TICKER_MAP) == (320193, "Apple Inc.")


def test_find_cik_suggests_near_matches():
    with pytest.raises(er.EdgarError) as e:
        er.find_cik("AM", TICKER_MAP)
    assert "AMZN" in str(e.value) and "AMC" in str(e.value)


def test_pick_revenue_tag_prefers_most_specific():
    facts = {"facts": {"us-gaap": {"Revenues": {}, "RevenueFromContractWithCustomerExcludingAssessedTax": {}}}}
    assert er.pick_revenue_tag(facts) == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_pick_revenue_tag_falls_back():
    assert er.pick_revenue_tag({"facts": {"us-gaap": {"Revenues": {}}}}) == "Revenues"


def test_annual_series_drops_quarters_and_10q():
    entries = [
        entry(2023, 1000),                       # keep
        entry(2023, 999, form="10-K", fp="FY", days=90),   # too short -> drop
        entry(2023, 888, form="10-Q"),           # wrong form -> drop
        entry(2022, 800, form="10-K", fp="Q4"),  # wrong fp -> drop
    ]
    assert er.annual_series(entries) == {2023: 1000}


def test_annual_series_prefers_latest_filing():
    entries = [
        entry(2023, 1000, filed="2023-11-01"),
        entry(2023, 1050, filed="2024-02-01"),  # restated, filed later -> wins
    ]
    assert er.annual_series(entries) == {2023: 1050}


def test_growth_table():
    series = {2021: 100_000_000, 2022: 120_000_000, 2023: 90_000_000, 2019: 50_000_000}
    rows = er.growth_table(series, years=3)
    assert rows == [
        (2021, 100_000_000, None),
        (2022, 120_000_000, 20.0),
        (2023, 90_000_000, -25.0),
    ]


def test_growth_table_first_year_has_no_yoy():
    rows = er.growth_table({2023: 100})
    assert rows == [(2023, 100, None)]


def test_render_table_shape():
    rows = [(2023, 383_285_000_000, 0.1), (2022, 394_328_000_000, None)]
    out = er.render_table("Apple Inc.", 320193, "Revenues", rows)
    assert "Apple Inc. — CIK 0000320193" in out
    assert "FY2023" in out and "383,285" in out
    assert "+0.1%" in out and "—" in out


def test_render_csv(tmp_path):
    path = tmp_path / "out.csv"
    er.render_csv([(2023, 100, 5.0)], path)
    with open(path, newline="") as f:
        assert list(csv.reader(f)) == [["fiscal_year", "revenue_usd", "yoy_pct"], ["2023", "100", "5.0"]]


def test_recorded_aapl_revenues_end_to_end():
    """The fixture is Apple's real RevenueFromContractWithCustomerExcludingAssessedTax
    data as EDGAR served it on 2026-11-07, quarters and all — the parser must drop
    the sub-year periods and keep the latest filing per fiscal year."""
    import json
    from pathlib import Path

    recorded = json.loads((Path(__file__).parent.parent / "examples" / "aapl_recorded.json").read_text())
    entries = recorded["entries"]
    series = er.annual_series(entries)
    assert series == {
        2017: 229_234_000_000,
        2018: 265_595_000_000,
        2019: 260_174_000_000,
        2020: 274_515_000_000,
        2021: 365_817_000_000,
        2022: 394_328_000_000,
        2023: 383_285_000_000,
        2024: 391_035_000_000,
        2025: 416_161_000_000,
        2026: 478_834_000_000,
    }


def test_main_reports_unknown_ticker(monkeypatch, capsys):
    monkeypatch.setattr(er, "load_ticker_map", lambda: TICKER_MAP)
    assert er.main(["NOPE"]) == 1
    assert "unknown ticker" in capsys.readouterr().err


def test_main_happy_path(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(er, "load_ticker_map", lambda: TICKER_MAP)
    monkeypatch.setattr(er, "http_json", lambda url: {
        "entityName": "Apple Inc.",
        "facts": {"us-gaap": {"Revenues": {"units": {"USD": [entry(2023, 383_285_000_000)]}}}},
    })
    out_csv = tmp_path / "rev.csv"
    assert er.main(["AAPL", "--csv", str(out_csv)]) == 0
    out = capsys.readouterr().out
    assert "Apple Inc." in out and "FY2023" in out and "383,285" in out
    assert out_csv.exists()


def test_from_file_replay(tmp_path, capsys):
    import shutil

    replay = tmp_path / "replay.json"
    shutil.copy("examples/aapl_recorded.json", replay)
    assert er.main(["AAPL", "--from-file", str(replay)]) == 0
    out = capsys.readouterr().out
    assert "Apple Inc. — CIK 0000320193" in out and "FY2026" in out and "478,834" in out


def test_render_table_without_cik():
    rows = [(2023, 100_000_000, None)]
    out = er.render_table("Some Co", None, "(recorded)", rows)
    assert "Some Co" in out and "CIK" not in out
