from dataclasses import dataclass
import os

@dataclass
class Client:
    key: str
    name: str
    fb_account: str
    sheet_id: str
    result_label: str = "Inbox"
    color: str = "#8E1F2D"

CLIENTS = [
    Client("tuba", "TUBA", os.getenv("FB_ACCOUNT_TUBA", "1979003202592442"), os.getenv("SHEET_TUBA", ""), "Inbox", "#8E1F2D")
]

MOCK_MODE = os.getenv("MOCK_MODE", "").lower() in {"1", "true", "yes", "on"}
