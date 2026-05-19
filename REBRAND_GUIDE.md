# 📦 Rebrand Guide — Everly → New Brand

This guide walks you through cloning the Everly Clinic dashboard and
re-branding it for a new clinic / business.

---

## 🚀 Quick Start (15 minutes)

```bash
# 1. Clone the repo
git clone https://github.com/naiyhuamarketing-biz/everly-clinic-dashboard.git yeyawa-dashboard
cd yeyawa-dashboard

# 2. Create new repo on GitHub for the new brand
#    (https://github.com/new — name it e.g. "yeyawa-dashboard")
git remote remove origin
git remote add origin https://github.com/YOUR_ORG/yeyawa-dashboard.git
git push -u origin main

# 3. Install dependencies
bash INSTALL.sh

# 4. Copy + edit .env
cp .env.example .env
# edit .env with NEW brand's FB credentials + LINE tokens
```

---

## 🎨 Files to Customize for Rebrand

### 1. Brand identity (`dashboard.html`)

**Search and replace** these strings throughout `dashboard.html`:

| Old (Everly) | New (เยียวยา / Yeyawa) |
|---|---|
| `Everly Clinic` | `เยียวยา คลินิก` |
| `everly` (in copyrights / footer) | `yeyawa` |
| `MAY 2026` | `[current month]` |

**Colors** — find this block near the top of `<style>`:

```css
:root {
  --rg-deepest: #4A2918;   /* Brown earth darkest */
  --rg-deep: #6B4330;      /* Brown earth deep */
  --rg-mid: #8A5B42;       /* Brown earth mid */
  --rg-light: #A87D5F;     /* Brown earth light */
  --rg-pale: #C9A98A;      /* Brown earth pale */
  --gold: #C9A968;         /* Accent gold */
  --warm: #D0784A;         /* Accent warm */
  --cream: #EFE5D2;        /* Background cream */
  --ivory: #F8F2E8;        /* Background ivory */
  /* … */
}
```

→ Replace with new brand's palette.

### 2. Logo (`assets/logos/everly.png`)

Replace with `yeyawa.png` (or your brand's logo).

In `dashboard.html`, change:
```html
<img src="/assets/logos/everly.png" />
```
→
```html
<img src="/assets/logos/yeyawa.png" />
```

### 3. FB Credentials (`.env`)

```bash
FB_ACCESS_TOKEN=<new brand's long-lived FB token>
FB_APP_ID=<new brand's FB app ID>
FB_APP_SECRET=<new brand's app secret>
FB_ACCOUNT_EVERLY=<rename + change to new ad account ID>
FB_PAGE_ID_EVERLY=<rename + change to new page ID>
```

⚠️ Rename `*_EVERLY` to `*_YEYAWA` and update references in `api_server.py`.

### 4. LINE Setup (`.env`)

```bash
LINE_CHANNEL_ACCESS_TOKEN=<new brand's LINE messaging API token>
LINE_GROUP_ID_EVERLY=<rename + change to new group ID>
```

### 5. Render Service (`render.yaml`)

```yaml
services:
  - type: web
    name: yeyawa-clinic  # ← change from everly-clinic
```

Then in Render dashboard:
1. Create new service from this repo
2. Set env vars listed above
3. Deploy

### 6. GitHub Actions (`.github/workflows/`)

In all 4 workflow files, find and replace the Render URL:

| Old | New |
|---|---|
| `https://everly-clinic.onrender.com` | `https://yeyawa-clinic.onrender.com` |

Files to update:
- `keepalive.yml`
- `daily-line.yml`
- `health-monitor.yml`
- `token-watch.yml`

---

## 🛠 Automated Rebrand Script

Run this from the new repo's root to do most replacements at once:

```bash
#!/bin/bash
# rebrand.sh — Bulk find-replace for new brand
# Edit OLD_BRAND and NEW_BRAND first, then run.

OLD_BRAND="everly"
NEW_BRAND="yeyawa"
OLD_RENDER_URL="https://everly-clinic.onrender.com"
NEW_RENDER_URL="https://yeyawa-clinic.onrender.com"

# Search-replace in all source files (case-sensitive)
find . -type f \( -name "*.py" -o -name "*.html" -o -name "*.yml" -o -name "*.md" -o -name "*.toml" \) \
  ! -path "./.git/*" ! -path "./.venv/*" ! -path "./node_modules/*" \
  -exec sed -i.bak "s|$OLD_RENDER_URL|$NEW_RENDER_URL|g" {} +

find . -type f \( -name "*.py" -o -name "*.html" -o -name "*.yml" -o -name "*.md" -o -name "*.toml" \) \
  ! -path "./.git/*" ! -path "./.venv/*" ! -path "./node_modules/*" \
  -exec sed -i.bak "s|$OLD_BRAND|$NEW_BRAND|g" {} +

# Clean up backup files
find . -name "*.bak" -delete

echo "✓ Rebrand complete. Review changes with: git diff"
```

---

## 📋 Project File Structure

```
.
├── api_server.py              # Main FastAPI backend (~1900 lines)
├── dashboard.html             # Single-page dashboard UI (~1500 lines)
├── daily_report.py            # Standalone CLI report builder
├── refresh_token.py           # FB token refresh helper
├── requirements.txt           # Python dependencies
├── render.yaml                # Render deployment config
├── Procfile                   # Render start command
├── INSTALL.sh                 # One-command local setup
├── .env.example               # Template for credentials
├── .github/workflows/         # GitHub Actions cron jobs
│   ├── keepalive.yml          #   Render warm + LINE auto-send
│   ├── daily-line.yml         #   Daily LINE backup cron
│   ├── health-monitor.yml     #   Health check every 6h
│   └── token-watch.yml        #   FB token expiry warning
├── assets/logos/              # Brand logos (replace per brand)
├── lib/                       # Helper modules
│   ├── meta_loader.py         #   FB Marketing API wrapper
│   └── notify.py              #   LINE Messaging API wrapper
└── outputs/                   # Generated reports (gitignored)
```

---

## 🔑 Required Credentials

You'll need to obtain these for the new brand:

### Facebook
1. **FB App** at https://developers.facebook.com/apps/
   - Need: App ID + App Secret
   - Enable Marketing API + Messenger product
2. **FB Ad Account** ID (e.g. `act_123456789`)
3. **FB Page** ID (for the brand's clinic page)
4. **Long-lived Access Token** with scopes:
   - `ads_management`, `ads_read`, `business_management`
   - `pages_show_list`, `pages_messaging`, `pages_read_engagement`

### LINE
1. **LINE Messaging API channel** at https://developers.line.biz
2. **Channel Access Token** (long-lived)
3. **Group ID** of the destination LINE group
   - Add the LINE Official Account to the group
   - Use `get_group_id.py` helper to capture it

### Render
1. **Render account** (free tier works)
2. Create new Web Service from the cloned GitHub repo
3. Add all env vars listed in `.env.example`

---

## ⚙️ Optional: Customize Brand Voice

### Daily LINE Report Text

In `api_server.py`, find function `_build_daily_text()` (around line 1850).
Customize the report format / language for the brand's tone.

### Dashboard Sections

In `dashboard.html`, sections are:
- Section 01: Overview (spend / inbox / booking / ROAS)
- Section 02: Top Ads
- Section 03: Trend
- Section 04: Daily Report

Each section can be toggled / removed by deleting the `<section>` block.

---

## 🚨 Common Issues After Rebrand

| Issue | Fix |
|---|---|
| Dashboard loads but data is 0 | FB token wrong / lacks ads_read scope |
| LINE doesn't send | LINE_CHANNEL_ACCESS_TOKEN or LINE_GROUP_ID missing |
| Render shows "spin down" | Free tier sleeps; keepalive.yml fires every 14 min to keep warm |
| GitHub Actions failing | Render URL in workflows still points to old brand |

---

## 📞 Token Refresh (Long-term)

FB tokens last 60 days (in Live mode) or 1-2 hours (Dev mode).

For Dev mode apps: user manually regenerates every 12 hours via Graph Explorer.

For Live mode (production): tokens auto-extend via the keepalive ping. Verify
expiry with `/api/everly/token-info` endpoint.

---

## 🎓 Project History / Memory

Original brand: **Everly Clinic** (เอเวอร์ลี่ คลินิก บางพลี)
- Brown earthy palette
- Focus: brow lifts, fillers, botox
- Started: May 2026

Rebrand notes: each new brand keeps the same architecture (FastAPI +
dashboard.html + GitHub Actions cron) but updates the visual + credentials.

---

Happy rebranding! 🚀
