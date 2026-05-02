"""Everly Clinic — Daily Ads Report (Live Meta API)
Brand-aligned earthy edition · Monthly comparison · Brown/Cream palette
"""
import base64
import os
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

BANGKOK_TZ = timezone(timedelta(hours=7))


def now_bkk():
    return datetime.now(BANGKOK_TZ)


def today_bkk():
    return now_bkk().date()

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    """Read from Streamlit secrets first (cloud), then env vars (local)."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
ACCOUNT_ID = _secret("FB_ACCOUNT_EVERLY", "1965556974211662")
HAS_META_TOKEN = bool(_secret("FB_ACCESS_TOKEN"))


# ── Brand palette (extracted from Everly Clinic logo) ─────
BROWN_DEEP = "#4A2A18"
BROWN_MID = "#6B4330"
BROWN_LIGHT = "#8A6749"
TAN = "#B5997A"
CHAMPAGNE = "#D9C5A2"
CREAM = "#E6D7B5"
IVORY = "#EEE1C8"
INK = "#2D1B10"
MUTED = "#8A7560"
GOLD_HIGHLIGHT = "#A38050"
SUCCESS = "#6B7F4A"
WARN = "#B47A48"
ERROR = "#974A3D"


st.set_page_config(
    page_title="Everly Clinic · Daily Report",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ── Glam CSS · brand-aligned (Glow-style structure, Everly palette) ─────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400;1,500;1,600&family=Italiana&family=Prompt:wght@200;300;400;500;600;700&family=Sarabun:wght@200;300;400;500;600;700&display=swap');

html, body, [class*="css"], .stMarkdown, p, span, div, button {{
    font-family: 'Prompt', 'Sarabun', sans-serif !important;
    color: {INK};
}}
.stApp {{
    background:
      radial-gradient(at 20% 0%, {IVORY} 0%, transparent 50%),
      radial-gradient(at 80% 100%, {CHAMPAGNE} 0%, transparent 60%),
      linear-gradient(180deg, {IVORY} 0%, {CREAM} 100%);
    background-attachment: fixed;
}}
.main .block-container {{ padding-top: 1rem; max-width: 1320px; }}
#MainMenu, footer, header {{ visibility: hidden; }}

/* ── Hero ─────────────────────────── */
.hero {{
    text-align: center;
    padding: 3.5rem 1rem 2.5rem 1rem;
    margin-bottom: 1.5rem;
    position: relative;
}}
.hero-with-logo {{
    padding: 2.5rem 1rem 2rem 1rem;
}}
.hero-brandmark {{
    margin: 0.6rem auto 1.4rem auto;
    max-width: 360px;
    padding: 0 1rem;
}}
.hero-brandmark img {{
    width: 100%;
    height: auto;
    display: block;
    filter: drop-shadow(0 4px 18px rgba(74, 42, 24, 0.10));
}}
.hero-logo {{
    width: 130px; height: 130px;
    margin: 0 auto 1.4rem auto;
    border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, white 0%, {CHAMPAGNE} 70%, {TAN} 100%);
    box-shadow:
      0 4px 30px rgba(122, 79, 58, 0.18),
      0 0 0 1px {GOLD_HIGHLIGHT}40;
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
}}
.hero-logo img {{ width: 100%; height: 100%; object-fit: cover; }}
.hero-monogram {{
    font-family: 'Italiana', 'Cormorant Garamond', serif;
    font-size: 3.6rem;
    font-weight: 400;
    color: {BROWN_DEEP};
    letter-spacing: 0;
    text-transform: lowercase;
    line-height: 1;
}}
.hero-eyebrow {{
    font-family: 'Prompt', 'Sarabun', sans-serif;
    color: {BROWN_LIGHT};
    letter-spacing: 7px;
    font-size: 0.72rem;
    font-weight: 500;
    text-transform: uppercase;
    margin-bottom: 0.7rem;
}}
.hero-title {{
    font-family: 'Italiana', 'Cormorant Garamond', serif;
    font-weight: 400;
    font-size: 5.5rem;
    line-height: 1;
    background: linear-gradient(135deg, {BROWN_DEEP} 0%, {BROWN_MID} 50%, {BROWN_LIGHT} 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: 1px;
    margin: 0;
    text-transform: lowercase;
}}
.hero-tagline {{
    color: {BROWN_DEEP};
    font-family: 'Italiana', 'Cormorant Garamond', serif;
    font-size: 1rem;
    margin-top: 0.3rem;
    letter-spacing: 12px;
    text-transform: uppercase;
    padding-left: 12px;
}}
.hero-period {{
    color: {BROWN_DEEP};
    font-family: 'Prompt', 'Sarabun', sans-serif;
    font-size: 0.78rem;
    margin-top: 1.4rem;
    letter-spacing: 4px;
    font-weight: 400;
    text-transform: uppercase;
}}
.hero-divider {{
    display: flex; align-items: center; justify-content: center;
    margin: 1rem auto;
    gap: 16px;
}}
.hero-divider::before, .hero-divider::after {{
    content: ""; height: 1px; width: 60px;
    background: linear-gradient(90deg, transparent, {BROWN_LIGHT}, transparent);
}}
.hero-divider-dot {{
    width: 6px; height: 6px;
    background: {GOLD_HIGHLIGHT};
    border-radius: 50%;
    transform: rotate(45deg);
}}

/* ── KPI cards ──────────────────── */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin: 1rem 0;
}}
.kpi {{
    background: linear-gradient(135deg, white 0%, {IVORY} 100%);
    border-radius: 16px;
    padding: 1.5rem 1.5rem 1.4rem 1.5rem;
    box-shadow:
      0 1px 1px rgba(122, 79, 58, 0.04),
      0 4px 24px rgba(122, 79, 58, 0.08);
    border: 1px solid {CHAMPAGNE}80;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
}}
.kpi:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(122, 79, 58, 0.13);
}}
.kpi::before {{
    content: ""; position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, {BROWN_LIGHT} 0%, {GOLD_HIGHLIGHT} 100%);
}}
.kpi::after {{
    content: ""; position: absolute;
    top: -30px; right: -30px; width: 100px; height: 100px;
    background: radial-gradient(circle, {GOLD_HIGHLIGHT}25 0%, transparent 70%);
    border-radius: 50%;
}}
.kpi-label {{
    font-family: 'Prompt', 'Sarabun', sans-serif;
    color: {BROWN_LIGHT};
    text-transform: uppercase;
    letter-spacing: 2.5px;
    font-size: 0.7rem;
    font-weight: 500;
    margin-bottom: 0.7rem;
    position: relative; z-index: 1;
}}
.kpi-value {{
    font-family: 'Cormorant Garamond', serif;
    color: {BROWN_DEEP};
    font-size: 2.4rem;
    font-weight: 500;
    line-height: 1.05;
    letter-spacing: -1px;
    font-variant-numeric: lining-nums tabular-nums;
    position: relative; z-index: 1;
}}
.kpi-suffix {{
    font-family: 'Prompt', 'Sarabun', sans-serif;
    color: {MUTED};
    font-size: 0.78rem;
    margin-top: 0.4rem;
    font-weight: 400;
    position: relative; z-index: 1;
}}
.kpi-delta-up {{ color: {SUCCESS}; font-weight: 600; }}
.kpi-delta-down {{ color: {ERROR}; font-weight: 600; }}

/* Section heads */
.section-head {{
    font-family: 'Cormorant Garamond', serif;
    color: {BROWN_DEEP};
    font-size: 1.7rem;
    font-weight: 500;
    margin: 2.5rem 0 0.3rem 0;
    letter-spacing: 1px;
}}
.section-head .accent {{ color: {BROWN_LIGHT}; font-style: italic; }}
.section-rule {{
    height: 1px;
    background: linear-gradient(90deg, {BROWN_LIGHT}, transparent);
    width: 80px;
    margin-bottom: 1.4rem;
}}
.mini-label {{
    font-family: 'Prompt', 'Sarabun', sans-serif;
    color: {BROWN_LIGHT};
    letter-spacing: 2.5px;
    font-size: 0.68rem;
    font-weight: 500;
    text-transform: uppercase;
}}
.mini-value {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.6rem;
    color: {BROWN_DEEP};
    font-weight: 500;
    letter-spacing: -0.5px;
    font-variant-numeric: lining-nums tabular-nums;
}}

/* Month comparison cards */
.month-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
}}
.month-card {{
    background: white;
    border-radius: 14px;
    padding: 1.4rem 1.3rem;
    box-shadow: 0 2px 20px rgba(122, 79, 58, 0.08);
    border-top: 3px solid {BROWN_LIGHT};
    position: relative;
}}
.month-card.current {{
    background: linear-gradient(135deg, {BROWN_LIGHT} 0%, {BROWN_DEEP} 100%);
    color: white;
    border-top-color: {GOLD_HIGHLIGHT};
}}
.month-card.current * {{ color: white !important; }}
.month-card-name {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.4rem;
    font-weight: 500;
    color: {BROWN_DEEP};
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 0.2rem;
}}
.month-card-days {{
    font-family: 'Prompt', 'Sarabun', sans-serif;
    font-size: 0.72rem;
    color: {MUTED};
    letter-spacing: 1.5px;
    margin-bottom: 1rem;
    text-transform: uppercase;
}}
.month-stat {{
    display: flex; justify-content: space-between;
    padding: 0.35rem 0;
    border-bottom: 1px solid {CHAMPAGNE}80;
    font-size: 0.85rem;
}}
.month-stat:last-child {{ border-bottom: none; }}
.month-stat-label {{
    font-family: 'Prompt', 'Sarabun', sans-serif;
    color: {MUTED};
    font-size: 0.78rem;
}}
.month-stat-value {{
    font-family: 'Cormorant Garamond', serif;
    color: {BROWN_DEEP};
    font-weight: 600;
    font-variant-numeric: lining-nums tabular-nums;
}}
.month-stat-delta {{
    font-family: 'Prompt', sans-serif;
    font-size: 0.7rem;
    margin-left: 6px;
    font-weight: 600;
}}
.delta-up {{ color: {SUCCESS}; }}
.delta-down {{ color: {ERROR}; }}
.delta-flat {{ color: {MUTED}; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: 1px solid {CHAMPAGNE};
    margin-bottom: 1.2rem;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    color: {MUTED};
    font-family: 'Prompt', 'Sarabun', sans-serif;
    letter-spacing: 3px;
    text-transform: uppercase;
    font-size: 0.78rem;
    font-weight: 500;
    padding: 0.8rem 2rem;
    border-bottom: 2px solid transparent;
}}
.stTabs [aria-selected="true"] {{
    color: {BROWN_DEEP} !important;
    border-bottom: 2px solid {BROWN_LIGHT} !important;
    background: transparent !important;
}}

/* DataFrame */
[data-testid="stDataFrame"] {{
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 2px 24px rgba(122, 79, 58, 0.06);
}}
[data-testid="stDataFrame"] table {{
    font-family: 'Prompt', 'Sarabun', sans-serif;
    font-size: 0.88rem;
}}

/* Footer */
.footer {{
    text-align: center;
    margin-top: 4rem;
    padding: 2rem 0;
    color: {MUTED};
    font-family: 'Cormorant Garamond', serif;
    letter-spacing: 4px;
    font-size: 0.85rem;
    text-transform: uppercase;
    border-top: 1px solid {CHAMPAGNE};
}}
.footer-divider {{
    width: 30px; height: 1px;
    background: {BROWN_LIGHT};
    margin: 0 auto 1rem auto;
}}
.footer-ornament {{
    color: {GOLD_HIGHLIGHT};
    font-size: 1.1rem;
    margin: 0 0 0.8rem 0;
    letter-spacing: 8px;
}}

/* ── Mobile ─────────────────────── */
@media (max-width: 768px) {{
    .main .block-container {{ padding: 0.6rem !important; }}
    .hero {{ padding: 1.5rem 0.5rem 1.2rem 0.5rem; }}
    .hero-logo {{ width: 80px; height: 80px; }}
    .hero-monogram {{ font-size: 2.2rem; }}
    .hero-eyebrow {{ font-size: 0.6rem; letter-spacing: 3px; }}
    .hero-title {{ font-size: 3rem; letter-spacing: 0.5px; }}
    .hero-tagline {{ font-size: 0.78rem; letter-spacing: 7px; padding-left: 7px; }}
    .hero-period {{ font-size: 0.7rem; letter-spacing: 2px; }}
    .hero-brandmark {{ max-width: 240px; }}
    .hero-with-logo {{ padding: 1.4rem 0.5rem 1rem 0.5rem; }}

    .kpi-grid {{ grid-template-columns: repeat(2, 1fr) !important; gap: 0.6rem !important; }}
    .kpi {{ padding: 1rem 0.9rem; }}
    .kpi-label {{ font-size: 0.6rem; letter-spacing: 1.5px; }}
    .kpi-value {{ font-size: 1.5rem; }}

    .month-grid {{ grid-template-columns: 1fr 1fr !important; }}
    .month-card {{ padding: 1rem; }}

    .section-head {{ font-size: 1.2rem; }}
    .stTabs [data-baseweb="tab"] {{
        padding: 0.5rem 0.8rem !important;
        font-size: 0.66rem !important;
        letter-spacing: 1.5px !important;
    }}
    [data-testid="stHorizontalBlock"] {{ flex-direction: column !important; gap: 0.7rem !important; }}
    [data-testid="stHorizontalBlock"] > div {{ width: 100% !important; flex: 1 1 100% !important; }}
}}
@media (max-width: 480px) {{
    .kpi-grid {{ grid-template-columns: 1fr !important; }}
    .month-grid {{ grid-template-columns: 1fr !important; }}
    .hero-title {{ font-size: 2.4rem; }}
}}
</style>
""", unsafe_allow_html=True)


# ── Load data ─────────────────────────────
@st.cache_data(show_spinner="กำลังดึงข้อมูลจาก Meta API…", ttl=600)
def _load_meta(sig, since_iso, until_iso):
    from lib.meta_loader import fetch_daily
    return fetch_daily(ACCOUNT_ID, date.fromisoformat(since_iso),
                       date.fromisoformat(until_iso))


if not HAS_META_TOKEN:
    st.error("FB_ACCESS_TOKEN ไม่พบ — เปิด `.env` แล้วเซ็ต token")
    st.stop()

from lib.meta_loader import signature as meta_sig
sig_label = meta_sig()
today = today_bkk()
since = date(2026, 2, 1)  # extend to Feb for monthly comparison

with st.spinner("กำลังดึงข้อมูลจาก Meta API…"):
    history = _load_meta(sig_label, since.isoformat(), today.isoformat())

if not history:
    st.error("ดึงข้อมูลไม่ได้ — เช็ค FB_ACCESS_TOKEN")
    st.stop()


# ── Helpers ─────────────────────────────
def day_total(d, field):
    return sum(float(a.get(field, 0) or 0) for a in d["ads"])


def fmt_delta(curr: float, prev: float, suffix: str = "%") -> str:
    if prev == 0:
        return f"<span class='delta-flat'>—</span>"
    pct = (curr - prev) / prev * 100
    if abs(pct) < 0.5:
        return f"<span class='delta-flat'>~0%</span>"
    cls = "delta-up" if pct > 0 else "delta-down"
    arrow = "▲" if pct > 0 else "▼"
    return f"<span class='{cls}'>{arrow} {abs(pct):.1f}{suffix}</span>"


# ── Hero ──────────────────────────────────
logo_path = ASSETS / "everly_logo.png"
has_logo = logo_path.exists() and logo_path.stat().st_size > 0

if has_logo:
    # Logo image already contains "everly" + "CLINIC" wordmark — display
    # it large as the hero, replacing the styled text title.
    logo_b64 = base64.b64encode(logo_path.read_bytes()).decode()
    st.markdown(f"""
    <div class='hero hero-with-logo'>
        <div class='hero-eyebrow'>นายหัว กรุ๊ป · Ad Operations</div>
        <div class='hero-brandmark'>
            <img src='data:image/png;base64,{logo_b64}' alt='Everly Clinic'/>
        </div>
        <div class='hero-divider'>
            <span class='hero-divider-dot'></span>
        </div>
        <div class='hero-period'>D A I L Y &nbsp;·&nbsp; R E P O R T &nbsp;·&nbsp; FEB – {today.strftime("%b").upper()} 2026</div>
    </div>
    """, unsafe_allow_html=True)
else:
    # Fallback styled text — Italiana lowercase + tracked CLINIC tagline.
    st.markdown(f"""
    <div class='hero'>
        <div class='hero-logo'>
            <div class='hero-monogram'>e</div>
        </div>
        <div class='hero-eyebrow'>นายหัว กรุ๊ป · Ad Operations</div>
        <h1 class='hero-title'>everly</h1>
        <div class='hero-tagline'>Clinic</div>
        <div class='hero-divider'>
            <span class='hero-divider-dot'></span>
        </div>
        <div class='hero-period'>D A I L Y &nbsp;·&nbsp; R E P O R T &nbsp;·&nbsp; FEB – {today.strftime("%b").upper()} 2026</div>
    </div>
    """, unsafe_allow_html=True)


# ── Refresh / Last updated ────────────────
fresh_col1, fresh_col2 = st.columns([5, 1])
with fresh_col1:
    last_str = now_bkk().strftime("%-d %b %Y · %H:%M") + " ICT"
    st.markdown(
        f"<div style='color:{MUTED};font-size:0.82rem;letter-spacing:1px;'>"
        f"<span style='color:{SUCCESS};font-weight:700;'>●</span> "
        f"<b style='color:{SUCCESS};letter-spacing:2px;'>LIVE</b> "
        f"&nbsp;จาก Meta Marketing API · ดึงเมื่อ <b>{last_str}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )
with fresh_col2:
    if st.button("🔄 รีเฟรช", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Tabs: Overview / Monthly / Daily ──────
tab_overview, tab_monthly, tab_daily = st.tabs(["ภาพรวม", "เปรียบเทียบรายเดือน", "รายวัน"])


# ─── helpers for month grouping ────
def by_month():
    grp = {}
    for d in history:
        m = d["date"][:7]
        grp.setdefault(m, []).append(d)
    return grp


MONTH_TH = {"02": "กุมภาพันธ์", "03": "มีนาคม", "04": "เมษายน", "05": "พฤษภาคม"}
MONTH_EN = {"02": "February", "03": "March", "04": "April", "05": "May"}


def month_stats(records):
    if not records:
        return None
    spend = sum(day_total(d, "spent") for d in records)
    inbox = sum(day_total(d, "result") for d in records)
    rev = sum(day_total(d, "conversion") for d in records)
    impr = sum(day_total(d, "impression") for d in records)
    reach = sum(day_total(d, "reach") for d in records)
    freq_avg = sum(day_total(d, "frequency") for d in records) / len(records) if records else 0
    return {
        "days": len(records),
        "spend": spend,
        "inbox": int(inbox),
        "revenue": rev,
        "roas": (rev / spend) if spend else 0,
        "cpi": (spend / inbox) if inbox else 0,
        "impr": int(impr),
        "reach": int(reach),
        "freq": freq_avg,
    }


# ════════════ OVERVIEW TAB ════════════
with tab_overview:
    overall = month_stats(history)

    # ── 6 KPI cards (2 rows × 3 cols) ──
    st.markdown(f"<div class='kpi-grid'>"
        f"<div class='kpi'>"
        f"  <div class='kpi-label'>ยอดใช้จ่าย · Spend</div>"
        f"  <div class='kpi-value'>฿{overall['spend']:,.0f}</div>"
        f"  <div class='kpi-suffix'>{overall['days']} วัน · เฉลี่ย ฿{overall['spend']/overall['days']:,.0f}/วัน</div>"
        f"</div>"
        f"<div class='kpi'>"
        f"  <div class='kpi-label'>รายได้ · Revenue</div>"
        f"  <div class='kpi-value'>฿{overall['revenue']:,.0f}</div>"
        f"  <div class='kpi-suffix'>จาก Pixel purchase events</div>"
        f"</div>"
        f"<div class='kpi'>"
        f"  <div class='kpi-label'>ROAS</div>"
        f"  <div class='kpi-value'>{overall['roas']:.2f}<span style='font-size:1.4rem;'>×</span></div>"
        f"  <div class='kpi-suffix'>เป้าหมาย 10× · ปัจจุบัน {overall['roas']/10*100:.0f}%</div>"
        f"</div>"
        f"<div class='kpi'>"
        f"  <div class='kpi-label'>Inbox</div>"
        f"  <div class='kpi-value'>{overall['inbox']:,}</div>"
        f"  <div class='kpi-suffix'>messaging conversations</div>"
        f"</div>"
        f"<div class='kpi'>"
        f"  <div class='kpi-label'>ต้นทุน / Inbox</div>"
        f"  <div class='kpi-value'>฿{overall['cpi']:,.0f}</div>"
        f"  <div class='kpi-suffix'>cost per messaging conv.</div>"
        f"</div>"
        f"<div class='kpi'>"
        f"  <div class='kpi-label'>Frequency</div>"
        f"  <div class='kpi-value'>{overall['freq']:.2f}<span style='font-size:1.4rem;'>×</span></div>"
        f"  <div class='kpi-suffix'>ครั้งที่คนเดิมเห็นโฆษณา</div>"
        f"</div>"
        f"</div>", unsafe_allow_html=True)

    # Secondary stats line
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"<div class='mini-label'>การมองเห็น · Impressions</div>"
                f"<div class='mini-value'>{overall['impr']:,}</div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='mini-label'>การเข้าถึง · Reach</div>"
                f"<div class='mini-value'>{overall['reach']:,}</div>", unsafe_allow_html=True)
    profit = overall["revenue"] - overall["spend"]
    profit_label = "กำไร · Net" if profit >= 0 else "ขาดทุน · Net"
    profit_color = SUCCESS if profit >= 0 else ERROR
    c3.markdown(f"<div class='mini-label'>{profit_label}</div>"
                f"<div class='mini-value' style='color:{profit_color}'>฿{profit:,.0f}</div>",
                unsafe_allow_html=True)

    # Spend trend chart
    st.markdown(f"<div class='section-head'>แนวโน้มยอดใช้จ่าย <span class='accent'>· Daily Spend</span></div>"
                f"<div class='section-rule'></div>", unsafe_allow_html=True)
    df = pd.DataFrame([{
        "date": d["date"],
        "label": datetime.fromisoformat(d["date"]).strftime("%-d %b"),
        "spent": day_total(d, "spent"),
        "inbox": day_total(d, "result"),
        "revenue": day_total(d, "conversion"),
        "roas": (day_total(d, "conversion") / day_total(d, "spent")) if day_total(d, "spent") else 0,
    } for d in history])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["label"], y=df["spent"], mode="lines",
                             line=dict(color=BROWN_LIGHT, width=0),
                             fill="tozeroy", fillcolor=f"rgba(122,79,58,0.16)",
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=df["label"], y=df["spent"], mode="lines+markers",
                             line=dict(color=BROWN_DEEP, width=2.5, shape="spline", smoothing=0.6),
                             marker=dict(size=5, color=BROWN_LIGHT, line=dict(color="white", width=1.5)),
                             showlegend=False,
                             hovertemplate="<b>%{x}</b><br>฿%{y:,.0f}<extra></extra>"))
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=10, b=40),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Prompt, Sarabun", color=BROWN_MID, size=11),
                      xaxis=dict(showgrid=False, color=MUTED),
                      yaxis=dict(showgrid=True, gridcolor="rgba(122,79,58,0.08)",
                                 color=MUTED, tickprefix="฿", tickformat=",.0f"),
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="spend_trend_overview")


# ════════════ MONTHLY COMPARISON TAB ════════════
with tab_monthly:
    grp = by_month()
    months = sorted(grp.keys())  # e.g. ['2026-02','2026-03','2026-04','2026-05']
    stats = {m: month_stats(grp[m]) for m in months}

    # ── Stat cards (one per month, deltas vs previous) ──
    st.markdown(f"<div class='section-head'>เปรียบเทียบรายเดือน <span class='accent'>· Month over Month</span></div>"
                f"<div class='section-rule'></div>", unsafe_allow_html=True)

    cards_html = "<div class='month-grid'>"
    for i, m in enumerate(months):
        s = stats[m]
        prev = stats[months[i-1]] if i > 0 else None
        is_current = (m == months[-1])
        cls = "month-card current" if is_current else "month-card"

        def stat_row(label, val_fmt, prev_val=None, curr_val=None, suffix=""):
            delta = fmt_delta(curr_val, prev_val) if prev_val is not None else ""
            return (f"<div class='month-stat'>"
                    f"<span class='month-stat-label'>{label}</span>"
                    f"<span class='month-stat-value'>{val_fmt}{suffix} <span class='month-stat-delta'>{delta}</span></span>"
                    f"</div>")

        rows = "".join([
            stat_row("ใช้จ่าย", f"฿{s['spend']:,.0f}",
                     prev["spend"] if prev else None, s["spend"]),
            stat_row("Inbox", f"{s['inbox']:,}",
                     prev["inbox"] if prev else None, s["inbox"]),
            stat_row("รายได้", f"฿{s['revenue']:,.0f}",
                     prev["revenue"] if prev else None, s["revenue"]),
            stat_row("ROAS", f"{s['roas']:.2f}×",
                     prev["roas"] if prev else None, s["roas"]),
            stat_row("ต้นทุน/Inbox", f"฿{s['cpi']:,.0f}",
                     prev["cpi"] if prev else None, s["cpi"]),
        ])

        cards_html += (f"<div class='{cls}'>"
                       f"<div class='month-card-name'>{MONTH_EN.get(m[5:7], m[5:7])}</div>"
                       f"<div class='month-card-days'>{MONTH_TH.get(m[5:7],'')} · {s['days']} วัน</div>"
                       f"{rows}"
                       f"</div>")
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)

    # ── Trend across months: Spend / Revenue / ROAS ──
    col_l, col_r = st.columns(2)
    month_labels = [MONTH_EN.get(m[5:7], m) for m in months]

    with col_l:
        st.markdown(f"<div class='section-head'>Spend <span class='accent'>vs</span> Revenue</div>"
                    f"<div class='section-rule'></div>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=month_labels, y=[stats[m]["spend"] for m in months],
                             name="Spend", marker_color=BROWN_LIGHT,
                             text=[f"฿{stats[m]['spend']:,.0f}" for m in months],
                             textposition="outside"))
        fig.add_trace(go.Bar(x=month_labels, y=[stats[m]["revenue"] for m in months],
                             name="Revenue", marker_color=GOLD_HIGHLIGHT,
                             text=[f"฿{stats[m]['revenue']:,.0f}" for m in months],
                             textposition="outside"))
        fig.update_layout(height=340, margin=dict(l=20, r=20, t=20, b=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="Prompt, Sarabun", color=BROWN_MID),
                          legend=dict(orientation="h", y=-0.15),
                          barmode="group",
                          xaxis=dict(showgrid=False, color=MUTED),
                          yaxis=dict(showgrid=True, gridcolor="rgba(122,79,58,0.08)",
                                     color=MUTED, tickprefix="฿"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="month_revenue")

    with col_r:
        st.markdown(f"<div class='section-head'>ROAS <span class='accent'>Trend</span></div>"
                    f"<div class='section-rule'></div>", unsafe_allow_html=True)
        roas_vals = [stats[m]["roas"] for m in months]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=month_labels, y=roas_vals,
                                 mode="lines+markers+text",
                                 line=dict(color=BROWN_LIGHT, width=3, shape="spline"),
                                 marker=dict(size=14, color=BROWN_LIGHT,
                                             line=dict(color="white", width=2)),
                                 fill="tozeroy", fillcolor=f"rgba(122,79,58,0.10)",
                                 text=[f"{v:.2f}×" for v in roas_vals],
                                 textposition="top center",
                                 textfont=dict(size=14, color=BROWN_DEEP),
                                 hovertemplate="<b>%{x}</b><br>%{y:.2f}× ROAS<extra></extra>"))
        fig.add_hline(y=10, line_dash="dash", line_color=GOLD_HIGHLIGHT,
                      annotation_text="Target 10×", annotation_position="right",
                      annotation_font=dict(color=BROWN_DEEP))
        fig.update_layout(height=340, margin=dict(l=20, r=20, t=20, b=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="Prompt, Sarabun", color=BROWN_MID),
                          xaxis=dict(showgrid=False, color=MUTED),
                          yaxis=dict(showgrid=True, gridcolor="rgba(122,79,58,0.08)",
                                     color=MUTED, ticksuffix="×"),
                          showlegend=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="month_roas")

    # ── Inbox volume trend ──
    st.markdown(f"<div class='section-head'>Inbox Volume <span class='accent'>Growth</span></div>"
                f"<div class='section-rule'></div>", unsafe_allow_html=True)
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=month_labels, y=[stats[m]["inbox"] for m in months],
                          marker=dict(color=BROWN_LIGHT,
                                      line=dict(color=BROWN_DEEP, width=0.5)),
                          text=[f"{stats[m]['inbox']:,}" for m in months],
                          textposition="outside"))
    fig3.update_layout(height=280, margin=dict(l=20, r=20, t=20, b=20),
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                       font=dict(family="Prompt, Sarabun", color=BROWN_MID),
                       xaxis=dict(showgrid=False, color=MUTED),
                       yaxis=dict(showgrid=True, gridcolor="rgba(122,79,58,0.08)", color=MUTED),
                       showlegend=False)
    st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False}, key="month_inbox_vol")


# ════════════ DAILY TAB ════════════
with tab_daily:
    # ── Filter bar ─────────────────────────
    st.markdown(f"<div class='section-head'>เลือกช่วงวันที่ <span class='accent'>· Filter</span></div>"
                f"<div class='section-rule'></div>", unsafe_allow_html=True)

    all_dates = sorted({r["date"] for r in history if day_total(r, "spent") > 0})
    date_objs = [datetime.fromisoformat(d).date() for d in all_dates]
    min_d, max_d = (min(date_objs), max(date_objs)) if date_objs else (since, today)

    f1, f2 = st.columns([2, 1])
    with f1:
        date_range = st.date_input("ช่วงวันที่", value=(min_d, max_d),
                                    min_value=min_d, max_value=max_d,
                                    format="DD/MM/YYYY", key="dr")
    with f2:
        view_mode = st.radio("มุมมอง", ["ทั้งช่วง", "เฉพาะวัน"], horizontal=True, key="vm")

    # Apply filter
    filtered = history
    period_label = "ทั้งช่วง"
    if view_mode == "เฉพาะวัน":
        single_d = st.selectbox("วัน", options=date_objs[::-1],
                                 format_func=lambda d: d.strftime("%-d %B %Y"))
        filtered = [r for r in history if datetime.fromisoformat(r["date"]).date() == single_d]
        period_label = single_d.strftime("%-d %B %Y")
    elif isinstance(date_range, tuple) and len(date_range) == 2:
        d1, d2 = date_range
        filtered = [r for r in history
                    if d1 <= datetime.fromisoformat(r["date"]).date() <= d2]
        period_label = f"{d1.strftime('%-d %b')} – {d2.strftime('%-d %b %Y')}"

    if not filtered:
        st.info("ยังไม่มีข้อมูลในช่วงนี้")
    else:
        period_stats = month_stats(filtered)

        # ── Period banner ─────────────────────
        st.markdown(
            f"<div style='font-family:Italiana,Cormorant,serif;font-size:1.6rem;color:{BROWN_DEEP};"
            f"text-align:center;letter-spacing:2px;margin:1.5rem 0 0.2rem 0;'>"
            f"{period_label}</div>"
            f"<div style='font-family:Prompt,sans-serif;font-size:0.65rem;color:{MUTED};"
            f"text-align:center;letter-spacing:5px;text-transform:uppercase;font-weight:300;"
            f"margin-bottom:1.4rem;'>"
            f"{len(filtered)} {'วัน' if len(filtered) > 1 else 'วัน'} · selected period</div>",
            unsafe_allow_html=True
        )

        # ── 6 KPI cards (filtered data) ─────
        avg_spend = period_stats['spend'] / max(period_stats['days'], 1)
        st.markdown(f"<div class='kpi-grid'>"
            f"<div class='kpi'>"
            f"  <div class='kpi-label'>ยอดใช้จ่าย · Spend</div>"
            f"  <div class='kpi-value'>฿{period_stats['spend']:,.0f}</div>"
            f"  <div class='kpi-suffix'>{period_stats['days']} วัน · เฉลี่ย ฿{avg_spend:,.0f}/วัน</div>"
            f"</div>"
            f"<div class='kpi'>"
            f"  <div class='kpi-label'>รายได้ · Revenue</div>"
            f"  <div class='kpi-value'>฿{period_stats['revenue']:,.0f}</div>"
            f"  <div class='kpi-suffix'>จาก Pixel purchase events</div>"
            f"</div>"
            f"<div class='kpi'>"
            f"  <div class='kpi-label'>ROAS</div>"
            f"  <div class='kpi-value'>{period_stats['roas']:.2f}<span style='font-size:1.4rem;'>×</span></div>"
            f"  <div class='kpi-suffix'>เป้าหมาย 10× · ปัจจุบัน {period_stats['roas']/10*100:.0f}%</div>"
            f"</div>"
            f"<div class='kpi'>"
            f"  <div class='kpi-label'>Inbox</div>"
            f"  <div class='kpi-value'>{period_stats['inbox']:,}</div>"
            f"  <div class='kpi-suffix'>messaging conversations</div>"
            f"</div>"
            f"<div class='kpi'>"
            f"  <div class='kpi-label'>ต้นทุน / Inbox</div>"
            f"  <div class='kpi-value'>฿{period_stats['cpi']:,.0f}</div>"
            f"  <div class='kpi-suffix'>cost per messaging conv.</div>"
            f"</div>"
            f"<div class='kpi'>"
            f"  <div class='kpi-label'>Frequency</div>"
            f"  <div class='kpi-value'>{period_stats['freq']:.2f}<span style='font-size:1.4rem;'>×</span></div>"
            f"  <div class='kpi-suffix'>ครั้งที่คนเดิมเห็นโฆษณา</div>"
            f"</div>"
            f"</div>", unsafe_allow_html=True)

        # ── Mini stats row ─────────────────────
        m1, m2, m3 = st.columns(3)
        m1.markdown(f"<div class='mini-label'>การมองเห็น · Impressions</div>"
                    f"<div class='mini-value'>{period_stats['impr']:,}</div>", unsafe_allow_html=True)
        m2.markdown(f"<div class='mini-label'>การเข้าถึง · Reach</div>"
                    f"<div class='mini-value'>{period_stats['reach']:,}</div>", unsafe_allow_html=True)
        profit = period_stats['revenue'] - period_stats['spend']
        profit_label = "กำไร · Net" if profit >= 0 else "ขาดทุน · Net"
        profit_color = SUCCESS if profit >= 0 else ERROR
        m3.markdown(f"<div class='mini-label'>{profit_label}</div>"
                    f"<div class='mini-value' style='color:{profit_color}'>฿{profit:,.0f}</div>",
                    unsafe_allow_html=True)

        # ── Performance insights (best/worst day) ──
        if len(filtered) > 1:
            st.markdown(f"<div class='section-head'>วันที่โดดเด่น <span class='accent'>· Highlights</span></div>"
                        f"<div class='section-rule'></div>", unsafe_allow_html=True)

            # Compute best/worst by ROAS, spend, inbox
            day_metrics = []
            for d in filtered:
                sp = day_total(d, "spent")
                if sp <= 0:
                    continue
                inbox = day_total(d, "result")
                rev = day_total(d, "conversion")
                day_metrics.append({
                    "date": d["date"],
                    "label": datetime.fromisoformat(d["date"]).strftime("%-d %b"),
                    "spend": sp,
                    "inbox": int(inbox),
                    "revenue": rev,
                    "roas": (rev / sp) if sp else 0,
                    "cpi": (sp / inbox) if inbox else 0,
                })

            if day_metrics:
                best_roas = max(day_metrics, key=lambda x: x["roas"])
                worst_roas = min(day_metrics, key=lambda x: x["roas"])
                best_spend = max(day_metrics, key=lambda x: x["spend"])
                most_inbox = max(day_metrics, key=lambda x: x["inbox"])

                hl_card = lambda title, day, val, sub, color: (
                    f"<div class='month-card' style='border-color:{color}aa;'>"
                    f"<div style='font-family:Prompt,sans-serif;font-size:0.6rem;letter-spacing:2.5px;"
                    f"color:{color};text-transform:uppercase;font-weight:500;margin-bottom:0.7rem;'>{title}</div>"
                    f"<div class='month-card-name'>{day['label']}</div>"
                    f"<div style='font-family:Cormorant,serif;font-size:1.4rem;color:{BROWN_DEEP};"
                    f"font-weight:500;margin-top:0.4rem;'>{val}</div>"
                    f"<div style='font-family:Prompt,sans-serif;font-size:0.7rem;color:{MUTED};"
                    f"margin-top:0.3rem;font-weight:300;'>{sub}</div>"
                    f"</div>"
                )

                st.markdown("<div class='month-grid'>" +
                    hl_card("ROAS สูงสุด", best_roas, f"{best_roas['roas']:.2f}×",
                            f"จ่าย ฿{best_roas['spend']:,.0f} · ได้ ฿{best_roas['revenue']:,.0f}", SUCCESS) +
                    hl_card("Inbox มากสุด", most_inbox, f"{most_inbox['inbox']:,}",
                            f"จ่าย ฿{most_inbox['spend']:,.0f} · CPI ฿{most_inbox['cpi']:,.0f}", GOLD_HIGHLIGHT) +
                    hl_card("ใช้จ่ายสูงสุด", best_spend, f"฿{best_spend['spend']:,.0f}",
                            f"ROAS {best_spend['roas']:.2f}× · {best_spend['inbox']} inbox", BROWN_LIGHT) +
                    hl_card("ROAS ต่ำสุด", worst_roas, f"{worst_roas['roas']:.2f}×",
                            f"จ่าย ฿{worst_roas['spend']:,.0f} · ได้ ฿{worst_roas['revenue']:,.0f}", ERROR) +
                    "</div>", unsafe_allow_html=True)

            # ── Daily trend chart ──
            st.markdown(f"<div class='section-head'>แนวโน้มรายวัน <span class='accent'>· Daily Trend</span></div>"
                        f"<div class='section-rule'></div>", unsafe_allow_html=True)
            df_t = pd.DataFrame(day_metrics)

            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(x=df_t["label"], y=df_t["spend"], mode="lines",
                                     name="Spend",
                                     line=dict(color=BROWN_LIGHT, width=0),
                                     fill="tozeroy", fillcolor="rgba(122,79,58,0.15)",
                                     showlegend=False, hoverinfo="skip"))
            fig_trend.add_trace(go.Scatter(x=df_t["label"], y=df_t["spend"], mode="lines+markers",
                                     name="Spend",
                                     line=dict(color=BROWN_DEEP, width=2, shape="spline", smoothing=0.6),
                                     marker=dict(size=5, color=BROWN_LIGHT,
                                                 line=dict(color=IVORY, width=1.5)),
                                     hovertemplate="<b>%{x}</b><br>฿%{y:,.0f}<extra></extra>"))
            fig_trend.add_trace(go.Scatter(x=df_t["label"], y=df_t["revenue"], mode="lines+markers",
                                     name="Revenue",
                                     line=dict(color=GOLD_HIGHLIGHT, width=2, shape="spline", smoothing=0.6),
                                     marker=dict(size=5, color=GOLD_HIGHLIGHT,
                                                 line=dict(color=IVORY, width=1.5)),
                                     hovertemplate="<b>%{x}</b><br>฿%{y:,.0f}<extra></extra>"))
            fig_trend.update_layout(height=320, margin=dict(l=20, r=20, t=10, b=40),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(family="Prompt, Sarabun", color=BROWN_MID, size=11),
                              legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center",
                                          font=dict(color=BROWN_MID, size=10)),
                              xaxis=dict(showgrid=False, color=MUTED),
                              yaxis=dict(showgrid=True, gridcolor="rgba(122,79,58,0.06)",
                                         color=MUTED, tickprefix="฿", tickformat=",.0f"),
                              hovermode="x unified")
            st.plotly_chart(fig_trend, use_container_width=True,
                            config={"displayModeBar": False}, key="daily_trend")

        # ── Top campaigns ─────────────────────
        camp_agg = {}
        for d in filtered:
            for ad in d["ads"]:
                name = str(ad.get("campaign", "—"))
                sp = float(ad.get("spent", 0) or 0)
                rs = float(ad.get("result", 0) or 0)
                rv = float(ad.get("conversion", 0) or 0)
                if name not in camp_agg:
                    camp_agg[name] = {"spend": 0, "inbox": 0, "revenue": 0, "days": 0}
                camp_agg[name]["spend"] += sp
                camp_agg[name]["inbox"] += rs
                camp_agg[name]["revenue"] += rv
                camp_agg[name]["days"] += 1

        top_camps = sorted(camp_agg.items(), key=lambda x: x[1]["spend"], reverse=True)[:5]
        if top_camps and len(top_camps) > 1:
            st.markdown(f"<div class='section-head'>แคมเปญที่ทำงาน <span class='accent'>· Top Campaigns</span></div>"
                        f"<div class='section-rule'></div>", unsafe_allow_html=True)

            camp_rows = []
            for name, st_d in top_camps:
                roas = (st_d["revenue"] / st_d["spend"]) if st_d["spend"] else 0
                cpi = (st_d["spend"] / st_d["inbox"]) if st_d["inbox"] else 0
                camp_rows.append({
                    "แคมเปญ": name[:50],
                    "ใช้จ่าย": st_d["spend"],
                    "Inbox": int(st_d["inbox"]),
                    "ต้นทุน/Inbox": cpi,
                    "รายได้": st_d["revenue"],
                    "ROAS": roas,
                })
            cdf = pd.DataFrame(camp_rows)
            st.dataframe(
                cdf.style.format({
                    "ใช้จ่าย": "฿{:,.0f}",
                    "ต้นทุน/Inbox": "฿{:,.0f}",
                    "รายได้": "฿{:,.0f}",
                    "ROAS": "{:.2f}×",
                }),
                use_container_width=True, hide_index=True,
                height=min(40 + 38 * len(camp_rows), 260),
                key="top_camp_table",
            )

        # ── Daily breakdown table ──────────────
        st.markdown(f"<div class='section-head'>รายละเอียดรายวัน <span class='accent'>· Daily Breakdown</span></div>"
                    f"<div class='section-rule'></div>", unsafe_allow_html=True)

        rows = []
        for d in filtered:
            sp = day_total(d, "spent")
            rs = day_total(d, "result")
            rv = day_total(d, "conversion")
            top = max(d["ads"], key=lambda a: float(a.get("spent", 0) or 0))
            rows.append({
                "วันที่": datetime.fromisoformat(d["date"]).strftime("%-d %b %Y"),
                "ยอดใช้": sp, "Inbox": int(rs),
                "ต้นทุน/Inbox": (sp / rs) if rs else 0,
                "รายได้": rv,
                "ROAS": (rv / sp) if sp else 0,
                "การมองเห็น": int(day_total(d, "impression")),
                "เข้าถึง": int(day_total(d, "reach")),
                "Top Campaign": str(top.get("campaign", ""))[:35],
            })
        tdf = pd.DataFrame(rows[::-1])
        st.dataframe(
            tdf.style.format({
                "ยอดใช้": "฿{:,.2f}",
                "ต้นทุน/Inbox": "฿{:,.2f}",
                "รายได้": "฿{:,.2f}",
                "ROAS": "{:.2f}×",
                "การมองเห็น": "{:,}",
                "เข้าถึง": "{:,}",
            }),
            use_container_width=True, hide_index=True, height=440,
            key="daily_table",
        )


# ── Footer ────────────────────────────────
st.markdown(f"""
<div class='footer'>
    <div class='footer-divider'></div>
    Everly Clinic &nbsp;·&nbsp; นายหัว กรุ๊ป &nbsp;·&nbsp; Live from Meta Marketing API
</div>
""", unsafe_allow_html=True)
