"""
scanner.py
Finds live sports markets where |YES_mid - NO_mid| >= DISCREPANCY_MIN (0.50).
Returns list of opportunity dicts with token_id, side (underdog), and entry price.
"""

import logging
import requests
from config import GAMMA_API, CLOB_HOST, DISCREPANCY_MIN, SPORTS_TAGS

log = logging.getLogger(__name__)


def _get_live_sports_markets(limit: int = 200) -> list[dict]:
    """Pull active sports markets from Gamma API."""
    markets = []
    for tag in SPORTS_TAGS:
        try:
            r = requests.get(
                f"{GAMMA_API}/markets",
                params={"active": "true", "tag_slug": tag, "limit": limit},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                markets.extend(data)
            elif isinstance(data, dict) and "markets" in data:
                markets.extend(data["markets"])
        except Exception as e:
            log.warning(f"Gamma fetch failed for tag={tag}: {e}")
    # deduplicate by conditionId
    seen = set()
    unique = []
    for m in markets:
        cid = m.get("conditionId") or m.get("id")
        if cid and cid not in seen:
            seen.add(cid)
            unique.append(m)
    return unique


def _get_mid(token_id: str) -> float | None:
    """Return mid price from CLOB orderbook for a token."""
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
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        return (best_bid + best_ask) / 2.0
    except Exception as e:
        log.debug(f"Orderbook fetch failed token={token_id}: {e}")
        return None


def scan_for_opportunities(open_market_ids: set) -> tuple[list[dict], dict]:
    """
    Returns (opportunities, scan_info).

    opportunities — list of dicts that meet DISCREPANCY_MIN:
        { market_id, question, token_id, side, entry_price, discrepancy }

    scan_info — diagnostic dict:
        { markets_fetched, markets_priced, top_markets (up to 20, sorted by gap desc) }
        top_markets entries: { question, yes_mid, no_mid, gap, qualifies }
    """
    markets = _get_live_sports_markets()
    log.info(f"Scanning {len(markets)} sports markets...")

    opportunities = []
    top_markets   = []

    for m in markets:
        market_id = m.get("conditionId") or m.get("id", "")
        if market_id in open_market_ids:
            continue

        tokens = m.get("tokens", [])
        if len(tokens) < 2:
            continue

        yes_token = next((t for t in tokens if t.get("outcome", "").upper() == "YES"), tokens[0])
        no_token  = next((t for t in tokens if t.get("outcome", "").upper() == "NO"),  tokens[1])

        yes_mid = _get_mid(yes_token["token_id"])
        no_mid  = _get_mid(no_token["token_id"])

        if yes_mid is None or no_mid is None:
            continue
        if yes_mid <= 0 or no_mid <= 0:
            continue

        discrepancy = abs(yes_mid - no_mid)
        qualifies   = discrepancy >= DISCREPANCY_MIN

        top_markets.append({
            "question":  m.get("question", "Unknown")[:80],
            "yes_mid":   round(yes_mid, 4),
            "no_mid":    round(no_mid, 4),
            "gap":       round(discrepancy, 4),
            "qualifies": qualifies,
        })

        if not qualifies:
            continue

        if yes_mid < no_mid:
            underdog_token = yes_token["token_id"]
            underdog_side  = "YES"
            entry_price    = yes_mid
        else:
            underdog_token = no_token["token_id"]
            underdog_side  = "NO"
            entry_price    = no_mid

        opportunities.append({
            "market_id":   market_id,
            "question":    m.get("question", "Unknown"),
            "token_id":    underdog_token,
            "side":        underdog_side,
            "entry_price": entry_price,
            "discrepancy": discrepancy,
        })
        log.info(
            f"OPPORTUNITY | {m.get('question','')[:60]} | "
            f"YES={yes_mid:.3f} NO={no_mid:.3f} | "
            f"gap={discrepancy:.3f} | bet={underdog_side}@{entry_price:.3f}"
        )

    top_markets.sort(key=lambda x: x["gap"], reverse=True)

    scan_info = {
        "markets_fetched": len(markets),
        "markets_priced":  len(top_markets),
        "top_markets":     top_markets[:20],
        "threshold":       DISCREPANCY_MIN,
    }

    return opportunities, scan_info
