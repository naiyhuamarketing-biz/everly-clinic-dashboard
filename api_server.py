"""FastAPI bridge — expose Everly Clinic Meta data to the HTML dashboard.

Reuses lib/meta_loader (same source as dashboard.py / Streamlit Cloud) so the
HTML dashboard reads the exact same numbers as Streamlit (when both running).

Run:   uvicorn api_server:app --port 8000 --reload
       (or: python api_server.py)
"""
from __future__ import annotations
import os
import json
import time
import re
import random
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

import sys
sys.path.insert(0, str(ROOT))

from lib.meta_loader import fetch_daily, signature
from lib.fb_ads import fetch_top3_ads, to_dict_list

ACCOUNT_ID = os.getenv("FB_ACCOUNT_EVERLY", "1965556974211662").replace("act_", "")
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
ASSETS_DIR = ROOT / "assets"
SENT_STATE_FILE = Path(os.getenv("SENT_STATE_FILE", "/tmp/everly-line-sent.json"))
SUMMARY_SNAPSHOT_DIR = Path(os.getenv("SUMMARY_SNAPSHOT_DIR", "/tmp/everly-summary-snapshots"))
SEND_DAILY_LINE_LOCK = threading.Lock()

# Mount /assets so brand logos (assets/logos/everly.png etc.) are served
# directly by FastAPI — used by <img src="/assets/logos/..."> in dashboard.html
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


# ── Cache: keep Meta API reads fresh while avoiding duplicate rapid refreshes ─────────────
_CACHE: dict = {}
TTL = 60  # seconds


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
def _has_fb_token() -> bool:
    return bool(os.getenv("FB_ACCESS_TOKEN") and ACCOUNT_ID)


def _mock_data_enabled() -> bool:
    """Use deterministic data only for local development or explicit demos.

    Public deployments must not silently show fake totals when Meta env vars are
    missing; that makes report numbers look real while they are not.
    """
    mock_env = os.getenv("MOCK_MODE", "").strip().lower()
    if mock_env in {"true", "1", "yes"}:
        return True
    if mock_env in {"false", "0", "no"}:
        return False
    if os.getenv("VERCEL") or os.getenv("RENDER"):
        return False
    return not _has_fb_token()


def _fetch_ad_account_identity() -> dict:
    """Best-effort live identity check for the locked Everly ad account."""
    fallback = {
        "account_name": None,
        "account_name_live": False,
        "account_name_matches_brand": None,
        "account_identity_error": None,
    }
    if not _has_fb_token():
        return {**fallback, "account_identity_error": "FB_ACCESS_TOKEN not set"}

    def _load():
        import requests

        response = requests.get(
            f"https://graph.facebook.com/v20.0/act_{ACCOUNT_ID}",
            params={
                "fields": "id,account_id,name",
                "access_token": os.getenv("FB_ACCESS_TOKEN"),
            },
            timeout=8,
        )
        if response.status_code != 200:
            raise RuntimeError(response.text[:220])
        payload = response.json()
        name = payload.get("name") or ""
        return {
            "account_name": name,
            "account_name_live": True,
            "account_name_matches_brand": "everly" in name.lower(),
            "account_identity_error": None,
        }

    try:
        return _cached(f"account-identity:{ACCOUNT_ID}:{signature()}", _load)
    except Exception as e:
        return {**fallback, "account_identity_error": str(e)[:220]}


def _iter_days(since: date, until: date):
    n = (until - since).days
    for i in range(max(n, 0) + 1):
        yield since + timedelta(days=i)


def _mock_daily_records(since: date, until: date) -> list[dict]:
    campaigns = [
        "Everly · Beauty Campaign",
        "Everly · Consultation",
        "Everly · Promotion",
        "Everly · Case Review",
        "Everly · Retargeting",
    ]
    out = []
    for d in _iter_days(since, until):
        rng = random.Random(f"everly-local-mock:{d.isoformat()}")
        spend = round(rng.uniform(950, 2800), 2)
        result = rng.randint(8, 32)
        reach = rng.randint(2500, 9000)
        frequency = round(rng.uniform(1.08, 1.85), 2)
        impression = int(reach * frequency)
        conversion = round(spend * rng.uniform(4.8, 13.5), 2)
        roas = conversion / spend if spend else 0
        synthetic_ad = {
            "campaign": campaigns[rng.randrange(len(campaigns))],
            "status": "Mock",
            "objective": "Inbox",
            "budget": 0,
            "impression": impression,
            "reach": reach,
            "frequency": frequency,
            "cpm": round((spend / impression * 1000) if impression else 0, 2),
            "ctr": round(rng.uniform(0.8, 3.5), 3),
            "cpc": round(rng.uniform(12, 45), 2),
            "link_clicks": rng.randint(20, 110),
            "conversion": conversion,
            "roas": round(roas, 2),
            "result": result,
            "cost_per_result": round((spend / result) if result else 0, 2),
            "spent": spend,
        }
        out.append({
            "date": d.isoformat(),
            "month": d.strftime("%b"),
            "day": d.day,
            "ads": [synthetic_ad],
        })
    return out


def _mock_top_ads_range(since: date, until: date, limit: int) -> dict:
    ads: dict[str, dict] = {}
    for record in _mock_daily_records(since, until):
        day = _day_totals(record)
        name = day.get("top_campaign") or "Everly · Mock Campaign"
        row = ads.setdefault(name, {
            "campaign": name,
            "spent": 0,
            "impression": 0,
            "reach": 0,
            "result": 0,
            "conversion": 0,
        })
        row["spent"] += day["spent"]
        row["impression"] += day["impression"]
        row["reach"] += day["reach"]
        row["result"] += day["result"]
        row["conversion"] += day["conversion"]

    rows = []
    for row in ads.values():
        spent = row["spent"]
        result = row["result"]
        impression = row["impression"]
        rows.append({
            "campaign": row["campaign"],
            "spent": round(spent, 2),
            "impression": impression,
            "reach": row["reach"],
            "cpm": round((spent / impression * 1000) if impression else 0, 2),
            "result": result,
            "cost_per_result": round((spent / result) if result else 0, 2),
            "conversion": round(row["conversion"], 2),
            "roas": round((row["conversion"] / spent) if spent else 0, 2),
        })
    rows.sort(key=lambda r: ((r["cost_per_result"] if r["result"] else 9e9), -r["spent"]))
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "n_ads": len(rows),
        "ads": rows[:limit],
        "fetched_at": now_bkk().isoformat(),
        "mock": True,
        "warning": "MOCK_MODE/no FB_ACCESS_TOKEN — showing deterministic local mock data",
    }


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
    if _mock_data_enabled():
        return _mock_daily_records(since, until)
    key = f"range:{since.isoformat()}:{until.isoformat()}:{signature()}"
    return _cached(key, lambda: fetch_daily(ACCOUNT_ID, since, until))


def _default_report_date() -> date:
    """Daily reports default to the previous complete Bangkok day."""
    return today_bkk() - timedelta(days=1)


def _within_auto_send_window(now: Optional[datetime] = None) -> bool:
    """Allow automatic LINE sends from midnight through morning Bangkok time.

    GitHub scheduled workflows on the free tier can start late. Keep the
    idempotency guard per report date, but allow delayed runs to still send the
    previous completed day before the team starts work.
    """
    now = now or now_bkk()
    return 0 <= now.hour <= 8


def _read_sent_state() -> dict:
    try:
        if SENT_STATE_FILE.exists():
            return json.loads(SENT_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_sent_state(state: dict) -> None:
    try:
        SENT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SENT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Sending the report is more important than failing on local state I/O.
        pass


def _already_sent(report_date: date) -> Optional[dict]:
    return _read_sent_state().get(report_date.isoformat())


def _mark_sent(report_date: date, preview: str) -> None:
    state = _read_sent_state()
    # Keep the file tiny: only retain the latest 45 report markers.
    state[report_date.isoformat()] = {
        "sent_at": now_bkk().isoformat(),
        "preview": preview[:180],
    }
    items = sorted(state.items())[-45:]
    _write_sent_state(dict(items))


def _summary_snapshot_path(since: date, until: date) -> Path:
    return SUMMARY_SNAPSHOT_DIR / f"{since.isoformat()}__{until.isoformat()}.json"


def _read_summary_snapshot(since: date, until: date) -> Optional[dict]:
    path = _summary_snapshot_path(since, until)
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            data["stale"] = True
            data["snapshot_loaded_at"] = now_bkk().isoformat()
            return data
    except Exception:
        pass
    return None


def _write_summary_snapshot(since: date, until: date, data: dict) -> None:
    try:
        SUMMARY_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        payload = dict(data)
        payload["stale"] = False
        payload["snapshot_saved_at"] = now_bkk().isoformat()
        _summary_snapshot_path(since, until).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


# ── Endpoints ───────────────────────────────────────────────────────
@app.get("/api/health")
@app.get("/api/everly/health")
def health():
    has_token = _has_fb_token()
    mock = _mock_data_enabled()
    account_identity = _fetch_ad_account_identity()
    return {
        "ok": True,
        "brand": "Everly Clinic",
        "account_id": ACCOUNT_ID,
        "account_ids": [ACCOUNT_ID],
        "account_locked": ACCOUNT_ID == "1965556974211662",
        **account_identity,
        "has_token": has_token,
        "configured": has_token,
        "required_account_env": "FB_ACCOUNT_EVERLY",
        "required_account_ids": ["1965556974211662"],
        "line_configured": bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN") and (os.getenv("LINE_GROUP_ID_EVERLY") or os.getenv("LINE_GROUP_ID"))),
        "meta_configured": bool(os.getenv("FB_ACCESS_TOKEN")),
        "mock_mode": mock,
        "mock": mock,
        "mock_data": mock,
        "today": today_bkk().isoformat(),
        "server_time_bkk": now_bkk().isoformat(),
        "now_bkk": now_bkk().isoformat(),
        "cache_keys": list(_CACHE.keys()),
    }


@app.get("/api/everly/summary")
def everly_summary(
    since: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today"),
    until: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today"),
):
    """Aggregated KPIs + per-day chart data for a date range."""
    today = today_bkk()
    s = date.fromisoformat(since) if since else today
    u = date.fromisoformat(until) if until else today

    try:
        records = _fetch_range(s, u)
    except Exception as e:
        snapshot = _read_summary_snapshot(s, u)
        if snapshot:
            snapshot["warning"] = f"Meta API error; showing last good snapshot: {str(e)[:160]}"
            return snapshot
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
    mock = _mock_data_enabled()

    response = {
        "brand": "Everly Clinic",
        "account_id": ACCOUNT_ID,
        "account_locked": ACCOUNT_ID == "1965556974211662",
        "mock": mock,
        "mock_mode": mock,
        "source": "mock" if mock else "meta_api",
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
    if mock:
        response["warning"] = "MOCK_MODE/no FB_ACCESS_TOKEN — showing deterministic local mock data"
    else:
        _write_summary_snapshot(s, u, response)
    return response


@app.get("/api/everly/monthly-trend")
def everly_monthly_trend(
    since: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to Feb 1 of current year"),
    until: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today"),
):
    """Monthly aggregated KPIs for the analysis view."""
    today = today_bkk()
    default_since = date(today.year, 2, 1)
    s = date.fromisoformat(since) if since else default_since
    u = date.fromisoformat(until) if until else today

    try:
        records = _fetch_range(s, u)
    except Exception as e:
        snapshot = _read_summary_snapshot(s, u)
        if not (snapshot and snapshot.get("days")):
            raise HTTPException(status_code=502, detail=f"Meta API error: {e}")
        records = [{"date": d["date"], "ads": [{
            "spent": d.get("spent", 0),
            "result": d.get("result", 0),
            "conversion": d.get("conversion", 0),
            "impression": d.get("impression", 0),
            "reach": d.get("reach", 0),
            "cpm": d.get("cpm", 0),
            "ctr": d.get("ctr", 0),
            "frequency": d.get("frequency", 0),
            "roas": d.get("roas", 0),
            "cost_per_result": d.get("cost_per_result", 0),
            "campaign": d.get("top_campaign", ""),
        }]} for d in snapshot["days"]]

    months: dict[str, dict] = {}
    for day in (_day_totals(r) for r in records):
        if not day:
            continue
        key = day["date"][:7]
        row = months.setdefault(key, {
            "key": key,
            "spend": 0.0,
            "result": 0,
            "conv": 0.0,
            "revenue": 0.0,
            "impr": 0,
            "reach": 0,
            "n": 0,
        })
        row["spend"] += day["spent"]
        row["result"] += day["result"]
        row["conv"] += day["conversion"]
        row["revenue"] += day["conversion"]
        row["impr"] += day["impression"]
        row["reach"] += day["reach"]
        row["n"] += 1

    rows = []
    for row in sorted(months.values(), key=lambda x: x["key"]):
        spend = row["spend"]
        result = row["result"]
        conv = row["conv"]
        key = row["key"]
        rows.append({
            **row,
            "spend": round(spend, 2),
            "conv": round(conv, 2),
            "revenue": round(conv, 2),
            "monthIdx": int(key[5:7]) - 1,
            "year": int(key[:4]),
            "roas": round((conv / spend) if spend else 0, 2),
            "cpi": round((spend / result) if result else 0, 2),
            "net": round(conv - spend, 2),
        })

    mock = _mock_data_enabled()
    return {
        "brand": "Everly Clinic",
        "account_id": ACCOUNT_ID,
        "account_locked": ACCOUNT_ID == "1965556974211662",
        "mock": mock,
        "mock_mode": mock,
        "source": "mock" if mock else "meta_api",
        "since": s.isoformat(),
        "until": u.isoformat(),
        "n_months": len(rows),
        "months": rows,
        "cache_ttl_sec": TTL,
        "fetched_at": now_bkk().isoformat(),
    }


def _resolve_target_date(target: Optional[str], date_value: Optional[str], default: date) -> date:
    return date.fromisoformat(target or date_value) if (target or date_value) else default


@app.get("/api/everly/day")
def everly_day(
    target: Optional[str] = Query(None),
    date_value: Optional[str] = Query(None, alias="date"),
):
    """Single-day totals. `target`/`date` defaults to today."""
    today = today_bkk()
    d = _resolve_target_date(target, date_value, today)
    try:
        records = _fetch_range(d, d)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta API error: {e}")
    if not records:
        return {"date": d.isoformat(), "spent": 0, "result": 0, "conversion": 0, "roas": 0, "cost_per_result": 0, "top_campaign": "", "empty": True}
    return _day_totals(records[0])


@app.get("/api/everly/top-ads")
def everly_top_ads(
    target: Optional[str] = Query(None),
    date_value: Optional[str] = Query(None, alias="date"),
):
    """Top 3 ads by spend for a given day (defaults to yesterday)."""
    d = _resolve_target_date(target, date_value, today_bkk() - timedelta(days=1))
    try:
        rows = _cached(
            f"top3:{d.isoformat()}:{signature()}",
            lambda: fetch_top3_ads(ACCOUNT_ID, d, "Inbox"),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta API error: {e}")
    response = {"date": d.isoformat(), "ads": to_dict_list(rows)}
    if _mock_data_enabled():
        response["mock"] = True
        response["warning"] = "MOCK_MODE/no FB_ACCESS_TOKEN — showing deterministic local mock data"
    return response


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
    if _mock_data_enabled():
        return _mock_top_ads_range(s, u, limit)

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
            if a.get("action_type") == "onsite_conversion.messaging_conversation_started_7d":
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
def everly_report(
    target: Optional[str] = Query(None),
    date_value: Optional[str] = Query(None, alias="date"),
):
    """Pre-formatted daily report text + structured data.
    Defaults to **yesterday** (today is usually incomplete).
    """
    d = _resolve_target_date(target, date_value, today_bkk() - timedelta(days=1))

    try:
        day = _fetch_range(d, d)
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

    response = {
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
    if _mock_data_enabled():
        response["mock"] = True
        response["warning"] = "MOCK_MODE/no FB_ACCESS_TOKEN — showing deterministic local mock data"
    return response


@app.get("/api/everly/cache/clear")
def clear_cache():
    n = len(_CACHE)
    _CACHE.clear()
    return {"cleared": n}


# Module-level runtime caches set by /admin/derive-page-token & /admin/bootstrap.
# Survive within the same process; Render restart reverts to env vars.
# Persistence file lets the chain survive restarts WITHOUT requiring a Render env-var
# edit (which the user might not be able to do at 3am). Token written here on every
# successful bootstrap; read here on startup. ROOT/.token_cache.json is gitignored.
_TOKEN_CACHE_FILE = ROOT / ".token_cache.json"

_RUNTIME_PAGE_TOKEN: Optional[str] = None
_RUNTIME_USER_TOKEN: Optional[str] = None  # bootstrap source for auto-refresh
_RUNTIME_PAGE_TOKEN_VERIFIED_AT: int = 0   # unix ts of last successful FB call


def _persist_runtime_tokens() -> None:
    """Best-effort write of cached tokens to disk so that Render redeploys/restarts
    don't lose the chain. Render free tier disk is ephemeral (lost on instance
    replacement) but persists across normal restarts and code redeploys, which is
    most of what users hit."""
    try:
        payload = {
            "user_token": _RUNTIME_USER_TOKEN,
            "page_token": _RUNTIME_PAGE_TOKEN,
            "verified_at": _RUNTIME_PAGE_TOKEN_VERIFIED_AT,
            "saved_at": int(time.time()),
        }
        _TOKEN_CACHE_FILE.write_text(json.dumps(payload))
    except Exception:
        pass  # disk write failures are non-fatal


def _load_runtime_tokens() -> None:
    """Counterpart of _persist_runtime_tokens — load on import."""
    global _RUNTIME_USER_TOKEN, _RUNTIME_PAGE_TOKEN, _RUNTIME_PAGE_TOKEN_VERIFIED_AT
    try:
        if not _TOKEN_CACHE_FILE.exists():
            return
        payload = json.loads(_TOKEN_CACHE_FILE.read_text())
        _RUNTIME_USER_TOKEN = payload.get("user_token") or _RUNTIME_USER_TOKEN
        _RUNTIME_PAGE_TOKEN = payload.get("page_token") or _RUNTIME_PAGE_TOKEN
        _RUNTIME_PAGE_TOKEN_VERIFIED_AT = int(payload.get("verified_at") or 0)
    except Exception:
        pass


# Load on module import — runs once per process start
_load_runtime_tokens()


def _try_auto_refresh_page_token() -> Optional[str]:
    """If env-stored page token is broken AND we have a cached user_token,
    automatically derive a fresh page token. Used by funnel endpoints.
    Returns the new page token on success, None on failure.
    """
    global _RUNTIME_PAGE_TOKEN, _RUNTIME_PAGE_TOKEN_VERIFIED_AT
    user_token = _RUNTIME_USER_TOKEN or os.getenv("FB_USER_TOKEN_NAIYHUA", "")
    if not user_token:
        return None
    page_id = os.getenv("FB_PAGE_ID_EVERLY", "776628652192729")
    import requests as _r
    # Try /me/accounts first (most permissive)
    try:
        r = _r.get(
            "https://graph.facebook.com/v20.0/me/accounts",
            params={"access_token": user_token, "fields": "id,access_token"},
            timeout=15,
        )
        if r.status_code == 200:
            for p in r.json().get("data", []):
                if str(p.get("id")) == str(page_id) and p.get("access_token"):
                    _RUNTIME_PAGE_TOKEN = p["access_token"]
                    _RUNTIME_PAGE_TOKEN_VERIFIED_AT = int(time.time())
                    _persist_runtime_tokens()
                    return _RUNTIME_PAGE_TOKEN
    except Exception:
        pass
    # Fall back to direct page fetch
    try:
        r = _r.get(
            f"https://graph.facebook.com/v20.0/{page_id}",
            params={"access_token": user_token, "fields": "id,access_token"},
            timeout=15,
        )
        if r.status_code == 200 and r.json().get("access_token"):
            _RUNTIME_PAGE_TOKEN = r.json()["access_token"]
            _RUNTIME_PAGE_TOKEN_VERIFIED_AT = int(time.time())
            _persist_runtime_tokens()
            return _RUNTIME_PAGE_TOKEN
    except Exception:
        pass
    return None


@app.post("/api/everly/admin/bootstrap")
async def admin_bootstrap(request: Request):
    """One-call setup: takes a user_token, stores in process memory,
    immediately derives & caches a page_token. Subsequent funnel calls
    will use the cached page_token; if it ever fails, /admin/funnel
    auto-refreshes from the stored user_token.

    Accepts the user_token from any of:
      - JSON body: {"user_token": "EAA..."}
      - Form-encoded body: user_token=EAA...
      - Text/plain body containing JSON (sendBeacon uses this)
      - Query string: ?user_token=EAA...
    Multi-format keeps cross-origin senders (sendBeacon, simple fetch,
    HTML form POST) working without CORS preflight gymnastics.
    """
    user_token = ""
    # Try query string first (works even with no body)
    user_token = (request.query_params.get("user_token") or "").strip()
    if not user_token:
        # Try parsing body in priority order
        body = await request.body()
        if body:
            ctype = (request.headers.get("content-type") or "").lower()
            try:
                if "application/json" in ctype or body[:1] in (b"{", b"["):
                    data = json.loads(body)
                    user_token = (data.get("user_token") if isinstance(data, dict) else "") or ""
                elif "form-urlencoded" in ctype:
                    from urllib.parse import parse_qs
                    data = parse_qs(body.decode("utf-8", errors="ignore"))
                    user_token = (data.get("user_token") or [""])[0]
                else:
                    # Last-resort: try to parse as JSON regardless of content-type
                    text = body.decode("utf-8", errors="ignore").strip()
                    if text.startswith("{"):
                        data = json.loads(text)
                        if isinstance(data, dict):
                            user_token = data.get("user_token", "") or ""
                    elif text.startswith("EAA") and len(text) > 50:
                        user_token = text  # raw token in body
            except Exception:
                pass
    user_token = (user_token or "").strip()
    if not user_token:
        raise HTTPException(400, "user_token required (JSON body, form, query string, or raw text)")
    global _RUNTIME_USER_TOKEN
    _RUNTIME_USER_TOKEN = user_token
    page_token = _try_auto_refresh_page_token()
    # Persist so Render restart doesn't wipe the chain
    _persist_runtime_tokens()
    return {
        "ok": page_token is not None,
        "user_token_cached": True,
        "user_token_len": len(user_token),
        "page_token_derived": page_token is not None,
        "page_token_prefix": page_token[:12] if page_token else None,
        "message": "Funnel will now auto-recover from page-token failures using the cached user_token.",
    }


@app.get("/api/everly/admin/token-debug")
def admin_token_debug():
    """Diagnostic — does NOT return token values, only metadata.
    Useful for debugging the auto-refresh chain when funnel returns 0."""
    user_token = _RUNTIME_USER_TOKEN or os.getenv("FB_USER_TOKEN_NAIYHUA", "")
    page_token, page_id = _page_credentials()
    info = {
        "page_id": page_id,
        "user_token": {
            "cached_in_memory": bool(_RUNTIME_USER_TOKEN),
            "from_env": bool(os.getenv("FB_USER_TOKEN_NAIYHUA")),
            "len": len(user_token) if user_token else 0,
            "prefix": user_token[:12] if user_token else None,
            "suffix": user_token[-8:] if user_token else None,
        },
        "page_token": {
            "from_runtime": bool(_RUNTIME_PAGE_TOKEN),
            "from_env": bool(os.getenv("FB_PAGE_TOKEN_EVERLY")),
            "len": len(page_token) if page_token else 0,
            "prefix": page_token[:12] if page_token else None,
            "verified_at": _RUNTIME_PAGE_TOKEN_VERIFIED_AT,
        },
    }
    # Live test of user_token by calling /me
    if user_token:
        import requests as _r
        try:
            r = _r.get("https://graph.facebook.com/v20.0/me",
                       params={"access_token": user_token, "fields": "id,name"}, timeout=10)
            info["user_token"]["live_test"] = {
                "status": r.status_code,
                "ok": r.status_code == 200,
                "body": r.text[:200] if r.status_code != 200 else r.json(),
            }
        except Exception as e:
            info["user_token"]["live_test"] = {"error": str(e)}
    return info


@app.get("/api/everly/admin/token-status")
def admin_token_status():
    """Health check for the token chain. Used by dashboard banner.
    Optimistic: if the env page_token's live probe fails AND a user_token
    is cached, proactively auto-refresh BEFORE reporting status. The banner
    therefore only shows when even the auto-refresh path is blocked, which
    matches the actual user-facing state of 'broken / needs intervention'.
    """
    import requests as _r

    def probe(tok, pid):
        try:
            r = _r.get(
                f"https://graph.facebook.com/v20.0/{pid}",
                params={"access_token": tok, "fields": "id"},
                timeout=8,
            )
            return (r.status_code == 200) and ("id" in r.json())
        except Exception:
            return False

    page_token, page_id = _page_credentials()
    has_user = bool(_RUNTIME_USER_TOKEN or os.getenv("FB_USER_TOKEN_NAIYHUA", ""))
    refreshed = False

    if not page_token or not page_id:
        live = False
    else:
        live = probe(page_token, page_id)
        if not live and has_user:
            # Auto-recover before reporting failure
            new_tok = _try_auto_refresh_page_token()
            if new_tok:
                page_token, page_id = _page_credentials()
                live = probe(page_token, page_id)
                refreshed = bool(live)

    return {
        "ok": live,
        "stage": "live" if live else ("missing" if not page_token else "expired"),
        "user_token_available": has_user,
        "auto_refresh_capable": has_user,
        "auto_refreshed_just_now": refreshed,
        "verified_at": _RUNTIME_PAGE_TOKEN_VERIFIED_AT,
    }


@app.post("/api/everly/admin/derive-page-token")
def derive_page_token(payload: dict = Body(...)):
    """One-shot helper: takes a user token (long or short), derives a page token.
    Tries exchange-to-long-lived FIRST (best — gives never-expiring page token).
    If exchange fails (e.g. token from Graph Explorer's app, not ours), falls back
    to using the user token directly — page token then inherits user-token lifetime.
    Stores in process memory so funnel endpoint uses it immediately,
    AND returns it so user can save permanently to FB_PAGE_TOKEN_EVERLY env.
    """
    import requests as _r
    user_token = (payload.get("user_token") or "").strip()
    if not user_token:
        raise HTTPException(400, "user_token required")
    page_id = os.getenv("FB_PAGE_ID_EVERLY", "776628652192729")
    app_id = os.getenv("FB_APP_ID", "")
    app_secret = os.getenv("FB_APP_SECRET", "")

    exchange_attempted = False
    exchange_ok = False
    exchange_error = ""
    effective_user_token = user_token  # default: use as-is
    long_lived = False

    # Step 1 (best path): short → long user token via OUR app's secret
    if app_id and app_secret:
        exchange_attempted = True
        try:
            r1 = _r.get(
                "https://graph.facebook.com/v20.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "fb_exchange_token": user_token,
                },
                timeout=15,
            )
            if r1.status_code == 200:
                lu = r1.json().get("access_token")
                if lu:
                    effective_user_token = lu
                    exchange_ok = True
                    long_lived = True
                else:
                    exchange_error = "Exchange returned no access_token"
            else:
                exchange_error = f"HTTP {r1.status_code}: {r1.text[:200]}"
        except Exception as e:
            exchange_error = f"Exception: {e!r}"

    # Step 2: derive page token. Try multiple paths because:
    #   - Classic Pages: /me/accounts returns the page
    #   - New Pages Experience (NPE): /me/accounts may return [], use /{page_id} direct
    #   - Some Business-owned pages: only accessible via /{page_id}?fields=access_token
    page_token = None
    page_name = ""
    derive_path = ""
    accounts_count = 0
    accounts_error = ""
    direct_error = ""

    # Path A: /me/accounts (classic pages)
    try:
        r2 = _r.get(
            "https://graph.facebook.com/v20.0/me/accounts",
            params={"access_token": effective_user_token, "fields": "id,name,access_token"},
            timeout=15,
        )
        if r2.status_code == 200:
            accounts = r2.json().get("data", [])
            accounts_count = len(accounts)
            matching = next((p for p in accounts if str(p.get("id")) == str(page_id)), None)
            if matching and matching.get("access_token"):
                page_token = matching["access_token"]
                page_name = matching.get("name", "")
                derive_path = "/me/accounts"
        else:
            accounts_error = f"HTTP {r2.status_code}: {r2.text[:200]}"
    except Exception as e:
        accounts_error = f"Exception: {e!r}"

    # Path B: /{page_id}?fields=access_token,name (NPE / Business-owned)
    if not page_token:
        try:
            r3 = _r.get(
                f"https://graph.facebook.com/v20.0/{page_id}",
                params={"access_token": effective_user_token, "fields": "id,name,access_token"},
                timeout=15,
            )
            if r3.status_code == 200:
                pdata = r3.json()
                if pdata.get("access_token"):
                    page_token = pdata["access_token"]
                    page_name = pdata.get("name", "")
                    derive_path = f"/{page_id} direct"
                else:
                    direct_error = f"Page returned but no access_token in response: {list(pdata.keys())}"
            else:
                direct_error = f"HTTP {r3.status_code}: {r3.text[:200]}"
        except Exception as e:
            direct_error = f"Exception: {e!r}"

    if not page_token:
        raise HTTPException(404, (
            f"Could not derive page token for page {page_id}. "
            f"Tried /me/accounts (returned {accounts_count} pages, error: {accounts_error or 'none'}) "
            f"and /{page_id} direct (error: {direct_error or 'none'}). "
            "Likely cause: user token is from a profile that does not have admin role on this page, "
            "OR the page is in 'New Pages Experience' and requires pages_manage_metadata permission."
        ))

    # Step 3: Verify by calling conversations
    r3 = _r.get(
        f"https://graph.facebook.com/v20.0/{page_id}/conversations",
        params={"fields": "message_count", "limit": 1, "access_token": page_token},
        timeout=15,
    )
    test_ok = r3.status_code == 200 and "data" in r3.json()
    test_error = "" if test_ok else f"HTTP {r3.status_code}: {r3.text[:200]}"

    # Step 4: stash in process memory (immediate use)
    global _RUNTIME_PAGE_TOKEN
    _RUNTIME_PAGE_TOKEN = page_token

    return {
        "ok": True,
        "page_name": page_name,
        "page_token": page_token,  # full value — caller saves to env then revokes from response history
        "page_token_prefix": page_token[:12],
        "page_token_suffix": page_token[-12:],
        "page_token_len": len(page_token),
        "long_lived": long_lived,
        "derive_path": derive_path,
        "exchange_attempted": exchange_attempted,
        "exchange_ok": exchange_ok,
        "exchange_error": exchange_error,
        "test_conversations_ok": test_ok,
        "test_error": test_error,
        "instructions": (
            "Save page_token to Render env var FB_PAGE_TOKEN_EVERLY. "
            + ("Long-lived page token — never expires." if long_lived
               else "WARNING: Token derived from short-lived user token — expires when user token expires (1-2 hours). "
                    "For permanent token, generate user token from OUR app (FB_APP_ID).")
        ),
    }


# ── Admin tab: Page Conversations API endpoints ─────────────────
def _page_credentials():
    """Page Access Token + Page ID — set in Render env vars.
    Falls back to runtime-derived token if available (set via /admin/derive-page-token)."""
    token = _RUNTIME_PAGE_TOKEN or os.getenv("FB_PAGE_TOKEN_EVERLY", "")
    pid = os.getenv("FB_PAGE_ID_EVERLY", "")
    return token, pid


# Thai phone number patterns — match common formats customers send in chat
_PHONE_PATTERNS = [
    # Mobile: 0[6,8,9]XXXXXXXX (10 digits, optional separators)
    re.compile(r'0\s*[689]\s*\d\s*[-.\s]?\s*\d\s*\d\s*\d\s*[-.\s]?\s*\d\s*\d\s*\d\s*\d?'),
    # International: +66[6,8,9]XXXXXXXX
    re.compile(r'\+?\s*66\s*[689]\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d?'),
]

def _text_has_phone(text: str) -> bool:
    """Detect Thai mobile phone number in message text. Strips Zalgo/zero-width
    chars then checks against Thai mobile patterns. Filters out FB user IDs and
    timestamps that might match by accident (≥11 contiguous digits → not a phone)."""
    if not text:
        return False
    # Normalize: strip thai digits → arabic, remove zero-width chars
    s = str(text)
    s = s.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    s = re.sub(r'[​‌‍﻿]', '', s)
    # If the candidate contains a 12+ digit run, it's likely an FB ID, not a phone
    for m in _PHONE_PATTERNS:
        match = m.search(s)
        if match:
            digits = re.sub(r'\D', '', match.group())
            # Thai mobile is exactly 10 digits (or 11 with country code)
            if 9 <= len(digits) <= 11:
                return True
    return False


def _analyze_conversation_messages(conv_id: str, token: str, since_ts: Optional[int] = None,
                                   page_id: Optional[str] = None) -> dict:
    """Paginate through a conversation's messages, tracking:
      - oldest_ts: chronologically first message (true conversation start)
      - has_phone: any customer message contains a Thai mobile number
      - first_customer_msg_ts: first message FROM customer (for response time calc)
      - first_admin_reply_ts: first message FROM page that comes AFTER first_customer_msg_ts
      - last_msg_from_customer: bool — is the most recent message from customer?
      - last_msg_ts: timestamp of most recent message
    Short-circuits when an oldest message older than since_ts is found.
    """
    import requests as _r
    next_url = f"https://graph.facebook.com/v20.0/{conv_id}/messages"
    params = {"limit": 100, "fields": "created_time,message,from", "access_token": token}
    all_msgs = []  # list of (ts, from_id, text) for sorting later
    has_phone = False
    found_old = False

    try:
        for _ in range(20):
            r = _r.get(next_url, params=params, timeout=15)
            if r.status_code != 200:
                break
            data = r.json()
            msgs = data.get("data", [])
            if not msgs:
                break
            for msg in msgs:
                ts_str = msg.get("created_time", "")
                try:
                    ts_dt = datetime.strptime(ts_str.split("+")[0], "%Y-%m-%dT%H:%M:%S")
                    ts = int(ts_dt.replace(tzinfo=timezone.utc).timestamp())
                except Exception:
                    continue
                from_id = (msg.get("from") or {}).get("id", "")
                text = msg.get("message", "")
                if text and not has_phone and _text_has_phone(text):
                    has_phone = True
                all_msgs.append((ts, from_id, bool(text)))
            # Short-circuit if oldest seen so far is already before since_ts
            if since_ts is not None and all_msgs:
                cur_oldest = min(m[0] for m in all_msgs)
                if cur_oldest < since_ts:
                    found_old = True
                    break
            next_url = (data.get("paging") or {}).get("next")
            if not next_url:
                break
            params = {}

        if not all_msgs:
            return {"oldest_ts": None, "has_phone": False, "error": True}

        # Sort chronologically (oldest first)
        all_msgs.sort(key=lambda x: x[0])
        oldest_ts = all_msgs[0][0]
        last_ts, last_from, _ = all_msgs[-1]

        # Identify first customer message + first admin reply after it
        first_cust_ts = None
        first_admin_reply_ts = None
        for ts, fid, _ in all_msgs:
            is_admin = page_id and fid == str(page_id)
            if first_cust_ts is None and not is_admin:
                first_cust_ts = ts
                continue
            if first_cust_ts is not None and first_admin_reply_ts is None and is_admin and ts >= first_cust_ts:
                first_admin_reply_ts = ts
                break

        last_from_customer = bool(last_from) and (not page_id or last_from != str(page_id))

        return {
            "oldest_ts": oldest_ts,
            "has_phone": has_phone,
            "first_customer_msg_ts": first_cust_ts,
            "first_admin_reply_ts": first_admin_reply_ts,
            "last_msg_from_customer": last_from_customer,
            "last_msg_ts": last_ts,
            "error": False,
        }
    except Exception:
        return {"oldest_ts": None, "has_phone": has_phone, "error": True}


# Backwards-compat shim: callers expecting just ts.
def _fetch_first_message_ts(conv_id: str, token: str, since_ts: Optional[int] = None) -> Optional[int]:
    return _analyze_conversation_messages(conv_id, token, since_ts).get("oldest_ts")


def _fetch_all_conversations(since_ts: int, until_ts: int, _debug: dict = None) -> list:
    """Pull all conversations updated within [since_ts, until_ts] (unix seconds).
    Returns list of conversation dicts with id, message_count, updated_time, link.
    If _debug dict is provided, populates with fetch diagnostics.
    """
    import requests as _r
    token, pid = _page_credentials()
    if _debug is not None:
        _debug["token_len"] = len(token)
        _debug["token_prefix"] = token[:8] if token else ""
        _debug["page_id"] = pid
        _debug["since_ts"] = since_ts
        _debug["until_ts"] = until_ts
    if not (token and pid):
        return []

    out = []
    url = f"https://graph.facebook.com/v20.0/{pid}/conversations"
    params = {
        "fields": "id,message_count,updated_time,link",
        "limit": 100,
        "access_token": token,
    }
    pages_fetched = 0
    raw_total = 0
    for _ in range(10):
        resp = _r.get(url, params=params, timeout=20)
        pages_fetched += 1
        if resp.status_code != 200:
            if _debug is not None:
                _debug["http_status"] = resp.status_code
                _debug["error"] = resp.text[:300]
            break
        data = resp.json()
        if _debug is not None and "fb_error" in data:
            _debug["fb_error"] = data["fb_error"]
        page_data = data.get("data", [])
        raw_total += len(page_data)
        for c in page_data:
            ut = c.get("updated_time", "")
            try:
                ut_dt = datetime.strptime(ut.split("+")[0], "%Y-%m-%dT%H:%M:%S")
                ut_ts = int(ut_dt.replace(tzinfo=timezone.utc).timestamp())
            except Exception:
                continue
            if ut_ts < since_ts:
                if _debug is not None:
                    _debug["pages_fetched"] = pages_fetched
                    _debug["raw_total"] = raw_total
                    _debug["filtered_total"] = len(out)
                    _debug["broke_on_old"] = True
                return out
            if ut_ts <= until_ts:
                out.append({
                    "id": c.get("id"),
                    "message_count": c.get("message_count", 0),
                    "updated_time": ut,
                    "link": c.get("link", ""),
                })
        next_url = data.get("paging", {}).get("next")
        if not next_url:
            break
        url = next_url
        params = {}
    if _debug is not None:
        _debug["pages_fetched"] = pages_fetched
        _debug["raw_total"] = raw_total
        _debug["filtered_total"] = len(out)
    return out


@app.get("/api/everly/admin/funnel")
def admin_funnel(
    since: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today"),
    until: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today"),
):
    """Funnel from real FB Page conversations:
      ทัก (>=1 msg) → คุย 2+ → 4+ → 6+ → 8+ → 10+ ประโยค
    Returns counts at each stage + raw conversation list.
    """
    today = today_bkk()
    s = date.fromisoformat(since) if since else today
    u = date.fromisoformat(until) if until else today

    # Convert to unix seconds in BKK
    s_dt = datetime.combine(s, datetime.min.time(), tzinfo=BANGKOK_TZ)
    u_dt = datetime.combine(u, datetime.max.time(), tzinfo=BANGKOK_TZ)
    s_ts = int(s_dt.timestamp())
    u_ts = int(u_dt.timestamp())

    # Result cache — return cached funnel response if recent (avoids re-fetching
    # every conversation's messages on tab open / filter change)
    cache_key = (s_ts, u_ts)
    now_unix = int(time.time())
    cached = _FUNNEL_CACHE.get(cache_key)
    if cached and (now_unix - cached["_cached_at"]) < _FUNNEL_CACHE_TTL:
        out = {k: v for k, v in cached.items() if k != "_cached_at"}
        out["cache_age_sec"] = now_unix - cached["_cached_at"]
        out["cache_hit"] = True
        return out

    token, pid = _page_credentials()
    if not (token and pid):
        # Fallback to mock if env vars not set
        return {
            "since": s.isoformat(),
            "until": u.isoformat(),
            "configured": False,
            "stages": [
                {"label": "ทัก", "count": 28, "pct": 100},
                {"label": "คุย 2+ ประโยค", "count": 22, "pct": 78},
                {"label": "คุย 4+ ประโยค", "count": 18, "pct": 64},
                {"label": "คุย 6+ ประโยค", "count": 14, "pct": 50},
                {"label": "คุย 8+ ประโยค", "count": 11, "pct": 39},
                {"label": "คุย 10+ ประโยค", "count": 9, "pct": 32},
                {"label": "ได้เบอร์", "count": 13, "pct": 46, "highlight": True},
            ],
            "total_inbox": 28,
            "no_reply": 3,
            "ghosted": 5,
            "avg_first_response_min": 4.2,
            "stale": True,
            "warning": "FB_PAGE_TOKEN_EVERLY + FB_PAGE_ID_EVERLY not set — showing mock data",
        }

    # Live: pull conversations updated in range (these include both NEW + continuing)
    debug_info = {}
    conversations = _fetch_all_conversations(s_ts, u_ts, _debug=debug_info)

    # Auto-recover: if fetch returned 0 due to a token error, try refreshing the
    # page_token from the cached user_token (set via /admin/bootstrap), then retry
    if not conversations and "Malformed access token" in str(debug_info.get("error", "")):
        debug_info["auto_refresh_attempted"] = True
        new_token = _try_auto_refresh_page_token()
        if new_token:
            debug_info["auto_refresh_ok"] = True
            debug_info_retry = {}
            conversations = _fetch_all_conversations(s_ts, u_ts, _debug=debug_info_retry)
            debug_info.update({k: v for k, v in debug_info_retry.items() if k not in debug_info})
        else:
            debug_info["auto_refresh_ok"] = False

    activity_total = len(conversations)
    if activity_total == 0:
        return {
            "since": s.isoformat(), "until": u.isoformat(),
            "configured": True, "total_inbox": 0,
            "stages": [], "no_reply": 0, "ghosted": 0,
            "response_time": {"samples": 0, "avg_min": None, "distribution": {"under_5min": 0, "min_5_30": 0, "min_30_60": 0, "over_1h": 0}, "slow_count": 0, "currently_waiting": 0},
            "hourly_heatmap": [0]*24,
            "lead_quality": {"conversion_rate": 0, "phones_count": 0, "avg_messages_to_phone": None},
            "debug": debug_info,
        }

    # Filter to ONLY conversations whose FIRST message (chronological) falls in range.
    # This is the correct definition of "ทัก" = new customer initiating contact.
    # Conversations that merely had activity (admin reply or customer follow-up to old thread)
    # are EXCLUDED because they don't represent a new lead.
    token, _ = _page_credentials()
    new_conversations = []
    skipped_old = 0
    fetch_errors = 0
    from concurrent.futures import ThreadPoolExecutor

    _, page_id = _page_credentials()

    def _check(c):
        result = _analyze_conversation_messages(c["id"], token, since_ts=s_ts, page_id=page_id)
        return c, result

    # Parallelize per-conversation message analysis (25 workers; matches corpus builder)
    with ThreadPoolExecutor(max_workers=25) as pool:
        for c, result in pool.map(_check, conversations):
            ts = result.get("oldest_ts")
            if ts is None:
                fetch_errors += 1
                continue
            if s_ts <= ts <= u_ts:
                c["first_message_ts"] = ts
                c["has_phone"] = bool(result.get("has_phone"))
                c["first_customer_msg_ts"] = result.get("first_customer_msg_ts")
                c["first_admin_reply_ts"] = result.get("first_admin_reply_ts")
                c["last_msg_from_customer"] = bool(result.get("last_msg_from_customer"))
                c["last_msg_ts"] = result.get("last_msg_ts")
                new_conversations.append(c)
            else:
                skipped_old += 1

    debug_info["activity_in_range"] = activity_total
    debug_info["new_in_range"] = len(new_conversations)
    debug_info["skipped_old_continuing"] = skipped_old
    debug_info["first_msg_fetch_errors"] = fetch_errors

    total = len(new_conversations)
    if total == 0:
        return {
            "since": s.isoformat(), "until": u.isoformat(),
            "configured": True, "total_inbox": 0,
            "stages": [], "no_reply": 0, "ghosted": 0,
            "response_time": {"samples": 0, "avg_min": None, "distribution": {"under_5min": 0, "min_5_30": 0, "min_30_60": 0, "over_1h": 0}, "slow_count": 0, "currently_waiting": 0},
            "hourly_heatmap": [0]*24,
            "lead_quality": {"conversion_rate": 0, "phones_count": 0, "avg_messages_to_phone": None},
            "debug": debug_info,
        }

    # Cumulative funnel — counts only NEW conversations at each engagement level
    def count_at(min_msg: int) -> int:
        return sum(1 for c in new_conversations if (c.get("message_count") or 0) >= min_msg)

    # Final stage: ได้เบอร์ — count NEW conversations where customer sent a Thai phone number
    phones_count = sum(1 for c in new_conversations if c.get("has_phone"))

    stages = [
        {"label": "ทัก", "count": total, "pct": 100, "highlight": False},
        {"label": "คุย 2+ ประโยค", "count": count_at(2), "pct": round(count_at(2) / total * 100), "highlight": False},
        {"label": "คุย 4+ ประโยค", "count": count_at(4), "pct": round(count_at(4) / total * 100), "highlight": False},
        {"label": "คุย 6+ ประโยค", "count": count_at(6), "pct": round(count_at(6) / total * 100), "highlight": False},
        {"label": "คุย 8+ ประโยค", "count": count_at(8), "pct": round(count_at(8) / total * 100), "highlight": False},
        {"label": "คุย 10+ ประโยค", "count": count_at(10), "pct": round(count_at(10) / total * 100), "highlight": False},
        {"label": "ได้เบอร์", "count": phones_count, "pct": round(phones_count / total * 100), "highlight": True},
    ]

    # No-reply: new convs with only 1 message (customer messaged, page didn't respond yet)
    no_reply = sum(1 for c in new_conversations if (c.get("message_count") or 0) == 1)
    # Ghosted: 2-3 messages (page replied but customer didn't continue)
    ghosted = sum(1 for c in new_conversations if 2 <= (c.get("message_count") or 0) <= 3)

    # ── Response time stats (NEW Phase 1) ──
    # Compute customer-to-admin first response time, in seconds, per NEW conversation
    response_secs = []
    for c in new_conversations:
        cm = c.get("first_customer_msg_ts")
        ar = c.get("first_admin_reply_ts")
        if cm and ar and ar >= cm:
            response_secs.append(ar - cm)
    if response_secs:
        avg_response_min = round(sum(response_secs) / len(response_secs) / 60, 1)
        rt_under_5 = sum(1 for s in response_secs if s < 300)
        rt_5_30   = sum(1 for s in response_secs if 300 <= s < 1800)
        rt_30_60  = sum(1 for s in response_secs if 1800 <= s < 3600)
        rt_over_1h = sum(1 for s in response_secs if s >= 3600)
        slow_count = rt_30_60 + rt_over_1h
    else:
        avg_response_min = None
        rt_under_5 = rt_5_30 = rt_30_60 = rt_over_1h = 0
        slow_count = 0

    # Currently waiting: last message from customer AND >5min ago (still queued for admin)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    waiting_count = sum(
        1 for c in new_conversations
        if c.get("last_msg_from_customer") and c.get("last_msg_ts")
        and (now_ts - int(c["last_msg_ts"])) >= 300
    )

    # Hourly heatmap (BKK timezone): bucket first_customer_msg_ts by hour 0-23
    hourly_buckets = [0] * 24
    for c in new_conversations:
        cm = c.get("first_customer_msg_ts")
        if cm:
            try:
                hr = datetime.fromtimestamp(int(cm), tz=BANGKOK_TZ).hour
                if 0 <= hr <= 23:
                    hourly_buckets[hr] += 1
            except Exception:
                pass

    # Lead quality stats
    avg_msgs_to_phone = None
    if phones_count > 0:
        msgs_with_phone = [(c.get("message_count") or 0) for c in new_conversations if c.get("has_phone")]
        if msgs_with_phone:
            avg_msgs_to_phone = round(sum(msgs_with_phone) / len(msgs_with_phone), 1)

    response_payload = {
        "since": s.isoformat(),
        "until": u.isoformat(),
        "configured": True,
        "total_inbox": total,
        "stages": stages,
        "no_reply": no_reply,
        "ghosted": ghosted,
        "response_time": {
            "samples": len(response_secs),
            "avg_min": avg_response_min,
            "distribution": {
                "under_5min":  rt_under_5,
                "min_5_30":    rt_5_30,
                "min_30_60":   rt_30_60,
                "over_1h":     rt_over_1h,
            },
            "slow_count": slow_count,
            "currently_waiting": waiting_count,
        },
        "hourly_heatmap": hourly_buckets,
        "lead_quality": {
            "conversion_rate": round(phones_count / total * 100, 1) if total else 0,
            "phones_count": phones_count,
            "avg_messages_to_phone": avg_msgs_to_phone,
        },
        "data_source": "FB Pages Conversations API",
        "cache_age_sec": 0,
        "cache_hit": False,
        "fetched_at": now_bkk().isoformat(),
        "debug": debug_info,
    }
    # Cache result so the next dashboard refresh / sister-section call returns instantly
    _FUNNEL_CACHE[cache_key] = {**response_payload, "_cached_at": now_unix}
    if len(_FUNNEL_CACHE) > 16:
        oldest = min(_FUNNEL_CACHE, key=lambda k: _FUNNEL_CACHE[k]["_cached_at"])
        _FUNNEL_CACHE.pop(oldest, None)
    return response_payload


# ── Silence Trigger + FAQ classification (keyword-based) ──────────
# Thai keyword patterns for classifying WHY customers go silent and WHAT they ask.
# Each category maps to a list of keyword patterns. First match wins (priority).
# Categories ordered roughly by typical frequency for clinic context.

_SILENCE_CATEGORIES = [
    ("💰 ราคา",        ["ราคา", "เท่าไหร่", "กี่บาท", "แพง", "ค่าใช้จ่าย", "ทุน", "บาท", "เริ่มต้น", "ค่าทำ", "งบ"]),
    ("📍 โลเคชัน",     ["ที่ไหน", "อยู่ไหน", "สาขา", "ที่ตั้ง", "map", "ใกล้", "ไกล", "เส้นทาง", "ที่อยู่", "บางพลี", "สมุทรปราการ"]),
    ("⏰ เวลานัด",     ["นัด", "จอง", "ว่างไหม", "เวลา", "วันไหน", "อาทิตย์", "พรุ่งนี้", "เปิดกี่โมง", "คิว"]),
    ("💸 ขอลด",       ["ลด", "ส่วนลด", "ดีลส์", "voucher", "deal", "discount", "ต่อราคา", "ขอราคาพิเศษ"]),
    ("📆 รอโปรโม",    ["โปร", "promotion", "รอโปร", "เดือนหน้า", "ครั้งหน้า", "โปรใหม่", "โปรโมชั่น"]),
    ("🩺 บริการ",      ["บริการ", "รักษา", "ทำไหม", "มี", "ฉีด", "นวด", "หัตถการ", "เสริม", "filler", "botox"]),
    ("👨‍⚕️ หมอ",        ["หมอ", "แพทย์", "ดร.", "ดอกเตอร์", "ผู้เชี่ยวชาญ", "ใครรักษา", "ใครทำ", "ประสบการณ์"]),
    ("🛡 ปลอดภัย",     ["ปลอดภัย", "อันตราย", "ผลข้างเคียง", "เจ็บไหม", "เจ็บ", "FDA", "มาตรฐาน", "รับรอง", "ช้ำ", "บวม"]),
    ("⏳ ขอคิดดูก่อน", ["คิดดู", "ปรึกษา", "ลังเล", "ขอเวลา", "เดี๋ยว", "ขอดูก่อน", "ยังไม่พร้อม", "ขอตัดสินใจ"]),
]
_SILENCE_OTHER_LABEL = "🤔 อื่นๆ"


def _classify_silence(text: str) -> str:
    """Return category label for a customer message based on keyword match.
    Falls back to 'อื่นๆ' if nothing matches. Order in _SILENCE_CATEGORIES
    encodes priority (price wins over service if both keywords present)."""
    if not text:
        return _SILENCE_OTHER_LABEL
    s = str(text).lower()
    s = s.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    for label, keywords in _SILENCE_CATEGORIES:
        for kw in keywords:
            if kw.lower() in s:
                return label
    return _SILENCE_OTHER_LABEL


# FAQ topic classification: which question is being asked
# Tuple (label, keywords) — order = priority (specific before generic)
_FAQ_TOPICS = [
    ("ราคาเท่าไหร่",         ["ราคา", "เท่าไหร่", "กี่บาท", "ค่าใช้จ่าย", "ค่าทำ"]),
    ("ที่ตั้งคลินิก / map",    ["ที่ไหน", "ที่ตั้ง", "สาขา", "อยู่ไหน", "map", "เส้นทาง", "ที่อยู่"]),
    ("มีโปรโมชั่น",          ["โปร", "promotion", "ลดไหม", "discount", "deal"]),
    ("จองคิว / นัดหมาย",      ["จอง", "นัด", "ว่างไหม", "คิว", "booking"]),
    ("ใช้เวลาทำกี่นาที",      ["กี่นาที", "นานไหม", "ใช้เวลา", "นาน"]),
    ("หมอชื่ออะไร",          ["หมอ", "แพทย์", "ดร.", "ใครทำ", "ใครรักษา"]),
    ("ผ่อนได้มั้ย",          ["ผ่อน", "0%", "installment", "ผ่อนชำระ"]),
    ("เจ็บมั้ย / ผลข้างเคียง", ["เจ็บ", "ผลข้างเคียง", "อันตราย", "ปลอดภัย", "ช้ำ", "บวม"]),
    ("อยู่ได้นานกี่เดือน",     ["นานกี่เดือน", "อยู่นาน", "ระยะเวลา", "นานแค่ไหน"]),
    ("เปิดวันไหนบ้าง",        ["เปิดวันไหน", "วันเปิด", "วันปิด", "หยุด"]),
    ("รีวิว / ผลก่อนหลัง",     ["รีวิว", "review", "ก่อนหลัง", "before after"]),
    ("ขั้นตอนทำ",            ["ขั้นตอน", "วิธีทำ", "ทำยังไง", "process"]),
]
_FAQ_OTHER_LABEL = "อื่นๆ"


def _is_question(text: str) -> bool:
    """Heuristic: does this customer message ask a question?"""
    if not text or len(text) < 3:
        return False
    s = str(text)
    # Direct question marks (Thai or Latin)
    if "?" in s or "？" in s:
        return True
    # Thai question particles
    for kw in ["ไหม", "มั้ย", "เหรอ", "หรอ", "หรือเปล่า", "กี่", "ที่ไหน", "เมื่อไหร่", "เท่าไหร่",
               "อะไร", "ทำไม", "ยังไง", "มีไหม", "ใคร", "บ้างไหม"]:
        if kw in s:
            return True
    return False


def _classify_faq(text: str) -> Optional[str]:
    """Return FAQ topic label for a customer question, or None if not a question."""
    if not _is_question(text):
        return None
    s = str(text).lower()
    for label, keywords in _FAQ_TOPICS:
        for kw in keywords:
            if kw.lower() in s:
                return label
    return _FAQ_OTHER_LABEL


# In-memory corpus cache. Funnel + Silence + FAQ all walk every message of every
# conversation in the date range — that's expensive (paginated FB API calls per
# conversation). The same date range is queried 3× back-to-back when the dashboard
# loads and every time the date filter changes. Cache by (since, until) with TTL.
_CORPUS_CACHE: dict = {}
_CORPUS_CACHE_TTL = 90  # seconds — short enough to feel live, long enough to amortize 3 endpoints

# Funnel response cache (separate from corpus because funnel does its own per-conv analysis
# with phone detection + response-time computation that the corpus doesn't include).
_FUNNEL_CACHE: dict = {}
_FUNNEL_CACHE_TTL = 90


def _build_admin_message_corpus(s_ts: int, u_ts: int) -> dict:
    """Helper: pull all conversations updated in range, then for each fetch ALL messages,
    keeping only customer-side messages (from.id != page_id). Returns:
      conversations: list of {id, message_count, first_message_ts, last_msg_ts,
                              last_msg_from_customer, customer_messages: [{ts, text}]}
      activity_total, fetched_total, errors, cached_at (unix), cache_age_sec
    Cached for 90 seconds per (since, until) to keep three back-to-back endpoint
    calls (funnel, silence-trigger, faq) from re-fetching the same data three times.
    Includes auto-refresh: if the initial fetch returns 0 due to a token error,
    tries to refresh from the cached user_token before giving up.
    """
    import requests as _r
    cache_key = (s_ts, u_ts)
    now = int(time.time())
    cached = _CORPUS_CACHE.get(cache_key)
    if cached and (now - cached["cached_at"]) < _CORPUS_CACHE_TTL:
        # Return a shallow copy with up-to-date age, preserving original cached_at
        out = dict(cached)
        out["cache_age_sec"] = now - cached["cached_at"]
        out["cache_hit"] = True
        return out

    token, page_id = _page_credentials()
    if not (token and page_id):
        return {"conversations": [], "activity_total": 0, "fetched_total": 0, "errors": "no creds",
                "cached_at": now, "cache_age_sec": 0, "cache_hit": False}

    debug = {}
    convs = _fetch_all_conversations(s_ts, u_ts, _debug=debug)
    if not convs and "Malformed access token" in str(debug.get("error", "")):
        # Auto-recover from cached user_token if available
        if _try_auto_refresh_page_token():
            token, page_id = _page_credentials()  # refresh local references
            convs = _fetch_all_conversations(s_ts, u_ts)
    activity_total = len(convs)

    out = []
    errors = 0

    def _fetch_full(c):
        try:
            next_url = f"https://graph.facebook.com/v20.0/{c['id']}/messages"
            params = {"limit": 100, "fields": "created_time,message,from", "access_token": token}
            customer_msgs = []
            oldest_ts = None
            last_ts = None
            last_from = None
            for _ in range(20):
                r = _r.get(next_url, params=params, timeout=15)
                if r.status_code != 200:
                    return None
                data = r.json()
                msgs = data.get("data", [])
                if not msgs:
                    break
                for m in msgs:
                    ts_str = m.get("created_time", "")
                    try:
                        ts_dt = datetime.strptime(ts_str.split("+")[0], "%Y-%m-%dT%H:%M:%S")
                        ts = int(ts_dt.replace(tzinfo=timezone.utc).timestamp())
                    except Exception:
                        continue
                    fid = (m.get("from") or {}).get("id", "")
                    text = m.get("message", "") or ""
                    if oldest_ts is None or ts < oldest_ts:
                        oldest_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
                        last_from = fid
                    if fid and str(fid) != str(page_id) and text:
                        customer_msgs.append({"ts": ts, "text": text})
                # Short-circuit if conversation predates range
                if s_ts and oldest_ts and oldest_ts < s_ts:
                    return None  # signal: skip (continuation, not new)
                next_url = (data.get("paging") or {}).get("next")
                if not next_url:
                    break
                params = {}
            customer_msgs.sort(key=lambda x: x["ts"])
            return {
                "id": c["id"],
                "message_count": c.get("message_count", 0),
                "first_message_ts": oldest_ts,
                "last_msg_ts": last_ts,
                "last_msg_from_customer": last_from and str(last_from) != str(page_id),
                "customer_messages": customer_msgs,
            }
        except Exception:
            return "error"

    from concurrent.futures import ThreadPoolExecutor
    # 25 workers — FB Graph API tolerates this for /conversations/messages reads;
    # cuts wall time from ~30s → ~5s on a 100-conv range.
    with ThreadPoolExecutor(max_workers=25) as pool:
        for result in pool.map(_fetch_full, convs):
            if result == "error":
                errors += 1
            elif result is not None:
                # Only count if first_message in range (genuinely NEW conversation)
                if result.get("first_message_ts") and s_ts <= result["first_message_ts"] <= u_ts:
                    out.append(result)

    payload = {
        "conversations": out,
        "activity_total": activity_total,
        "fetched_total": len(out),
        "errors": errors,
        "cached_at": now,
        "cache_age_sec": 0,
        "cache_hit": False,
    }
    # Write to cache only on success (avoid caching errored 0-result responses)
    if activity_total > 0 or errors == 0:
        _CORPUS_CACHE[cache_key] = payload
        # Trim cache size — keep at most 16 most recent ranges
        if len(_CORPUS_CACHE) > 16:
            oldest_key = min(_CORPUS_CACHE, key=lambda k: _CORPUS_CACHE[k]["cached_at"])
            _CORPUS_CACHE.pop(oldest_key, None)
    return payload


@app.get("/api/everly/admin/silence-trigger")
def admin_silence_trigger(
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
):
    """Real Silence Trigger analysis — categorizes ghosted customers by likely reason.
    Method: for each NEW conversation in range that's 'ghosted' (3-15 messages, last
    from customer, customer didn't reply within 24h after admin's last reply), inspect
    the LAST 3 customer messages and classify with keyword matcher.
    """
    today = today_bkk()
    s = date.fromisoformat(since) if since else (today - timedelta(days=7))
    u = date.fromisoformat(until) if until else today
    s_dt = datetime.combine(s, datetime.min.time(), tzinfo=BANGKOK_TZ)
    u_dt = datetime.combine(u, datetime.max.time(), tzinfo=BANGKOK_TZ)
    s_ts = int(s_dt.timestamp())
    u_ts = int(u_dt.timestamp())

    corpus = _build_admin_message_corpus(s_ts, u_ts)
    convs = corpus["conversations"]

    # Identify ghosted conversations: 3-15 total messages, last is from customer
    # OR last admin reply was >24h ago and customer hasn't responded since
    now_ts = int(datetime.now(timezone.utc).timestamp())
    ghosted = []
    for c in convs:
        mc = c.get("message_count", 0)
        if not (3 <= mc <= 15):
            continue
        cms = c.get("customer_messages", [])
        if not cms:
            continue
        last_ts = c.get("last_msg_ts") or 0
        # Silent for 24+ hours
        if (now_ts - last_ts) >= 86400:
            ghosted.append(c)

    # Classify each ghosted conv by the LAST 3 customer messages combined
    counts = {}
    samples = {}  # category -> list of recent message snippets (for tooltip)
    for c in ghosted:
        last_3 = c["customer_messages"][-3:]
        text = " ".join(m["text"] for m in last_3)
        cat = _classify_silence(text)
        counts[cat] = counts.get(cat, 0) + 1
        samples.setdefault(cat, []).append(last_3[-1]["text"][:80] if last_3 else "")

    total = sum(counts.values())
    # Build all categories (include 0-counts for stable rendering order)
    all_cats = [lbl for lbl, _ in _SILENCE_CATEGORIES] + [_SILENCE_OTHER_LABEL]
    rows = []
    for cat in all_cats:
        c = counts.get(cat, 0)
        rows.append({
            "label": cat,
            "count": c,
            "pct": round(c / total * 100, 1) if total else 0,
            "samples": samples.get(cat, [])[:3],
        })
    rows.sort(key=lambda r: -r["count"])

    return {
        "since": s.isoformat(),
        "until": u.isoformat(),
        "total_ghosted": total,
        "categories": rows,
        "data_source": "FB Pages Conversations API",
        "cache_age_sec": corpus.get("cache_age_sec", 0),
        "cache_hit": corpus.get("cache_hit", False),
        "debug": {
            "activity_total": corpus["activity_total"],
            "fetched_total": corpus["fetched_total"],
            "errors": corpus["errors"],
            "ghosted_total": len(ghosted),
        },
        "fetched_at": now_bkk().isoformat(),
    }


# ── Live stats — Tier 2 polling endpoint for the header ticker ──
# Aggregates the most important "right-now" numbers into ONE call so the dashboard
# can poll every 30 seconds without hammering the FB API with multiple requests.
# Heavily cached (15 seconds) because three of the four numbers come from a
# corpus build that's already cached.
_LIVE_STATS_CACHE: dict = {}
_LIVE_STATS_TTL = 20  # short cache — header should feel "live"


@app.get("/api/everly/admin/live-stats")
def admin_live_stats():
    """Real-time aggregate for the live ticker bar:
      - today_inbox_count: ลูกค้าใหม่ที่ทักวันนี้ (since midnight BKK)
      - waiting_count: ลูกค้าที่รอ admin ตอบเกิน 5 นาที
      - longest_wait_min: คนรอนานสุดในนาที
      - inbox_queue: list of {sender_hint, wait_min, last_text} (top 5 longest waits)
      - last_message_ts: timestamp ของข้อความล่าสุดที่เข้ามา
      - server_now: unix ts ของ server (เพื่อ sync client-side clock)
    """
    now_ts = int(time.time())
    cached = _LIVE_STATS_CACHE.get("v1")
    if cached and (now_ts - cached["_cached_at"]) < _LIVE_STATS_TTL:
        out = {k: v for k, v in cached.items() if k != "_cached_at"}
        out["cache_age_sec"] = now_ts - cached["_cached_at"]
        out["cache_hit"] = True
        return out

    today = today_bkk()
    s_dt = datetime.combine(today, datetime.min.time(), tzinfo=BANGKOK_TZ)
    u_dt = datetime.combine(today, datetime.max.time(), tzinfo=BANGKOK_TZ)
    s_ts = int(s_dt.timestamp())
    u_ts = int(u_dt.timestamp())

    corpus = _build_admin_message_corpus(s_ts, u_ts)
    convs = corpus["conversations"]

    # NEW customer conversations today (first message in range)
    new_today = [c for c in convs
                 if c.get("first_message_ts") and s_ts <= c["first_message_ts"] <= u_ts]

    # Waiting queue: last message from customer AND >5 min ago (still waiting for admin)
    queue = []
    for c in convs:
        if not c.get("last_msg_from_customer") or not c.get("last_msg_ts"):
            continue
        wait_sec = now_ts - int(c["last_msg_ts"])
        if wait_sec < 300:  # less than 5 min — not "waiting" yet, ignore
            continue
        last_text = ""
        for m in reversed(c.get("customer_messages", [])):
            if m.get("text"):
                last_text = m["text"][:80]
                break
        queue.append({
            "wait_min": round(wait_sec / 60, 1),
            "wait_sec": wait_sec,
            "last_text": last_text,
            "message_count": c.get("message_count", 0),
            "conv_id": c.get("id", ""),
        })
    queue.sort(key=lambda x: -x["wait_sec"])

    # Last message timestamp across all conversations (for "เพิ่งมีคนทักเมื่อ X นาทีที่แล้ว")
    all_last_ts = [c.get("last_msg_ts") for c in convs if c.get("last_msg_ts")]
    last_message_ts = max(all_last_ts) if all_last_ts else None
    seconds_since_last = (now_ts - last_message_ts) if last_message_ts else None

    payload = {
        "today_inbox_count": len(new_today),
        "waiting_count": len(queue),
        "longest_wait_min": queue[0]["wait_min"] if queue else 0,
        "inbox_queue": queue[:8],  # top 8 most overdue
        "last_message_ts": last_message_ts,
        "seconds_since_last_message": seconds_since_last,
        "server_now": now_ts,
        "data_source": "FB Pages Conversations API",
        "cache_hit": False,
        "cache_age_sec": 0,
    }
    _LIVE_STATS_CACHE["v1"] = {**payload, "_cached_at": now_ts}
    return payload


@app.get("/api/everly/admin/faq")
def admin_faq(
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
):
    """Real FAQ analysis — extracts customer questions in range and groups by topic.
    Method: collect every customer message that looks like a question, classify each
    by topic (keyword match), return top 10 + counts.
    """
    today = today_bkk()
    s = date.fromisoformat(since) if since else (today - timedelta(days=7))
    u = date.fromisoformat(until) if until else today
    s_dt = datetime.combine(s, datetime.min.time(), tzinfo=BANGKOK_TZ)
    u_dt = datetime.combine(u, datetime.max.time(), tzinfo=BANGKOK_TZ)
    s_ts = int(s_dt.timestamp())
    u_ts = int(u_dt.timestamp())

    corpus = _build_admin_message_corpus(s_ts, u_ts)

    counts = {}
    examples = {}  # topic -> list of representative questions
    total_questions = 0
    total_messages = 0
    for c in corpus["conversations"]:
        for m in c.get("customer_messages", []):
            total_messages += 1
            topic = _classify_faq(m["text"])
            if topic is None:
                continue
            total_questions += 1
            counts[topic] = counts.get(topic, 0) + 1
            if topic not in examples:
                examples[topic] = []
            if len(examples[topic]) < 3 and m["text"][:80] not in examples[topic]:
                examples[topic].append(m["text"][:80])

    rows = [
        {
            "topic": topic,
            "count": c,
            "pct": round(c / total_questions * 100, 1) if total_questions else 0,
            "examples": examples.get(topic, []),
        }
        for topic, c in counts.items()
    ]
    rows.sort(key=lambda r: -r["count"])
    rows = rows[:12]  # top 12

    return {
        "since": s.isoformat(),
        "until": u.isoformat(),
        "total_messages": total_messages,
        "total_questions": total_questions,
        "topics": rows,
        "data_source": "FB Pages Conversations API",
        "cache_age_sec": corpus.get("cache_age_sec", 0),
        "cache_hit": corpus.get("cache_hit", False),
        "debug": {
            "activity_total": corpus["activity_total"],
            "fetched_total": corpus["fetched_total"],
            "errors": corpus["errors"],
        },
        "fetched_at": now_bkk().isoformat(),
    }


@app.get("/api/everly/keepalive")
def keepalive():
    """Lightweight ping that:
      1. Confirms the Render service is awake
      2. AUTO-TRIGGERS daily LINE in the 00:00-08:59 BKK window if not sent
         — this gives LINE several chances to go out at midnight,
         without touching Meta API on every ping.
    """
    # Auto-LINE check: send the completed previous-day report at midnight BKK.
    line_status = "not_triggered"
    line_reason = ""
    try:
        now = now_bkk()
        # Trigger window: 00:00 BKK → 08:59 BKK.
        # GitHub schedule delays are common, so delayed early-morning runs
        # should still deliver the previous complete day's report.
        within_send_window = _within_auto_send_window(now)
        if within_send_window:
            target_date = _default_report_date()
            with SEND_DAILY_LINE_LOCK:
                if not _already_sent(target_date):
                    # Inline call — avoid HTTP round-trip
                    has_token = bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
                    has_group = bool(os.getenv("LINE_GROUP_ID_EVERLY") or os.getenv("LINE_GROUP_ID"))
                    if has_token and has_group:
                        try:
                            text = _build_daily_text(target_date)
                            from lib.notify import send_line_summary
                            if send_line_summary(text):
                                _mark_sent(target_date, text)
                                line_status = "sent"
                                line_reason = f"auto-triggered from keepalive · date={target_date.isoformat()}"
                            else:
                                line_status = "send_failed"
                        except Exception as e:
                            line_status = "build_failed"
                            line_reason = str(e)[:100]
                    else:
                        line_status = "line_not_configured"
                else:
                    line_status = "already_sent_today"
        else:
            line_status = "outside_window"
            line_reason = f"hour={now.hour} min={now.minute} · window: 00:00-08:59"
    except Exception as e:
        line_status = "error"
        line_reason = str(e)[:100]

    return {
        "ok": True,
        "now_bkk": now_bkk().isoformat(),
        "cached_keys": len(_CACHE),
        "line_auto_send": line_status,
        "line_reason": line_reason,
        "message": "Render awake + auto-LINE checked",
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
    """Push dashboard-provided report text to the Everly LINE group."""
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    has_token = bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
    has_group = bool(os.getenv("LINE_GROUP_ID_EVERLY") or os.getenv("LINE_GROUP_ID"))
    if not (has_token and has_group):
        raise HTTPException(503, "LINE not configured (set LINE_CHANNEL_ACCESS_TOKEN + LINE_GROUP_ID_EVERLY)")

    from lib.notify import send_line_summary
    ok = send_line_summary(text)
    if not ok:
        raise HTTPException(502, "LINE push failed (check server logs)")
    return {"ok": True, "sent_at": now_bkk().isoformat()}


THAI_MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
               'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']


def _thai_date(d: date) -> str:
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year}"


def _thai_range(d1: date, d2: date) -> str:
    if d1.year == d2.year and d1.month == d2.month:
        return f"{d1.day}-{d2.day} {THAI_MONTHS[d1.month - 1]} {d1.year}"
    if d1.year == d2.year:
        return (f"{d1.day} {THAI_MONTHS[d1.month - 1]} - "
                f"{d2.day} {THAI_MONTHS[d2.month - 1]} {d1.year}")
    return (f"{d1.day} {THAI_MONTHS[d1.month - 1]} {d1.year} - "
            f"{d2.day} {THAI_MONTHS[d2.month - 1]} {d2.year}")


def _fmt_pl(profit: float) -> str:
    if profit < 0:
        return f"-฿{abs(round(profit)):,}"
    if profit > 0:
        return f"+฿{round(profit):,}"
    return "฿0"


def _fmt_money(v: float) -> str:
    return f"฿{round(v):,}"


def _daily_recommendation_lines(ads: list[dict]) -> list[str]:
    """Short, rule-based recommendations for LINE. Never invents missing data."""
    if not ads:
        return ["คำแนะนำ: ยังประเมินแคมเปญไม่ได้ เพราะไม่มี Top Ads data ในรอบนี้"]

    lines: list[str] = []

    scale = next(
        (a for a in ads if a.get("spent", 0) >= 500 and a.get("result", 0) >= 3 and a.get("roas", 0) >= 8),
        None,
    )
    if scale:
        lines.append(
            "เพิ่มงบ\n"
            f"- แคมเปญ: {scale['campaign']}\n"
            f"- เหตุผล: MTD ROAS {scale['roas']:.2f}x / {scale['result']} คนทัก"
        )

    test = next(
        (a for a in ads if a.get("conversion", 0) > 0 and (a.get("spent", 0) < 500 or a.get("result", 0) <= 2)),
        None,
    )
    if test and test is not scale:
        lines.append(
            "เปิดเทสต์ต่อ\n"
            f"- แคมเปญ: {test['campaign']}\n"
            f"- เหตุผล: MTD ROAS {test['roas']:.2f}x แต่ sample ยังน้อย"
        )

    watch = next(
        (a for a in sorted(ads, key=lambda x: x.get("spent", 0), reverse=True)
         if a.get("spent", 0) >= 1000 and a.get("result", 0) > 0 and a.get("conversion", 0) == 0),
        None,
    )
    if watch:
        lines.append(
            "เช็กด่วน\n"
            f"- แคมเปญ: {watch['campaign']}\n"
            f"- เหตุผล: MTD คนทัก {watch['result']} แต่ยอดขายในระบบ {_fmt_money(watch['conversion'])}"
        )

    expensive = next(
        (a for a in sorted(ads, key=lambda x: x.get("cost_per_result", 0), reverse=True)
         if a.get("result", 0) > 0 and a.get("cost_per_result", 0) >= 200 and a.get("conversion", 0) == 0),
        None,
    )
    if expensive:
        lines.append(
            "เฝ้าระวัง/แก้ creative\n"
            f"- แคมเปญ: {expensive['campaign']}\n"
            f"- เหตุผล: MTD ค่าทัก {_fmt_money(expensive['cost_per_result'])}"
        )

    pause_names = [
        a["campaign"] for a in ads
        if a.get("spent", 0) >= 300 and a.get("result", 0) == 0 and a.get("conversion", 0) == 0
    ][:2]
    if pause_names:
        lines.append(
            "ควรปิด/พัก\n"
            f"- แคมเปญ: {', '.join(pause_names)}\n"
            "- เหตุผล: MTD ใช้เงินแล้วไม่เกิดคนทัก/ยอดขาย"
        )

    return lines or ["คำแนะนำ: ยังไม่มีตัวที่ชัดพอให้เพิ่มงบหรือปิด ให้เก็บข้อมูลต่ออีก 24 ชม."]


def _build_daily_text(target_d: date) -> str:
    """Build the doctor-friendly daily report text exactly like dashboard."""
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
    L.append(f"วันที่รายงาน: {_thai_date(target_d)}")
    L.append(f"เกณฑ์วัดผลแอด: MTD {_thai_range(month_start, target_d)}")
    L.append("")
    L.append("============")
    L.append("1) ลิงก์วิเคราะห์")
    L.append("https://everly-clinic.onrender.com/analysis")
    L.append("")
    L.append("============")
    L.append("2) วันนี้")
    L.append(f"- ใช้เงิน: ฿{sel_spend:,.2f}")
    L.append(f"- คนทัก: {sel_inbox} คน")
    L.append(f"- เฉลี่ยต่อคนทัก: ฿{sel_cpr:,}" if sel_inbox else "- เฉลี่ยต่อคนทัก: —")
    L.append(f"- ยอดขาย: ฿{round(sel_conv):,}")
    L.append(f"- กำไร/ขาดทุน: {_fmt_pl(day_profit)}")
    L.append("")
    L.append("============")
    L.append("3) สะสมเดือนนี้")
    L.append(f"- ช่วงข้อมูล: {_thai_range(month_start, target_d)}")
    L.append(f"- ใช้เงินรวม: ฿{round(mtd_spend):,}")
    L.append(f"- เฉลี่ยต่อวัน: ฿{avg_daily:,}")
    L.append(f"- คนทักรวม: {mtd_inbox} คน")
    L.append(f"- เฉลี่ยต่อคนทัก: ฿{mtd_cpr:,}" if mtd_inbox else "- เฉลี่ยต่อคนทัก: —")
    L.append(f"- ยอดขาย: ฿{round(mtd_conv):,}")
    L.append(f"- กำไร/ขาดทุน: {_fmt_pl(mtd_profit)}")
    L.append(f"- ROAS เดือนนี้: {(mtd_conv / mtd_spend if mtd_spend else 0):.2f}x")
    L.append("")
    L.append("============")
    L.append("4) Action แนะนำ")
    try:
        top_ads = everly_top_ads_range(
            since=month_start.isoformat(),
            until=target_d.isoformat(),
            limit=20,
        ).get("ads", [])
        recommendations = _daily_recommendation_lines(top_ads)
        for i, item in enumerate(recommendations):
            if i:
                L.append("")
            L.append(item)
    except Exception as e:
        L.append(f"คำแนะนำ: ยังประเมิน Top Ads ไม่ได้จาก API รอบนี้ ({str(e)[:80]})")
    L.append("")
    L.append("============")
    L.append("5) หมายเหตุ")
    L.append("- คำแนะนำวัดจากข้อมูล MTD ตั้งแต่วันที่ 1 ถึงวันที่รายงาน")
    L.append("- ถ้ายอดขายจริงมีแต่ระบบไม่จับ ให้เช็ก tracking/การบันทึกยอดขายก่อนตัดสินใจปิดแอด")
    L.append("============")
    return "\n".join(L)


@app.post("/api/everly/send-daily-line")
def send_daily_line(
    request: Request,
    target: Optional[str] = Query(None),
    force: bool = Query(False, description="Force resend even if this report date was already sent."),
    secret: Optional[str] = Query(None, description="Optional CRON_SECRET fallback for simple cron services."),
):
    """Build daily report and push to LINE.
    Called by GitHub Actions at 00:00 BKK (17:00 UTC) every day.
    `target` defaults to the previous complete day around midnight BKK.
    Token-protected via X-Cron-Secret header if CRON_SECRET env var is set.
    """
    # Optional hardening: if CRON_SECRET is set on Render, only scheduled jobs
    # that know the secret can trigger LINE sends.
    expected_secret = os.getenv("CRON_SECRET", "")
    if expected_secret:
        supplied_secret = request.headers.get("x-cron-secret") or secret or ""
        if supplied_secret != expected_secret:
            raise HTTPException(401, "Invalid cron secret")

    if not force and target is None and not _within_auto_send_window():
        now = now_bkk()
        return {
            "ok": True,
            "skipped": True,
            "reason": "outside_auto_send_window",
            "now_bkk": now.isoformat(),
            "window": "00:00-08:59 BKK",
        }

    d = date.fromisoformat(target) if target else _default_report_date()

    with SEND_DAILY_LINE_LOCK:
        existing = _already_sent(d)
        if existing and not force:
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_sent",
                "date": d.isoformat(),
                "first_sent_at": existing.get("sent_at"),
                "preview": existing.get("preview", ""),
            }

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
        _mark_sent(d, text)
        return {
            "ok": True,
            "skipped": False,
            "date": d.isoformat(),
            "sent_at": now_bkk().isoformat(),
            "preview": text[:200] + ("..." if len(text) > 200 else ""),
        }


@app.get("/api/everly/daily-text")
def daily_text(target: Optional[str] = Query(None)):
    """Preview the daily report text without sending. Useful for debugging."""
    d = date.fromisoformat(target) if target else _default_report_date()
    try:
        return {"date": d.isoformat(), "text": _build_daily_text(d)}
    except Exception as e:
        raise HTTPException(502, f"Failed to build report: {e}")


@app.get("/api/everly/send-state")
def send_state():
    """Small diagnostic endpoint showing which report dates were sent."""
    state = _read_sent_state()
    return {
        "ok": True,
        "state_file": str(SENT_STATE_FILE),
        "sent_dates": sorted(state.keys()),
        "latest": dict(sorted(state.items())[-5:]),
    }


# ── Dashboard routes (HTML at same origin as API) ─────────────
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.head("/")
def root_dashboard_head():
    return Response(status_code=200, media_type="text/html", headers=NO_CACHE_HEADERS)


@app.get("/")
def root_dashboard():
    return FileResponse(DASHBOARD_FILE, headers=NO_CACHE_HEADERS)


@app.head("/dashboard")
def dashboard_alias_head():
    return Response(status_code=200, media_type="text/html", headers=NO_CACHE_HEADERS)


@app.get("/dashboard")
def dashboard_alias():
    return FileResponse(DASHBOARD_FILE, headers=NO_CACHE_HEADERS)


@app.head("/analysis")
def analysis_alias_head():
    return Response(headers=NO_CACHE_HEADERS)


@app.get("/analysis")
def analysis_alias():
    return FileResponse(DASHBOARD_FILE, headers=NO_CACHE_HEADERS)


if __name__ == "__main__":
    import uvicorn
    # Render injects PORT env var; default to 8000 for local
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
