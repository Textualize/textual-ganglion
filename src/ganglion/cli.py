import asyncio
from ast import literal_eval
from pathlib import Path
from typing import Iterable

import click
from rich.highlighter import ReprHighlighter
from rich.pretty import Pretty
from rich.table import Table
from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog
from textual.worker import Worker, WorkerState

from . import constants
from . import db
from . import identity
from ._logging import init_logging
from .config import load_config
from .db import init_db, db_session
from .packets import PACKET_NAME_MAP
from .packets import Packet
from .slugify import slugify


class ParseError(Exception):
    pass


@click.group()
def app():
    pass


@app.command()
@click.option(
    "--config",
    default=constants.GANGLION_CONFIG,
    show_default=constants.GANGLION_CONFIG,
    metavar="PATH.toml",
    help="Path to config",
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=constants.GANGLION_PORT,
    help="Port to serve HTTP on",
)
@click.option(
    "--exit-on-idle",
    type=int,
    default=-1,
    help="Number of seconds of inactivity before stopping the process.",
)
def serve(config: str, port: int, exit_on_idle: int) -> None:
    from .server import GanglionWebServer

    init_logging()

    config_path = Path(config)
    root_path = config_path.absolute().parent

    _config = load_config(Path(config))
    server = GanglionWebServer(root_path, _config, port=port, exit_on_idle=exit_on_idle)

    server.run()


@app.command()
@click.option(
    "--config",
    default=constants.GANGLION_CONFIG,
    metavar="PATH.toml",
    help="Path to config",
)
def initdb(config: str):
    server_config = load_config(config)
    from ganglion.models import Base

    async def run_init_db() -> None:
        engine = await init_db(server_config)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(run_init_db())


@app.command()
@click.option(
    "--config",
    default=constants.GANGLION_CONFIG,
    metavar="PATH.toml",
    help="Path to config",
)
@click.option("--name", default=None)
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.option("--slug", default=None)
def new_account(
    config: str,
    name: str | None = None,
    email: str | None = None,
    password: str | None = None,
    slug: str | None = None,
) -> None:
    from .db import init_db
    from rich import print

    server_config = load_config(config)
    name = input("Name: ") if name is None else name
    email = input("Email: ") if email is None else email
    password = input("Password: ") if password is None else password
    slug = slugify((input("Slug: ") if slug is None else slug) or name)

    async def insert_user() -> None:
        await init_db(server_config)
        async with db_session():
            user = await db.create_user(name, email, password)
            account = await db.create_account(name, slug, [user])
            print(f"Created account: {account!r}")

    asyncio.run(insert_user())


@app.command
@click.option(
    "--config",
    default=constants.GANGLION_CONFIG,
    metavar="PATH.toml",
    help="Path to config",
)
def list_accounts(config: str) -> None:
    from rich import print
    from .models import Account
    from sqlalchemy import select

    server_config = load_config(config)

    async def do_list():
        await init_db(server_config)
        async with db_session() as session:
            query = select(Account)
            accounts = list((await session.execute(query)).scalars())
        for account in accounts:
            print(account)

    asyncio.run(do_list())


@app.command
@click.option(
    "--config",
    default=constants.GANGLION_CONFIG,
    metavar="PATH.toml",
    help="Path to config",
)
def list_urls(config: str) -> None:
    server_config = load_config(config)
    from .models import Application
    from sqlalchemy import select

    server_config = load_config(config)

    async def list_urls():
        await init_db(server_config)
        async with db_session() as session:
            query = select(Application)
            applications = list((await session.execute(query)).scalars())
        for application in applications:
            url = f"{server_config.server.base_url}/{application.account.slug}/{application.slug}"
            print(url)

    asyncio.run(list_urls())


@app.command()
@click.argument("key")
@click.option(
    "--config",
    default=constants.GANGLION_CONFIG,
    metavar="PATH.toml",
    help="Path to config",
)
def get_account_from_api_key(key: str, config: str) -> None:
    from sqlalchemy import select
    from sqlalchemy.exc import NoResultFound
    from .models import APIKey
    from rich import print

    server_config = load_config(config)

    async def get_user() -> None:
        await init_db(server_config)

        async with db_session() as session:
            try:
                api_key = (
                    await session.execute(select(APIKey).where(APIKey.key == key))
                ).scalar_one()
            except NoResultFound:
                print("Not found")
            else:
                print(await api_key.awaitable_attrs.account)

    asyncio.run(get_user())


@app.command()
@click.argument("query")
@click.option(
    "--config",
    default=constants.GANGLION_CONFIG,
    metavar="PATH.toml",
    help="Path to config",
)
def get_user(config: str, query: str) -> None:
    from rich import print
    from .models import User, AccountToUser
    from sqlalchemy import select

    server_config = load_config(config)

    async def get_user() -> None:
        await init_db(server_config)
        async with db_session() as session:
            users = (
                (
                    await session.execute(
                        select(User).where(User.email == query).join(AccountToUser)
                    )
                )
                .unique()
                .scalars()
            )
            for user in users:
                print(user)
                for account_to_user in user.accounts:
                    print(await account_to_user.awaitable_attrs.account)

    asyncio.run(get_user())


@app.command()
@click.option(
    "--config",
    default=constants.GANGLION_CONFIG,
    metavar="PATH.toml",
    help="Path to config",
)
@click.option("--account-id", default=None)
@click.option("--name", default=None)
def new_application(
    config: str, account_id: str | None = None, name: str | None = None
) -> None:
    from sqlalchemy import select
    from .models import Account, Application
    from rich import print

    server_config = load_config(config)
    account_id = input("Account identity: ") if account_id is None else account_id
    name = input("Application name: ") if name is None else name

    async def insert_application() -> None:
        assert name is not None
        await init_db(server_config)

        async with db_session() as session:
            account = (
                await session.execute(select(Account).where(Account.id == account_id))
            ).scalar_one()

            application = Application(
                id=identity.new_application(),
                account=account,
                name=name,
                slug=slugify(name),
                color="#000000",
            )
            session.add(application)

            await session.commit()

            print(application)

    asyncio.run(insert_application())


@app.command()
def client() -> None:
    from .client import Client

    class LoggingClient(Client):
        def __init__(self, url: str, app: App) -> None:
            super().__init__(url)
            self.app = app

        async def send(self, packet: Packet) -> None:
            await super().send(packet)
            self.app.call_later(self.app.outgoing_packet, packet)

        async def dispatch_packet(self, packet: Packet) -> None:
            self.app.call_later(self.app.incoming_packet, packet)
            return await super().dispatch_packet(packet)

    class GanglionConsole(App):
        CSS = """
        Input {
            dock: bottom;
        }
        RichLog {
            height: 1fr;
        }
        """

        highlighter = ReprHighlighter()

        def compose(self) -> ComposeResult:
            yield RichLog(markup=True, highlight=True, wrap=True)
            yield Input(highlighter=ReprHighlighter())

        def on_ready(self) -> None:
            self.client = LoggingClient("ws://localhost:8080/app-service/", self)
            self.run_worker(self.client.run, exit_on_error=False)
            self.query_one(Input).focus()

        def write(self, prefix: str, data: object) -> None:
            grid = Table.grid(padding=1)
            grid.add_row(
                prefix,
                Pretty(data) if not isinstance(data, str) else self.highlighter(data),
            )
            self.query_one(RichLog).write(grid)

        def parse_parameters(self, message: str) -> Iterable[object]:
            """Parse a space separated list of Python literals.

            Args:
                message: Space separated literals.

            Returns:
                Iterable of objects

            """
            message += " "

            index = 0
            while index < len(message):
                char = message[index]
                if char == " ":
                    try:
                        yield literal_eval(message[:index])
                    except Exception:
                        pass
                    else:
                        message = message[index:]
                        index = 0
                        continue
                index += 1
            if message.strip():
                self.write(r"[red]\[error]", f"Unable to parse {message.strip()!r}")
                raise ParseError("parse parameters failed")

        async def make_packet(self, msg: str) -> Packet | None:
            text_log = self.query_one(RichLog)
            packet_name, _, payload = msg.partition(" ")

            try:
                packet_payload = list(self.parse_parameters(payload))
            except ParseError:
                return None

            packet_name = packet_name.lower()
            if packet_name not in PACKET_NAME_MAP:
                self.write("[red]\\[error]", "unknown command")
                return None

            packet_type = PACKET_NAME_MAP[packet_name]
            packet_data = []
            for datum, (attribute_name, attribute_type) in zip(
                packet_payload, packet_type._attributes
            ):
                try:
                    if isinstance(datum, str) and attribute_type is bytes:
                        packet_data.append(datum.encode("utf-8", errors="ignore"))
                    else:
                        packet_data.append(datum)
                except Exception as error:
                    text_log.write(str(error))
                    continue
            try:
                packet = packet_type.build(*packet_data)
            except Exception as error:
                text_log.write(str(error))
                return None
            return packet

        async def on_input_submitted(self, event) -> None:
            self.query_one(Input).value = ""
            packet = await self.make_packet(event.value)
            if packet is not None:
                await self.client.send(packet)

        async def outgoing_packet(self, packet: Packet) -> None:
            self.write(r"[dim]\[send]", packet)

        async def incoming_packet(self, packet: Packet) -> None:
            self.write(r"[dim]\[recv]", packet)

        def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
            if event.state == WorkerState.ERROR:
                self.query_one(RichLog).write(event.worker._error)
                self.query_one(Input).disabled = True
            if event.state == WorkerState.SUCCESS:
                self.query_one(RichLog).write("Connection closed")
                self.query_one(Input).disabled = True

    app = GanglionConsole()
    app.run()


def run():
    app(auto_envvar_prefix="GANGLION")
