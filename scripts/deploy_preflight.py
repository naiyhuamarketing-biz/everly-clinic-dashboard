#!/usr/bin/env python3
"""Pre-deploy checks for the Everly dashboard.

This script is intentionally conservative. If the local hardening requires
CRON_SECRET but production Render does not have it yet, deployment should stop
until the Render env var is configured.
"""

from __future__ import annotations

import json
import sys
import urllib.request


BASE_URL = "https://everly-clinic.onrender.com"
EXPECTED_BRAND = "Everly Clinic"
EXPECTED_ACCOUNT_ID = "1965556974211662"


def fetch_json(path: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        health = fetch_json("/api/health")
    except Exception as exc:  # pragma: no cover - used as CLI diagnostic
        errors.append(f"Cannot read Everly production health: {exc}")
        health = {}

    try:
        line = fetch_json("/api/line/status")
    except Exception as exc:  # pragma: no cover - used as CLI diagnostic
        errors.append(f"Cannot read Everly LINE status: {exc}")
        line = {}

    try:
        send_state = fetch_json("/api/everly/send-state")
    except Exception as exc:  # pragma: no cover - used as CLI diagnostic
        warnings.append(f"Cannot read Everly send-state: {exc}")
        send_state = {}

    if health:
        if health.get("brand") != EXPECTED_BRAND:
            errors.append(f"Wrong production brand: {health.get('brand')!r}")
        if str(health.get("account_id")) != EXPECTED_ACCOUNT_ID:
            errors.append(f"Wrong Everly ad account: {health.get('account_id')!r}")
        if health.get("mock") or health.get("mock_data"):
            errors.append("Production is in mock mode")
        if not health.get("meta_configured"):
            errors.append("Meta is not configured on production")
        if not health.get("line_configured"):
            errors.append("LINE is not configured on production")
        if not health.get("account_name_matches_brand", True):
            errors.append("Production account name does not match Everly")

    if line:
        if not line.get("configured"):
            errors.append("LINE status is not configured")
        if not line.get("has_everly_group"):
            errors.append("LINE_GROUP_ID_EVERLY is missing")
        if not line.get("manual_send_locked"):
            errors.append("Manual LINE send is not locked")
        if not line.get("cron_secret_configured"):
            errors.append(
                "Render CRON_SECRET is missing. Set it before deploying code "
                "that requires X-Cron-Secret for scheduled LINE reports."
            )
        if line.get("fallback_group_present_but_ignored"):
            warnings.append("Fallback LINE_GROUP_ID exists but is ignored; verify this is intentional.")

    if send_state:
        state_storage = send_state.get("state_storage")
        state_file = send_state.get("state_file")
        if state_storage:
            if state_storage.get("uses_tmp_storage"):
                warnings.append(
                    "Production still uses /tmp state storage. Configure a persistent state path "
                    "before relying on send-state for duplicate-send protection."
                )
        elif state_file and str(state_file).startswith("/tmp/"):
            warnings.append(
                "Production send-state still reports /tmp storage and does not expose state_storage. "
                "Deploy the diagnostic code and configure persistent storage."
            )

    if warnings:
        print("Preflight warnings:")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("Everly deploy preflight failed.")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Everly deploy preflight passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
