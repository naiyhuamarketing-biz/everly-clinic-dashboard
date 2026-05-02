#!/usr/bin/env python3
"""Verify Everly daily numbers via Meta Marketing API.

Pulls Everly Clinic per-day spend + inbox count from FB API and prints a
table for ad-hoc auditing.

Usage:
    python verify.py                # full April compare
    python verify.py --date 2026-04-15
    python verify.py --range 2026-04-01:2026-04-15

Requires in .env:
    FB_ACCESS_TOKEN
    FB_APP_ID
    FB_APP_SECRET
    FB_ACCOUNT_EVERLY   (1965556974211662)
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta
from typing import Tuple

from dotenv import load_dotenv

load_dotenv()

ACCOUNT_ID = os.getenv("FB_ACCOUNT_EVERLY", "1965556974211662")
TOKEN = os.getenv("FB_ACCESS_TOKEN")

# ANSI colors
G, R, Y, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[94m", "\033[0m"


def init_api():
    if not TOKEN:
        print(f"{R}✗ FB_ACCESS_TOKEN not set in .env{X}")
        print(f"  → ดู README.md หัวข้อ 'Setup FB Marketing API'")
        sys.exit(1)
    from facebook_business.api import FacebookAdsApi
    FacebookAdsApi.init(
        app_id=os.getenv("FB_APP_ID"),
        app_secret=os.getenv("FB_APP_SECRET"),
        access_token=TOKEN,
    )


INBOX_ACTIONS = (
    # Matches "Messaging Conversations Started" column in Ads Manager UI
    "onsite_conversion.messaging_conversation_started_7d",
)


def fetch_meta_day(d: date) -> Tuple[float, int, float]:
    """Returns (total_spend, inbox_count, inbox_spend) for a day at ACCOUNT level."""
    from facebook_business.adobjects.adaccount import AdAccount

    account = AdAccount(f"act_{ACCOUNT_ID}")
    iso = d.isoformat()
    # Account-level totals — sums across ALL ads & statuses regardless
    insights = list(account.get_insights(
        fields=["spend", "actions"],
        params={
            "time_range": {"since": iso, "until": iso},
            "level": "account",
        },
    ))

    total_spend = 0.0
    inbox_count = 0
    for ins in insights:
        total_spend += float(ins.get("spend", 0) or 0)
        for a in ins.get("actions") or []:
            if a.get("action_type") in INBOX_ACTIONS:
                inbox_count += int(float(a.get("value", 0)))
    return total_spend, inbox_count, total_spend  # inbox_spent ≈ total at account level


def fetch_xlsx_day(d: date) -> Tuple[float, int, float]:
    # Everly has no xlsx baseline — Meta API is the only source of truth.
    return 0.0, 0, 0.0


def diff_pct(a: float, b: float) -> str:
    if b == 0 and a == 0:
        return f"{G}=={X}"
    if b == 0:
        return f"{R}new{X}"
    pct = (a - b) / b * 100
    color = G if abs(pct) < 5 else (Y if abs(pct) < 15 else R)
    return f"{color}{pct:+.1f}%{X}"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="single date YYYY-MM-DD")
    p.add_argument("--range", help="YYYY-MM-DD:YYYY-MM-DD")
    return p.parse_args()


def main():
    args = parse_args()
    init_api()

    if args.date:
        days = [date.fromisoformat(args.date)]
    elif args.range:
        a, b = args.range.split(":")
        d1, d2 = date.fromisoformat(a), date.fromisoformat(b)
        days = [d1 + timedelta(days=i) for i in range((d2 - d1).days + 1)]
    else:
        days = [date(2026, 4, 1) + timedelta(days=i) for i in range(30)]

    print(f"\n{B}━━━ Verify Everly Clinic : Meta API ━━━{X}")
    print(f"  Account: act_{ACCOUNT_ID}")
    print(f"  Range  : {days[0]} → {days[-1]} ({len(days)} days)\n")
    print(f"{'Date':12s} {'Meta Spend':>11s} {'xlsx Spend':>11s} {'Δ':>8s}  "
          f"{'Meta Inbox':>10s} {'xlsx Inbox':>10s} {'Δ':>8s}")
    print("─" * 80)

    totals = {"meta_sp": 0, "xlsx_sp": 0, "meta_in": 0, "xlsx_in": 0}
    for d in days:
        try:
            m_sp, m_in, _ = fetch_meta_day(d)
        except Exception as e:
            print(f"{d}  {R}fetch error: {e}{X}")
            continue
        x_sp, x_in, _ = fetch_xlsx_day(d)
        totals["meta_sp"] += m_sp
        totals["xlsx_sp"] += x_sp
        totals["meta_in"] += m_in
        totals["xlsx_in"] += x_in
        print(f"{d}  {m_sp:>11.2f} {x_sp:>11.2f}  {diff_pct(m_sp, x_sp):>15s}  "
              f"{m_in:>10d} {x_in:>10d}  {diff_pct(m_in, x_in):>15s}")

    print("─" * 80)
    print(f"{'TOTAL':12s} {totals['meta_sp']:>11.2f} {totals['xlsx_sp']:>11.2f}  "
          f"{diff_pct(totals['meta_sp'], totals['xlsx_sp']):>15s}  "
          f"{totals['meta_in']:>10d} {totals['xlsx_in']:>10d}  "
          f"{diff_pct(totals['meta_in'], totals['xlsx_in']):>15s}")
    print()


if __name__ == "__main__":
    main()
