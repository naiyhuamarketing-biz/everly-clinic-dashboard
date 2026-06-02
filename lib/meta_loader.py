"""Pull Everly Clinic daily metrics directly from Meta Marketing API.

ONE API call returns the full date range broken down by day (`time_increment=1`).
Returns a record-per-day shape consumed by dashboard.py.
"""
import os
from datetime import date, timedelta
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    """Read env vars first, then Streamlit secrets when running Streamlit."""
    env_value = os.getenv(key)
    if env_value:
        return env_value
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


# These are the action types Meta returns for messaging-objective ads.
# `messaging_conversation_started_7d` is what Ads Manager UI calls
# "Messaging Conversations Started".
INBOX_ACTIONS = (
    "onsite_conversion.messaging_conversation_started_7d",
)


def _init_api():
    from facebook_business.api import FacebookAdsApi
    FacebookAdsApi.init(
        app_id=_secret("FB_APP_ID") or None,
        app_secret=_secret("FB_APP_SECRET") or None,
        access_token=_secret("FB_ACCESS_TOKEN"),
    )


def fetch_daily(account_id: str, since: date, until: date) -> List[dict]:
    """Returns list of records, one per day.

    Each record:
        {
            "date": "2026-04-15",
            "month": "Apr",
            "day": 15,
            "ads": [{spent, result, impression, reach, cpm, conversion,
                     campaign, status, objective, ...}, ...]
        }

    NOTE: Meta API at account-level returns aggregates, not per-ad rows.
    To preserve the existing dashboard shape, we synthesize one "ads" entry
    per day that holds the daily totals. The "campaign" field shows which
    real campaign drove the most spend that day (fetched separately).
    """
    if not _secret("FB_ACCESS_TOKEN"):
        raise RuntimeError("FB_ACCESS_TOKEN not set")

    _init_api()
    from facebook_business.adobjects.adaccount import AdAccount

    account = AdAccount(f"act_{account_id}")
    fields = ["date_start", "spend", "impressions", "reach", "frequency",
              "ctr", "cpc", "cpm", "actions", "action_values"]
    params = {
        "time_range": {"since": since.isoformat(), "until": until.isoformat()},
        "time_increment": 1,
        "level": "account",
    }

    raw = list(account.get_insights(fields=fields, params=params))

    # Per-day "top campaign by spend" (best-effort — single batched call)
    top_camp = _top_campaign_per_day(account_id, since, until)

    out = []
    for row in raw:
        d_str = row.get("date_start")
        if not d_str:
            continue
        d = date.fromisoformat(d_str)

        spend = float(row.get("spend", 0) or 0)
        impression = int(row.get("impressions", 0) or 0)
        reach = int(row.get("reach", 0) or 0)
        frequency = float(row.get("frequency", 0) or 0)
        cpm = float(row.get("cpm", 0) or 0)
        ctr = float(row.get("ctr", 0) or 0)
        cpc = float(row.get("cpc", 0) or 0)

        # Inbox count from messaging conversations
        inbox = 0
        link_clicks = 0
        for a in row.get("actions") or []:
            t = a.get("action_type")
            if t in INBOX_ACTIONS:
                inbox += int(float(a.get("value", 0) or 0))
            elif t == "link_click":
                link_clicks += int(float(a.get("value", 0) or 0))

        # Conversion value (Pixel purchase events). Take the largest single
        # bucket to avoid double-counting across omni_* action types.
        conv_value = 0.0
        for v in row.get("action_values") or []:
            if v.get("action_type") in (
                "purchase",
                "omni_purchase",
                "offsite_conversion.fb_pixel_purchase",
                "onsite_conversion.purchase",
            ):
                conv_value = max(conv_value, float(v.get("value", 0) or 0))

        roas = (conv_value / spend) if spend else 0

        synthetic_ad = {
            "campaign": top_camp.get(d_str, "Daily Total"),
            "status": "Normal",
            "objective": "Inbox",
            "budget": 0,
            "impression": impression,
            "reach": reach,
            "frequency": round(frequency, 2),
            "cpm": round(cpm, 2),
            "ctr": round(ctr, 3),
            "cpc": round(cpc, 2),
            "link_clicks": link_clicks,
            "conversion": round(conv_value, 2),
            "roas": round(roas, 2),
            "result": inbox,
            "cost_per_result": (spend / inbox) if inbox else 0,
            "spent": round(spend, 2),
        }

        out.append({
            "date": d_str,
            "month": d.strftime("%b"),
            "day": d.day,
            "ads": [synthetic_ad],
        })

    return out


def _top_campaign_per_day(account_id: str, since: date, until: date) -> dict:
    """Map date -> top campaign name (by spend) for that day."""
    from facebook_business.adobjects.adaccount import AdAccount

    account = AdAccount(f"act_{account_id}")
    try:
        rows = list(account.get_insights(
            fields=["date_start", "campaign_name", "spend"],
            params={
                "time_range": {"since": since.isoformat(), "until": until.isoformat()},
                "time_increment": 1,
                "level": "campaign",
            },
        ))
    except Exception:
        return {}

    by_day: dict = {}
    for r in rows:
        d = r.get("date_start")
        sp = float(r.get("spend", 0) or 0)
        name = r.get("campaign_name") or ""
        cur = by_day.get(d)
        if not cur or sp > cur[1]:
            by_day[d] = (name, sp)
    return {d: v[0] for d, v in by_day.items()}


def signature() -> str:
    """Cache-busting signature — token + account_id."""
    tok = _secret("FB_ACCESS_TOKEN", "")
    accounts = _secret("FB_ACCOUNT_EVERLY", "1965556974211662")
    return f"{tok[-12:]}-{accounts}"
