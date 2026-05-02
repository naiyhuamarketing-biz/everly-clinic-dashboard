import os
from typing import List


SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive.readonly"]
DAILY_LOG_TAB = "📅 Daily Log"


def _client():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    import gspread

    cred_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials/google_oauth.json")
    token_path = os.getenv("GOOGLE_TOKEN_PATH", "./credentials/google_token.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return gspread.authorize(creds)


def write_daily_log(sheet_id: str, day_number: int, ad_rows: List[list]) -> None:
    """Write up to 3 ad rows for a given day. Skips if MOCK_MODE."""
    from config import MOCK_MODE
    if MOCK_MODE:
        print(f"  [MOCK] would write {len(ad_rows)} rows to sheet {sheet_id[:10]}… day {day_number}")
        return

    gc = _client()
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(DAILY_LOG_TAB)

    start_row = 6 + (day_number - 1) * 5  # row 6 for Day 1
    end_row = start_row + len(ad_rows) - 1
    cell_range = f"A{start_row}:N{end_row}"

    # Pad/trim to 14 columns; preserve ROAS formula by sending None at col K
    safe = []
    for row in ad_rows[:3]:
        padded = list(row) + [None] * (14 - len(row))
        safe.append(padded[:14])

    ws.update(cell_range, safe, value_input_option="USER_ENTERED")
    print(f"  ✓ wrote {len(safe)} rows → {cell_range}")
