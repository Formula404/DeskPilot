from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from backend.app.db.repository import new_id


class BrowserBridgeError(RuntimeError):
    pass


class BrowserBridge:
    def __init__(self) -> None:
        self._websocket: WebSocket | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self.client_info: dict[str, Any] | None = None

    @property
    def is_connected(self) -> bool:
        return self._websocket is not None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if self._websocket is not None:
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(BrowserBridgeError("浏览器扩展连接已被新的连接替换。"))
                self._pending.clear()
                await self._websocket.close(code=4000, reason="Replaced by a newer browser bridge connection")
            self._websocket = websocket
            self.client_info = None

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if self._websocket is not websocket:
                return
            self._websocket = None
            self.client_info = None
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(BrowserBridgeError("浏览器扩展连接已断开。"))
            self._pending.clear()

    async def handle_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "browser.register":
            self.client_info = message
            return
        if message_type != "browser.result":
            return

        request_id = message.get("request_id")
        if not isinstance(request_id, str):
            return
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_result(message)

    async def command(
        self,
        command: str,
        *,
        target: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: float = 8.0,
    ) -> dict[str, Any]:
        websocket = self._websocket
        if websocket is None:
            raise BrowserBridgeError("浏览器扩展未连接，请先安装并启用 DeskPilot 浏览器扩展。")

        request_id = new_id()
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future
        try:
            await websocket.send_json(
                {
                    "type": "browser.command",
                    "request_id": request_id,
                    "command": command,
                    "target": target or {"tab": "active"},
                    "payload": payload or {},
                }
            )
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            raise BrowserBridgeError(f"浏览器扩展执行 {command} 超时。") from exc
        finally:
            self._pending.pop(request_id, None)

    async def collect_page(self, timeout: float = 8.0) -> dict[str, Any]:
        result = await self.command(
            "collect_page",
            payload={
                "include_visible_text": True,
                "include_dom_summary": True,
                "max_text_chars": 30000,
            },
            timeout=timeout,
        )
        if not result.get("ok"):
            error = result.get("error") or {}
            message = error.get("message") or "浏览器扩展采集当前页失败。"
            raise BrowserBridgeError(message)
        data = result.get("data")
        if not isinstance(data, dict):
            raise BrowserBridgeError("浏览器扩展返回了无效的当前页数据。")
        return data


browser_bridge = BrowserBridge()
