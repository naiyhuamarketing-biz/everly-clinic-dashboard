#!/usr/bin/env python3
"""Refresh the FB long-lived token to extend another 60 days.

Run this if `verify.py` starts returning auth errors.
Long-lived tokens auto-extend when used in API calls, so this only needed
if the dashboard hasn't been opened for >60 days.

Usage:
    python refresh_token.py
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

env_path = Path(__file__).parent / ".env"
env = env_path.read_text()


def get(key):
    m = re.search(rf"^{key}=(.*)$", env, re.M)
    return m.group(1).strip() if m else ""


current = get("FB_ACCESS_TOKEN")
app_id = get("FB_APP_ID")
app_secret = get("FB_APP_SECRET")

if not all([current, app_id, app_secret]):
    print("✗ Missing FB_ACCESS_TOKEN / FB_APP_ID / FB_APP_SECRET in .env")
    sys.exit(1)

url = "https://graph.facebook.com/v20.0/oauth/access_token?" + urllib.parse.urlencode({
    "grant_type": "fb_exchange_token",
    "client_id": app_id,
    "client_secret": app_secret,
    "fb_exchange_token": current,
})

resp = json.loads(urllib.request.urlopen(url, timeout=15).read())
if "access_token" not in resp:
    print(f"✗ Refresh failed: {resp}")
    sys.exit(1)

new_token = resp["access_token"]
days = resp.get("expires_in", 0) / 86400

env = re.sub(r"^FB_ACCESS_TOKEN=.*$", f"FB_ACCESS_TOKEN={new_token}", env, flags=re.M)
env_path.write_text(env)

print(f"✓ Token refreshed — valid for {days:.0f} more days")
print(f"  ...{new_token[-15:]}")
