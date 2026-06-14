import os
import requests
from pathlib import Path
from typing import List, Optional


def send_line_summary(message: str, image_paths: List[Path] = None, retry_key: Optional[str] = None) -> bool:
    """Push text + images to LINE OA group via Messaging API.

    Everly must use its own LINE group. Do not fall back to another brand's
    LINE_GROUP_ID; that can leak client reports to the wrong room.
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    group_id = os.getenv("LINE_GROUP_ID_EVERLY")
    if not token or not group_id:
        print("  [SKIP] LINE not configured (LINE_CHANNEL_ACCESS_TOKEN / LINE_GROUP_ID_EVERLY)")
        return False

    messages = [{"type": "text", "text": message}]
    for p in (image_paths or []):
        url = _upload_image(p)
        if url:
            messages.append({"type": "image", "originalContentUrl": url, "previewImageUrl": url})

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if retry_key:
        headers["X-Line-Retry-Key"] = retry_key

    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=headers,
        json={"to": group_id, "messages": messages[:5]},
        timeout=15,
    )
    if r.status_code == 200:
        print(f"  ✓ LINE sent ({len(messages)} parts)")
        return True
    if r.status_code == 409 and retry_key:
        print("  ✓ LINE duplicate blocked by retry key")
        return True
    print(f"  ✗ LINE failed [{r.status_code}]: {r.text}")
    return False


def _upload_image(path: Path) -> str:
    """LINE needs a public HTTPS URL. Caller must host PNGs (e.g. Cloudflare Pages, Imgur)."""
    base = os.getenv("PUBLIC_IMAGE_BASE_URL", "").rstrip("/")
    if not base:
        return ""
    return f"{base}/{path.name}"


def send_email_fallback(subject: str, body: str) -> bool:
    """Gmail SMTP fallback for failure alerts."""
    import smtplib
    from email.mime.text import MIMEText

    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASSWORD")
    to = os.getenv("SMTP_TO")
    if not all([user, pw, to]):
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)
    return True
