from __future__ import annotations


import aiohttp


from .console import print
from .msgpack_codec import MsgPackCodec
from .packet_decoder import PacketDecoder
from . import packets
from .packets import Packet, Handlers


class ClientError(Exception):
    pass


class Client(Handlers):
    """A client class to connect to Ganglion and process messages."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.codec = MsgPackCodec()
        self.packet_decoder = PacketDecoder(self.codec)

    async def run(self) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.url, timeout=1) as websocket:
                self._websocket = websocket
                async for msg in websocket:
                    print(msg)
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        packet = self.packet_decoder.decode(msg.data)
                        if packet is not None:
                            # Dispatch the packet to its `on_` handler
                            await self.dispatch_packet(packet)
                        else:
                            await self.bad_packet(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        raise ClientError(str(msg))

    async def post_connect(self) -> None:
        """Called when the client connects, but prior to processing any messages."""

    async def bad_packet(self, packet: bytes) -> None:
        print("Unknown packet", packet)

    async def send(self, packet: Packet) -> None:
        """Send a packet.

        Args:
            packet (Packet): A undifferentiated packet.
        """
        packet_bytes = self.codec.encode(packet)
        await self._websocket.send_bytes(packet_bytes)

    async def on_ping(self, packet: packets.Ping) -> None:
        """Sent by the server."""
        # Reply to a Ping with an immediate Pong.
        await self.send(packets.Pong(packet.data))
