"""
The Service class is a base class for objects which respond to incoming websocket data.

Services are sans IO, which means they delegate the responsibility of send and receiving network data to helper objects.

This will make them easier to test, as we can write mocks for tests.

"""


from __future__ import annotations

from asyncio import Task, current_task
from rich import print
from typing import (
    Callable,
    Awaitable,
    Generic,
    TypeVar,
    Type,
    Self,
)
from types import TracebackType
from starlette.types import Message


from .codec import Codec
from .console import print
from .packets import Packet, Handlers
from .stream import Stream
from .packet_decoder import PacketDecoder
from .registry import Registry

from logging import getLogger

log = getLogger("ganglion")


async def run_service(
    service: Service, get_message: Callable[[], Awaitable[Message]]
) -> None:
    """Run a service from a Starlette Websocket.

    Args:
        service (Service): Service object
        get_message (Callable[[], Awaitable[Message]]): Awaitable that gets the next message.
    """
    if not await service.start():
        return

    while not service.stream.is_closed:
        match message := await get_message():
            case {"type": "websocket.disconnect"}:
                print("Disconnected")
                break
            case {"type": "websocket.receive", "bytes": data_bytes}:
                await service.process_bytes(data_bytes)
            case _:
                print(f"Unknown message: {message!r}")


IdentityType = TypeVar("IdentityType")


class Service(Handlers, Generic[IdentityType]):
    """An abstract service that processes byte packets."""

    registry: Registry[IdentityType, Self] = Registry()

    def __init__(self, stream: Stream, codec: Codec, identity: IdentityType) -> None:
        """Create a service.

        Args:
            stream (PacketStream): A packet stream.
            codec (Codec): A codec.
        """

        self.stream = stream
        self.codec = codec
        self.identity = identity
        self._packet_decoder = PacketDecoder(codec)
        self.task: Task | None = None

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
        """Called when the service starts.

        Returns:
            bool: True to indicate the service should continue, or False to prevent further processing.
        """
        return True

    async def send(self, packet: Packet) -> bool:
        """Send a packet.

        Args:
            packet (Packet): Packet to send.

        Returns:
            bool: True if the packet was sent, or False if the stream was closing or closed.
        """
        log.debug("<SEND> %r", packet)
        packet_bytes = self.codec.encode(packet)
        return await self.stream.send_bytes(packet_bytes)

    async def process_bytes(self, data: bytes) -> None:
        """Process bytes from a websocket message.

        Args:
            data (bytes): Bytes from a message.
        """
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
                    print("packet error", error)
                    await self.handle_packet_error(packet, error)

    async def handle_packet_decode_error(self, data: bytes, error: Exception) -> None:
        """Incoming packet is not encoded correctly. Probably a client sending garbage.

        Args:
            data (bytes): Raw data.
            error (Exception): Exception object.
        """
        await self.stream.close()

    async def handle_unknown_packet(self, data: bytes) -> None:
        """Packet is encoded correctly

        Args:
            data (bytes): _description_
        """
        await self.stream.close()

    async def handle_packet_error(self, packet: Packet, error: Exception) -> None:
        await self.stream.close()

    async def handle_packet(self, packet: Packet) -> None:
        await self.dispatch_packet(packet)
