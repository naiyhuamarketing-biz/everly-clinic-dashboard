# 🌿 Everly Clinic Dashboard — Master Reference
อัปเดต: 3 พฤษภาคม 2026 · DEPLOYED LIVE

---

## 🔗 ลิงก์ที่ต้องรู้ (สำคัญที่สุด!)

| | URL |
|---|---|
| 🌐 **ลิงก์เปิด dashboard** | **https://everly-clinic.onrender.com** |
| 🐙 GitHub repo | https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard |
| 🔧 Render dashboard | https://dashboard.render.com/web/srv-d7rjoj77f7vs73d1f2dg |
| ⏰ GitHub Actions runs | https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard/actions |
| 📂 Local code | `~/Desktop/Code/ads-report-everly/` |

---

## ✅ ทำงานอัตโนมัติแล้ว (Mac ปิดก็ใช้ได้)

| ฟีเจอร์ | สถานะ |
|---|---|
| Dashboard เปิดได้ 24/7 | ✅ Render free tier |
| Live Meta API (รีเฟรชสด ~1 นาที) | ✅ |
| Auto refresh ทุกครั้ง user กด refresh | ✅ |
| **ส่ง LINE 00:00 ทุกคืน** | ✅ GitHub Actions cron |
| Auto-redeploy เมื่อ push code | ✅ |

---

## ⏰ LINE 00:00 BKK auto-send

- **Workflow:** `.github/workflows/daily-line.yml`
- **Schedule:** `59 16 * * *` + backup retries (UTC = 23:59 Bangkok primary)
- **Endpoint:** `/api/cron/run`
- **Report date:** วันที่เพิ่งจบไป เช่น 21 พ.ค. 00:00 จะรายงาน 20 พ.ค. และสะสม 1-20 พ.ค.
- **กลุ่มที่ส่ง:** Everly Clinic LINE group เท่านั้น
- **ทดสอบแล้ว:** ✅ `25279508679` workflow run = success
- **Trigger manual:** GitHub Actions tab → "Run workflow"

### Format ที่ส่ง
```
EVERLY CLINIC — DAILY REPORT

Report ประจำวัน (3 พฤษภาคม 2026)

วันที่รายงาน ใช้เงิน: ฿xxx.xx
คนทัก: x คน
เฉลี่ยต่อคนทัก: ฿xx
ยอดขาย: ฿xxx
กำไร/ขาดทุน: ±฿xxx

============
Report สะสมตั้งแต่ต้นเดือน - ถึงวันที่รายงาน
ภาพรวม ใช้เงินรวม: ...
```

---

## 🔑 Credentials (ใน Render env vars)

```
FB_ACCESS_TOKEN=<set in Render only>
FB_APP_ID=<set in Render only>
FB_APP_SECRET=<set in Render only>
FB_ACCOUNT_EVERLY=1965556974211662
LINE_CHANNEL_ACCESS_TOKEN=<set in Render only>
LINE_GROUP_ID_EVERLY=<Everly LINE group id only>
CRON_SECRET=<same value in Render and GitHub Actions secrets>
```

**Token expires:** ~2026-07-01 (60 days)
- ถ้าเปิด dashboard ทุก 24 ชม → token auto-extend
- ถ้าหมด: รัน `~/Desktop/Code/ads-report-everly/refresh_token.py` → copy token ใหม่ → Render env → save

---

## 🆘 Troubleshooting

| ปัญหา | วิธีแก้ |
|---|---|
| Dashboard เปิดช้า ครั้งแรก ~30 วิ | Cold start (Render free tier) — รอ ปกติ |
| ตัวเลขไม่อัปเดต | กดปุ่ม "↻ Refresh" ใน dashboard |
| LINE ไม่ส่ง 00:00 | เช็ค https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard/actions |
| Token error | refresh token + อัปเดต Render env |
| Render down | https://status.render.com |

### Manual ทดสอบ LINE ส่ง
```bash
curl -X POST https://everly-clinic.onrender.com/api/cron/run \
  -H "X-Cron-Secret: <CRON_SECRET>"
```

### Manual trigger GitHub Actions cron
- เปิด https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard/actions
- เลือก "Daily LINE notification"
- กด "Run workflow"

---

## 🚀 Roadmap (อยากทำต่อ)

- [x] Deploy 24/7 ✅
- [x] LINE 00:00 auto ✅
- [ ] ใส่โลโก้จริงแทน "e" monogram (save `assets/everly_logo.png`)
- [ ] ยืนยันว่า Render ใช้ `LINE_GROUP_ID_EVERLY` ของกลุ่มหลังบ้าน Everly เท่านั้น
- [ ] AI Insights — narrative สรุปเดือน
- [ ] เพิ่มคลินิกอื่นในอนาคตโดยแยก repo/env ให้ชัดเจน

---

## 🔐 ห้ามแชร์

- FB App Secret · FB Access Token · LINE Channel Token · GitHub PAT
- ถ้า leak: revoke ทันทีที่ developers.facebook.com / line developer console / github settings
