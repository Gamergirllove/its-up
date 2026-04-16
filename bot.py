"""
bot.py  –  Polymarket Underdog Betting Bot
==========================================
Logic:
  1. Scan live sports markets every POLL_INTERVAL seconds
  2. Flag markets where |YES_mid - NO_mid| >= 0.50 (50 points)
  3. Bet $1 on the underdog (lower-probability side)
  4. SELL when position gains +$0.05  OR  loses -$0.50
  5. Cap concurrent open bets at MAX_OPEN_BETS

Usage:
  cp .env.example .env   # fill in your creds
  pip install -r requirements.txt
  python bot.py
"""

import logging
import time
import sys

from config import POLL_INTERVAL, MAX_OPEN_BETS, PRIVATE_KEY, API_KEY
from scanner import scan_for_opportunities
from trader import Trader

# ─── logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log"),
    ],
)
log = logging.getLogger(__name__)


# ─── preflight ───────────────────────────────────────────────────────────────

def preflight():
    missing = []
    if not PRIVATE_KEY:    missing.append("PRIVATE_KEY")
    if not API_KEY:        missing.append("POLY_API_KEY")
    if missing:
        log.error(f"Missing env vars: {missing}. Copy .env.example → .env and fill in.")
        sys.exit(1)
    log.info("✓ Credentials loaded")


# ─── main loop ───────────────────────────────────────────────────────────────

def run():
    preflight()
    trader = Trader()
    log.info("=== Polymarket Underdog Bot STARTED ===")
    log.info(f"  Discrepancy threshold : 0.50 (50 pts)")
    log.info(f"  Bet size              : $1.00")
    log.info(f"  Take profit           : +$0.05")
    log.info(f"  Stop loss             : -$0.50")
    log.info(f"  Max concurrent bets   : {MAX_OPEN_BETS}")

    cycle = 0
    while True:
        cycle += 1
        log.info(f"─── Cycle {cycle} | Open positions: {trader.open_count}/{MAX_OPEN_BETS} ───")

        # 1. Monitor existing positions first
        trader.monitor_positions()

        # 2. Scan for new opportunities if under cap
        if trader.open_count < MAX_OPEN_BETS:
            slots_available = MAX_OPEN_BETS - trader.open_count
            opps = scan_for_opportunities(trader.open_market_ids)

            if not opps:
                log.info("No opportunities this cycle.")
            else:
                log.info(f"Found {len(opps)} opportunity/ies. Taking up to {slots_available}.")
                for opp in opps[:slots_available]:
                    trader.open_position(opp)
                    time.sleep(1)  # brief pause between orders
        else:
            log.info("Max open bets reached – skipping scan.")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
