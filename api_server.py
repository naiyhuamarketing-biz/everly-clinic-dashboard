import json
import os
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")

BRAND_NAME = "TUBA"
AD_ACCOUNT_ID = "1979003202592442"
AD_ACCOUNT_ENV = "FB_ACCOUNT_TUBA"
LINE_GROUP_ENV = "LINE_GROUP_ID_TUBA"
BKK = timezone(timedelta(hours=7))
SENT_STATE_FILE = Path(os.getenv("SENT_STATE_FILE", "/tmp/tuba-line-sent.json"))

app = FastAPI(title="TUBA Data API", version="1.0.0")
if (ROOT / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(ROOT / "assets")), name="assets")


def now_bkk() -> datetime:
    return datetime.now(BKK)


def today_bkk() -> date:
    return now_bkk().date()


def parse_date(value: Optional[str], fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return fallback


def date_range(since: date, until: date) -> List[date]:
    if until < since:
        since, until = until, since
    days: List[date] = []
    cursor = since
    while cursor <= until:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def mock_mode() -> bool:
    return os.getenv("MOCK_MODE", "").lower() in {"1", "true", "yes", "on"} or not bool(os.getenv("FB_ACCESS_TOKEN"))


def line_group_id() -> str:
    return os.getenv(LINE_GROUP_ENV) or os.getenv("LINE_GROUP_ID") or ""


def line_configured() -> bool:
    return bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN") and line_group_id())


def action_count(actions: Any) -> int:
    if not isinstance(actions, list):
        return 0
    keys = {
        "onsite_conversion.messaging_conversation_started_7d",
        "onsite_conversion.messaging_first_reply",
        "messaging_conversation_started_7d",
        "lead",
    }
    total = 0
    for item in actions:
        if not isinstance(item, dict):
            continue
        if item.get("action_type") in keys:
            try:
                total += int(float(item.get("value", 0)))
            except (TypeError, ValueError):
                pass
    return total


def compute_totals(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    spend = sum(float(r.get("spend", 0) or 0) for r in rows)
    impressions = sum(int(float(r.get("impressions", 0) or 0)) for r in rows)
    reach = sum(int(float(r.get("reach", 0) or 0)) for r in rows)
    result = sum(int(float(r.get("result", 0) or 0)) for r in rows)
    return {
        "spend": round(spend, 2),
        "impressions": impressions,
        "reach": reach,
        "result": result,
        "cpm": round((spend / impressions) * 1000, 2) if impressions else 0,
        "cost_per_result": round(spend / result, 2) if result else 0,
    }


def make_mock_rows(since: date, until: date) -> Dict[str, Any]:
    campaigns = [
        "TUBA · Back to School",
        "TUBA · Reunion After Dark",
        "TUBA · Photo Booth UGC",
        "TUBA · Private Room",
        "TUBA · LINE Retargeting",
        "TUBA · Group Booking",
    ]
    days: List[Dict[str, Any]] = []
    ads: List[Dict[str, Any]] = []
    for d in date_range(since, until):
        rng = random.Random(f"tuba:{AD_ACCOUNT_ID}:{d.isoformat()}")
        spend = round(rng.uniform(800, 4200), 2)
        impressions = rng.randint(5500, 36000)
        reach = int(impressions * rng.uniform(0.46, 0.78))
        result = rng.randint(5, 58)
        campaign = campaigns[rng.randrange(len(campaigns))]
        days.append({
            "date": d.isoformat(),
            "spend": spend,
            "impressions": impressions,
            "reach": reach,
            "result": result,
            "cpm": round((spend / impressions) * 1000, 2),
            "cost_per_result": round(spend / result, 2),
        })
        for i in range(3):
            ad_spend = round(spend * rng.uniform(0.16, 0.42), 2)
            ad_result = max(1, int(result * rng.uniform(0.12, 0.44)))
            ads.append({
                "account_id": AD_ACCOUNT_ID,
                "campaign_name": campaign,
                "adset_name": f"Bangkok · Group {i + 1}",
                "ad_name": f"TUBA Creative {i + 1}",
                "spent": ad_spend,
                "impressions": int(impressions * rng.uniform(0.12, 0.4)),
                "reach": int(reach * rng.uniform(0.12, 0.4)),
                "result": ad_result,
                "cost_per_result": round(ad_spend / ad_result, 2),
            })
    ads.sort(key=lambda row: float(row.get("spent", 0)), reverse=True)
    return {"days": days, "ads": ads}


def fetch_meta_rows(since: date, until: date) -> Dict[str, Any]:
    if mock_mode():
        return make_mock_rows(since, until)
    try:
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.api import FacebookAdsApi
    except Exception as exc:
        fallback = make_mock_rows(since, until)
        fallback["error"] = f"facebook_business import failed: {exc}"
        return fallback

    token = os.getenv("FB_ACCESS_TOKEN")
    FacebookAdsApi.init(os.getenv("FB_APP_ID"), os.getenv("FB_APP_SECRET"), token)
    account = AdAccount(f"act_{AD_ACCOUNT_ID}")
    params = {
        "time_range": {"since": since.isoformat(), "until": until.isoformat()},
        "time_increment": 1,
        "level": "ad",
        "limit": 500,
    }
    fields = [
        "date_start",
        "campaign_name",
        "adset_name",
        "ad_name",
        "spend",
        "impressions",
        "reach",
        "actions",
    ]
    per_day: Dict[str, Dict[str, Any]] = {}
    ads: List[Dict[str, Any]] = []
    for item in account.get_insights(fields=fields, params=params):
        row = dict(item)
        d = row.get("date_start", since.isoformat())
        spend = float(row.get("spend", 0) or 0)
        impressions = int(float(row.get("impressions", 0) or 0))
        reach = int(float(row.get("reach", 0) or 0))
        result = action_count(row.get("actions"))
        bucket = per_day.setdefault(d, {"date": d, "spend": 0.0, "impressions": 0, "reach": 0, "result": 0})
        bucket["spend"] += spend
        bucket["impressions"] += impressions
        bucket["reach"] += reach
        bucket["result"] += result
        ads.append({
            "account_id": AD_ACCOUNT_ID,
            "campaign_name": row.get("campaign_name") or "TUBA Campaign",
            "adset_name": row.get("adset_name") or "TUBA Ad Set",
            "ad_name": row.get("ad_name") or "TUBA Ad",
            "spent": round(spend, 2),
            "impressions": impressions,
            "reach": reach,
            "result": result,
            "cost_per_result": round(spend / result, 2) if result else 0,
        })
    days = []
    for d in date_range(since, until):
        bucket = per_day.get(d.isoformat(), {"date": d.isoformat(), "spend": 0.0, "impressions": 0, "reach": 0, "result": 0})
        bucket["spend"] = round(float(bucket["spend"]), 2)
        bucket["cpm"] = round((bucket["spend"] / bucket["impressions"]) * 1000, 2) if bucket["impressions"] else 0
        bucket["cost_per_result"] = round(bucket["spend"] / bucket["result"], 2) if bucket["result"] else 0
        days.append(bucket)
    ads.sort(key=lambda row: float(row.get("spent", 0)), reverse=True)
    return {"days": days, "ads": ads}


def summary_payload(since: date, until: date) -> Dict[str, Any]:
    data = fetch_meta_rows(since, until)
    totals = compute_totals(data.get("days", []))
    return {
        "ok": True,
        "brand": BRAND_NAME,
        "account_id": AD_ACCOUNT_ID,
        "range": {"since": since.isoformat(), "until": until.isoformat()},
        "mock_mode": mock_mode(),
        "totals": totals,
        "days": data.get("days", []),
        "top_ads": data.get("ads", [])[:10],
        "error": data.get("error"),
    }


def daily_text(target: date) -> str:
    data = summary_payload(target, target)
    totals = data["totals"]
    top_ads = data.get("top_ads", [])[:3]
    lines = [
        "TUBA — DAILY REPORT",
        "",
        f"Date: {target.isoformat()} (Bangkok)",
        f"Account: {AD_ACCOUNT_ID}",
        "",
        "Performance Overview",
        f"Spend: ฿{totals['spend']:,.2f}",
        f"Inbox / Leads: {totals['result']:,}",
        f"Cost per Result: ฿{totals['cost_per_result']:,.2f}",
        f"Reach: {totals['reach']:,}",
        f"Impressions: {totals['impressions']:,}",
        f"CPM: ฿{totals['cpm']:,.2f}",
        "",
        "Top Highlights",
    ]
    if top_ads:
        for idx, ad in enumerate(top_ads, start=1):
            lines.append(f"{idx}. {ad.get('ad_name', 'TUBA Ad')} — ฿{float(ad.get('spent', 0)):,.2f} / {int(ad.get('result', 0)):,} results")
    else:
        lines.append("วันนี้ยังไม่มีข้อมูลโฆษณา")
    lines.extend(["", "Status", "ระบบล็อกเฉพาะแบรนด์ TUBA เท่านั้น"])
    return "\n".join(lines)


def send_line_message(text: str) -> Dict[str, Any]:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    group = line_group_id()
    if not token or not group:
        return {"ok": False, "configured": False, "error": f"Missing LINE_CHANNEL_ACCESS_TOKEN or {LINE_GROUP_ENV}"}
    res = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"to": group, "messages": [{"type": "text", "text": text}]},
        timeout=20,
    )
    return {"ok": res.ok, "status_code": res.status_code, "response": res.text[:500], "configured": True}


def read_send_state() -> Dict[str, Any]:
    if not SENT_STATE_FILE.exists():
        return {}
    try:
        return json.loads(SENT_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_send_state(state: Dict[str, Any]) -> None:
    SENT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/")
@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(ROOT / "dashboard.html")


@app.get("/api/health")
@app.get("/api/tuba/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "brand": BRAND_NAME,
        "account_id": AD_ACCOUNT_ID,
        "expected_env": AD_ACCOUNT_ENV,
        "mock_mode": mock_mode(),
        "line_configured": line_configured(),
        "now_bangkok": now_bkk().isoformat(),
    }


@app.get("/api/tuba/summary")
def tuba_summary(since: Optional[str] = Query(None), until: Optional[str] = Query(None), refresh: bool = Query(False)) -> Dict[str, Any]:
    s = parse_date(since, today_bkk())
    u = parse_date(until, s)
    return summary_payload(s, u)


@app.get("/api/tuba/day")
def tuba_day(target: Optional[str] = Query(None)) -> Dict[str, Any]:
    d = parse_date(target, today_bkk())
    return summary_payload(d, d)


@app.get("/api/tuba/top-ads")
def tuba_top_ads(target: Optional[str] = Query(None), limit: int = Query(10, ge=1, le=50)) -> Dict[str, Any]:
    d = parse_date(target, today_bkk())
    data = summary_payload(d, d)
    return {"ok": True, "brand": BRAND_NAME, "account_id": AD_ACCOUNT_ID, "ads": data.get("top_ads", [])[:limit]}


@app.get("/api/tuba/top-ads-range")
def tuba_top_ads_range(since: Optional[str] = Query(None), until: Optional[str] = Query(None), limit: int = Query(10, ge=1, le=50)) -> Dict[str, Any]:
    s = parse_date(since, today_bkk())
    u = parse_date(until, s)
    data = summary_payload(s, u)
    return {"ok": True, "brand": BRAND_NAME, "account_id": AD_ACCOUNT_ID, "range": data["range"], "ads": data.get("top_ads", [])[:limit]}


@app.get("/api/tuba/report")
@app.get("/api/tuba/daily-text")
def tuba_daily_text(target: Optional[str] = Query(None)) -> Dict[str, Any]:
    d = parse_date(target, today_bkk())
    return {"ok": True, "brand": BRAND_NAME, "account_id": AD_ACCOUNT_ID, "target": d.isoformat(), "text": daily_text(d)}


@app.get("/api/tuba/send-state")
def tuba_send_state() -> Dict[str, Any]:
    return {"ok": True, "brand": BRAND_NAME, "state_file": str(SENT_STATE_FILE), "state": read_send_state()}


@app.post("/api/tuba/send-daily-line")
def send_daily_line(request: Request, body: Optional[Dict[str, Any]] = Body(default=None), target: Optional[str] = Query(None), force: bool = Query(False)) -> Dict[str, Any]:
    payload = body or {}
    force = bool(force or payload.get("force"))
    d = parse_date(target or payload.get("target"), today_bkk())
    now = now_bkk()
    if not force and now.hour != 0:
        return {"ok": True, "skipped": True, "reason": "outside_auto_send_window", "brand": BRAND_NAME, "now_bangkok": now.isoformat()}
    state = read_send_state()
    key = d.isoformat()
    if not force and state.get(key, {}).get("sent"):
        return {"ok": True, "skipped": True, "reason": "already_sent", "brand": BRAND_NAME, "target": key, "state": state.get(key)}
    result = send_line_message(daily_text(d))
    if result.get("ok"):
        state[key] = {"sent": True, "sent_at_bangkok": now.isoformat(), "account_id": AD_ACCOUNT_ID}
        write_send_state(state)
    return {"ok": bool(result.get("ok")), "brand": BRAND_NAME, "target": key, "line": result}


@app.get("/api/tuba/keepalive")
def keepalive() -> Dict[str, Any]:
    data = summary_payload(today_bkk(), today_bkk())
    return {"ok": True, "brand": BRAND_NAME, "account_id": AD_ACCOUNT_ID, "mock_mode": mock_mode(), "totals": data.get("totals", {})}


@app.get("/api/tuba/token-info")
def token_info() -> Dict[str, Any]:
    token = os.getenv("FB_ACCESS_TOKEN", "")
    app_token = f"{os.getenv('FB_APP_ID', '')}|{os.getenv('FB_APP_SECRET', '')}"
    if not token or not os.getenv("FB_APP_ID") or not os.getenv("FB_APP_SECRET"):
        return {"ok": True, "brand": BRAND_NAME, "configured": False, "is_valid": False, "days_left": -1, "note": "Meta token/app secret not configured"}
    try:
        res = requests.get("https://graph.facebook.com/debug_token", params={"input_token": token, "access_token": app_token}, timeout=20)
        data = res.json().get("data", {})
        expires_at = data.get("expires_at")
        days_left = -1
        if expires_at:
            days_left = int((datetime.fromtimestamp(int(expires_at), tz=timezone.utc) - datetime.now(timezone.utc)).total_seconds() // 86400)
        return {"ok": res.ok, "brand": BRAND_NAME, "configured": True, "is_valid": bool(data.get("is_valid")), "days_left": days_left, "data": data}
    except Exception as exc:
        return {"ok": False, "brand": BRAND_NAME, "configured": True, "is_valid": False, "days_left": -1, "error": str(exc)}


@app.get("/api/line/status")
def line_status() -> Dict[str, Any]:
    group = line_group_id()
    return {
        "ok": True,
        "brand": BRAND_NAME,
        "configured": line_configured(),
        "line_group_env": LINE_GROUP_ENV,
        "group_id_present": bool(group),
        "token_present": bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN")),
    }


@app.post("/api/line/send")
def line_send(body: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    text = str(body.get("text") or "").strip()
    if not text:
        return {"ok": False, "brand": BRAND_NAME, "error": "text is required"}
    return {"brand": BRAND_NAME, **send_line_message(text)}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def unknown_api(path: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"ok": False, "brand": BRAND_NAME, "detail": "This dashboard is TUBA-only. Use /api/tuba/* endpoints.", "path": f"/api/{path}"})


@app.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/"):
        return JSONResponse(status_code=404, content={"ok": False, "brand": BRAND_NAME, "detail": "Unknown API path"})
    return FileResponse(ROOT / "dashboard.html")
