"""
Pure-Python stats engine over a list of closed-trade dicts.

Trade dict shape (produced by mt5_client.MT5Client.get_trade_history):
  ticket, symbol, side, open_time, close_time, open_price, close_price,
  volume, profit, duration_minutes, hour, weekday
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def _empty_stats() -> dict[str, Any]:
    return {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_profit": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "max_win_streak": 0,
        "max_loss_streak": 0,
        "avg_duration_minutes": 0.0,
        "most_traded_symbol": "N/A",
    }


def compute_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return _empty_stats()

    # Sort chronologically so streaks reflect real trade order.
    ordered = sorted(trades, key=lambda t: t.get("close_time", 0))

    total = len(ordered)
    wins_list = [t for t in ordered if float(t["profit"]) > 0]
    losses_list = [t for t in ordered if float(t["profit"]) <= 0]
    wins = len(wins_list)
    losses = len(losses_list)
    win_rate = round((wins / total) * 100, 2) if total else 0.0

    gross_profit = sum(float(t["profit"]) for t in wins_list)
    gross_loss = abs(sum(float(t["profit"]) for t in losses_list))
    if gross_loss == 0 and gross_profit > 0:
        profit_factor = 999.99
    elif gross_profit == 0 and gross_loss == 0:
        profit_factor = 0.0
    else:
        profit_factor = round(gross_profit / gross_loss, 2)

    total_profit = round(sum(float(t["profit"]) for t in ordered), 2)
    avg_win = round(gross_profit / wins, 2) if wins else 0.0
    avg_loss = (
        round(sum(float(t["profit"]) for t in losses_list) / losses, 2)
        if losses else 0.0
    )
    largest_win = round(max((float(t["profit"]) for t in wins_list), default=0.0), 2)
    largest_loss = round(min((float(t["profit"]) for t in losses_list), default=0.0), 2)

    max_win_streak = 0
    max_loss_streak = 0
    cur_win = 0
    cur_loss = 0
    for t in ordered:
        if float(t["profit"]) > 0:
            cur_win += 1
            cur_loss = 0
            if cur_win > max_win_streak:
                max_win_streak = cur_win
        else:
            cur_loss += 1
            cur_win = 0
            if cur_loss > max_loss_streak:
                max_loss_streak = cur_loss

    durations = [float(t.get("duration_minutes", 0)) for t in ordered]
    avg_duration_minutes = round(sum(durations) / len(durations), 1) if durations else 0.0

    symbol_counts = Counter(t["symbol"] for t in ordered if t.get("symbol"))
    most_traded_symbol = symbol_counts.most_common(1)[0][0] if symbol_counts else "N/A"

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_profit": total_profit,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "avg_duration_minutes": avg_duration_minutes,
        "most_traded_symbol": most_traded_symbol,
    }


def per_symbol_breakdown(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group trades by symbol; return rows sorted by net_pnl descending."""
    if not trades:
        return []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in trades:
        sym = t.get("symbol")
        if sym:
            groups[sym].append(t)
    rows: list[dict[str, Any]] = []
    for symbol, group in groups.items():
        n = len(group)
        wins = sum(1 for t in group if float(t["profit"]) > 0)
        net = sum(float(t["profit"]) for t in group)
        rows.append({
            "symbol": symbol,
            "trades": n,
            "wins": wins,
            "win_rate": round((wins / n) * 100, 2) if n else 0.0,
            "net_pnl": round(net, 2),
            "avg_pnl": round(net / n, 2) if n else 0.0,
        })
    rows.sort(key=lambda r: r["net_pnl"], reverse=True)
    return rows


def hourly_heatmap(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """24 buckets for hours 0..23 — always returns all 24, zero-filled."""
    buckets = {h: {"trades": 0, "wins": 0, "pnl": 0.0} for h in range(24)}
    for t in trades:
        try:
            h = int(t.get("hour", 0))
        except (TypeError, ValueError):
            continue
        if 0 <= h <= 23:
            b = buckets[h]
            b["trades"] += 1
            if float(t["profit"]) > 0:
                b["wins"] += 1
            b["pnl"] += float(t["profit"])
    out: list[dict[str, Any]] = []
    for h in range(24):
        b = buckets[h]
        n = b["trades"]
        out.append({
            "hour": h,
            "trades": n,
            "wins": b["wins"],
            "win_rate": round((b["wins"] / n) * 100, 2) if n else 0.0,
            "pnl": round(b["pnl"], 2),
        })
    return out


def weekday_heatmap(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """7 buckets, Monday=0 .. Sunday=6, matching datetime.weekday()."""
    buckets = {d: {"trades": 0, "wins": 0, "pnl": 0.0} for d in range(7)}
    for t in trades:
        try:
            d = int(t.get("weekday", 0))
        except (TypeError, ValueError):
            continue
        if 0 <= d <= 6:
            b = buckets[d]
            b["trades"] += 1
            if float(t["profit"]) > 0:
                b["wins"] += 1
            b["pnl"] += float(t["profit"])
    out: list[dict[str, Any]] = []
    for d in range(7):
        b = buckets[d]
        n = b["trades"]
        out.append({
            "weekday": d,
            "trades": n,
            "wins": b["wins"],
            "win_rate": round((b["wins"] / n) * 100, 2) if n else 0.0,
            "pnl": round(b["pnl"], 2),
        })
    return out


def compute_drawdown(
    equity_curve: list[dict[str, Any]],
    starting_balance: float,
) -> dict[str, Any]:
    """
    Track the running peak across the curve, the max drop from any running peak,
    and the current drop from the all-time peak.
    """
    if not equity_curve:
        return {
            "current_dd": 0.0,
            "current_dd_pct": 0.0,
            "max_dd": 0.0,
            "peak": float(starting_balance),
        }
    peak = float(starting_balance)
    max_dd = 0.0
    for point in equity_curve:
        v = float(point["v"])
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    current_equity = float(equity_curve[-1]["v"])
    current_dd = max(0.0, peak - current_equity)
    current_dd_pct = round((current_dd / peak) * 100, 2) if peak > 0 else 0.0
    return {
        "current_dd": round(current_dd, 2),
        "current_dd_pct": current_dd_pct,
        "max_dd": round(max_dd, 2),
        "peak": round(peak, 2),
    }
