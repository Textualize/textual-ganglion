from __future__ import annotations

import sys
from typing import Any, IO

from rich.console import Console

from . import constants

__all__ = ["console", "print"]

console = Console(
    file=open(sys.__stdout__.fileno(), "wt"),
    quiet=not constants.DEBUG,
)

if constants.DEBUG:

    def print(
        *objects: Any,
        sep: str = " ",
        end: str = "\n",
        file: IO[str] | None = None,
        flush: bool = False,
    ) -> None:
        console.log(*objects, sep=sep, end=end, _stack_offset=2)

else:

    print = print
