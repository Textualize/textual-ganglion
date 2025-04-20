from __future__ import annotations

import datetime
from typing import Generic, List, TypeVar, cast

import rich.repr
from sqlalchemy import ForeignKey, UniqueConstraint, func, inspect
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from . import identity

IdentityType = TypeVar("IdentityType", bound=str)


class IdentityProperty(Generic[IdentityType]):
    """Create a property that cases self.id to the appropriate identity type."""

    def __get__(self, obj: Base, _objtype: type[Base] | None = None) -> IdentityType:
        return cast(IdentityType, obj.id)


@rich.repr.auto
class Base(AsyncAttrs, DeclarativeBase):
    """Base class for models."""

    # id: Mapped[str]

    def __rich_repr__(self) -> rich.repr.Result:
        inspect_self = inspect(self)
        if inspect_self is not None:
            for key, state in inspect_self.attrs.items():
                try:
                    yield key, state.value
                except Exception:
                    pass


class AccountToUser(Base):
    """Association table to join account and user."""

    __tablename__ = "account_to_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    role: Mapped[str] = mapped_column(default="admin")  # Placeholder for variable roles

    account: Mapped[Account] = relationship(back_populates="users")
    user: Mapped[User] = relationship(back_populates="accounts")

    __table_args__ = (UniqueConstraint("account_id", "user_id"),)


class APIKey(Base):
    """An API key associated with an account."""

    __tablename__ = "apikey"

    identity = IdentityProperty[identity.APIKeyIdentity]()

    id: Mapped[str] = mapped_column(primary_key=True)
    create_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    key: Mapped[str] = mapped_column(unique=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"))
    account: Mapped[Account] = relationship(back_populates="api_keys")


class Account(Base):
    """A user / company account."""

    __tablename__ = "account"

    identity = IdentityProperty[identity.AccountIdentity]()

    id: Mapped[str] = mapped_column(primary_key=True)
    create_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    name: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    temporary: Mapped[bool]

    api_keys: Mapped[List[APIKey]] = relationship(back_populates="account")
    applications: Mapped[List[Application]] = relationship(back_populates="account")
    usage_buckets: Mapped[List[UsageBucket]] = relationship(
        back_populates=("account"), cascade="all, delete-orphan"
    )

    users: Mapped[List[AccountToUser]] = relationship()


class UsageBucket(Base):
    __tablename__ = "usagebucket"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"))
    account: Mapped[Account] = relationship()

    start_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    seconds: Mapped[float] = mapped_column(default=0, nullable=False)


class User(Base):
    """A user."""

    __tablename__ = "user"

    identity = IdentityProperty[identity.UserIdentity]()
    id: Mapped[str] = mapped_column(primary_key=True)

    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    validated: Mapped[bool] = mapped_column(default=False)
    password_hash: Mapped[str]

    auth_tokens: Mapped[List[AuthToken]] = relationship(
        back_populates="user", lazy="joined"
    )

    accounts: Mapped[List[AccountToUser]] = relationship(lazy="joined")


class AuthToken(Base):
    """An auto token (indicates user is logged in)."""

    __tablename__ = "authtoken"

    token: Mapped[str] = mapped_column(primary_key=True)
    create_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    user: Mapped[User] = relationship(lazy="joined")


class Application(Base):
    """An application served by an ApplicationClient"""

    __tablename__ = "application"

    # Exposed fields (may be updated by client)
    EXPOSED_FIELDS = {"name", "slug", "color"}

    identity = IdentityProperty[identity.ApplicationIdentity]()

    id: Mapped[str] = mapped_column(primary_key=True)
    create_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), nullable=False)
    account: Mapped[Account] = relationship(lazy="joined")

    client_id: Mapped[str] = mapped_column(ForeignKey("applicationclient.id"))
    client: Mapped[ApplicationClient] = relationship(
        back_populates="applications", lazy="joined"
    )

    routing_code: Mapped[str]
    region: Mapped[str | None] = mapped_column(nullable=True)

    name: Mapped[str]
    slug: Mapped[str]
    color: Mapped[str]


class ApplicationClient(Base):
    """A client which serves applications (textual-serve)."""

    __tablename__ = "applicationclient"

    identity = IdentityProperty[identity.ApplicationClientIdentity]()

    id: Mapped[str] = mapped_column(primary_key=True)
    create_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"))
    account: Mapped[Account] = relationship()

    applications: Mapped[List[Application]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )

    routing_code: Mapped[str]

    ip_address: Mapped[str] = mapped_column(server_default="", nullable=False)


class WebClient(Base):
    """A web client where applications are served."""

    __tablename__ = "webclient"

    identity = IdentityProperty[identity.WebClientIdentity]()

    id: Mapped[str] = mapped_column(primary_key=True)
    create_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    ip_address: Mapped[str] = mapped_column(server_default="", nullable=False)


class ApplicationSession(Base):
    __tablename__ = "applicationsession"

    id: Mapped[str] = mapped_column(primary_key=True)
    create_date: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    application_id: Mapped[str] = mapped_column(ForeignKey("application.id"))
    application: Mapped[Application] = relationship()
