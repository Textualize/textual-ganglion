from __future__ import annotations

from aiohttp import web


from .stream import Stream


class WebsocketStream(Stream):
    def __init__(self, websocket: web.WebSocketResponse) -> None:
        self._websocket = websocket
        super().__init__()

    async def send_bytes(self, data: bytes) -> bool:
        if self.allow_send:
            try:
                await self._websocket.send_bytes(data)
            except ConnectionResetError:
                return False
            return True
        return True

    async def close(self, code: int = 1000, message: str = "") -> None:
        await self._websocket.close(
            code=code, message=message.encode("utf-8", errors="replace")
        )
