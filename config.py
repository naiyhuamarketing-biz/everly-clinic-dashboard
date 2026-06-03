import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Client:
    key: str
    name: str
    fb_account_id: str
    sheet_id: str
    objective: str  # "Inbox" or "Purchase"
    color: str  # accent color for dashboard card


CLIENTS = [
    Client("everly", "Everly Clinic",
           os.getenv("FB_ACCOUNT_EVERLY", "1965556974211662"),
           os.getenv("SHEET_EVERLY", ""),
           "Purchase", "#D4A5A5"),
]

MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

THEME = {
    "burgundy": "#6B1A35",
    "rose": "#D9899C",
    "blush": "#F5E1E5",
    "gold": "#C9A961",
    "cream": "#FBF6F0",
    "ink": "#2C0E1B",
}
