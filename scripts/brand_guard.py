#!/usr/bin/env python3
"""Fail fast if the Everly project is contaminated by another brand."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

EVERLY_REQUIRED = {
    "api_server.py": ["Everly Clinic", "1965556974211662", "/api/everly", "FB_ACCOUNT_EVERLY"],
    "dashboard.html": ["Everly Clinic", "1965556974211662", "/api/everly"],
    "config.py": ["Everly Clinic", "1965556974211662", "FB_ACCOUNT_EVERLY"],
    "lib/meta_loader.py": ["Everly Clinic", "1965556974211662", "FB_ACCOUNT_EVERLY"],
    "lib/notify.py": ["LINE_GROUP_ID_EVERLY"],
    "render.yaml": ["Everly Clinic", "FB_ACCOUNT_EVERLY", "LINE_GROUP_ID_EVERLY"],
    "vercel.json": ["/api/everly/send-daily-line"],
    ".github/workflows/daily-line.yml": ["/api/everly/send-daily-line"],
    ".github/workflows/health-monitor.yml": ["Everly Clinic", "/api/everly/keepalive"],
    ".github/workflows/keepalive.yml": ["/api/everly/keepalive"],
    ".github/workflows/token-watch.yml": ["Everly Clinic", "/api/everly/token-info"],
}

FORBIDDEN = [
    "TUBA",
    "tuba",
    "ทูบา",
    "Yiaoya",
    "yiaoya",
    "เยียวยา",
    "1979003202592442",
    "702987921684167",
    "1014027174637621",
    "FB_ACCOUNT_TUBA",
    "FB_ACCOUNT_YIAOYA",
    "LINE_GROUP_ID_TUBA",
    "LINE_GROUP_ID_YIAOYA",
    "/api/tuba",
    "/api/yiaoya",
    "tuba-clinic",
]


def main() -> int:
    errors: list[str] = []

    for relative, required_values in EVERLY_REQUIRED.items():
        path = ROOT / relative
        if not path.exists():
            errors.append(f"missing required file: {relative}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for value in required_values:
            if value not in text:
                errors.append(f"{relative}: missing required Everly marker `{value}`")
        for value in FORBIDDEN:
            if value in text:
                errors.append(f"{relative}: forbidden non-Everly marker `{value}`")

    logo_path = ROOT / "assets" / "logos" / "everly.png"
    if not logo_path.exists():
        errors.append("missing Everly logo: assets/logos/everly.png")

    if errors:
        print("Brand guard failed: this repo must stay Everly-only.")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Brand guard passed: Everly-only configuration is clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
