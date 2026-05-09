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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Body, Request
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
ASSETS_DIR = ROOT / "assets"
SENT_STATE_FILE = Path(os.getenv("SENT_STATE_FILE", "/tmp/everly-line-sent.json"))
SUMMARY_SNAPSHOT_DIR = Path(os.getenv("SUMMARY_SNAPSHOT_DIR", "/tmp/everly-summary-snapshots"))

# Mount /assets so brand logos (assets/logos/everly.png etc.) are served
# directly by FastAPI — used by <img src="/assets/logos/..."> in dashboard.html
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


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


def _default_report_date() -> date:
    """Pick the report date safely for scheduled jobs.

    Normal daily send runs at 23:59 BKK, so it should report today.
    If a delayed/retry job runs shortly after midnight, it should still report
    yesterday instead of accidentally sending an empty new-day report.
    """
    now = now_bkk()
    if now.hour < 1:
        return now.date() - timedelta(days=1)
    return now.date()


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

    response = {
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
    _write_summary_snapshot(s, u, response)
    return response


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


# Module-level runtime caches set by /admin/derive-page-token & /admin/bootstrap.
# Survive within the same process; Render restart reverts to env vars.
_RUNTIME_PAGE_TOKEN: Optional[str] = None
_RUNTIME_USER_TOKEN: Optional[str] = None  # bootstrap source for auto-refresh
_RUNTIME_PAGE_TOKEN_VERIFIED_AT: int = 0   # unix ts of last successful FB call


def _try_auto_refresh_page_token() -> Optional[str]:
    """If env-stored page token is broken AND we have a cached user_token,
    automatically derive a fresh page token. Used by funnel endpoints.
    Returns the new page token on success, None on failure.
    """
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
                    global _RUNTIME_PAGE_TOKEN, _RUNTIME_PAGE_TOKEN_VERIFIED_AT
                    _RUNTIME_PAGE_TOKEN = p["access_token"]
                    _RUNTIME_PAGE_TOKEN_VERIFIED_AT = int(time.time())
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
            global _RUNTIME_PAGE_TOKEN, _RUNTIME_PAGE_TOKEN_VERIFIED_AT
            _RUNTIME_PAGE_TOKEN = r.json()["access_token"]
            _RUNTIME_PAGE_TOKEN_VERIFIED_AT = int(time.time())
            return _RUNTIME_PAGE_TOKEN
    except Exception:
        pass
    return None


@app.post("/api/everly/admin/bootstrap")
def admin_bootstrap(payload: dict = Body(...)):
    """One-call setup: takes a user_token, stores in process memory,
    immediately derives & caches a page_token. Subsequent funnel calls
    will use the cached page_token; if it ever fails, /admin/funnel
    auto-refreshes from the stored user_token.

    User flow:
      POST {"user_token": "EAA..."} → server caches both, returns status
      User goes away → server keeps deriving fresh page_tokens as needed
      Token chain only breaks if user_token itself expires (no auto-refresh
      yet for user_token; that requires App Live mode or System User).
    """
    user_token = (payload.get("user_token") or "").strip()
    if not user_token:
        raise HTTPException(400, "user_token required")
    global _RUNTIME_USER_TOKEN
    _RUNTIME_USER_TOKEN = user_token
    page_token = _try_auto_refresh_page_token()
    return {
        "ok": page_token is not None,
        "user_token_cached": True,
        "page_token_derived": page_token is not None,
        "page_token_prefix": page_token[:12] if page_token else None,
        "message": "Funnel will now auto-recover from page-token failures using the cached user_token. "
                   "If user_token itself expires, dashboard will show ⚠ banner asking for refresh.",
    }


@app.get("/api/everly/admin/token-status")
def admin_token_status():
    """Health check for the token chain. Used by dashboard banner."""
    page_token, page_id = _page_credentials()
    has_user = bool(_RUNTIME_USER_TOKEN or os.getenv("FB_USER_TOKEN_NAIYHUA", ""))
    if not page_token or not page_id:
        return {"ok": False, "stage": "missing", "user_token_available": has_user}
    # Quick liveness probe
    import requests as _r
    try:
        r = _r.get(
            f"https://graph.facebook.com/v20.0/{page_id}",
            params={"access_token": page_token, "fields": "id"},
            timeout=8,
        )
        live = (r.status_code == 200) and ("id" in r.json())
    except Exception:
        live = False
    return {
        "ok": live,
        "stage": "live" if live else "expired",
        "user_token_available": has_user,
        "auto_refresh_capable": has_user,
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

    # Parallelize per-conversation message analysis (10 workers ≈ 3-4× faster)
    with ThreadPoolExecutor(max_workers=10) as pool:
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

    return {
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
        "fetched_at": now_bkk().isoformat(),
        "debug": debug_info,
    }


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
def send_daily_line(
    request: Request,
    target: Optional[str] = Query(None),
    force: bool = Query(False, description="Force resend even if this report date was already sent."),
    secret: Optional[str] = Query(None, description="Optional CRON_SECRET fallback for simple cron services."),
):
    """Build daily report and push to LINE.
    Called by GitHub Actions at 23:59 BKK (16:59 UTC) every day.
    `target` defaults to today (BKK). Token-protected via X-Cron-Secret header
    if CRON_SECRET env var is set.
    """
    # Optional hardening: if CRON_SECRET is set on Render, only scheduled jobs
    # that know the secret can trigger LINE sends.
    expected_secret = os.getenv("CRON_SECRET", "")
    if expected_secret:
        supplied_secret = request.headers.get("x-cron-secret") or secret or ""
        if supplied_secret != expected_secret:
            raise HTTPException(401, "Invalid cron secret")

    d = date.fromisoformat(target) if target else _default_report_date()

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
