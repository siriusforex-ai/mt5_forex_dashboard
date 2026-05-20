"""
FastAPI app: serves the static dashboard and streams MT5 data over a websocket.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
from analytics import (
    compute_stats,
    compute_drawdown,
    per_symbol_breakdown,
    hourly_heatmap,
    weekday_heatmap,
)
from mt5_client import MT5Client, MT5Error

log = logging.getLogger("mt5_dashboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")

STATIC_DIR = Path(__file__).parent / "static"
client = MT5Client()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        client.connect()
        log.info("MT5 connected.")
    except MT5Error as e:
        log.error("MT5 connection failed: %s", e)
    yield
    client.shutdown()
    log.info("MT5 shut down.")


app = FastAPI(title="MT5 Live Dashboard", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    log.info("WS client connected.")

    try:
        # Initial payload: snapshot + full equity curve.
        try:
            equity_curve = await asyncio.to_thread(client.get_equity_curve)
            snap = await asyncio.to_thread(client.snapshot)
            history = await asyncio.to_thread(client.get_trade_history)
            ticks = await asyncio.to_thread(client.get_watched_ticks)
        except MT5Error as e:
            await ws.send_json({"type": "error", "message": str(e)})
            await ws.close()
            return

        starting_balance = (
            float(equity_curve[0]["v"]) if equity_curve
            else float(snap["account"]["balance"])
        )

        snap["stats"]      = compute_stats(history)
        snap["drawdown"]   = compute_drawdown(equity_curve, starting_balance)
        snap["per_symbol"] = per_symbol_breakdown(history)
        snap["hourly"]     = hourly_heatmap(history)
        snap["weekday"]    = weekday_heatmap(history)
        snap["ticks"]      = ticks

        log.info(
            "WS init payload: equity_curve len=%d, positions=%d, balance=%.2f, equity=%.2f, trades=%d, ticks=%d",
            len(equity_curve),
            len(snap["positions"]),
            snap["account"]["balance"],
            snap["account"]["equity"],
            len(history),
            len(ticks),
        )
        await ws.send_json({
            "type": "init",
            "equity_curve": equity_curve,
            **snap,
        })

        # Tick loop.
        while True:
            await asyncio.sleep(config.REFRESH_INTERVAL)
            try:
                snap = await asyncio.to_thread(client.snapshot)
                history = await asyncio.to_thread(client.get_trade_history)
                ticks = await asyncio.to_thread(client.get_watched_ticks)
            except MT5Error as e:
                await ws.send_json({"type": "error", "message": str(e)})
                continue

            # Append live equity to the cached curve for an accurate live drawdown.
            equity_curve.append({
                "t": snap["timestamp"],
                "v": round(snap["account"]["equity"], 2),
            })
            if len(equity_curve) > 5000:
                equity_curve.pop(0)

            snap["stats"]      = compute_stats(history)
            snap["drawdown"]   = compute_drawdown(equity_curve, starting_balance)
            snap["per_symbol"] = per_symbol_breakdown(history)
            snap["hourly"]     = hourly_heatmap(history)
            snap["weekday"]    = weekday_heatmap(history)
            snap["ticks"]      = ticks

            tick = {
                "type": "tick",
                "equity_point": {
                    "t": snap["timestamp"],
                    "v": round(snap["account"]["equity"], 2),
                },
                **snap,
            }
            await ws.send_json(tick)

    except WebSocketDisconnect:
        log.info("WS client disconnected.")
    except Exception as e:
        log.exception("WS loop crashed: %s", e)
        try:
            await ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)
