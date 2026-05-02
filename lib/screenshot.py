import os
from pathlib import Path


def capture_dashboard(sheet_id: str, out_path: Path) -> bool:
    """Open Sheet's Dashboard tab in headless Chromium and screenshot it.

    Requires the Sheet to be link-viewable, OR a logged-in profile.
    Falls back to noop in MOCK_MODE.
    """
    from config import MOCK_MODE
    if MOCK_MODE:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"")
        return True

    from playwright.sync_api import sync_playwright

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid=0"
    profile_dir = os.getenv("CHROME_PROFILE_DIR", "./credentials/chrome_profile")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile_dir, headless=False, viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_path), full_page=True)
        ctx.close()
    return True
