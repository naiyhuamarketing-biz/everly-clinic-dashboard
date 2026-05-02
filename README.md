# 🌿 Everly Clinic · Daily Ads Report

Streamlit dashboard ดึงข้อมูล Meta Marketing API ของ **Everly Clinic** มาแสดงรายวัน + เปรียบเทียบรายเดือน

---

## 🚀 Quick start

```bash
cd ~/Desktop/Code/ads-report-everly
bash INSTALL.sh
source .venv/bin/activate
streamlit run dashboard.py --server.port 8502
```

เปิด <http://localhost:8502> (ใช้ port 8502 เพื่อไม่ชนกับ Glow ที่อยู่ port 8501)

---

## 🔑 .env

```
FB_ACCESS_TOKEN=EAAB...
FB_APP_ID=966060955830858
FB_APP_SECRET=...
FB_ACCOUNT_EVERLY=1965556974211662
```

> Token เป็น long-lived (60 วัน) — ใช้ token เดียวกันกับ Glow ได้ เพราะ App เดียวกัน

---

## 📁 Files

| File | Purpose |
|---|---|
| `dashboard.py` | Streamlit dashboard หลัก |
| `lib/meta_loader.py` | ดึงข้อมูลจาก Meta API |
| `verify.py` | เช็คตัวเลขรายวันผ่าน Meta API |
| `refresh_token.py` | ต่ออายุ FB token |
| `assets/everly_logo.png` | โลโก้แบรนด์ |
| `.env` | 🔒 Secrets — ห้ามแชร์ |

---

## 🎨 Brand palette

Brown deep `#5A3724` · Brown mid `#7A4F3A` · Brown light `#9B7558` · Tan `#C9B399` · Champagne `#E8DAC2` · Cream `#F0E5D0` · Gold accent `#B8945F` · Ink `#3A2517`

ฟอนต์: Cormorant Garamond italic (heading) + Sarabun (body)

---

## ⏰ Token expiry

Token หมด **1 ก.ค. 2026** — ต่ออายุได้:
```bash
.venv/bin/python refresh_token.py
```

ถ้าใช้ dashboard ทุก 24 ชม. → token จะ auto-extend ตัวเอง
