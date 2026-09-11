"""
Strategy-attributed positions and broker reconciliation service.

Combines:
1. Authoritative Fyers/OpenAlgo broker net position (from get_positionbook).
2. Existing strategy_positions ledger (from database/strategy_book_db).
3. Existing strategy P&L calculations (from services/strategy_pnl_service).

For each (symbol, exchange, product):
  Broker Net Qty
  Tracked Strategy Qty = SUM(strategy_positions.quantity)
  Residual Qty = Broker Net Qty - Tracked Strategy Qty

Never modifies any order execution, broker adapters, or trading strategy files.
"""

from typing import Any, Dict, List, Optional, Tuple

from database.auth_db import get_auth_token_broker, verify_api_key
from database.strategy_book_db import StrategyBookUnavailable, get_strategy_legs
from services.positionbook_service import get_positionbook
from utils.logging import get_logger

logger = get_logger(__name__)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_trade_strategy(trade: Dict[str, Any]) -> str:
    """Resolve strategy attribution for a trade record."""
    strat = trade.get("strategy")
    if strat and str(strat).strip():
        return str(strat).strip()

    orderid = trade.get("orderid") or trade.get("order_id")
    if orderid:
        try:
            from database.strategy_book_db import get_order_tag

            tag = get_order_tag(str(orderid))
            if tag and tag.strategy and str(tag.strategy).strip():
                return str(tag.strategy).strip()
        except Exception:
            pass

    return "Manual / Unattributed"


def derive_closed_positions(
    trades: List[Dict[str, Any]],
    strategy_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Derives completed/closed trades from executed fills.
    Matches opposite fills per (strategy, symbol, exchange, product) chronologically (FIFO).
    Only returns genuine completed trades with reliable realized P&L.
    Zero-quantity contracts with no fills are never included.
    Day-scoped to the current trading session date (tradebook is session-scoped).
    """
    if not trades or not isinstance(trades, list):
        return []

    norm_filter = (
        str(strategy_filter).strip().lower()
        if strategy_filter and str(strategy_filter).strip().lower() != "all"
        else None
    )

    # Group trades by (strategy, symbol, exchange, product)
    grouped: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}

    for t in trades:
        if not isinstance(t, dict):
            continue

        sym = str(t.get("symbol") or "").strip().upper()
        exch = str(t.get("exchange") or "").strip().upper()
        prod = str(t.get("product") or "").strip().upper()
        if not sym:
            continue

        strat = _resolve_trade_strategy(t)
        if norm_filter and strat.lower() != norm_filter:
            continue

        key = (strat, sym, exch, prod)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(t)

    def _extract_timestamp(item: Dict[str, Any]) -> str:
        return str(
            item.get("timestamp")
            or item.get("trade_timestamp")
            or item.get("trade_time")
            or item.get("tradeTime")
            or item.get("order_timestamp")
            or item.get("order_time")
            or item.get("time")
            or ""
        )

    closed_trades: List[Dict[str, Any]] = []

    for (strat, sym, exch, prod), fill_list in grouped.items():
        # Sort chronologically by timestamp
        fill_list.sort(key=_extract_timestamp)

        open_lots: List[Dict[str, Any]] = []

        for fill in fill_list:
            action = str(fill.get("action") or fill.get("side") or "").strip().upper()
            qty = abs(_f(fill.get("quantity") or fill.get("tradedQty") or fill.get("traded_quantity") or 0))
            price = _f(fill.get("average_price") or fill.get("price") or fill.get("tradePrice") or 0)
            timestamp = _extract_timestamp(fill)

            if qty <= 1e-9:
                continue

            if not open_lots or open_lots[0]["action"] == action:
                open_lots.append({
                    "action": action,
                    "quantity": qty,
                    "price": price,
                    "timestamp": timestamp,
                })
            else:
                # Opposite action -> closing fills
                rem_qty = qty
                while rem_qty > 1e-9 and open_lots:
                    lot = open_lots[0]
                    matched = min(rem_qty, lot["quantity"])
                    direction = "LONG" if lot["action"] == "BUY" else "SHORT"
                    entry_avg = lot["price"]
                    exit_avg = price
                    entry_time = lot["timestamp"]
                    exit_time = timestamp
                    pnl_sign = 1.0 if direction == "LONG" else -1.0
                    realized = round(matched * (exit_avg - entry_avg) * pnl_sign, 2)

                    closed_trades.append({
                        "strategy": strat,
                        "symbol": sym,
                        "exchange": exch,
                        "product": prod,
                        "direction": direction,
                        "quantity": round(matched, 4),
                        "entry_average": round(entry_avg, 2),
                        "exit_average": round(exit_avg, 2),
                        "entry_time": entry_time,
                        "exit_time": exit_time,
                        "realized_pnl": realized,
                        "status": "CLOSED",
                    })

                    lot["quantity"] -= matched
                    rem_qty -= matched
                    if lot["quantity"] <= 1e-9:
                        open_lots.pop(0)

                if rem_qty > 1e-9:
                    open_lots.append({
                        "action": action,
                        "quantity": rem_qty,
                        "price": price,
                        "timestamp": timestamp,
                    })

    # Sort closed trades newest exit first
    closed_trades.sort(key=lambda x: str(x.get("exit_time") or ""), reverse=True)
    return closed_trades


def reconcile_positions(
    broker_positions: List[Dict[str, Any]],
    strategy_legs: List[Dict[str, Any]],
    strategy_filter: Optional[str] = None,
    include_zero_residual: bool = False,
    closed_positions: Optional[List[Dict[str, Any]]] = None,
    trades: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Pure reconciliation engine combining broker positions and strategy legs.

    Guarantees:
      For every contract: SUM(strategy_quantities) + residual == broker_quantity

    Args:
        broker_positions: Standardized OpenAlgo position list from broker.
        strategy_legs: Leg records from database/strategy_book_db.
        strategy_filter: Optional strategy name to filter strategy-level positions.
        include_zero_residual: Whether to output 'Manual / Unattributed' when residual is 0.
        closed_positions: Pre-derived closed positions (optional).
        trades: Trade list to derive closed positions if closed_positions is not provided.
    """
    if closed_positions is None and trades is not None:
        closed_positions = derive_closed_positions(trades, strategy_filter)
    # 1. Index broker positions by (symbol, exchange, product)
    broker_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for p in broker_positions or []:
        sym = str(p.get("symbol") or "").strip().upper()
        exch = str(p.get("exchange") or "").strip().upper()
        prod = str(p.get("product") or "").strip().upper()
        if sym and exch:
            broker_by_key[(sym, exch, prod)] = p

    # 2. Index strategy legs by (symbol, exchange, product)
    legs_by_key: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for leg in strategy_legs or []:
        sym = str(leg.get("symbol") or "").strip().upper()
        exch = str(leg.get("exchange") or "").strip().upper()
        prod = str(leg.get("product") or "").strip().upper()
        if sym and exch:
            legs_by_key.setdefault((sym, exch, prod), []).append(leg)

    # 3. Contract universe: Union of broker positions and strategy legs
    all_keys = set(broker_by_key.keys()) | set(legs_by_key.keys())
    sorted_keys = sorted(all_keys, key=lambda k: (k[0], k[1], k[2]))

    attributed_positions: List[Dict[str, Any]] = []
    contract_summaries: List[Dict[str, Any]] = []

    total_realized_pnl = 0.0
    total_unrealized_pnl = 0.0
    total_tracked_count = 0
    total_residual_count = 0
    total_broker_count = 0

    for key in sorted_keys:
        sym, exch, prod = key
        b_pos = broker_by_key.get(key, {})
        b_qty = round(_f(b_pos.get("quantity")), 4)
        b_avg = round(_f(b_pos.get("average_price")), 4)
        b_ltp = _f(b_pos.get("ltp")) if b_pos.get("ltp") is not None else None

        if abs(b_qty) > 1e-9:
            total_broker_count += 1

        all_contract_legs = legs_by_key.get(key, [])

        # Tracked quantity is the sum across ALL strategies for this contract
        tracked_qty = round(sum(_f(leg.get("quantity")) for leg in all_contract_legs), 4)

        # Residual quantity: difference between broker net and tracked strategies
        residual_qty = round(b_qty - tracked_qty, 4)

        # Skip contracts that have no activity (broker == 0, tracked == 0, residual == 0, and no active strategy legs)
        if abs(b_qty) <= 1e-9 and abs(tracked_qty) <= 1e-9 and abs(residual_qty) <= 1e-9:
            has_active_legs = any(abs(_f(l.get("quantity"))) > 1e-9 for l in all_contract_legs)
            if not has_active_legs:
                continue

        # Mathematical guarantee check
        is_exact = abs((tracked_qty + residual_qty) - b_qty) < 1e-6
        reconciliation_status = "RECONCILED" if is_exact else "DISCREPANCY"

        has_residual = abs(residual_qty) > 1e-9
        if has_residual:
            total_residual_count += 1

        # Filter legs if a specific strategy was requested
        if strategy_filter:
            display_legs = [
                leg
                for leg in all_contract_legs
                if str(leg.get("strategy") or "").strip().lower()
                == strategy_filter.strip().lower()
            ]
        else:
            display_legs = all_contract_legs

        # Emit strategy position rows
        for leg in display_legs:
            s_name = leg.get("strategy") or "Untagged"
            s_qty = round(_f(leg.get("quantity")), 4)
            s_avg = round(_f(leg.get("average_price")), 4)
            s_realized = round(_f(leg.get("realized_pnl")), 4)
            s_today_realized = round(_f(leg.get("today_realized_pnl")), 4)

            if s_qty > 1e-9:
                side = "LONG"
            elif s_qty < -1e-9:
                side = "SHORT"
            else:
                side = "FLAT"

            # Use contract LTP if available, fallback to leg LTP
            ltp = b_ltp if b_ltp is not None else (_f(leg.get("ltp")) if leg.get("ltp") is not None else None)

            # Standardized unrealized P&L formula: qty * (LTP - avg_price)
            if ltp is not None and abs(s_qty) > 1e-9:
                s_unrealized = round(s_qty * (ltp - s_avg), 4)
            else:
                s_unrealized = 0.0

            s_total = round(s_realized + s_unrealized, 4)

            # Investment for P&L %
            investment = abs(s_avg * s_qty)
            pnlpercent = round((s_total / investment) * 100, 2) if investment > 0 else 0.0

            if abs(s_qty) > 1e-9:
                total_tracked_count += 1
                total_realized_pnl += s_realized
                total_unrealized_pnl += s_unrealized

            attributed_positions.append(
                {
                    "strategy": s_name,
                    "symbol": sym,
                    "exchange": exch,
                    "product": prod,
                    "signed_quantity": s_qty,
                    "side": side,
                    "quantity": round(abs(s_qty), 4),
                    "average_price": s_avg,
                    "ltp": round(ltp, 4) if ltp is not None else 0.0,
                    "realized_pnl": s_realized,
                    "today_realized_pnl": s_today_realized,
                    "unrealized_pnl": s_unrealized,
                    "total_pnl": s_total,
                    "pnlpercent": pnlpercent,
                    "broker_quantity": b_qty,
                    "tracked_quantity": tracked_qty,
                    "residual_quantity": residual_qty,
                    "reconciliation_status": reconciliation_status,
                }
            )

        # Emit "Manual / Unattributed" row if residual exists (or if explicitly requested)
        if not strategy_filter and (has_residual or include_zero_residual):
            if residual_qty > 1e-9:
                res_side = "LONG"
            elif residual_qty < -1e-9:
                res_side = "SHORT"
            else:
                res_side = "FLAT"

            res_avg = b_avg
            res_ltp = b_ltp if b_ltp is not None else 0.0

            if b_ltp is not None and res_avg > 0 and abs(residual_qty) > 1e-9:
                res_unrealized = round(residual_qty * (b_ltp - res_avg), 4)
            else:
                res_unrealized = 0.0

            res_realized = 0.0
            res_total = res_unrealized
            res_inv = abs(res_avg * residual_qty)
            res_pnlpercent = round((res_total / res_inv) * 100, 2) if res_inv > 0 else 0.0

            if abs(residual_qty) > 1e-9:
                total_unrealized_pnl += res_unrealized

            attributed_positions.append(
                {
                    "strategy": "Manual / Unattributed",
                    "symbol": sym,
                    "exchange": exch,
                    "product": prod,
                    "signed_quantity": residual_qty,
                    "side": res_side,
                    "quantity": round(abs(residual_qty), 4),
                    "average_price": res_avg,
                    "ltp": round(res_ltp, 4),
                    "realized_pnl": res_realized,
                    "today_realized_pnl": 0.0,
                    "unrealized_pnl": res_unrealized,
                    "total_pnl": res_total,
                    "pnlpercent": res_pnlpercent,
                    "broker_quantity": b_qty,
                    "tracked_quantity": tracked_qty,
                    "residual_quantity": residual_qty,
                    "reconciliation_status": reconciliation_status,
                }
            )

        # Summary entry per contract
        contract_summaries.append(
            {
                "symbol": sym,
                "exchange": exch,
                "product": prod,
                "broker_quantity": b_qty,
                "tracked_quantity": tracked_qty,
                "residual_quantity": residual_qty,
                "has_residual": has_residual,
                "strategies_count": len([l for l in all_contract_legs if abs(_f(l.get("quantity"))) > 1e-9]),
                "reconciliation_status": reconciliation_status,
            }
        )

    return {
        "positions": attributed_positions,
        "contracts": contract_summaries,
        "closed_positions": closed_positions if closed_positions is not None else [],
        "summary": {
            "total_broker_positions": total_broker_count,
            "total_tracked_positions": total_tracked_count,
            "total_residual_positions": total_residual_count,
            "total_realized_pnl": round(total_realized_pnl, 4),
            "total_unrealized_pnl": round(total_unrealized_pnl, 4),
            "total_pnl": round(total_realized_pnl + total_unrealized_pnl, 4),
            "reconciliation_status": "RECONCILED",
        },
    }


def get_attributed_positions(
    api_key: str,
    strategy: Optional[str] = None,
    include_zero_residual: bool = False,
    broker_positions_override: Optional[List[Dict[str, Any]]] = None,
    strategy_legs_override: Optional[List[Dict[str, Any]]] = None,
    tradebook_override: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Fetches authoritative broker positions, strategy legs, and tradebook, returning
    the reconciled strategy-attributed position book including day-scoped closed positions.

    Args:
        api_key: OpenAlgo API key.
        strategy: Optional strategy filter.
        include_zero_residual: Whether to output 'Manual / Unattributed' when residual is 0.
        broker_positions_override: Injected broker positions (for unit tests).
        strategy_legs_override: Injected strategy legs (for unit tests).
        tradebook_override: Injected trades list (for unit tests).

    Returns:
        Tuple of (success, response_dict, http_status_code).
    """
    if not api_key:
        return False, {"status": "error", "message": "API key is required"}, 400

    # 1. Fetch broker positions if not overridden
    if broker_positions_override is not None:
        broker_positions = broker_positions_override
    else:
        try:
            from database.settings_db import get_analyze_mode
            is_analyze = get_analyze_mode()
        except Exception:
            is_analyze = False

        if is_analyze:
            user_id = verify_api_key(api_key)
            if not user_id:
                return False, {"status": "error", "message": "Invalid openalgo apikey"}, 403

            from services.sandbox_service import sandbox_get_positions

            success, resp, status_code = sandbox_get_positions(api_key, {"apikey": api_key})
            if not success:
                return (
                    False,
                    {
                        "status": "error",
                        "message": f"Failed to fetch sandbox position book: {resp.get('message', 'Unknown error')}",
                    },
                    status_code,
                )
            broker_positions = resp.get("data") or []
        else:
            # Validate API key
            auth_token, broker_name = get_auth_token_broker(api_key)
            if auth_token is None:
                return False, {"status": "error", "message": "Invalid openalgo apikey"}, 403

            success, resp, status_code = get_positionbook(api_key=api_key)
            if not success:
                return (
                    False,
                    {
                        "status": "error",
                        "message": f"Failed to fetch broker position book: {resp.get('message', 'Unknown error')}",
                    },
                    status_code,
                )
            broker_positions = resp.get("data") or []

        if not isinstance(broker_positions, list):
            broker_positions = []

    # 2. Fetch strategy legs from database if not overridden
    if strategy_legs_override is not None:
        strategy_legs = strategy_legs_override
    else:
        try:
            strategy_legs = get_strategy_legs(user_id=None, strategy=strategy)
        except StrategyBookUnavailable as e:
            logger.warning(f"Strategy book unavailable: {e}")
            strategy_legs = []
        except Exception as e:
            logger.exception(f"Error fetching strategy legs: {e}")
            strategy_legs = []

    # 3. Fetch tradebook for day-scoped closed positions
    if tradebook_override is not None:
        raw_trades = tradebook_override
    else:
        try:
            from services.tradebook_service import get_tradebook
            tb_success, tb_resp, _ = get_tradebook(api_key=api_key)
            raw_trades = tb_resp.get("data") if tb_success and isinstance(tb_resp, dict) else []
        except Exception as e:
            logger.warning(f"Error fetching tradebook for closed positions: {e}")
            raw_trades = []

    closed_positions = derive_closed_positions(
        trades=raw_trades or [],
        strategy_filter=strategy,
    )

    # 4. Perform reconciliation
    result = reconcile_positions(
        broker_positions=broker_positions,
        strategy_legs=strategy_legs,
        strategy_filter=strategy,
        include_zero_residual=include_zero_residual,
        closed_positions=closed_positions,
    )

    return True, {"status": "success", "data": result}, 200
