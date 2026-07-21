from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.browser.bridge import browser_bridge
from backend.app.core.config import get_settings

router = APIRouter(prefix="/browser", tags=["browser"])


@router.websocket("/ws")
async def browser_ws(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin", "")
    allowed = set(get_settings().cors_origins)
    if origin and origin not in allowed and not origin.startswith("chrome-extension://"):
        await websocket.close(code=1008, reason="Untrusted browser bridge origin")
        return
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
