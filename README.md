# edgar-rev

[![CI](https://github.com/amanvicky/edgar-rev/actions/workflows/ci.yml/badge.svg)](https://github.com/amanvicky/edgar-rev/actions/workflows/ci.yml)

One command, ten years of a public company's revenue — straight from SEC EDGAR. No API key, no account, no dependencies: one Python file, standard library only.

```bash
$ python edgar_rev.py AAPL
Apple Inc. — CIK 0000320193
annual revenue, USD millions (10-K, us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax)

FY2017       229,234         —
FY2018       265,595    +15.9%
FY2019       260,174     -2.0%
FY2020       274,515     +5.5%
FY2021       365,817    +33.3%
FY2022       394,328     +7.8%
FY2023       383,285     -2.8%
FY2024       391,035     +2.0%
FY2025       416,161     +6.4%
FY2026       478,834    +15.1%

$ python edgar_rev.py TSLA --years 5 --csv tsla.csv
```

The output above is the tool's real output — Apple's FY2026 figures as filed with the SEC on 2026-11-03.

## Why

[Genesis](https://github.com/amanvicky/Genesis-Business-Decoding-Engine) (my venture-research engine) needs SEC-filing revenue history, and I wanted that same data from a terminal in one line — so the fetch-and-reshape part became this tool. Along the way it handles the annoying parts of EDGAR:

- **Companies switch revenue tags mid-history.** Apple stopped filing `us-gaap:Revenues` after FY2018 and moved to the contract-revenue tag. edgar-rev tries tags most-specific first and tells you which one it used.
- **Quarterly and year-to-date values share the tag with annual ones.** Any period shorter than ~300 days is dropped.
- **The same fiscal year gets re-filed in amendments and restatements.** The latest `filed` date wins.

## Install

Any Python ≥ 3.9. Either copy the single file, or install it as a console command:

```bash
pip install git+https://github.com/amanvicky/edgar-rev
edgar-rev MSFT --csv msft.csv
```

| Argument | What it does |
|---|---|
| `ticker` | stock ticker (`AAPL`, `TSLA`, …) — unknown tickers get a "did you mean" list |
| `--years N` | fiscal years to show (default 10) |
| `--csv PATH` | also write the table to a CSV |

## EDGAR etiquette

The tool sends a single User-Agent identifying itself, per [SEC's fair-access rule](https://www.sec.gov/os/accessing-edgar-data). SEC blocks some networks (VPNs, cloud IPs) and rate-limits bursts — if you get an HTTP 403, that's them, not the ticker; try again later or from a different connection.

## Tests

```bash
pytest tests/ -q
```

Thirteen tests, no network: the parsers are checked against synthetic shapes (quarter noise, wrong forms, duplicate filings) and against a recorded fixture of Apple's real company-concept data as EDGAR served it — quarters and restatements included. CI runs the suite on every push.
