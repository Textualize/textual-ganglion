"""
A number of app level constants where the value is pulled from environment variables.
"""

import os
from pathlib import Path
from typing import Final
import logging


log = logging.getLogger("ganglion")

get_environ = os.environ.get


def get_environ_bytes(name: str, default: bytes) -> bytes:
    """Get an environment variable as bytes.

    Args:
        name (str): Name of environment variable.
        default (bytes): Default bytes.

    Returns:
        bytes: Env var value.
    """
    try:
        value = os.environ[name].encode("utf-8")
    except KeyError:
        value = default
    return value


def get_environ_bool(name: str) -> bool:
    """Check an environment variable switch.

    Args:
        name (str): Name of environment variable.

    Returns:
        bool: True if the env var is "1", otherwise False.
    """
    has_environ = os.environ.get(name) == "1"
    return has_environ


def get_environ_int(name: str, default: int) -> int:
    """Check an environment variable int.

    Args:
        name (str): Name of the environment variable.

    Returns:
        int: An integer.
    """

    try:
        value = os.environ[name]
    except KeyError:
        return default

    try:
        return int(value)
    except ValueError:
        log.error(
            "Environment variable {name!r} expected an integer, using default of {default}"
        )
        return default


DATA_PATH: Final[str] = str(Path(__file__).absolute().parent / "data")


DEBUG: Final[bool] = get_environ_bool("DEBUG")
DEBUG_SQL: Final[bool] = get_environ_bool("DEBUG_SQL")
SECRET: Final[str] = get_environ("GANGLION_SECRET", "sdf234234smnbrteoritwoiernfspewer")
SECRET_BYTES = SECRET.encode("utf-8")

SERVER: Final[str] = get_environ("GANGLION_SERVER", "dev")
SERVER_INSTANCE: Final[str] = get_environ("GANGLION_INSTANCE", "A")

SERVER_ID: Final[str] = f"{SERVER}-{SERVER_INSTANCE}"

GANGLION_CONFIG: Final[str] = get_environ(
    "GANGLION_CONFIG", f"{DATA_PATH}/ganglion-local.toml"
)
GANGLION_PORT: Final[int] = get_environ_int("GANGLION_PORT", 8080)

ROUTING_CODE: Final[str] = get_environ("FLY_MACHINE_ID", "local")
REGION: Final[str] = get_environ("FLY_REGION", "lhr")

LOG_LEVEL: Final[str] = get_environ("LOG_LEVEL", "INFO")
