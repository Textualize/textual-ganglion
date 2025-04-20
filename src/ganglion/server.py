import asyncio
from datetime import datetime
import os
import random
import signal
from asyncio import CancelledError
from functools import partial
from logging import getLogger
from pathlib import Path
from contextlib import _AsyncGeneratorContextManager
from typing import cast

import aiohttp
import aiohttp_jinja2
import jinja2
from aiohttp import web
from aiohttp.web import Request
from aiohttp.web_runner import GracefulExit
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
import uvloop

from textual.color import Color

import rich.repr

from ganglion.download_manager import DownloadError, DownloadManager

from . import context
from . import constants
from . import identity
from .application_service import ApplicationService
from .config import Config
from .models import WebClient
from .console import print
from . import db
from . import api
from . import regions
from .db import init_db, db_session
from .timer import Timer
from .websocket_stream import WebsocketStream
from .web_client_service import WebClientService
from .router import Router
from .middlewares import setup_middlewares

log = getLogger("ganglion")


@rich.repr.auto(angular=True)
class GanglionWebServer:
    """The web(sockets) server."""

    def __init__(
        self,
        root_path: Path,
        config: Config,
        port: int,
        exit_on_idle: int,
    ) -> None:
        self.root_path = root_path
        self.config = config
        self.port = port

        self.exit_on_idle = exit_on_idle
        """Number of seconds of inactivity (no apps being served) to exit on."""

        self._idle_shutdown_timer: Timer | None = None
        """When the timer ends, the service will gracefully shutdown."""

        self.exiting = False
        self.routing_code = constants.ROUTING_CODE
        self._app: web.Application
        self.router = Router(
            WebClientService.registry,
            ApplicationService.registry,
        )
        self.download_manager = DownloadManager()
        self.start_time = datetime.now()
        self._poll_clients = Timer(60 * 15, self.poll_clients, "poll clients")

    def __rich_repr__(self) -> rich.repr.Result:
        yield from ()

    async def poll_clients(self) -> None:
        for app_service in list(ApplicationService.registry):
            await app_service.poll()

    def run(self) -> None:
        """Run the server."""

        print(self.config)

        async def make_app() -> web.Application:
            """Make the aiohttp Application object"""
            loop = asyncio.get_running_loop()

            log.info(f"loop={loop!r}")
            sqlalchemy_async_engine = await init_db(self.config)
            async_session_maker = async_sessionmaker(
                sqlalchemy_async_engine, expire_on_commit=False
            )
            context.set_session_maker(async_session_maker)

            self._app = app = web.Application()

            self._poll_clients.start()

            app.on_startup.append(self.on_startup)
            app.on_shutdown.append(self.on_shutdown)
            app.on_cleanup.append(self.on_cleanup)

            app["config"] = self.config
            app["engine"] = sqlalchemy_async_engine

            aiohttp_jinja2.setup(
                app,
                loader=jinja2.FileSystemLoader(self.config.templates.root),
            )

            # Set the active server
            context.server_context.set(self)

            self._add_routes(app)
            setup_middlewares(app)

            return app

        uvloop.install()
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self.request_exit)
        loop.add_signal_handler(signal.SIGTERM, self.request_exit)
        web.run_app(make_app(), port=self.port, handle_signals=False, loop=loop)

    async def on_shutdown(self, app: web.Application) -> None:
        """Hook called when server is shutting down."""
        create_task = asyncio.create_task
        if self._poll_clients is not None:
            await self._poll_clients.stop()
        if WebClientService.registry:
            await asyncio.wait(
                [
                    create_task(web_client.close(message=b"bye"))
                    for web_client in WebClientService.registry
                ]
            )

        if ApplicationService.registry:
            await asyncio.wait(
                [
                    create_task(app_client.close())
                    for app_client in ApplicationService.registry
                ]
            )

    async def on_startup(self, app: web.Application) -> None:
        await self.start_idle_shutdown_timer()

        async with self.db_session():
            await db.delete_application_clients_by_routing_code(self.routing_code)

    async def on_cleanup(self, app: web.Application) -> None:
        if self._idle_shutdown_timer is not None:
            await self._idle_shutdown_timer.stop()

    @property
    def app(self) -> web.Application:
        return self._app

    def db_session(self) -> _AsyncGeneratorContextManager[AsyncSession]:
        """Start a new DB session.

        Returns a context manager.

        """
        return db_session()

    def _add_routes(self, app: web.Application) -> None:
        """Add routes to the aiohttp app."""
        app.add_routes(
            [
                web.get(
                    "/",
                    self.handle_index,
                ),  # Placeholder index
                web.static(
                    "/static",
                    self.root_path / self.config.static.root,
                ),  # Static files
                web.get(
                    "/app-service/",
                    self.handle_application_service,
                    name="app-websocket",
                ),
                web.get("/download/{key}", self.handle_download, name="download"),
                web.get(
                    "/{account_slug}/{application_slug}/ws",
                    self.handle_web_client,
                    name="web-client",
                ),
                web.get(
                    "/{account_slug}/{application_slug}",
                    self.app_index,
                    name="app-index",
                ),  # Serve HTML with terminal
                web.post("/api/signup/", api.signup, name="api-signup"),
            ]
        )

    def get_app_url(self, account_slug: str, application_slug: str) -> str:
        """Get a URL for an app.

        Args:
            account_slug: Account slug.
            application_slug: Application slug.

        Returns:
            str: URL to app.
        """
        url = self.config.server.app_url_format.format(
            account=account_slug,
            application=application_slug,
        )
        return url

    def request_exit(self, reason: str | None = None) -> None:
        """Gracefully exit the application, optionally supplying a reason.

        Args:
            reason: The reason for exiting which will be included in the Ganglion server log.
        """
        log.info(f"Exiting - {reason if reason else ''}")
        raise GracefulExit()

    @aiohttp_jinja2.template("index.html")
    async def handle_index(self, request: Request):
        uptime = datetime.now() - self.start_time

        return {
            "name": "World",
            "uptime": uptime,
            "routing_code": self.routing_code,
            "region": os.environ.get("FLY_REGION", "?"),
        }

    async def handle_application_service(
        self, request: Request
    ) -> web.WebSocketResponse:
        """WS endpoint which the textual-serve connects to."""

        await self.stop_idle_shutdown_timer()

        key = request.headers.get("GANGLIONAPIKEY", None) or None

        async with self.db_session():
            if key is None:
                account = await db.create_temporary_account()
            else:
                # Lookup API Key
                api_key = await db.get_api_key(key)
                if api_key is None:
                    raise web.HTTPForbidden()
                # Create an application client object
                # This will live for the lifetime of the connection
                account = await api_key.awaitable_attrs.account
            application_client = await db.create_application_client(
                account, self.routing_code
            )
            application_client.ip_address = request.headers.get(
                "Fly-Client-IP", request.remote or ""
            )

        websocket = web.WebSocketResponse(heartbeat=15)
        try:
            await websocket.prepare(request)

            stream = WebsocketStream(websocket)
            service = ApplicationService(
                self,
                stream,
                identity=application_client.identity,
                download_manager=self.download_manager,
            )

            if account.temporary:
                await service.send_info(
                    "No API Key provided. Using a temporary account."
                )
                await service.send_info(
                    "Create an account with 'textual-web --signup'!"
                )

            BINARY = aiohttp.WSMsgType.BINARY
            ERROR = aiohttp.WSMsgType.ERROR
            async with service:
                async for message in websocket:
                    if message.type == BINARY:
                        await service.process_bytes(message.data)
                    elif message.type == ERROR:
                        print(
                            "ws connection closed with exception %s"
                            % websocket.exception()
                        )
                        print(message)

        except CancelledError as e:
            await websocket.close()
        finally:
            if self.is_idle:
                await self.start_idle_shutdown_timer()

            # Remove application client
            async with self.db_session():
                await db.delete_application_client(application_client)
            if application_client.account.temporary:
                async with self.db_session():
                    await db.delete_account(application_client.account)

        return websocket

    async def start_idle_shutdown_timer(self) -> None:
        """Start the idle shutdown timer."""
        await self.stop_idle_shutdown_timer()
        if self.exit_on_idle > 0:
            timer = self.get_idle_shutdown_timer()
            self._idle_shutdown_timer = timer
            self._idle_shutdown_timer.start()
            log.debug(f"Started idle shutdown timer ({self.exit_on_idle}s).")

    async def stop_idle_shutdown_timer(self) -> None:
        """Stop the idle shutdown timer."""
        if self._idle_shutdown_timer is not None:
            await self._idle_shutdown_timer.stop()
            self._idle_shutdown_timer = None
            log.debug("Stopped idle shutdown timer.")

    def get_idle_shutdown_timer(self) -> Timer:
        """Gets the idle shutdown Timer (but does not start it).

        Returns:
            A Timer configured which will gracefully exit after `exit_on_idle` seconds.
        """
        shutdown_callback = partial(
            self.request_exit,
            reason=f"{self.exit_on_idle}s exit-on-idle timer triggered.",
        )
        return Timer(self.exit_on_idle, shutdown_callback, "idle shutdown timer")

    @property
    def is_idle(self) -> bool:
        """True if there are no apps being served via this server."""
        return len(ApplicationService.registry) == 0

    async def handle_web_client(
        self, request: Request
    ) -> web.WebSocketResponse | web.Response:
        """Websocket endpoint which a web client connects to."""

        try:
            width = int(request.query.get("width", "80"))
        except ValueError:
            width = 80

        try:
            height = int(request.query.get("height", "24"))
        except ValueError:
            height = 24

        account_slug = request.match_info["account_slug"]
        application_slug = request.match_info["application_slug"]

        web_client: WebClient | None = None
        try:
            async with self.db_session():
                applications = await db.get_applications(account_slug, application_slug)
                if not applications:
                    raise web.HTTPNotFound()
                application_map = {
                    application.routing_code: application
                    for application in applications
                }
                if self.routing_code not in application_map:
                    # Requested application is not running on this server
                    log.info(
                        f"routing_code={self.routing_code!r} region={constants.REGION!r}"
                    )
                    # Regions where application is running
                    application_regions = tuple(
                        set(application.region for application in applications)
                    )
                    log.info(f"application_regions={application_regions!r}")
                    # The closest region
                    closest_region = regions.get_closest_region(
                        constants.REGION, application_regions
                    )
                    log.info(f"closest_region={closest_region!r}")
                    # Get a routing code for applications in this region
                    redirect_routing_code = random.choice(
                        [
                            application.routing_code
                            for application in applications
                            if application.region == closest_region
                        ]
                    )
                    assert redirect_routing_code is not None
                    log.info(
                        f"Redirecting from region {constants.REGION!r} to {closest_region!r}; instance={redirect_routing_code!r}"
                    )
                    # Tell Fly to replay to the instance that is serving this application.
                    return web.Response(
                        headers={"fly-replay": f"instance={redirect_routing_code}"}
                    )
                else:
                    application = application_map[self.routing_code]

                web_client = await db.create_web_client()
                web_client.ip_address = request.headers.get(
                    "Fly-Client-IP", request.remote or ""
                )

            websocket = web.WebSocketResponse(heartbeat=15)
            await websocket.prepare(request)

            web_client_service = WebClientService(
                request,
                websocket,
                cast(identity.WebClientIdentity, web_client.identity),
                application,
                (width, height),
            )

            async with web_client_service:
                await web_client_service.run()

        except Exception:
            log.exception("error in handle_web_client")
            raise

        finally:
            if web_client is not None:
                async with self.db_session():
                    await db.delete_web_client(web_client)

        return websocket

    async def handle_download(self, request: web.Request) -> web.StreamResponse:
        """Handle a download request."""

        # If the request is from a different instance, send it on to the correct instance.
        instance = request.query.get("instance", None)
        if instance is not None and instance != os.getenv("FLY_MACHINE_ID"):
            return web.Response(headers={"fly-replay": f"instance={instance}"})

        key = request.match_info["key"]
        log.info(f"Handling download request for key={key!r}")

        try:
            download_meta = await self.download_manager.get_download_metadata(key)
        except DownloadError:
            raise web.HTTPNotFound()

        response = web.StreamResponse()
        mime_type = download_meta.mime_type

        content_type = mime_type
        if download_meta.encoding:
            content_type += f"; charset={download_meta.encoding}"

        response.headers["Content-Type"] = content_type
        disposition = (
            "inline" if download_meta.open_method == "browser" else "attachment"
        )
        response.headers["Content-Disposition"] = (
            f"{disposition}; filename={download_meta.file_name}"
        )

        log.info(f"Retrieved download {download_meta!r}")

        await response.prepare(request)

        try:
            async for chunk in self.download_manager.download(key):
                await response.write(chunk)
        except DownloadError:
            log.exception("error in handle_download")
            raise web.HTTPNotFound()

        await response.write_eof()
        return response

    @aiohttp_jinja2.template("app_index.html")
    async def app_index(self, request: Request) -> dict[str, object]:
        """The URL a user visits to interact with a Textual app.

        Args:
            request: Request object.

        Raises:
            web.HTTPNotFound: If there is no app on this URL.

        Returns:
            dict: Template data.
        """

        ping_url = request.query.get("ping", None)
        account_slug = request.match_info["account_slug"]
        application_slug = request.match_info["application_slug"]
        try:
            font_size = int(request.query.get("fontsize", "16"))
        except ValueError:
            font_size = 16

        async with self.db_session():
            application = await db.get_application_from_slugs(
                account_slug, application_slug, self.routing_code
            )

        if application is None:
            log.error(
                f"No application account_slug={account_slug!r} application_slug={application_slug!r} routing_code={self.routing_code!r}"
            )
            raise web.HTTPNotFound()

        config: Config = request.app["config"]

        # try:
        #     background_color = Color.parse(application.color)
        # except Exception:
        background_color = Color.parse("#ffffff")
        text_color = background_color.get_contrast_text()

        websocket_path = request.app.router["web-client"].url_for(
            account_slug=account_slug, application_slug=application_slug
        )

        app_websocket_url = f"{config.server.app_websocket_url}{websocket_path}"

        return {
            "request": request,
            "config": config,
            "application": application,
            "background_color": background_color.css,
            "text_color": text_color.css,
            "app_websocket_url": app_websocket_url,
            "font_size": font_size,
            "ping_url": ping_url,
            "instance": os.getenv("FLY_MACHINE_ID", ""),
        }
