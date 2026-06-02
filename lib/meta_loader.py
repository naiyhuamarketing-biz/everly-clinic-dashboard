"""Small Meta loader helpers for the TUBA dashboard."""
import os
from datetime import date

ACCOUNT_ID = "1979003202592442"

def account_id() -> str:
    return "1979003202592442"

def account_ref() -> str:
    return f"act_{ACCOUNT_ID}"

def meta_configured() -> bool:
    return bool(os.getenv("FB_ACCESS_TOKEN"))

def default_time_range(target: date) -> dict:
    return {"since": target.isoformat(), "until": target.isoformat()}
