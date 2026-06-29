from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.browser.bridge import browser_bridge

router = APIRouter(prefix="/browser", tags=["browser"])


@router.websocket("/ws")
async def browser_ws(websocket: WebSocket) -> None:
    await browser_bridge.connect(websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict):
                await browser_bridge.handle_message(message)
    except WebSocketDisconnect:
        await browser_bridge.disconnect(websocket)
    except Exception:
        await browser_bridge.disconnect(websocket)
        raise
