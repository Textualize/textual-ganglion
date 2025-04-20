from __future__ import annotations

import json
import logging
from asyncio import current_task
from datetime import datetime, timedelta
import os
from types import TracebackType
from typing import Self, Type

import aiohttp
from aiohttp.web import Request, WebSocketResponse

from .identity import WebClientIdentity
from .models import Application
from .registry import Registry
from .usage import add_usage

log = logging.getLogger("ganglion")


class WebClientService:
    """Manages a web client (websocket connection to the browser)."""

    registry: Registry[WebClientIdentity, WebClientService] = Registry()

    def __init__(
        self,
        request: Request,
        websocket: WebSocketResponse,
        identity: WebClientIdentity,
        application: Application,
        size: tuple[int, int],
    ) -> None:
        self._request = request
        self.websocket = websocket
        self.identity = identity
        self.application = application
        self.initial_size = size

    async def __aenter__(self) -> Self:
        try:
            self.task = current_task()
            self.registry.add_service(self.identity, self)
        except Exception:
            log.exception("Error in WebClientServe.__aenter__")
            raise
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.registry.remove_service(self.identity)

    async def send_bytes(self, data: bytes) -> bool:
        if self.websocket.closed:
            return False
        try:
            await self.websocket.send_bytes(data)
        except ConnectionResetError:
            return False
        return True

    async def send_meta(self, data: object) -> bool:
        if self.websocket.closed:
            return False
        try:
            await self.websocket.send_json(data)
        except ConnectionResetError:
            return False
        return True

    async def run(self) -> None:
        """Run the websocket"""

        from .application_service import ApplicationService

        application_service = ApplicationService.registry.get(
            self.application.client.identity
        )
        assert (
            application_service is not None
        ), f"No application with identity {self.application.client.identity}"

        websocket = self.websocket

        route = await application_service.open_session(
            self.application.identity,
            self.application.slug,
            self.identity,
            self.initial_size,
        )

        user_agent = self._request.headers.get("User-Agent", "unknown")
        ip_address = self._request.headers.get(
            "Fly-Client-IP", self._request.remote or ""
        )
        await application_service.send_info(
            f"{ip_address} {self.application.name!r} {user_agent!r} "
        )

        start_time = datetime.now()
        try:
            await self.send_meta(["instance_id", os.getenv("FLY_MACHINE_ID", "")])
            async for message in websocket:
                if message.type == aiohttp.WSMsgType.TEXT:
                    try:
                        message_data: list | dict = json.loads(message.data)
                    except Exception as error:
                        await websocket.close(
                            code=aiohttp.WSCloseCode.ABNORMAL_CLOSURE,
                            message=(
                                b"JSON decode error; {%s}"
                                % (str(error).encode("utf-8", errors="ignore"))
                            ),
                        )
                        break
                    else:
                        match message_data:
                            case ["stdin", stdin]:
                                await route.send_stdin(stdin.encode("utf-8", "ignore"))
                            case ["resize", {"width": width, "height": height}]:
                                await route.send_application_size(width, height)
                            case ["ping", data]:
                                await route.send_ping(data)
                            case ["focus"]:
                                await route.send_focus()
                            case ["blur"]:
                                await route.send_blur()
                            case _:
                                if not isinstance(message_data, list):
                                    await websocket.close(
                                        code=aiohttp.WSCloseCode.ABNORMAL_CLOSURE,
                                        message=b"Expected list",
                                    )
                                    break
        finally:
            end_time = datetime.now()
            await application_service.close_session(route.session_identity, route.key)
            await add_usage(self.application.account, start_time, end_time)
            usage_seconds = (end_time - start_time).seconds
            await application_service.send_info(
                f"{ip_address} {self.application.name!r} {timedelta(seconds=usage_seconds)}"
            )

    async def close(self, message: bytes) -> None:
        await self.websocket.close(message=b"Server going away (try again later)")
