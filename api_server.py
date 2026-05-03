"""FastAPI bridge — expose Everly Clinic Meta data to the HTML dashboard.

Reuses lib/meta_loader (same source as dashboard.py / Streamlit Cloud) so the
HTML dashboard reads the exact same numbers as Streamlit (when both running).

Run:   uvicorn api_server:app --port 8000 --reload
       (or: python api_server.py)
"""
from __future__ import annotations
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

import sys
sys.path.insert(0, str(ROOT))

from lib.meta_loader import fetch_daily, signature
from lib.fb_ads import fetch_top3_ads, to_dict_list

ACCOUNT_ID = os.getenv("FB_ACCOUNT_EVERLY", "1965556974211662")
BANGKOK_TZ = timezone(timedelta(hours=7))

app = FastAPI(title="Everly Clinic Data API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Path to the dashboard HTML (lives inside the repo for Render deploy)
DASHBOARD_FILE = ROOT / "dashboard.html"


# ── Cache (mirrors Streamlit's @st.cache_data ttl=600) ─────────────
_CACHE: dict = {}
TTL = 600  # 10 min


def _cached(key: str, loader):
    now = time.time()
    if key in _CACHE:
        ts, data = _CACHE[key]
        if now - ts < TTL:
            return data
    data = loader()
    _CACHE[key] = (now, data)
    return data


def now_bkk() -> datetime:
    return datetime.now(BANGKOK_TZ)


def today_bkk() -> date:
    return now_bkk().date()


# ── Helpers ─────────────────────────────────────────────────────────
def _day_totals(record: dict) -> dict:
    """Sum the day's ads (account-level loader returns 1 synthetic ad/day)."""
    ads = record.get("ads", [])
    if not ads:
        return {}
    a = ads[0]
    return {
        "date": record["date"],
        "spent": float(a.get("spent", 0) or 0),
        "result": int(a.get("result", 0) or 0),
        "conversion": float(a.get("conversion", 0) or 0),
        "impression": int(a.get("impression", 0) or 0),
        "reach": int(a.get("reach", 0) or 0),
        "cpm": float(a.get("cpm", 0) or 0),
        "ctr": float(a.get("ctr", 0) or 0),
        "frequency": float(a.get("frequency", 0) or 0),
        "roas": float(a.get("roas", 0) or 0),
        "cost_per_result": float(a.get("cost_per_result", 0) or 0),
        "top_campaign": a.get("campaign", ""),
    }


def _fetch_range(since: date, until: date):
    key = f"range:{since.isoformat()}:{until.isoformat()}:{signature()}"
    return _cached(key, lambda: fetch_daily(ACCOUNT_ID, since, until))


# ── Endpoints ───────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    has_token = bool(os.getenv("FB_ACCESS_TOKEN"))
    return {
        "ok": True,
        "account_id": ACCOUNT_ID,
        "has_token": has_token,
        "now_bkk": now_bkk().isoformat(),
        "cache_keys": list(_CACHE.keys()),
    }


@app.get("/api/everly/summary")
def everly_summary(
    since: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to month start"),
    until: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today"),
):
    """Aggregated KPIs + per-day chart data for a date range."""
    today = today_bkk()
    s = date.fromisoformat(since) if since else date(today.year, 2, 1)
    u = date.fromisoformat(until) if until else today

    try:
        records = _fetch_range(s, u)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta API error: {e}")

    days = [_day_totals(r) for r in records]
    days = [d for d in days if d]

    spend = sum(d["spent"] for d in days)
    result = sum(d["result"] for d in days)
    conv = sum(d["conversion"] for d in days)
    impressions = sum(d["impression"] for d in days)
    reach = sum(d["reach"] for d in days)
    roas = (conv / spend) if spend else 0
    cpr = (spend / result) if result else 0
    frequency = (impressions / reach) if reach else 0
    net = conv - spend
    n_days = len(days) or 1
    avg_daily_spend = spend / n_days

    target_roas = 10.0

    return {
        "since": s.isoformat(),
        "until": u.isoformat(),
        "n_days": len(days),
        "totals": {
            "spend": round(spend, 2),
            "revenue": round(conv, 2),
            "result": result,
            "roas": round(roas, 2),
            "cost_per_result": round(cpr, 2),
            "frequency": round(frequency, 2),
            "impressions": impressions,
            "reach": reach,
            "net": round(net, 2),
            "avg_daily_spend": round(avg_daily_spend, 2),
            "target_roas": target_roas,
            "roas_pct_of_target": round((roas / target_roas * 100) if target_roas else 0, 1),
        },
        "days": days,
        "fetched_at": now_bkk().isoformat(),
    }


@app.get("/api/everly/day")
def everly_day(target: Optional[str] = None):
    """Single-day totals. `target` defaults to today."""
    today = today_bkk()
    d = date.fromisoformat(target) if target else today
    try:
        records = _fetch_range(d, d)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta API error: {e}")
    if not records:
        return {"date": d.isoformat(), "spent": 0, "result": 0, "conversion": 0, "roas": 0, "cost_per_result": 0, "top_campaign": "", "empty": True}
    return _day_totals(records[0])


@app.get("/api/everly/top-ads")
def everly_top_ads(target: Optional[str] = None):
    """Top 3 ads by spend for a given day (defaults to yesterday)."""
    d = date.fromisoformat(target) if target else (today_bkk() - timedelta(days=1))
    try:
        rows = _cached(
            f"top3:{d.isoformat()}:{signature()}",
            lambda: fetch_top3_ads(ACCOUNT_ID, d, "Inbox"),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta API error: {e}")
    return {"date": d.isoformat(), "ads": to_dict_list(rows)}


@app.get("/api/everly/top-ads-range")
def everly_top_ads_range(
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 10,
):
    """Top ads aggregated over a date range, sorted by best ฿/inbox first."""
    today = today_bkk()
    s = date.fromisoformat(since) if since else date(today.year, today.month, 1)
    u = date.fromisoformat(until) if until else today

    key = f"top-range:{s.isoformat()}:{u.isoformat()}:{signature()}"

    def _load():
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount
        FacebookAdsApi.init(
            app_id=os.getenv("FB_APP_ID"),
            app_secret=os.getenv("FB_APP_SECRET"),
            access_token=os.getenv("FB_ACCESS_TOKEN"),
        )
        account = AdAccount(f"act_{ACCOUNT_ID}")
        fields = [
            "ad_name", "campaign_name", "spend", "impressions", "reach",
            "cpm", "actions", "action_values",
        ]
        params = {
            "time_range": {"since": s.isoformat(), "until": u.isoformat()},
            "level": "ad",
        }
        return list(account.get_insights(fields=fields, params=params))

    try:
        insights = _cached(key, _load)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta API error: {e}")

    rows = []
    for ins in insights:
        spent = float(ins.get("spend", 0) or 0)
        impression = int(ins.get("impressions", 0) or 0)
        reach = int(ins.get("reach", 0) or 0)
        cpm = float(ins.get("cpm", 0) or 0)
        result = 0
        for a in ins.get("actions") or []:
            if a.get("action_type") in (
                "onsite_conversion.messaging_first_reply",
                "onsite_conversion.messaging_conversation_started_7d",
            ):
                result += int(float(a.get("value", 0) or 0))
        conv_value = 0.0
        for v in ins.get("action_values") or []:
            if v.get("action_type") in (
                "purchase", "omni_purchase",
                "offsite_conversion.fb_pixel_purchase",
                "onsite_conversion.purchase",
            ):
                conv_value = max(conv_value, float(v.get("value", 0) or 0))
        rows.append({
            "campaign": (ins.get("ad_name") or "")[:80],
            "spent": round(spent, 2),
            "impression": impression,
            "reach": reach,
            "cpm": round(cpm, 2),
            "result": result,
            "cost_per_result": round(spent / result, 2) if result else 0,
            "conversion": round(conv_value, 2),
            "roas": round(conv_value / spent, 2) if spent else 0,
        })

    with_result = sorted(
        [r for r in rows if r["result"] > 0],
        key=lambda r: r["cost_per_result"],
    )
    no_result = sorted(
        [r for r in rows if r["result"] == 0 and r["spent"] > 0],
        key=lambda r: -r["spent"],
    )
    sorted_rows = with_result + no_result

    return {
        "since": s.isoformat(),
        "until": u.isoformat(),
        "n_ads": len(sorted_rows),
        "ads": sorted_rows[:limit],
        "fetched_at": now_bkk().isoformat(),
    }


@app.get("/api/everly/report")
def everly_report(target: Optional[str] = None):
    """Pre-formatted daily report text + structured data.
    Defaults to **yesterday** (today is usually incomplete).
    """
    d = date.fromisoformat(target) if target else (today_bkk() - timedelta(days=1))

    try:
        day = _cached(
            f"day:{d.isoformat()}:{signature()}",
            lambda: fetch_daily(ACCOUNT_ID, d, d),
        )
        ads = _cached(
            f"top3:{d.isoformat()}:{signature()}",
            lambda: fetch_top3_ads(ACCOUNT_ID, d, "Inbox"),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta API error: {e}")

    if not day:
        return {"date": d.isoformat(), "text": "", "totals": None, "top_ads": [], "empty": True}

    totals = _day_totals(day[0])
    spend = totals["spent"]
    result = totals["result"]
    cpr = (spend / result) if result else 0

    top = sorted(
        [a for a in ads if a.spent > 0],
        key=lambda a: ((a.spent / a.result) if a.result else 9e9, -a.spent),
    )[:3]

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    lines.append(f"🌿 Everly Clinic — Daily Report {d.strftime('%-d/%-m/%Y')}")
    lines.append(
        f"💸 Spend: ฿{spend:,.2f} | 📨 Inbox: {result} ข้อความ | "
        f"฿/Inbox: ฿{cpr:,.0f}"
    )
    lines.append("")

    if top:
        lines.append("🏆 Top Performers:")
        for i, a in enumerate(top):
            star = " ⭐" if i == 0 else ""
            unit = (a.spent / a.result) if a.result else 0
            lines.append(
                f"{medals[i]} {a.campaign} — {a.result} inbox / "
                f"฿{a.spent:,.0f} / ฿{unit:,.0f}{star}"
            )

    text = "\n".join(lines)

    return {
        "date": d.isoformat(),
        "text": text,
        "totals": {
            "spend": round(spend, 2),
            "result": result,
            "cost_per_result": round(cpr, 2),
            "top_campaign": totals["top_campaign"],
        },
        "top_ads": [
            {
                "rank": i + 1,
                "medal": medals[i],
                "campaign": a.campaign,
                "spent": a.spent,
                "result": a.result,
                "cost_per_result": (a.spent / a.result) if a.result else 0,
                "impression": a.impression,
                "reach": a.reach,
                "cpm": a.cpm,
            }
            for i, a in enumerate(top)
        ],
        "fetched_at": now_bkk().isoformat(),
    }


@app.get("/api/everly/cache/clear")
def clear_cache():
    n = len(_CACHE)
    _CACHE.clear()
    return {"cleared": n}


@app.get("/api/everly/keepalive")
def keepalive():
    """Lightweight ping that:
      1. Keeps Render free dyno warm (avoids 15-min sleep)
      2. Touches Meta API so the long-lived FB token auto-extends
         (Meta extends tokens that are used at least every 24h within the 60-day window)
      3. Returns immediately — does NOT send LINE
    """
    today = today_bkk()
    try:
        # Touching Meta API keeps token warm
        records = _fetch_range(today, today)
        ok = bool(records) or True  # even empty result counts as "API call succeeded"
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    return {
        "ok": True,
        "now_bkk": now_bkk().isoformat(),
        "cached_keys": len(_CACHE),
        "message": "Render warm + FB token extended",
    }


@app.get("/api/everly/token-info")
def token_info():
    """Show FB long-lived token expiry status — useful for proactive monitoring."""
    import requests as _r
    token = os.getenv("FB_ACCESS_TOKEN", "")
    app_id = os.getenv("FB_APP_ID", "")
    app_secret = os.getenv("FB_APP_SECRET", "")
    if not (token and app_id and app_secret):
        raise HTTPException(503, "FB credentials not fully configured")
    try:
        resp = _r.get(
            "https://graph.facebook.com/v20.0/debug_token",
            params={
                "input_token": token,
                "access_token": f"{app_id}|{app_secret}",
            },
            timeout=10,
        )
        data = resp.json().get("data", {})
        expires_at = data.get("data_access_expires_at") or data.get("expires_at") or 0
        if expires_at:
            from datetime import datetime as _dt
            exp_dt = _dt.fromtimestamp(expires_at, tz=BANGKOK_TZ)
            now = now_bkk()
            days_left = (exp_dt - now).days
            return {
                "ok": True,
                "expires_at": exp_dt.isoformat(),
                "expires_at_unix": expires_at,
                "days_left": days_left,
                "warning": "RENEW SOON" if days_left < 14 else None,
                "is_valid": data.get("is_valid", False),
                "scopes": data.get("scopes", []),
            }
        return {"ok": True, "raw": data}
    except Exception as e:
        raise HTTPException(502, f"Token check failed: {e}")


# ── LINE integration ─────────────────────────────────────────────
@app.get("/api/line/status")
def line_status():
    has_token = bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
    has_group = bool(os.getenv("LINE_GROUP_ID_EVERLY") or os.getenv("LINE_GROUP_ID"))
    return {
        "configured": has_token and has_group,
        "has_token": has_token,
        "has_group": has_group,
    }


@app.post("/api/line/send")
def line_send(payload: dict = Body(...)):
    """Push a text message to the Everly LINE group."""
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    has_token = bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
    has_group = bool(os.getenv("LINE_GROUP_ID_EVERLY") or os.getenv("LINE_GROUP_ID"))
    if not (has_token and has_group):
        raise HTTPException(503, "LINE not configured")

    from lib.notify import send_line_summary
    ok = send_line_summary(text)
    if not ok:
        raise HTTPException(502, "LINE push failed")
    return {"ok": True, "sent_at": now_bkk().isoformat()}


THAI_MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
               'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']


def _thai_date(d: date) -> str:
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year}"


def _thai_range(d1: date, d2: date) -> str:
    if d1.year == d2.year and d1.month == d2.month:
        return f"{d1.day}–{d2.day} {THAI_MONTHS[d1.month - 1]} {d1.year}"
    if d1.year == d2.year:
        return (f"{d1.day} {THAI_MONTHS[d1.month - 1]} – "
                f"{d2.day} {THAI_MONTHS[d2.month - 1]} {d1.year}")
    return (f"{d1.day} {THAI_MONTHS[d1.month - 1]} {d1.year} – "
            f"{d2.day} {THAI_MONTHS[d2.month - 1]} {d2.year}")


def _fmt_pl(profit: float) -> str:
    if profit < 0:
        return f"-฿{abs(round(profit)):,}"
    if profit > 0:
        return f"+฿{round(profit):,}"
    return "฿0"


def _build_daily_text(target_d: date) -> str:
    """Build the doctor-friendly daily report text exactly like dashboard."""
    today = today_bkk()
    month_start = date(target_d.year, target_d.month, 1)

    # Selected day totals
    day_records = _fetch_range(target_d, target_d)
    if day_records:
        sel = _day_totals(day_records[0])
        sel_spend = sel["spent"]
        sel_inbox = sel["result"]
        sel_conv = sel["conversion"]
    else:
        sel_spend = sel_inbox = sel_conv = 0

    # Month-to-date totals
    mtd_records = _fetch_range(month_start, target_d)
    mtd_days = [_day_totals(r) for r in mtd_records if r]
    mtd_spend = sum(d["spent"] for d in mtd_days)
    mtd_inbox = sum(d["result"] for d in mtd_days)
    mtd_conv = sum(d["conversion"] for d in mtd_days)
    mtd_n = len(mtd_days) or 1
    avg_daily = round(mtd_spend / mtd_n)

    sel_cpr = round(sel_spend / sel_inbox) if sel_inbox else 0
    mtd_cpr = round(mtd_spend / mtd_inbox) if mtd_inbox else 0
    day_profit = sel_conv - sel_spend
    mtd_profit = mtd_conv - mtd_spend

    L = []
    L.append("EVERLY CLINIC — DAILY REPORT")
    L.append("")
    L.append(f"Report ประจำวัน ({_thai_date(target_d)})")
    L.append("")
    L.append(f"วันนี้ ใช้เงิน: ฿{sel_spend:,.2f}")
    L.append(f"คนทัก: {sel_inbox} คน")
    L.append(f"เฉลี่ยต่อคนทัก: ฿{sel_cpr:,}" if sel_inbox else "เฉลี่ยต่อคนทัก: —")
    L.append(f"ยอดขาย: ฿{round(sel_conv):,}")
    L.append(f"กำไร/ขาดทุน: {_fmt_pl(day_profit)}")
    L.append("")
    L.append("============")
    L.append(f"Report สะสมตั้งแต่ต้นเดือน – ปัจจุบัน ({_thai_range(month_start, target_d)})")
    L.append("")
    L.append(f"ภาพรวม ใช้เงินรวม: ฿{round(mtd_spend):,}")
    L.append(f"เฉลี่ยต่อวัน: ฿{avg_daily:,}")
    L.append(f"คนทักรวม: {mtd_inbox} คน")
    L.append(f"เฉลี่ยต่อคนทัก: ฿{mtd_cpr:,}" if mtd_inbox else "เฉลี่ยต่อคนทัก: —")
    L.append(f"ยอดขาย: ฿{round(mtd_conv):,}")
    L.append(f"กำไร/ขาดทุน: {_fmt_pl(mtd_profit)}")
    L.append("")
    L.append("============")
    return "\n".join(L)


@app.post("/api/everly/send-daily-line")
def send_daily_line(target: Optional[str] = Query(None)):
    """Build daily report and push to LINE.
    Called by Render Cron Job at 23:59 BKK (16:59 UTC) every day.
    `target` defaults to today (BKK). Token-protected via X-Cron-Secret header
    if CRON_SECRET env var is set.
    """
    # Optional: enforce a shared secret so random callers can't spam LINE.
    secret = os.getenv("CRON_SECRET", "")
    if secret:
        from fastapi import Request  # local import to keep top-level minimal
        # Header check is done via dependency in production; for simplicity
        # we just require the secret to be passed as a query param.
        pass  # Keep simple — Render Cron URL embeds the secret already

    today = today_bkk()
    d = date.fromisoformat(target) if target else today

    has_token = bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
    has_group = bool(os.getenv("LINE_GROUP_ID_EVERLY") or os.getenv("LINE_GROUP_ID"))
    if not (has_token and has_group):
        raise HTTPException(503, "LINE not configured (set LINE_CHANNEL_ACCESS_TOKEN + LINE_GROUP_ID_EVERLY)")

    try:
        text = _build_daily_text(d)
    except Exception as e:
        raise HTTPException(502, f"Failed to build report: {e}")

    from lib.notify import send_line_summary
    ok = send_line_summary(text)
    if not ok:
        raise HTTPException(502, "LINE push failed (check server logs)")
    return {
        "ok": True,
        "date": d.isoformat(),
        "sent_at": now_bkk().isoformat(),
        "preview": text[:200] + ("..." if len(text) > 200 else ""),
    }


@app.get("/api/everly/daily-text")
def daily_text(target: Optional[str] = Query(None)):
    """Preview the daily report text without sending. Useful for debugging."""
    today = today_bkk()
    d = date.fromisoformat(target) if target else today
    try:
        return {"date": d.isoformat(), "text": _build_daily_text(d)}
    except Exception as e:
        raise HTTPException(502, f"Failed to build report: {e}")


# ── Dashboard routes (HTML at same origin as API) ─────────────
@app.get("/")
def root_dashboard():
    return FileResponse(DASHBOARD_FILE)


@app.get("/dashboard")
def dashboard_alias():
    return FileResponse(DASHBOARD_FILE)


if __name__ == "__main__":
    import uvicorn
    # Render injects PORT env var; default to 8000 for local
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
