from __future__ import annotations

from asyncio import Task, current_task
from contextlib import _AsyncGeneratorContextManager
from time import monotonic
from logging import getLogger
from typing import Self, Type, TYPE_CHECKING
from types import TracebackType


import rich.repr
from sqlalchemy.ext.asyncio import AsyncSession


from . import constants
from . import packets
from . import db
from .identity import (
    ApplicationClientIdentity,
    WebClientIdentity,
    ApplicationIdentity,
    SessionIdentity,
    new_session,
)
from .packets import Handlers, Packet

from ._binary_encode import load as binary_load
from ._filesize import decimal
from .context import get_router
from .models import ApplicationClient
from .router import Route, RouteKey
from .stream import Stream
from .msgpack_codec import MsgPackCodec
from .registry import Registry
from .packet_decoder import PacketDecoder
from .web_client_service import WebClientService


from ._digest import hash_with_salt, check_digest

if TYPE_CHECKING:
    from .server import GanglionWebServer
    from .download_manager import DownloadManager

log = getLogger("ganglion")


@rich.repr.auto
class ApplicationService(Handlers):
    """An application service.

    A Textual app (or rather an agent that spawns Textual apps) connects to this end-point via websocket.
    """

    registry: Registry[ApplicationClientIdentity, ApplicationService] = Registry()

    def __init__(
        self,
        server: GanglionWebServer,
        stream: Stream,
        identity: ApplicationClientIdentity,
        download_manager: DownloadManager,
    ) -> None:
        self.server = server
        self.stream = stream
        self.codec = MsgPackCodec()
        self._packet_decoder = PacketDecoder(self.codec)
        self.identity = identity
        self._round_trip_time: float | None = None
        self.task: Task | None = None
        self._bytes_sent = 0
        self._bytes_received = 0
        self._poll_time: float = monotonic()
        self._download_manager = download_manager

    def db_session(self) -> _AsyncGeneratorContextManager[AsyncSession]:
        """Get a DB session context manager."""
        return self.server.db_session()

    def cancel(self) -> None:
        if self.task is not None:
            self.task.cancel()

    async def __aenter__(self) -> Self:
        self.task = current_task()
        self.registry.add_service(self.identity, self)
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.registry.remove_service(self.identity)
        self.task = None

    async def start(self) -> bool:
        await self.send_ping()
        return True

    async def close(self) -> None:
        await self.stream.close()

    async def poll(self) -> None:
        """Called at regular intervals."""
        poll_time = monotonic()
        time_delta = poll_time - self._poll_time
        sent = int((self._bytes_sent) / time_delta)
        received = int((self._bytes_received) / time_delta)

        self._bytes_sent = 0
        self._bytes_received = 0
        self._poll_time = poll_time

        if sent or received:
            await self.send_info(f"In: {decimal(sent)}/s Out: {decimal(received)}/s")

    async def send_log(self, message: str) -> bool:
        """Send a log message.

        Args:
            message: Message to send.
        """
        return await self.send(packets.Log(message))

    async def send_info(self, message: str) -> bool:
        """Send an info message.

        Args:
            message: Message to send.
        """
        return await self.send(packets.Info(message))

    async def send(self, packet: Packet) -> bool:
        """Send a packet.

        Args:
            packet (Packet): Packet to send.

        Returns:
            bool: True if the packet was sent, or False if the stream was closing or closed.
        """
        log.debug("<SEND> %r", packet)
        packet_bytes = self.codec.encode(packet)
        self._bytes_sent += len(packet_bytes)
        return await self.stream.send_bytes(packet_bytes)

    async def process_bytes(self, data: bytes) -> None:
        """Process bytes from a websocket message.

        Args:
            data (bytes): Bytes from a message.
        """
        self._bytes_received += len(data)
        try:
            packet = self._packet_decoder.decode(data)
        except Exception as error:
            log.exception("Error decoding bytes")
            await self.handle_packet_decode_error(data, error)
        else:
            if packet is None:
                log.warning("Unknown packet")
                await self.handle_unknown_packet(data)
            else:
                log.debug("<RECV> %r", packet)
                try:
                    await self.handle_packet(packet)
                except Exception as error:
                    if constants.DEBUG:
                        from rich.traceback import Traceback
                        from rich import print

                        print(Traceback(show_locals=True))
                    else:
                        log.exception("Error in packet handler for %r", packet)
                    await self.handle_packet_error(packet, error)

    async def handle_packet_decode_error(self, data: bytes, error: Exception) -> None:
        """Incoming packet is not encoded correctly. Probably a client sending garbage.

        Args:
            data (bytes): Raw data.
            error (Exception): Exception object.
        """

        await self.stream.close()

    async def handle_unknown_packet(self, data: bytes) -> None:
        """Packet is encoded correctly, but the packet type isn't recognised.

        Args:
            data (bytes): Data in packet.
        """
        await self.stream.close()

    async def handle_packet_error(self, packet: Packet, error: Exception) -> None:
        await self.stream.close()

    async def handle_packet(self, packet: Packet) -> None:
        await self.dispatch_packet(packet)

    async def get_application_client(self) -> ApplicationClient:
        async with self.db_session():
            application_client = await db.get_application_client(self.identity)

        assert application_client is not None
        return application_client

    async def send_ping(self) -> None:
        """Send a ping packet."""
        # A ping consists of data plus a salted hash
        # Our data is the server time
        # We can use this to calculate the round trip time when the client returns a pong
        data = b"%f" % monotonic()
        digest = hash_with_salt(data)
        await self.send(packets.Ping(b"%s/%s" % (data, digest.encode("utf-8"))))

    async def open_session(
        self,
        application_identity: ApplicationIdentity,
        application_slug: str,
        web_client_identity: WebClientIdentity,
        size: tuple[int, int],
    ) -> Route:
        router = get_router()
        session_identity = new_session()
        route = router.add_route(session_identity, web_client_identity, self.identity)
        width, height = size
        await self.send(
            packets.SessionOpen(
                session_id=session_identity,
                app_id=application_identity,
                application_slug=application_slug,
                route_key=route.key,
                width=width,
                height=height,
            )
        )
        return route

    async def close_session(
        self, session_identity: SessionIdentity, route_key: RouteKey
    ) -> None:
        await self.send(packets.SessionClose(session_identity, route_key))
        await self._download_manager.cancel_app_downloads(self.identity)

    async def send_route(self, route: Route, data: bytes) -> bool:
        return await self.send(packets.SessionData(route.key, data))

    # -- Packet handlers --------------------------------------------------------------

    async def on_log(self, packet: packets.Log) -> None:
        """A message to be written to debug logs."""
        print(f"LOG {packet.message!r}")

    async def on_ping(self, packet: packets.Ping) -> None:
        """Request packet data to be returned via a PONG"""
        await self.send(packets.Pong(packet.data))

    async def on_pong(self, packet: packets.Pong) -> None:
        """Client replied to ping."""
        received_time = monotonic()
        data, separator, digest = packet.data.partition(b"/")
        if not separator:
            return

        if not check_digest(data, digest):
            # The digest doesn't match
            # This means the pong is not in response to our ping
            print("Unsolicited pong")
            return

        # Since the digest matches we can be sure this is the same data we were sent
        self._round_trip_time = round_trip_time = received_time - float(
            data.decode("utf-8")
        )
        log.debug("ping=%.1dms", round_trip_time * 1000)

    async def on_declare_apps(self, packet: packets.DeclareApps) -> None:
        async with self.db_session():
            application_client = await db.get_application_client(self.identity)
            if application_client is not None:
                applications = await db.create_applications(
                    application_client,
                    self.server.routing_code,
                    packet.apps,
                )
                await self.send_info("---")
                for application in applications:
                    url = self.server.get_app_url(
                        application.account.slug, application.slug
                    )
                    await self.send_info(f"Serving {url}")

    async def on_session_data(self, packet: packets.SessionData) -> None:
        route = get_router().get_route(RouteKey(packet.route_key))
        if route is None:
            return
        web_client = WebClientService.registry.get(route.web)
        if web_client is not None:
            try:
                await web_client.websocket.send_bytes(packet.data)
            except Exception:
                # TODO: Handle transport errors
                pass

    async def on_route_pong(self, packet: packets.RoutePong) -> None:
        route = get_router().get_route(RouteKey(packet.route_key))
        if route is not None and route.web_client_service is not None:
            await route.web_client_service.send_meta(["pong", packet.data])

    async def on_session_close(self, packet: packets.SessionClose) -> None:
        route = get_router().get_route(RouteKey(packet.route_key))
        if route is not None:
            web_client = WebClientService.registry.get(route.web)
            if web_client is not None:
                await web_client.close(b"Remote client closed the session")

    async def on_open_url(self, packet: packets.OpenUrl) -> None:
        route = get_router().get_route(RouteKey(packet.route_key))
        if route is not None:
            web_client = WebClientService.registry.get(route.web)
            if web_client is not None:
                await web_client.send_meta(
                    ["open_url", {"url": packet.url, "new_tab": packet.new_tab}]
                )

    async def on_deliver_file_start(self, packet: packets.DeliverFileStart) -> None:
        """The app indicates to the server that it is ready to send a file."""
        log.debug("Deliver file start")

        router = get_router()
        route_key = RouteKey(packet.route_key)
        route = router.get_route(route_key)

        delivery_key = packet.delivery_key

        await self._download_manager.create_download(
            route_key=route_key,
            delivery_key=delivery_key,
            file_name=packet.file_name,
            open_method=packet.open_method,
            mime_type=packet.mime_type,
            encoding=packet.encoding,
        )

        # Get the web client so we can inform the front-end that the file is ready to be delivered
        # This will trigger the front-end to visit the appropriate endpoint to download the file.
        if route is not None:
            web_client_id = route.web
            web_client = WebClientService.registry.get(web_client_id)
            if web_client is not None:
                await web_client.send_meta(["deliver_file_start", delivery_key])

    async def on_binary_encoded_message(
        self, packet: packets.BinaryEncodedMessage
    ) -> None:
        unpacked = packet.data
        # If we receive a chunk, hand it to the download manager to
        # handle distribution to the browser.
        unpacked = binary_load(packet.data)
        if unpacked[0] == "deliver_chunk":
            _, delivery_key, chunk = unpacked
            await self._download_manager.chunk_received(delivery_key, chunk)
