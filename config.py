import os
from dotenv import load_dotenv

load_dotenv()

PRIVATE_KEY       = os.getenv("PRIVATE_KEY")
API_KEY           = os.getenv("POLY_API_KEY")
API_SECRET        = os.getenv("POLY_API_SECRET")
API_PASSPHRASE    = os.getenv("POLY_API_PASSPHRASE")

CLOB_HOST         = "https://clob.polymarket.com"
GAMMA_API         = "https://gamma-api.polymarket.com"
CHAIN_ID          = 137          # Polygon mainnet

BET_SIZE          = 1.00         # $1 USDC per bet
TAKE_PROFIT_USD   = 0.05         # +$0.05 → sell
STOP_LOSS_USD     = 0.50         # -$0.50 → sell (keep $0.50)
DISCREPANCY_MIN   = 0.50         # 50-point gap between YES/NO mids
POLL_INTERVAL     = 8            # seconds between scans
MAX_OPEN_BETS     = 5            # concurrent position cap
SPORTS_TAGS       = ["sports", "soccer", "basketball", "football",
                     "baseball", "hockey", "tennis", "mma", "boxing"]
