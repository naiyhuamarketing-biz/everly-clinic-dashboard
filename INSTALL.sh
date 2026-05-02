#!/usr/bin/env bash
# One-command setup. Run from inside the ads-report directory.
set -e

echo "▶ Creating venv..."
python3 -m venv .venv
source .venv/bin/activate

echo "▶ Upgrading pip..."
pip install --quiet --upgrade pip

echo "▶ Installing dependencies (this may take a couple of minutes)..."
pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "▶ Creating .env from template..."
  cp .env.example .env
  echo "  ✏️  edit .env and fill in your tokens & IDs"
fi

mkdir -p outputs logs credentials

echo ""
echo "✅ Done. Next steps:"
echo "  1. source .venv/bin/activate"
echo "  2. streamlit run dashboard.py    # see dashboard with mock data"
echo "  3. edit .env, set MOCK_MODE=false to enable real API"
echo "  4. python daily_report.py        # test the cron script"
