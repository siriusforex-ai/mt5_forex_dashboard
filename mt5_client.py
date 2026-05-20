"""
MetaTrader5 reader. All terminal calls live here so the FastAPI layer stays clean.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import MetaTrader5 as mt5

import config


class MT5Error(RuntimeError):
    pass


class MT5Client:
    def __init__(self) -> None:
        self._connected = False

    # ---- lifecycle ----------------------------------------------------------
    def connect(self) -> None:
        kwargs: dict[str, Any] = {}
        if config.MT5_PATH:
            kwargs["path"] = config.MT5_PATH
        if config.MT5_LOGIN:
            kwargs["login"] = int(config.MT5_LOGIN)
        if config.MT5_PASSWORD:
            kwargs["password"] = config.MT5_PASSWORD
        if config.MT5_SERVER:
            kwargs["server"] = config.MT5_SERVER

        if not mt5.initialize(**kwargs):
            err = mt5.last_error()
            raise MT5Error(f"mt5.initialize failed: {err}")
        self._connected = True

    def shutdown(self) -> None:
        if self._connected:
            mt5.shutdown()
            self._connected = False

    # ---- reads --------------------------------------------------------------
    def get_account(self) -> dict[str, Any]:
        info = mt5.account_info()
        if info is None:
            raise MT5Error(f"account_info failed: {mt5.last_error()}")
        return {
            "login": info.login,
            "name": info.name,
            "server": info.server,
            "currency": info.currency,
            "balance": float(info.balance),
            "equity": float(info.equity),
            "margin": float(info.margin),
            "free_margin": float(info.margin_free),
            "margin_level": float(info.margin_level) if info.margin else 0.0,
            "leverage": int(info.leverage),
            "open_pnl": float(info.profit),
        }

    def get_positions(self) -> list[dict[str, Any]]:
        positions = mt5.positions_get()
        if positions is None:
            return []
        out: list[dict[str, Any]] = []
        for p in positions:
            out.append({
                "ticket": int(p.ticket),
                "symbol": p.symbol,
                "side": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": float(p.volume),
                "price_open": float(p.price_open),
                "price_current": float(p.price_current),
                "sl": float(p.sl),
                "tp": float(p.tp),
                "swap": float(p.swap),
                "profit": float(p.profit),
                "time": int(p.time),
            })
        return out

    def get_today_pnl(self) -> float:
        now = datetime.now()
        start = datetime(now.year, now.month, now.day)
        deals = mt5.history_deals_get(start, now + timedelta(seconds=1))
        if deals is None:
            return 0.0
        total = 0.0
        for d in deals:
            # Count closing-side deals only (entry OUT or INOUT); skip balance ops.
            if d.type not in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
                continue
            if d.entry == mt5.DEAL_ENTRY_IN:
                continue
            total += float(d.profit) + float(d.swap) + float(d.commission)
        return total

    def get_equity_curve(self) -> list[dict[str, Any]]:
        """
        Reconstruct a balance curve over the last N days from closed deals,
        then append the live equity point so the chart lands on 'now'.
        """
        account = self.get_account()
        now = datetime.now()
        start = now - timedelta(days=config.HISTORY_DAYS)
        print(f"[mt5_client] history_deals_get range: {start.isoformat()} → {now.isoformat()}")
        deals = mt5.history_deals_get(start, now + timedelta(seconds=1))
        print(f"[mt5_client] deals returned: "
              f"{len(deals) if deals is not None else 'None'} "
              f"(last_error={mt5.last_error()})")

        # Realised cashflow events (closes, swaps, commissions, plus balance ops).
        events: list[tuple[int, float]] = []
        if deals is not None:
            for d in deals:
                if d.type == mt5.DEAL_TYPE_BALANCE:
                    events.append((int(d.time), float(d.profit)))
                    continue
                if d.type not in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
                    continue
                if d.entry == mt5.DEAL_ENTRY_IN:
                    continue
                net = float(d.profit) + float(d.swap) + float(d.commission)
                if net == 0.0:
                    continue
                events.append((int(d.time), net))

        events.sort(key=lambda e: e[0])

        # Walk backward from current balance to find the starting balance.
        realised_sum = sum(e[1] for e in events)
        starting_balance = account["balance"] - realised_sum

        curve: list[dict[str, Any]] = []
        running = starting_balance
        curve.append({"t": int(start.timestamp()), "v": round(running, 2)})
        for ts, delta in events:
            running += delta
            curve.append({"t": ts, "v": round(running, 2)})

        # Final live point — equity (includes open PnL), not just balance.
        curve.append({"t": int(now.timestamp()), "v": round(account["equity"], 2)})
        print(f"[mt5_client] equity curve built: {len(curve)} points | "
              f"first={curve[0]} | last={curve[-1]} | "
              f"realised_sum={realised_sum:.2f} | starting_balance={starting_balance:.2f}")
        return curve

    def get_trade_history(self) -> list[dict[str, Any]]:
        """
        Return one dict per closed position over the last HISTORY_DAYS days,
        pairing entry/exit deals by position_id.
        """
        now = datetime.now()
        start = now - timedelta(days=config.HISTORY_DAYS)
        deals = mt5.history_deals_get(start, now + timedelta(seconds=1))
        if not deals:
            return []

        groups: dict[int, list] = defaultdict(list)
        for d in deals:
            if d.type not in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
                continue
            if d.position_id == 0:
                continue
            groups[d.position_id].append(d)

        trades: list[dict[str, Any]] = []
        for pid, group in groups.items():
            ins = [d for d in group if d.entry == mt5.DEAL_ENTRY_IN]
            outs = [d for d in group if d.entry != mt5.DEAL_ENTRY_IN]
            if not outs:
                continue  # position still open

            if ins:
                in_deal = min(ins, key=lambda d: d.time)
                side = "BUY" if in_deal.type == mt5.DEAL_TYPE_BUY else "SELL"
                open_time = int(in_deal.time)
                open_price = float(in_deal.price)
            else:
                # IN deal is outside the window; fall back to the OUT deal's data.
                first_out = min(outs, key=lambda d: d.time)
                side = "SELL" if first_out.type == mt5.DEAL_TYPE_BUY else "BUY"
                open_time = int(first_out.time)
                open_price = 0.0

            last_out = max(outs, key=lambda d: d.time)
            close_time = int(last_out.time)
            close_price = float(last_out.price)
            volume = sum(float(d.volume) for d in outs)
            profit = sum(
                float(d.profit) + float(d.swap) + float(d.commission)
                for d in group
            )
            duration_minutes = max(0.0, (close_time - open_time) / 60.0)
            ct = datetime.fromtimestamp(close_time)

            trades.append({
                "ticket": int(pid),
                "symbol": group[0].symbol,
                "side": side,
                "open_time": open_time,
                "close_time": close_time,
                "open_price": round(open_price, 5),
                "close_price": round(close_price, 5),
                "volume": round(volume, 2),
                "profit": round(profit, 2),
                "duration_minutes": round(duration_minutes, 1),
                "hour": ct.hour,
                "weekday": ct.weekday(),
            })

        trades.sort(key=lambda t: t["close_time"])
        return trades

    def get_watched_ticks(self) -> list[dict[str, Any]]:
        """Live bid/ask for every symbol in config.WATCHED_SYMBOLS."""
        out: list[dict[str, Any]] = []
        for symbol in getattr(config, "WATCHED_SYMBOLS", []):
            info = mt5.symbol_info(symbol)
            if info is None:
                continue
            if not info.visible:
                mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                continue
            bid = float(tick.bid)
            ask = float(tick.ask)
            digits = int(info.digits)
            out.append({
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "spread": round(ask - bid, digits),
                "digits": digits,
                "time": int(tick.time),
            })
        return out

    def snapshot(self) -> dict[str, Any]:
        """One-shot bundle used for both the initial WS message and each tick."""
        account = self.get_account()
        positions = self.get_positions()
        today_pnl = self.get_today_pnl()
        return {
            "account": account,
            "positions": positions,
            "today_pnl": round(today_pnl, 2),
            "timestamp": int(datetime.now().timestamp()),
        }
