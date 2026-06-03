import os
import random
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import List


@dataclass
class AdRow:
    status: str
    objective: str
    campaign: str
    update_date: str
    budget_per_day: float
    impression: int
    reach: int
    cpm: float
    conversion: float
    result: int
    cost_per_result: float
    spent: float

    def as_sheet_row(self, no: int) -> list:
        # Matches Daily Log columns A–N. ROAS (col K) left blank — formula in template.
        return [
            no, self.status, self.objective, self.campaign, self.update_date,
            self.budget_per_day, self.impression, self.reach, self.cpm,
            self.conversion, None, self.result, self.cost_per_result, self.spent,
        ]


def fetch_top3_ads(account_id: str, target_date: date, objective: str) -> List[AdRow]:
    """Pull top 3 ads by spend for a given day. Falls back to mock when MOCK_MODE."""
    from config import MOCK_MODE
    if MOCK_MODE or not account_id or not os.getenv("FB_ACCESS_TOKEN"):
        return _mock_ads(target_date, objective)
    return _real_ads(account_id, target_date, objective)


def _mock_ads(d: date, objective: str) -> List[AdRow]:
    rng = random.Random(f"{d.isoformat()}-{objective}")
    samples = [
        ("M KOL พูดโปร", "Inbox"),
        ("M Filler ปาก", "Inbox"),
        ("M 9 ใบเทา", "Inbox"),
        ("Conversion Botox 2026", "Purchase"),
        ("Lead - Skin Booster", "Inbox"),
        ("Promo สงกรานต์", "Purchase"),
    ]
    rng.shuffle(samples)
    rows = []
    for camp, _ in samples[:3]:
        spent = round(rng.uniform(300, 1500), 2)
        impression = rng.randint(2000, 12000)
        reach = int(impression * rng.uniform(0.55, 0.85))
        cpm = round(spent / impression * 1000, 2)
        result = rng.randint(2, 12)
        conv = round(spent * rng.uniform(0, 18), 2) if objective == "Purchase" else 0
        rows.append(AdRow(
            status="Normal",
            objective=objective,
            campaign=f"{camp} ({d.strftime('%d/%m/%y')})",
            update_date=d.strftime("%-d/%-m/%Y"),
            budget_per_day=1111,
            impression=impression,
            reach=reach,
            cpm=cpm,
            conversion=conv,
            result=result,
            cost_per_result=round(spent / result, 2) if result else 0,
            spent=spent,
        ))
    return rows


def _real_ads(account_id: str, d: date, objective: str) -> List[AdRow]:
    from facebook_business.api import FacebookAdsApi
    from facebook_business.adobjects.adaccount import AdAccount

    FacebookAdsApi.init(
        app_id=os.getenv("FB_APP_ID"),
        app_secret=os.getenv("FB_APP_SECRET"),
        access_token=os.getenv("FB_ACCESS_TOKEN"),
    )

    account = AdAccount(f"act_{account_id}")
    fields = [
        "ad_name", "campaign_name", "spend", "impressions", "reach",
        "cpm", "actions", "action_values",
    ]
    params = {
        "time_range": {"since": d.isoformat(), "until": d.isoformat()},
        "level": "ad",
        "filtering": [{"field": "ad.effective_status", "operator": "IN", "value": ["ACTIVE"]}],
    }

    insights = list(account.get_insights(fields=fields, params=params))
    insights.sort(key=lambda i: float(i.get("spend", 0)), reverse=True)

    rows = []
    for ins in insights[:3]:
        spent = float(ins.get("spend", 0))
        impression = int(ins.get("impressions", 0))
        reach = int(ins.get("reach", 0))
        cpm = float(ins.get("cpm", 0))

        result = 0
        for a in ins.get("actions", []):
            if objective == "Inbox" and a.get("action_type") == "onsite_conversion.messaging_conversation_started_7d":
                result += int(float(a.get("value", 0)))
            elif objective == "Purchase" and a.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase"):
                result += int(float(a.get("value", 0)))

        conv_value = 0.0
        for v in ins.get("action_values", []):
            if v.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase"):
                conv_value += float(v.get("value", 0))

        rows.append(AdRow(
            status="Normal",
            objective=objective,
            campaign=ins.get("ad_name", "")[:60],
            update_date=d.strftime("%-d/%-m/%Y"),
            budget_per_day=1111,
            impression=impression,
            reach=reach,
            cpm=round(cpm, 2),
            conversion=round(conv_value, 2),
            result=result,
            cost_per_result=round(spent / result, 2) if result else 0,
            spent=round(spent, 2),
        ))
    return rows


def to_dict_list(rows: List[AdRow]) -> List[dict]:
    return [asdict(r) for r in rows]
