import pytest

from ganglion.msgpack_codec import MsgPackCodec


@pytest.mark.parametrize(
    "data", [[], [1], [b""], [""], [b"foo"], ["bar"], [1, b"foo", "bar"]]
)
def test_msgpack_codec(data):

    codec = MsgPackCodec()

    # Encoded should result in a bytes result
    encoded = codec.encode(data)
    assert isinstance(encoded, bytes)

    # Decoding should result in the original input data
    decoded = codec.decode(encoded)
    assert decoded == data
