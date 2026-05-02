#!/usr/bin/env python3
"""Daily Facebook Ads Report — cron entry point.

Runs nightly at 23:59 (see crontab in README). For each client:
  1. Pull yesterday's top-3 ads from FB Marketing API
  2. Write into Google Sheet's "📅 Daily Log" tab
  3. Cache rows to outputs/<client>_<date>.json (Streamlit reads this)
  4. Screenshot Dashboard tab
  5. Push summary + screenshots to LINE OA
"""
import json
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

from config import CLIENTS, MOCK_MODE
from lib.fb_ads import fetch_top3_ads, to_dict_list
from lib.sheets import write_daily_log
from lib.screenshot import capture_dashboard
from lib.notify import send_line_summary, send_email_fallback


ROOT = Path(__file__).parent
OUT = ROOT / "outputs"
LOGS = ROOT / "logs"


def run_for_client(client, target_date: date) -> dict:
    print(f"\n▶ {client.name}")
    rows = fetch_top3_ads(client.fb_account_id, target_date, client.objective)
    sheet_rows = [r.as_sheet_row(i + 1) for i, r in enumerate(rows)]

    if client.sheet_id:
        write_daily_log(client.sheet_id, target_date.day, sheet_rows)
    else:
        print(f"  [SKIP] no sheet_id for {client.key}")

    # Cache for Streamlit dashboard
    OUT.mkdir(exist_ok=True)
    cache_path = OUT / f"{client.key}_{target_date.isoformat()}.json"
    cache_path.write_text(json.dumps({
        "client": client.name,
        "key": client.key,
        "objective": client.objective,
        "color": client.color,
        "date": target_date.isoformat(),
        "ads": to_dict_list(rows),
    }, ensure_ascii=False, indent=2))

    # Screenshot
    shot_path = OUT / f"{client.key}_{target_date.isoformat()}.png"
    try:
        capture_dashboard(client.sheet_id, shot_path)
    except Exception as e:
        print(f"  ✗ screenshot failed: {e}")

    spend = sum(r.spent for r in rows)
    results = sum(r.result for r in rows)
    conv = sum(r.conversion for r in rows)
    roas = (conv / spend) if spend else 0
    return {
        "name": client.name, "spend": spend, "results": results,
        "roas": roas, "screenshot": shot_path,
    }


def format_summary(target_date: date, summaries: list) -> str:
    lines = [f"📊 Daily Ads Report · {target_date.strftime('%-d/%-m/%Y')}"]
    if MOCK_MODE:
        lines.append("⚠️  MOCK MODE — ข้อมูลทดสอบ")
    lines.append("─" * 28)
    for s in summaries:
        roas_emoji = "🟢" if s["roas"] >= 10 else ("🟡" if s["roas"] >= 5 else "🔴")
        lines.append(f"{roas_emoji} {s['name']}")
        lines.append(f"   Spend ฿{s['spend']:,.0f}  |  Results {s['results']}  |  ROAS {s['roas']:.2f}x")
    total_spend = sum(s["spend"] for s in summaries)
    lines.append("─" * 28)
    lines.append(f"💰 รวม Spend วันนี้: ฿{total_spend:,.0f}")
    return "\n".join(lines)


def main():
    target = date.today() - timedelta(days=1)
    print(f"=== Daily Report · {target} {'(MOCK)' if MOCK_MODE else ''} ===")
    LOGS.mkdir(exist_ok=True)

    summaries = []
    failed = []
    for client in CLIENTS:
        try:
            summaries.append(run_for_client(client, target))
        except Exception as e:
            print(f"  ✗ {client.name} failed: {e}")
            traceback.print_exc()
            failed.append((client.name, str(e)))

    msg = format_summary(target, summaries)
    print("\n" + msg)
    shots = [s["screenshot"] for s in summaries if s["screenshot"].exists() and s["screenshot"].stat().st_size > 0]
    send_line_summary(msg, shots)

    if failed:
        body = "\n".join(f"{n}: {e}" for n, e in failed)
        send_email_fallback(f"[Ads Report] {len(failed)} client(s) failed", body)
        sys.exit(1)


if __name__ == "__main__":
    main()
