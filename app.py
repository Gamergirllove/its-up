"""
app.py  –  Flask backend for Polymarket Bot Dashboard
Real-time P&L via Server-Sent Events (SSE)
"""

import json
import logging
import queue
import threading
import time
from datetime import datetime
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from config import (
    BET_SIZE, TAKE_PROFIT_USD, STOP_LOSS_USD,
    DISCREPANCY_MIN, POLL_INTERVAL, MAX_OPEN_BETS
)
from scanner import scan_for_opportunities
from trader import Trader

# ─── app setup ───────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static")
CORS(app)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─── shared state ────────────────────────────────────────────────────────────

_state = {
    "running":       False,
    "credentials":   {},          # api_key, api_secret, api_passphrase, private_key
    "positions":     {},          # market_id → position dict
    "closed_trades": [],          # list of completed trades
    "total_pnl":     0.0,
    "total_bets":    0,
    "wins":          0,
    "losses":        0,
    "start_time":    None,
    "last_scan":     None,        # scan_info dict from most recent cycle
    "scan_count":    0,
}
_state_lock  = threading.Lock()
_event_queue: queue.Queue = queue.Queue(maxsize=200)
_bot_thread: threading.Thread | None = None
_trader: Trader | None = None


def _push_event(event_type: str, data: dict):
    payload = json.dumps({"type": event_type, "data": data, "ts": time.time()})
    try:
        _event_queue.put_nowait(payload)
    except queue.Full:
        _event_queue.get_nowait()
        _event_queue.put_nowait(payload)


def _snapshot() -> dict:
    with _state_lock:
        positions = []
        if _trader:
            for mid, pos in _trader.positions.items():
                from trader import _current_mid
                cur = _current_mid(pos.token_id) or pos.entry_price
                cur_value = cur * pos.shares
                pnl = cur_value - BET_SIZE
                positions.append({
                    "market_id":   mid,
                    "question":    pos.question[:60],
                    "side":        pos.side,
                    "entry_price": round(pos.entry_price, 4),
                    "current_price": round(cur, 4),
                    "shares":      round(pos.shares, 4),
                    "pnl":         round(pnl, 4),
                    "pnl_pct":     round((pnl / BET_SIZE) * 100, 2),
                    "filled":      pos.filled,
                    "tp_price":    round(pos.tp_price, 4),
                    "sl_price":    round(pos.sl_price, 4),
                })
        return {
            "running":       _state["running"],
            "positions":     positions,
            "closed_trades": _state["closed_trades"][-50:],
            "total_pnl":     round(_state["total_pnl"], 4),
            "total_bets":    _state["total_bets"],
            "wins":          _state["wins"],
            "losses":        _state["losses"],
            "open_count":    len(positions),
            "uptime":        int(time.time() - _state["start_time"]) if _state["start_time"] else 0,
            "last_scan":     _state["last_scan"],
            "scan_count":    _state["scan_count"],
        }


# ─── bot thread ──────────────────────────────────────────────────────────────

def _bot_loop(creds: dict):
    global _trader
    import os
    os.environ["PRIVATE_KEY"]       = creds.get("private_key", "")
    os.environ["POLY_API_KEY"]      = creds.get("api_key", "")
    os.environ["POLY_API_SECRET"]   = creds.get("api_secret", "")
    os.environ["POLY_API_PASSPHRASE"] = creds.get("api_passphrase", "")

    import importlib, trader as trader_mod, config as cfg_mod
    importlib.reload(cfg_mod)
    importlib.reload(trader_mod)
    from trader import Trader as T, _current_mid

    _trader = T()
    cycle = 0

    with _state_lock:
        _state["running"]    = True
        _state["start_time"] = time.time()

    _push_event("status", {"msg": "Bot started", "running": True})

    while _state["running"]:
        cycle += 1

        # monitor positions
        if _trader.positions:
            _check_positions(_trader, _current_mid)

        # scan for new
        if _trader.open_count < MAX_OPEN_BETS:
            opps, scan_info = scan_for_opportunities(_trader.open_market_ids)
            with _state_lock:
                _state["last_scan"]  = scan_info
                _state["scan_count"] += 1
            _push_event("scan_result", scan_info)
            for opp in opps[:MAX_OPEN_BETS - _trader.open_count]:
                pos = _trader.open_position(opp)
                if pos:
                    with _state_lock:
                        _state["total_bets"] += 1
                    _push_event("new_bet", {
                        "question":    opp["question"][:60],
                        "side":        opp["side"],
                        "entry_price": opp["entry_price"],
                        "discrepancy": round(opp["discrepancy"], 3),
                    })

        snap = _snapshot()
        _push_event("snapshot", snap)
        time.sleep(POLL_INTERVAL)

    _push_event("status", {"msg": "Bot stopped", "running": False})
    _trader = None


def _check_positions(trader_obj, _current_mid_fn):
    """Wrap trader monitor to capture closed trades."""
    from trader import TAKE_PROFIT_USD as TP, STOP_LOSS_USD as SL, BET_SIZE as BS
    for mid, pos in list(trader_obj.positions.items()):
        if pos.closed:
            continue
        trader_obj.check_order_fill(pos)
        if not pos.filled:
            continue

        cur = _current_mid_fn(pos.token_id)
        if cur is None:
            continue

        cur_val = cur * pos.shares
        pnl     = cur_val - BS
        reason  = None

        if cur >= pos.tp_price:
            reason = "TP"
        elif cur <= pos.sl_price:
            reason = "SL"

        if reason:
            trader_obj._sell_position(pos, reason)
            trade = {
                "question":    pos.question[:60],
                "side":        pos.side,
                "entry_price": round(pos.entry_price, 4),
                "exit_price":  round(cur, 4),
                "pnl":         round(pnl, 4),
                "result":      reason,
                "ts":          datetime.utcnow().isoformat(),
            }
            with _state_lock:
                _state["closed_trades"].append(trade)
                _state["total_pnl"] += pnl
                if pnl > 0:
                    _state["wins"] += 1
                else:
                    _state["losses"] += 1
            _push_event("trade_closed", trade)


# ─── routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/config", methods=["POST"])
def set_config():
    data = request.json or {}
    required = ["private_key", "api_key", "api_secret", "api_passphrase"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing: {missing}"}), 400
    with _state_lock:
        _state["credentials"] = data
    return jsonify({"ok": True})


@app.route("/api/start", methods=["POST"])
def start_bot():
    global _bot_thread
    with _state_lock:
        if _state["running"]:
            return jsonify({"error": "Already running"}), 400
        creds = _state["credentials"]
    if not creds:
        return jsonify({"error": "Set credentials first via /api/config"}), 400

    _bot_thread = threading.Thread(target=_bot_loop, args=(creds,), daemon=True)
    _bot_thread.start()
    return jsonify({"ok": True, "msg": "Bot started"})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    with _state_lock:
        _state["running"] = False
    return jsonify({"ok": True, "msg": "Stopping..."})


@app.route("/api/status")
def status():
    return jsonify(_snapshot())


@app.route("/api/stream")
def stream():
    """SSE endpoint – browser connects here for real-time updates."""
    def event_gen():
        # send immediate snapshot
        yield f"data: {json.dumps({'type':'snapshot','data':_snapshot()})}\n\n"
        while True:
            try:
                msg = _event_queue.get(timeout=25)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield ": ping\n\n"  # keep-alive

    return Response(
        event_gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/reset", methods=["POST"])
def reset_stats():
    with _state_lock:
        if _state["running"]:
            return jsonify({"error": "Stop bot first"}), 400
        _state["closed_trades"] = []
        _state["total_pnl"]     = 0.0
        _state["total_bets"]    = 0
        _state["wins"]          = 0
        _state["losses"]        = 0
    return jsonify({"ok": True})


# ─── run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
