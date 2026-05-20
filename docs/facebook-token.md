# 🔑 Setup Facebook Marketing API Token

ทำครั้งเดียวใช้ได้ตลอดไป — token ใช้ได้นาน 60 วัน (แล้วต่ออายุได้ผ่าน script)

---

## ขั้นตอน (ใช้เวลาประมาณ 10 นาที)

### 1️⃣ สร้าง Facebook App

เปิด <https://developers.facebook.com/apps/>

→ คลิก **Create App** (มุมขวาบน)

→ Use case: เลือก **Other**

→ App type: เลือก **Business**

→ App name: ใส่อะไรก็ได้ เช่น `Naihua Ads Report`

→ Contact email: อีเมลคุณ

→ Business portfolio: เลือก **นายหัว 2497** (หรือ business ที่มีสิทธิ์ดู Ad Account)

→ คลิก **Create app**

---

### 2️⃣ Add Marketing API Product

ในหน้า App ที่สร้างเสร็จ → ไปที่ left sidebar `Add products to your app`

→ หา **Marketing API** → คลิก **Set up**

---

### 3️⃣ Generate Access Token

ใน sidebar → **Marketing API** → **Tools**

→ เลื่อนลงไปหา **Get Access Token**

→ ติ๊ก permissions:
   - ✅ `ads_read`
   - ✅ `ads_management` (ถ้าต้องการให้ระบบ pause/run ads ได้ในอนาคต)
   - ✅ `business_management`

→ คลิก **Get Token**

→ จะได้ string ยาวๆ เช่น `EAAB...` — **copy เก็บไว้**

> ⚠️ Token นี้อายุ ~1 ชั่วโมง ต้องแลกเป็น long-lived token ในขั้นตอน 4

---

### 4️⃣ แลกเป็น Long-Lived Token (อายุ 60 วัน)

เปิด terminal:

```bash
cd ~/Desktop/Code/ads-report
source .venv/bin/activate

# แทน <SHORT_TOKEN> ด้วย token ที่เพิ่ง copy
# แทน <APP_ID> และ <APP_SECRET> ที่หาได้จาก
#   App Dashboard → Settings → Basic
SHORT="<SHORT_TOKEN>"
APP_ID="<APP_ID>"
APP_SECRET="<APP_SECRET>"

curl -G "https://graph.facebook.com/v20.0/oauth/access_token" \
  --data-urlencode "grant_type=fb_exchange_token" \
  --data-urlencode "client_id=$APP_ID" \
  --data-urlencode "client_secret=$APP_SECRET" \
  --data-urlencode "fb_exchange_token=$SHORT"
```

จะได้ JSON response เช่น:
```json
{"access_token":"EAAB...LONG...","token_type":"bearer","expires_in":5183999}
```

`access_token` ตัวนี้คือ long-lived (60 วัน)

---

### 5️⃣ ใส่ใน .env

```bash
nano .env
```

แก้ 4 บรรทัดนี้:
```
FB_ACCESS_TOKEN=EAAB...LONG_TOKEN...
FB_APP_ID=1234567890
FB_APP_SECRET=abcdef1234567890
FB_ACCOUNT_GLOW=24221442597468246   # มีอยู่แล้ว
```

save (ctrl+O, enter, ctrl+X)

---

### 6️⃣ ทดสอบ

```bash
python verify.py --date 2026-04-15
```

ถ้า token ใช้ได้จะเห็นผลลัพธ์เทียบ Meta vs xlsx เช่น:
```
Date          Meta Spend  xlsx Spend       Δ   Meta Inbox  xlsx Inbox       Δ
2026-04-15      2752.30     2752.00    +0.0%        17          17    +0.0%
```

✅ ถ้าตัวเลขตรงกัน 100% = data accurate
⚠️ ถ้า Δ > 5% = ทีมกรอก xlsx ไม่ตรง (auto-detect แล้ว)

---

### 7️⃣ ดึงข้อมูล April ทั้งเดือนเทียบ

```bash
python verify.py
```

หรือ range:
```bash
python verify.py --range 2026-04-01:2026-04-30
```

---

## หลังจาก setup เสร็จ — ทำอะไรต่อได้บ้าง

1. **Auto-pull ทุกคืน 00:00** — `daily_report.py` จะดึง Meta API ตรงๆ ไม่ต้องผ่าน xlsx
2. **Dashboard live data** — เปลี่ยน `MOCK_MODE=false` ใน `.env` แล้วรีเฟรช → ดึงจาก Meta สด
3. **Auto-detect ความผิดพลาดของทีม** — verify.py ถ้าเจอ diff > 15% ส่งแจ้ง LINE

---

## หาก Token หมดอายุ (ทุก 60 วัน)

```bash
python refresh_token.py
```

(script นี้ผมจะเขียนให้ตอนคุณส่ง token แรกมา)
