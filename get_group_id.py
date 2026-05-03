#!/usr/bin/env python3
"""Helper: discover LINE group ID after adding the bot to a new group.

How to use:
    1. Add the bot "ทีมคุณฟา (AI)" to your Everly LINE group
    2. Send any message in the group (e.g. "test") — LINE only logs events
       AFTER the bot is added, so you need a message to trigger a webhook
       OR use the alternative method below
    3. Run this script:  python get_group_id.py
    4. The script polls the LINE Messaging API and prints any group IDs
       it finds in recent webhook events

Alternative (if no webhook URL is configured):
    Use Messaging API "Get group summary" — but you need the group ID first
    (chicken/egg problem).

The reliable method: temporarily set up a webhook on a free service like
https://webhook.site/, configure it as the LINE bot's webhook URL, send a
message in the group, then read the group ID from the webhook payload.

Steps:
    1. Open https://webhook.site → copy your unique URL
    2. LINE Developers Console → ทีมคุณฟา (AI) channel → Messaging API
       settings → "Webhook URL" → paste the webhook.site URL → Update
    3. Make sure "Use webhook" toggle is ON
    4. In the LINE group, send any message (e.g. "test")
    5. Refresh webhook.site — you'll see a JSON payload with:
       events: [{ source: { type: "group", groupId: "C..." }, ... }]
    6. Copy the groupId — that's your LINE_GROUP_ID_EVERLY value
"""
import os
import sys

print(__doc__)
print()
print("─" * 60)
print("This helper just shows instructions — there is no programmatic way")
print("to list groups a bot is in via the LINE Messaging API. You must use")
print("a webhook receiver to capture the group ID once.")
print("─" * 60)
