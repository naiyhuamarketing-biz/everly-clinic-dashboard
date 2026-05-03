# 🌿 Everly Clinic · Daily Ads Report

Live FastAPI dashboard ที่ดึงข้อมูล Meta Marketing API ของ Everly Clinic
แสดงรายวัน + เปรียบเทียบรายเดือน + ส่ง LINE 23:59 อัตโนมัติทุกคืน

---

## 🔗 ลิงก์สำคัญ

| | URL |
|---|---|
| **Live dashboard** | **https://everly-clinic.onrender.com** |
| GitHub repo | https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard |
| Render dashboard | https://dashboard.render.com/web/srv-d7rjoj77f7vs73d1f2dg |
| GitHub Actions cron | https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard/actions |

---

## 📊 Dashboard structure (5 sections, all LIVE)

1. **Performance Overview** — KPI cards (Spend / Revenue / ROAS / Inbox / CPI / Frequency)
2. **Daily Operations** — date filter → smartboard
3. **Top Highlights** — top ads by ROAS (range filter)
4. **Performance Trend** — month-over-month + ROAS trend + Spend vs Revenue
5. **Daily Report** — LINE-ready text (with Copy + → ส่ง LINE buttons)

---

## 📲 LINE Auto-send (23:59 ทุกคืน)

GitHub Actions cron ยิง endpoint `/api/everly/send-daily-line` ทุกวัน 16:59 UTC = 23:59 BKK

ตอนนี้ส่งเข้า LINE group เดียวกับ Glow (ใช้ `LINE_GROUP_ID`)

ถ้าอยากแยกกลุ่มของ Everly เอง ตั้ง `LINE_GROUP_ID_EVERLY` ใน Render env vars แทน

---

## 🛠 Tech stack

- Python 3.11 (FastAPI + uvicorn)
- HTML + Tailwind (CDN) + Chart.js
- facebook-business SDK
- Render (web service free tier)
- GitHub Actions (cron, free for public repo)

---

## 🔑 Env vars (set in Render dashboard)

```
FB_ACCESS_TOKEN=EAANuoJg...
FB_APP_ID=966060955830858
FB_APP_SECRET=...
FB_ACCOUNT_EVERLY=1965556974211662
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_GROUP_ID=Ca5ee252c90c5b73799813eed13f0ec6d   (Glow/Everly shared)
# หรือ
LINE_GROUP_ID_EVERLY=...                          (Everly-only — overrides above)
```

---

## 💻 Run locally

```bash
cd ~/Desktop/Code/ads-report-everly
./.venv/bin/python api_server.py    # FastAPI :8000
# หรือ Streamlit รุ่นแรก
./.venv/bin/streamlit run dashboard.py --server.port 8502
```

---

## 📁 Files

| File | Purpose |
|---|---|
| `api_server.py` | ⭐ FastAPI server — serves HTML + Meta API + LINE |
| `dashboard.html` | ⭐ Single-page Tailwind + Chart.js dashboard |
| `dashboard.py` | (legacy) Streamlit version of the same data |
| `lib/meta_loader.py` | Meta Marketing API client (cache 10 min) |
| `lib/fb_ads.py` | Top ads query |
| `lib/notify.py` | LINE push (`send_line_summary`) |
| `render.yaml` | Render blueprint (web service) |
| `Procfile` | Render start command |
| `.github/workflows/daily-line.yml` | GitHub Actions cron 23:59 BKK |
| `requirements.txt` | Python deps |
| `runtime.txt` | python-3.11 (Render) |

---

## ⚠️ Token expiry

Token long-lived expires `~2026-07-01` (60 days).

**Auto-extend:** ถ้าเปิด dashboard ทุก 24 ชม. → Render fetches Meta API → token ต่ออายุเอง

**Manual refresh:** ถ้า token หมด → รัน `python refresh_token.py` (ของ Glow) ที่ Mac → copy token ใหม่ → Render env vars → save

---

## 🌿 Brand palette

Brown deep `#5A3724` · Brown mid `#7A4F3A` · Brown light `#9B7558` · Tan `#C9B399` · Champagne `#E8DAC2` · Cream `#F0E5D0` · Gold accent `#B8945F`

Fonts: **Italiana** (hero "everly") · **Cormorant Garamond** (numbers) · **Prompt** (Thai loopless body)
