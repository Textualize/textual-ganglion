from __future__ import annotations

from contextvars import ContextVar, Token
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .server import GanglionWebServer
    from .router import Router


server_context: ContextVar[GanglionWebServer] = ContextVar("server_context")

db_session_context: ContextVar[AsyncSession] = ContextVar("db_session_context")

session_maker_context: ContextVar = ContextVar("session_maker_context")


def get_server() -> GanglionWebServer:
    """Get the active server instance."""
    return server_context.get()


def get_router() -> Router:
    """Get the active Router instance."""
    return get_server().router


def get_db_session() -> AsyncSession:
    """Get the Database session."""
    return db_session_context.get()


def set_db_session(session: AsyncSession) -> Token:
    """Set the db session."""
    return db_session_context.set(session)


def reset_db_session(token: Token) -> None:
    db_session_context.reset(token)


def set_session_maker(session_maker) -> None:
    session_maker_context.set(session_maker)


def get_session_maker() -> Callable[[], AsyncSession]:
    return session_maker_context.get()
