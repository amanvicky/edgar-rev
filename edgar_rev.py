#!/usr/bin/env python3
"""edgar-rev — a public company's annual revenue history, straight from SEC EDGAR.

Zero dependencies. EDGAR's XBRL company-facts API is public; the only thing
this tool sends is a User-Agent string identifying it, per EDGAR's fair-use
rule (https://www.sec.gov/os/accessing-edgar-data).
"""

import argparse
import csv
import json
import sys
import urllib.request
from datetime import date

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
USER_AGENT = "edgar-rev (https://github.com/amanvicky/edgar-rev)"

# Most specific tag first. Smaller companies often only report "Revenues".
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
)


class EdgarError(Exception):
    pass


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def load_ticker_map():
    """SEC's ticker->CIK mapping, shape: {"0": {"cik_str", "ticker", "title"}, ...}."""
    raw = http_json(TICKERS_URL)
    return {v["ticker"].upper(): v for v in raw.values()}


def find_cik(ticker, ticker_map):
    hit = ticker_map.get(ticker.upper())
    if hit:
        return hit["cik_str"], hit["title"]
    near = sorted(t for t in ticker_map if ticker.upper() in t)
    hint = ", ".join(sorted(near)[:8])
    raise EdgarError(f"unknown ticker {ticker!r}" + (f" — did you mean: {hint}?" if hint else ""))


def pick_revenue_tag(facts):
    """The first revenue tag EDGAR actually reports for this company."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in REVENUE_TAGS:
        if tag in us_gaap:
            return tag
    available = [k for k in us_gaap if "Revenue" in k]
    raise EdgarError(
        "no annual revenue tag found"
        + (f" (company reports: {', '.join(sorted(available)[:5])})" if available else "")
    )


def annual_series(entries, min_days=300):
    """Keep 10-K full-year USD values, keyed by fiscal year, deduped by latest filing.

    Quarterly and year-to-date values appear under the same tag; a period of at
    least `min_days` days filters them out without hardcoding calendar logic.
    """
    best = {}
    for e in entries:
        if e.get("form") != "10-K" or e.get("fp") != "FY":
            continue
        start, end = e.get("start"), e.get("end")
        if not start or not end:
            continue
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
        if (d1 - d0).days < min_days:
            continue
        fy = d1.year
        if fy not in best or e.get("filed", "") > best[fy].get("filed", ""):
            best[fy] = e
    return {fy: e["val"] for fy, e in sorted(best.items())}


def revenue_history(facts):
    tag = pick_revenue_tag(facts)
    units = facts["facts"]["us-gaap"][tag].get("units", {})
    usd = units.get("USD", [])
    return tag, annual_series(usd)


def growth_table(series, years=10):
    """[(fy, value, yoy_pct_or_None)] for the most recent `years` fiscal years."""
    keys = sorted(series)[-years:]
    rows = []
    for i, fy in enumerate(keys):
        prev = series.get(keys[i - 1]) if i else None
        yoy = (series[fy] - prev) / prev * 100 if prev else None
        rows.append((fy, series[fy], round(yoy, 1) if yoy is not None else None))
    return rows


def render_table(name, cik, tag, rows):
    lines = [f"{name} — CIK {cik:0>10}", f"annual revenue, USD millions (10-K, us-gaap:{tag})", ""]
    for fy, val, yoy in rows:
        yoy_s = f"{yoy:+.1f}%" if yoy is not None else "—"
        lines.append(f"FY{fy}  {val / 1e6:>12,.0f}  {yoy_s:>8}")
    return "\n".join(lines)


def render_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fiscal_year", "revenue_usd", "yoy_pct"])
        w.writerows(rows)


def main(argv=None):
    p = argparse.ArgumentParser(description="annual revenue history from SEC EDGAR")
    p.add_argument("ticker", help="stock ticker, e.g. AAPL")
    p.add_argument("--years", type=int, default=10, help="fiscal years to show (default 10)")
    p.add_argument("--csv", metavar="PATH", help="also write a CSV to PATH")
    args = p.parse_args(argv)

    try:
        ticker_map = load_ticker_map()
        cik, title = find_cik(args.ticker, ticker_map)
        facts = http_json(FACTS_URL.format(cik=cik))
        tag, series = revenue_history(facts)
        rows = growth_table(series, args.years)
        if not rows:
            raise EdgarError("no 10-K revenue data found for this company")
    except EdgarError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except urllib.error.HTTPError as e:
        hint = (
            "SEC blocks some networks (VPNs, cloud IPs) and rate-limits bursts — "
            "try again later or from a different connection"
            if e.code == 403
            else "check the ticker or retry"
        )
        print(f"error: EDGAR returned HTTP {e.code} — {hint}", file=sys.stderr)
        return 1

    print(render_table(facts["entityName"], cik, tag, rows))
    if args.csv:
        render_csv(rows, args.csv)
        print(f"\ncsv written to {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
