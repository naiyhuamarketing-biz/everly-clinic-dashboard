from datetime import date, timedelta
import random

ACCOUNT_ID = "1979003202592442"

def mock_insights(days: int = 7):
    campaigns = [
        "TUBA · Back to School",
        "TUBA · Reunion After Dark",
        "TUBA · Photo Booth UGC",
        "TUBA · Private Room",
        "TUBA · LINE Retargeting",
        "TUBA · Group Booking",
    ]
    today = date.today()
    rows = []
    for offset in range(days):
        current = today - timedelta(days=days - offset - 1)
        rng = random.Random(f"tuba:{ACCOUNT_ID}:{current.isoformat()}")
        spend = round(rng.uniform(800, 4200), 2)
        result = rng.randint(5, 58)
        impressions = rng.randint(5500, 36000)
        rows.append({
            "date": current.isoformat(),
            "account_id": ACCOUNT_ID,
            "campaign_name": campaigns[rng.randrange(len(campaigns))],
            "spend": spend,
            "result": result,
            "impressions": impressions,
            "cost_per_result": round(spend / result, 2),
        })
    return rows
