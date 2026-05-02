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
    Client("glow", "Glow Visage Clinic",
           os.getenv("FB_ACCOUNT_GLOW", ""),
           os.getenv("SHEET_GLOW", ""),
           "Inbox", "#E8B4BC"),
    Client("everly", "Everly Clinic",
           os.getenv("FB_ACCOUNT_EVERLY", ""),
           os.getenv("SHEET_EVERLY", ""),
           "Purchase", "#D4A5A5"),
    Client("yiaoya", "เยียวยา (Yiaoya)",
           os.getenv("FB_ACCOUNT_YIAOYA", ""),
           os.getenv("SHEET_YIAOYA", ""),
           "Inbox", "#C9A961"),
    Client("tuba", "Tuba",
           os.getenv("FB_ACCOUNT_TUBA", ""),
           os.getenv("SHEET_TUBA", ""),
           "Purchase", "#B8869C"),
    Client("beautier", "Beautier Clinic",
           os.getenv("FB_ACCOUNT_BEAUTIER", ""),
           os.getenv("SHEET_BEAUTIER", ""),
           "Inbox", "#D9899C"),
]

MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"

THEME = {
    "burgundy": "#6B1A35",
    "rose": "#D9899C",
    "blush": "#F5E1E5",
    "gold": "#C9A961",
    "cream": "#FBF6F0",
    "ink": "#2C0E1B",
}
