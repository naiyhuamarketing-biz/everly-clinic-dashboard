# 🆘 Disaster Recovery — Everly Clinic Dashboard

**ถ้าทุกอย่างพัง / สูญหาย / ลืม credentials — เริ่มที่นี่**

---

## Scenario A: Dashboard เปิดไม่ได้

### 1. เช็คว่าใครพัง
```bash
# ✓ ป๊กดี = Render ทำงาน + Meta + LINE ครบ
curl https://everly-clinic.onrender.com/api/health
curl https://everly-clinic.onrender.com/api/everly/keepalive
curl https://everly-clinic.onrender.com/api/everly/token-info
curl https://everly-clinic.onrender.com/api/line/status
```

### 2. ดู Render logs
- เข้า https://dashboard.render.com/web/srv-d7rjoj77f7vs73d1f2dg
- กด tab **"Logs"** ดู error จริง

### 3. Manual deploy ใหม่
- Render → Manual Deploy → "Clear build cache & deploy"

---

## Scenario B: FB Token หมดอายุ

### Trigger:
- LINE alert "TOKEN EXPIRES IN X DAYS" หรือ "TOKEN INVALID"
- ตัวเลขใน dashboard เป็น 0 หมด

### Fix:
1. เปิด terminal บน Mac
2. ไปที่โฟลเดอร์ Glow:
   ```bash
   cd ~/Desktop/Code/ads-report
   ./.venv/bin/python refresh_token.py
   ```
3. Script จะ print token ใหม่ + อายุ
4. Copy token → Render → Environment → แก้ `FB_ACCESS_TOKEN` → Save

> ถ้า refresh script พังด้วย → ไปสร้าง token ใหม่ที่ https://developers.facebook.com/tools/debug/accesstoken/

---

## Scenario C: GitHub repo สูญหาย

### Local backup:
- โค้ดอยู่ที่ `~/Desktop/Code/ads-report-everly/`
- ถ้า Mac เสีย → repo อยู่บน https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard

### ถ้า Repo ถูกลบ:
```bash
cd ~/Desktop/Code/ads-report-everly
git remote remove origin
gh repo create naiyhuamarketing-biz/everly-clinic-dashboard --public --source=. --push
```

---

## Scenario D: Render ปิดบริการ / เปลี่ยน policy

### Backup hosting (ฟรีเหมือนกัน):
- **Railway** — railway.app (deploy ผ่าน GitHub ในนาที)
- **Fly.io** — fly.io (free tier 3 VMs)

### Migration steps:
1. ไป Railway → New Project from GitHub repo
2. เพิ่ม env vars ทั้งหมด (copy จาก Render)
3. Deploy
4. แก้ URL ใน workflows (`.github/workflows/*.yml`) จาก `everly-clinic.onrender.com` → URL ใหม่
5. Push → workflows ตามไปที่ใหม่

---

## Scenario E: LINE bot โดนเตะออกจากกลุ่ม

### Symptoms:
- HTTP 200 จาก /api/line/status
- แต่ข้อความไม่เข้ากลุ่ม

### Fix:
1. ในกลุ่ม LINE → invite bot **ทีมคุณฟา (AI)** กลับเข้าใหม่
2. Render env vars ไม่ต้องแก้ (group_id เดิมยังใช้ได้)

### ถ้า group_id เปลี่ยน:
- ทำตาม `get_group_id.py` ใน repo

---

## 🔐 Credentials ทั้งหมด (จดไว้ที่ปลอดภัย!)

```
GitHub user: naiyhuamarketing-biz
Email: naiy.hua.marketing@gmail.com

GitHub repo: https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard
Render service ID: srv-d7rjoj77f7vs73d1f2dg
Render URL: https://everly-clinic.onrender.com

FB App ID: 966060955830858
FB App Secret: 3e691fecc3d944143a01c0bc62347c6c
FB Account Everly: 1965556974211662
FB Token: ดูใน Render env vars

LINE Group "หลังบ้าน Everly": Cadcdbc4edb28e9f1441e5b2c16f78628
LINE Channel Token: ดูใน Render env vars
```

---

## 🚨 ติดต่อ recovery

ถ้าจริง ๆ ทำเองไม่ได้:
1. โพส issue ที่ GitHub repo
2. หา dev มาช่วย — ส่ง repo URL + RECOVERY.md ให้
3. ทุกอย่างมีระบุไว้ในนี้แล้ว · ใครก็ทำต่อได้
