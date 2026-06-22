# 🌿 Everly Clinic · Daily Ads Report

Live FastAPI dashboard ที่ดึงข้อมูล Meta Marketing API ของ Everly Clinic
แสดงรายวัน + เปรียบเทียบรายเดือน + ส่ง LINE 00:00 อัตโนมัติทุกคืน
โดยรายงานเป็นข้อมูลของวันที่เพิ่งจบไป และยอดสะสมตั้งแต่วันที่ 1 ถึงวันที่รายงาน

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

## 📲 LINE Auto-send (00:00 ทุกคืน)

GitHub Actions cron ยิง endpoint `/api/cron/run` ทุกวันช่วง 23:59-00:55 เวลาไทย พร้อม backup หลังเที่ยงคืน

ตัวอย่าง: ถ้าวันนี้วันที่ 21 ระบบจะส่ง Report ของวันที่ 20 ทั้งวัน และยอดสะสมวันที่ 1-20

ระบบนี้บังคับส่งเข้า LINE group ของ Everly เท่านั้น (`LINE_GROUP_ID_EVERLY`)

ห้ามใช้ `LINE_GROUP_ID` รวมกับแบรนด์อื่น เพราะเสี่ยงส่งรายงานลูกค้าเข้าผิดกลุ่ม

## 📲 LINE Front Group (ลูกค้า / หน้าบ้าน)

หน้าบ้าน Everly ใช้ตัวแปรแยก `LINE_GROUP_ID_EVERLY_FRONT` และต้องส่งผ่านระบบอนุมัติเท่านั้น:

1. พิมพ์ `test` ในกลุ่ม LINE → webhook จะตอบ groupId
2. ถ้าเป็นกลุ่มหน้าบ้าน Everly ให้ตั้ง `LINE_GROUP_ID_EVERLY_FRONT`
3. ส่ง preview เข้าหลังบ้านผ่าน `/api/everly/front-line/review`
4. หลังบ้านตรวจแล้วพิมพ์ `CF`
5. ระบบจึงส่งข้อความ safe-for-client ไปหน้าบ้าน

ห้ามส่งหน้าบ้านโดยตรงก่อน CF และต้องตั้ง `LINE_CHANNEL_SECRET` เพื่อให้ webhook ตรวจลายเซ็น LINE ได้จริง

### ใช้ LINE channel ร่วมกับหลายแบรนด์

ถ้า LINE channel เดียวกันถูกใช้กับหลายแบรนด์ ห้ามให้โปรเจกต์แต่ละแบรนด์ตั้ง webhook เอง เพราะ LINE มี webhook URL ได้ทีละ 1 URL เท่านั้น และโปรเจกต์ที่ตั้งทีหลังจะทับของแบรนด์อื่นทันที

ค่าเริ่มต้นของ Everly จึงปิดการ sync webhook ไว้ (`ALLOW_LINE_WEBHOOK_SYNC=false`) เพื่อไม่ทำลายงานแบรนด์อื่น

โครงที่ถูกต้องสำหรับหลายแบรนด์:

1. ตั้ง LINE webhook ไปที่ router กลางเพียงที่เดียว
2. Router กลางตรวจ `groupId`
3. ถ้าเป็นกลุ่มหลังบ้าน Everly และพิมพ์ `CF` ให้ router เรียก:
   `POST https://everly-clinic.onrender.com/api/everly/line-router-command`
4. ส่ง JSON:

```json
{
  "group_id": "LINE groupId",
  "text": "CF",
  "reply_token": "LINE replyToken ถ้ามี"
}
```

Header ต้องมี `X-Cron-Secret: <CRON_SECRET ของ Everly>`

ถ้า LINE channel เป็นของ Everly แบรนด์เดียวจริง ๆ เท่านั้น จึงค่อยตั้ง `ALLOW_LINE_WEBHOOK_SYNC=true` แล้วใช้ `/api/line/webhook-config/sync`

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
FB_ACCESS_TOKEN=<set in Render only>
FB_APP_ID=<set in Render only>
FB_APP_SECRET=<set in Render only>
FB_ACCOUNT_EVERLY=1965556974211662
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_GROUP_ID_EVERLY=...
LINE_GROUP_ID_EVERLY_FRONT=...
LINE_GROUP_NAME_EVERLY_FRONT=หน้าบ้าน Everly
LINE_CHANNEL_SECRET=...
CRON_SECRET=...
ALLOW_LINE_WEBHOOK_SYNC=false
```

Before deploying changes that affect LINE, cron, or security, run:

```bash
python scripts/brand_guard.py
python scripts/deploy_preflight.py
```

`deploy_preflight.py` must pass before deploy. If it reports `Render CRON_SECRET is missing`,
set `CRON_SECRET` in Render to the same value used in GitHub Actions first.

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
| `lib/meta_loader.py` | Meta Marketing API client (cache 60 sec) |
| `lib/fb_ads.py` | Top ads query |
| `lib/notify.py` | LINE push (`send_line_summary`) |
| `render.yaml` | Render blueprint (web service) |
| `Procfile` | Render start command |
| `.github/workflows/daily-line.yml` | GitHub Actions cron 00:00 BKK |
| `requirements.txt` | Python deps |
| `runtime.txt` | python-3.11 (Render) |
| `docs/` | Master reference, recovery guide, and Facebook token notes |

---

## ⚠️ Token expiry

Token long-lived expires `~2026-07-01` (60 days).

**Auto-extend:** ถ้าเปิด dashboard ทุก 24 ชม. → Render fetches Meta API → token ต่ออายุเอง

**Manual refresh:** ถ้า token หมด → รัน `python refresh_token.py` ในโปรเจกต์ Everly นี้ → copy token ใหม่ → Render env vars → save

---

## 🌿 Brand palette

Brown deep `#5A3724` · Brown mid `#7A4F3A` · Brown light `#9B7558` · Tan `#C9B399` · Champagne `#E8DAC2` · Cream `#F0E5D0` · Gold accent `#B8945F`

Fonts: **Italiana** (hero "everly") · **Cormorant Garamond** (numbers) · **Prompt** (Thai loopless body)
