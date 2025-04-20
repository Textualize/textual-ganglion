from contextlib import asynccontextmanager
import logging
from rich import print
from typing import AsyncGenerator, Iterable

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession


from .config import Config
from .context import (
    set_db_session,
    get_db_session,
    reset_db_session,
    set_session_maker,
    get_session_maker,
)
from . import constants
from . import identity
from .password import hash_password

from .models import (
    AuthToken,
    APIKey,
    Application,
    Account,
    AccountToUser,
    WebClient,
    ApplicationClient,
    User,
)


log = logging.getLogger("ganglion")


async def init_db(config: Config) -> AsyncEngine:
    """Initialize the database.

    Should be called once on init.

    Args:
        config: Configuration object

    Returns:
        SQLAlchemy AsyncEngine object.
    """
    db_url = config.db.url
    if db_url.startswith("postgres:"):
        _protocol, _separator, url = db_url.partition(":")
        db_url = f"postgresql+asyncpg:{url}"
        db_url = db_url.replace("?sslmode=disable", "?ssl=disable")
    engine = create_async_engine(
        db_url, pool_pre_ping=True, pool_size=30, max_overflow=0
    )
    if constants.DEBUG_SQL:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    set_session_maker(async_sessionmaker(engine, expire_on_commit=False))
    return engine


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_maker()() as session:
        token = set_db_session(session)
        try:
            yield session
        except Exception as error:
            await session.rollback()
            raise
        else:
            await session.commit()
        finally:
            reset_db_session(token)


async def get_application_from_slugs(
    account_slug: str, slug: str, routing_code: str
) -> Application | None:
    """Get application

    Args:
        account_slug: Account slug.
        slug: Application slug.
        routing_code: Server routing code.

    Returns:
        Application object.
    """
    session = get_db_session()
    application = (
        await session.execute(
            select(Application)
            .join(Application.account)
            .where(
                Application.slug == slug,
                Account.slug == account_slug,
            ),
        )
    ).scalar()
    return application


async def get_applications(account_slug: str, slug: str) -> list[Application]:
    """Get an application.

    Args:
        account_slug: Account slug.
        slug: Application slug.

    Returns:
        list of matching applications.
    """
    session = get_db_session()
    applications = list(
        (
            await session.execute(
                select(Application)
                .join(ApplicationClient)
                .join(Account)
                .where(
                    Application.slug == slug,
                    Account.slug == account_slug,
                )
            )
        ).scalars()
    )
    return applications


async def get_api_key(key: str) -> APIKey | None:
    """Get an APIKey object from a key string.

    Args:
        session: Async session.
        key: API key.

    Returns:
        APIKey instance.
    """
    session = get_db_session()
    api_key = (
        await session.execute(select(APIKey).where(APIKey.key == key).join(Account))
    ).scalar()
    return api_key


async def create_web_client() -> WebClient:
    """Create a new web client.

    Args:
        session: AsyncSession

    Returns:
        WebClient instance.
    """
    session = get_db_session()
    web_client = WebClient(id=identity.new_web())
    session.add(web_client)
    return web_client


async def create_user(name: str, email: str, password: str) -> User:
    session = get_db_session()
    user = User(
        id=identity.new_user(),
        name=name,
        email=email,
        password_hash=hash_password(password),
    )
    session.add(user)
    return user


async def check_email(email: str) -> bool:
    session = get_db_session()
    return (
        await session.execute(select(User).where(User.email == email))
    ).unique().one_or_none() is None


async def check_account_slug(slug: str) -> bool:
    session = get_db_session()
    return (
        await session.execute(select(Account).where(Account.slug == slug))
    ).unique().one_or_none() is None


async def login_user(user: User) -> AuthToken:
    session = get_db_session()
    auth_token = AuthToken(token=identity.generate(20), user=user)
    session.add(auth_token)
    return auth_token


async def create_account(
    name: str, slug: str, users: Iterable[User]
) -> tuple[Account, APIKey]:
    session = get_db_session()
    account = Account(
        id=identity.new_account(),
        name=name,
        slug=slug,
        temporary=False,
    )
    for user in users:
        account_to_user = AccountToUser(account_id=account.id, user_id=user.id)
        await session.commit()
        print(account_to_user.id)
        session.add(account_to_user)

    api_key_identity = identity.new_apikey()
    _, key = identity.parse(api_key_identity)
    api_key = APIKey(id=api_key_identity, account=account, key=key)
    session.add(account)
    session.add(api_key)
    return account, api_key


async def delete_web_client(web_client: WebClient) -> None:
    """Remove a web client from the database.

    Args:
        web_client: WebClient instance to remove.
    """
    session = get_db_session()
    await session.delete(web_client)


async def create_temporary_account(email: str = "") -> Account:
    """Create a temporary account.

    Args:
        email: Email address.

    """
    session = get_db_session()
    account_identity = identity.new_account()
    account = Account(
        id=account_identity,
        name="",
        slug=identity.unqualify(account_identity).lower(),
        temporary=True,
    )
    session.add(account)
    return account


async def delete_account(account: Account) -> None:
    session = get_db_session()
    await session.delete(account)


async def create_application_client(
    account: Account, routing_code: str
) -> ApplicationClient:
    """Create a new application client.

    Args:
        account: Account associated with application client.

    Returns:
        New models.ApplicationClient instance.
    """
    session = get_db_session()
    application_client = ApplicationClient(
        account=account,
        id=identity.new_application_client(),
        routing_code=routing_code,
    )
    session.add(application_client)
    return application_client


async def get_application_client(identity: str) -> ApplicationClient | None:
    """Get an application client from an identity.

    Args:
        identity: Application client identity.

    Returns:
        An ApplicationClient instance or `None` if none exists.
    """
    session = get_db_session()
    application_client = (
        await session.execute(
            select(ApplicationClient)
            .where(ApplicationClient.id == identity)
            .join(Account)
        )
    ).scalar()
    return application_client


async def delete_application_client(application_client: ApplicationClient) -> None:
    """Delete an application client.

    Args:
        application_client: Application client instance.
    """
    session = get_db_session()
    await session.delete(application_client)


async def delete_application_clients_by_routing_code(routing_code: str) -> None:
    """Delete application clients with the given routing code.

    Args:
        session: AsyncSession.
        routing_code: Routing code.
    """
    session = get_db_session()
    await session.execute(
        delete(Application).where(Application.routing_code == routing_code)
    )
    _application_clients = await session.execute(
        delete(ApplicationClient).where(ApplicationClient.routing_code == routing_code)
    )


async def create_applications(
    application_client: ApplicationClient,
    routing_code: str,
    application_data: list[dict[object, object]],
) -> list[Application]:
    """Create new applications associated with an application client.

    Args:
        application_client: Application client.
        routing_code: Server routing code.
        application_data: Raw data from client.
    """

    session = get_db_session()
    new_applications: list[Application] = []
    for application_dict in application_data:
        application = Application(
            account_id=(await application_client.awaitable_attrs.account).identity,
            id=identity.new_application(),
            client=application_client,
            routing_code=routing_code,
            region=constants.REGION,
            **{
                key: value
                for key, value in application_dict.items()
                if isinstance(key, str) and key in Application.EXPOSED_FIELDS
            },
        )
        if not application.slug:
            application.slug = identity.generate().lower()
        if not application.name:
            application.name = "Application"
        session.add(application)
        new_applications.append(application)
    await session.commit()
    return new_applications
