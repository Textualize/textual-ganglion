import logging
from logging import StreamHandler


from rich.logging import RichHandler
from . import constants


def init_logging() -> None:
    FORMAT = "%(message)s"

    import sqlalchemy

    if constants.DEBUG:
        logging.basicConfig(
            level="NOTSET",
            format=FORMAT,
            datefmt="[%X]",
            handlers=[
                RichHandler(
                    rich_tracebacks=True,
                    tracebacks_show_locals=True,
                    tracebacks_suppress=[sqlalchemy],
                    show_path=False,
                )
            ],
            force=True,
        )
    else:
        logging.basicConfig(
            level=constants.LOG_LEVEL,
            format=FORMAT,
            datefmt="[%X]",
            handlers=[StreamHandler()],
            force=True,
        )
