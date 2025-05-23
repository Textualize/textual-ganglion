import hmac

from . import constants


def hash_with_salt(data: bytes) -> str:
    """Hash some data and return digest. We can use this digest to later validate the data.

    Args:
        data (bytes): Some bytes.

    Returns:
        bytes: A byte encoded digest.
    """
    digest = hmac.new(constants.SECRET_BYTES, data, "sha256").hexdigest()
    return digest


def check_digest(data: bytes, digest: bytes) -> bool:
    """Check the data was generated by use.

    Args:
        data (bytes): Some bytes to check digest against.
        digest (bytes): A digest.

    Returns:
        bool: True if the digest was generated on the server, or False if there is no match.
    """
    data_digest = (
        hmac.new(constants.SECRET_BYTES, data, "sha256").hexdigest().encode("utf-8")
    )
    return digest == data_digest
