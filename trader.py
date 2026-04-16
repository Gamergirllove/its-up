"""
trader.py
Places $1 limit buy on underdog token.
Monitors price → sell at +$0.05 profit OR -$0.50 loss.

Position math:
  shares = BET_SIZE / entry_price
  tp_price = entry_price + (TAKE_PROFIT_USD / shares)   → value = $1.05
  sl_price = entry_price - (STOP_LOSS_USD  / shares)    → value = $0.50
"""

import logging
import time
import requests
from dataclasses import dataclass, field
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from config import (
    PRIVATE_KEY, API_KEY, API_SECRET, API_PASSPHRASE,
    CLOB_HOST, CHAIN_ID, BET_SIZE, TAKE_PROFIT_USD, STOP_LOSS_USD,
)

log = logging.getLogger(__name__)


@dataclass
class Position:
    market_id:   str
    question:    str
    token_id:    str
    side:        str
    entry_price: float
    shares:      float
    tp_price:    float
    sl_price:    float
    order_id:    str | None = None
    filled:      bool = False
    closed:      bool = False


def _build_client() -> ClobClient:
    creds = ApiCreds(
        api_key=API_KEY,
        api_secret=API_SECRET,
        api_passphrase=API_PASSPHRASE,
    )
    return ClobClient(
        host=CLOB_HOST,
        key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        api_creds=creds,
    )


def _current_mid(token_id: str) -> float | None:
    try:
        r = requests.get(
            f"{CLOB_HOST}/book",
            params={"token_id": token_id},
            timeout=8,
        )
        r.raise_for_status()
        ob = r.json()
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        if not bids or not asks:
            return None
        return (float(bids[0]["price"]) + float(asks[0]["price"])) / 2.0
    except Exception as e:
        log.debug(f"Mid fetch failed: {e}")
        return None


class Trader:
    def __init__(self):
        self.client    = _build_client()
        self.positions: dict[str, Position] = {}  # market_id → Position

    # ─── open ────────────────────────────────────────────────────────────────

    def open_position(self, opp: dict) -> Position | None:
        token_id    = opp["token_id"]
        entry_price = opp["entry_price"]
        shares      = BET_SIZE / entry_price
        tp_price    = entry_price + (TAKE_PROFIT_USD / shares)
        sl_price    = entry_price - (STOP_LOSS_USD   / shares)

        # Clamp prices to valid range
        tp_price = min(tp_price, 0.999)
        sl_price = max(sl_price, 0.001)

        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=round(entry_price, 4),
                size=round(BET_SIZE, 2),
                side=BUY,
            )
            signed = self.client.create_order(order_args)
            resp   = self.client.post_order(signed, OrderType.GTC)
            order_id = resp.get("orderID") or resp.get("id")

            pos = Position(
                market_id=opp["market_id"],
                question=opp["question"],
                token_id=token_id,
                side=opp["side"],
                entry_price=entry_price,
                shares=shares,
                tp_price=tp_price,
                sl_price=sl_price,
                order_id=order_id,
                filled=False,
                closed=False,
            )
            self.positions[opp["market_id"]] = pos
            log.info(
                f"BUY {opp['side']} | {opp['question'][:50]} | "
                f"${BET_SIZE:.2f} @ {entry_price:.4f} | "
                f"shares={shares:.4f} | TP={tp_price:.4f} SL={sl_price:.4f}"
            )
            return pos

        except Exception as e:
            log.error(f"Order placement failed: {e}")
            return None

    # ─── close ───────────────────────────────────────────────────────────────

    def _sell_position(self, pos: Position, reason: str):
        try:
            mid = _current_mid(pos.token_id)
            sell_price = mid if mid else pos.entry_price

            order_args = OrderArgs(
                token_id=pos.token_id,
                price=round(sell_price, 4),
                size=round(pos.shares, 4),
                side=SELL,
            )
            signed = self.client.create_order(order_args)
            self.client.post_order(signed, OrderType.GTC)

            pnl = (sell_price - pos.entry_price) * pos.shares
            log.info(
                f"SELL [{reason}] | {pos.question[:50]} | "
                f"exit={sell_price:.4f} | PnL=${pnl:+.4f}"
            )
        except Exception as e:
            log.error(f"Sell failed for {pos.market_id}: {e}")
        finally:
            pos.closed = True
            self.positions.pop(pos.market_id, None)

    # ─── monitor ─────────────────────────────────────────────────────────────

    def check_order_fill(self, pos: Position):
        """Mark position as filled once order is no longer open."""
        if pos.filled:
            return
        try:
            orders = self.client.get_orders({"market": pos.market_id})
            open_ids = [o["id"] for o in orders if o.get("status") in ("LIVE", "UNMATCHED")]
            if pos.order_id not in open_ids:
                pos.filled = True
                log.info(f"ORDER FILLED | {pos.question[:50]}")
        except Exception as e:
            log.debug(f"Fill check failed: {e}")

    def monitor_positions(self):
        """Called every poll cycle. Check TP/SL for all filled positions."""
        for market_id, pos in list(self.positions.items()):
            if pos.closed:
                continue

            self.check_order_fill(pos)
            if not pos.filled:
                continue

            mid = _current_mid(pos.token_id)
            if mid is None:
                continue

            current_value = mid * pos.shares

            if mid >= pos.tp_price:
                log.info(f"TAKE PROFIT HIT | value=${current_value:.4f}")
                self._sell_position(pos, "TP")

            elif mid <= pos.sl_price:
                log.info(f"STOP LOSS HIT   | value=${current_value:.4f}")
                self._sell_position(pos, "SL")

    @property
    def open_market_ids(self) -> set:
        return set(self.positions.keys())

    @property
    def open_count(self) -> int:
        return len(self.positions)
