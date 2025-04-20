from functools import partial
from typing import cast, Sequence

import msgpack

from .codec import Codec, CodecDataType, DecodeError


class MsgPackCodec(Codec):
    """A codec using the msgpack format."""

    def __init__(self) -> None:
        self._packb = partial(msgpack.packb, use_bin_type=True)
        self._unpackb = partial(msgpack.unpackb, use_list=True, raw=False)

    def encode(self, data: Sequence[object]) -> bytes:
        return cast(bytes, self._packb(data))

    def decode(self, packet: bytes) -> tuple[CodecDataType]:
        try:
            packet_data = self._unpackb(packet)
        except Exception as error:
            raise DecodeError(f"packet failed to decode; {error}")
        if not isinstance(packet_data, (tuple, list)):
            raise DecodeError(f"packet expected to be tuple, not {type(packet_data)}")
        return cast(tuple[CodecDataType], packet_data)
