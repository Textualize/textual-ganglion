from abc import ABC, abstractmethod


class Stream(ABC):
    """A abstract stream for outgoing data.

    This will generally wrap a websocket, or a mock websocket.

    """

    def __init__(self) -> None:
        self._closing = False
        self._closed = False

    @property
    def is_closing(self) -> bool:
        """A stream that is closing may still receive packets, but not send."""
        return self._closing

    @property
    def is_closed(self) -> bool:
        """A closed stream may no longer send or receive packets."""
        return self._closed

    @property
    def allow_send(self) -> bool:
        """Check is send is permitted (not closed or closing)."""
        return not (self._closing or self._closed)

    @abstractmethod
    async def send_bytes(self, data: bytes) -> bool:
        """Send a packet.

        Args:
            data (bytes): Bytes to send.

        Returns:
            bool: True if the bytes were sent, False if the send failed.
        """

    @abstractmethod
    async def close(self, code: int = 1000, message: str = "") -> None:
        """Close the stream. Further sends will fail."""
