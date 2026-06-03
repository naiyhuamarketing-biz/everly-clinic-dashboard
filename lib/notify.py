import os
import requests

LINE_GROUP_ENV = "LINE_GROUP_ID_TUBA"

def line_target() -> str:
    return os.getenv(LINE_GROUP_ENV) or os.getenv("LINE_GROUP_ID") or ""

def send_line(text: str) -> dict:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    group_id = line_target()
    if not token or not group_id:
        return {"ok": False, "configured": False, "error": f"Missing LINE_CHANNEL_ACCESS_TOKEN or {LINE_GROUP_ENV}"}
    response = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"to": group_id, "messages": [{"type": "text", "text": text}]},
        timeout=20,
    )
    return {"ok": response.ok, "status_code": response.status_code, "response": response.text[:500]}
