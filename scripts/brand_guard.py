#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail fast if the TUBA dashboard is contaminated by another brand."""
from __future__ import annotations
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
TUBA_REQUIRED = {
    "api_server.py": ["TUBA", "1979003202592442", "/api/tuba", "FB_ACCOUNT_TUBA"],
    "dashboard.html": ["TUBA", "1979003202592442", "/api/tuba", "assets/logos/tuba-brand.jpg"],
    "config.py": ["TUBA", "1979003202592442", "FB_ACCOUNT_TUBA"],
    "lib/meta_loader.py": ["TUBA", "1979003202592442"],
    "lib/notify.py": ["LINE_GROUP_ID_TUBA"],
    "render.yaml": ["TUBA", "FB_ACCOUNT_TUBA"],
    "vercel.json": ["/api/tuba/send-daily-line"],
    ".github/workflows/daily-line.yml": ["/api/tuba/send-daily-line"],
    ".github/workflows/health-monitor.yml": ["TUBA", "/api/tuba/keepalive"],
    ".github/workflows/keepalive.yml": ["/api/tuba/keepalive"],
    ".github/workflows/token-watch.yml": ["TUBA", "/api/tuba/token-info"],
}
FORBIDDEN = ["Everly Clinic", "FB_ACCOUNT_EVERLY", "LINE_GROUP_ID_EVERLY", "/api/everly", "1965556974211662", "Yiaoya", "yiaoya", "เยียวยา", "702987921684167", "1014027174637621", "FB_ACCOUNT_YIAOYA", "LINE_GROUP_ID_YIAOYA", "/api/yiaoya", "Glow Visage", "Beautier"]
def main() -> int:
    errors: list[str] = []
    for relative, required_values in TUBA_REQUIRED.items():
        path = ROOT / relative
        if not path.exists():
            errors.append(f"missing required file: {relative}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for value in required_values:
            if value not in text:
                errors.append(f"{relative}: missing required TUBA marker `{value}`")
        for value in FORBIDDEN:
            if value in text:
                errors.append(f"{relative}: forbidden non-TUBA marker `{value}`")
    if not (ROOT / "assets/logos/tuba-brand.jpg").exists():
        errors.append("missing TUBA logo: assets/logos/tuba-brand.jpg")
    if errors:
        print("Brand guard failed: this repo must stay TUBA-only.")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Brand guard passed: TUBA-only configuration is clean.")
    return 0
if __name__ == "__main__":
    sys.exit(main())
