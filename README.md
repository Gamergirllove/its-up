# POLY BOT — Polymarket Underdog Trading Bot

Bets $1 on the underdog whenever a live sports market shows a 50-point discrepancy.
Auto-sells at **+$0.05 profit** or **-$0.50 loss**.

## Quick Start (local)

```bash
pip install -r requirements.txt
python app.py          # opens http://localhost:5000
```

Enter your Polygon private key + Polymarket API credentials in the web UI.

## Deploy to Railway (free, mobile-accessible)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select this repo — Railway auto-detects `Procfile`
4. Get your public URL (e.g. `https://poly-bot.up.railway.app`)
5. Open on mobile ✓

## Deploy to Render (free tier)

1. [render.com](https://render.com) → New Web Service → Connect GitHub repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4`

## Bot Logic

| Parameter          | Value  |
|--------------------|--------|
| Bet size           | $1.00  |
| Take profit        | +$0.05 |
| Stop loss          | -$0.50 |
| Discrepancy needed | 50 pts |
| Max open bets      | 5      |

## Getting Polymarket API Keys

1. Go to [polymarket.com](https://polymarket.com)
2. Connect your Polygon wallet
3. Profile → API Keys → Generate
4. Copy key / secret / passphrase into the bot UI

> ⚠️ Never commit your `.env` or private key. All credentials are session-only in the UI.
