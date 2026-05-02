import os
import requests
from pathlib import Path
from typing import List


def send_line_summary(message: str, image_paths: List[Path] = None) -> bool:
    """Push text + images to LINE OA group via Messaging API."""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    group_id = os.getenv("LINE_GROUP_ID")
    if not token or not group_id:
        print("  [SKIP] LINE not configured (LINE_CHANNEL_ACCESS_TOKEN / LINE_GROUP_ID)")
        return False

    messages = [{"type": "text", "text": message}]
    for p in (image_paths or []):
        url = _upload_image(p)
        if url:
            messages.append({"type": "image", "originalContentUrl": url, "previewImageUrl": url})

    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"to": group_id, "messages": messages[:5]},
        timeout=15,
    )
    if r.status_code == 200:
        print(f"  ✓ LINE sent ({len(messages)} parts)")
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
