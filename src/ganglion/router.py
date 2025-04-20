"""
The Router is an in-memory data structure to connect web clients with application clients (textual-serve)

"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import NewType, Final, TYPE_CHECKING

from . import identity

from .packets import Packet, SessionData, NotifyTerminalSize, RoutePing, Focus, Blur

if TYPE_CHECKING:
    from .application_service import ApplicationService
    from .web_client_service import WebClientService
    from .registry import Registry

RouteKey = NewType("RouteKey", str)

ROUTE_KEY_SIZE: Final = 8


@dataclass
class Route:
    """Defines a 'route' (two endpoints where traffic will be routed)."""

    router: Router
    key: RouteKey
    session_identity: identity.SessionIdentity
    web: identity.WebClientIdentity
    application: identity.ApplicationClientIdentity

    @property
    def application_service(self) -> ApplicationService | None:
        """The application service, or `None` if it is unavailable (offline)."""
        return self.router.app_clients.get(self.application)

    @property
    def web_client_service(self) -> WebClientService | None:
        """The web client service, or `None` if it is unavailable (offline)."""
        return self.router.web_clients.get(self.web)

    async def send_application(self, packet: Packet) -> bool:
        """Send a packet to the application.

        Args:
            packet: Packet to send.

        Returns:
            bool: True if packet was send.
        """
        application_service = self.application_service
        if application_service is None:
            sent = False
        else:
            sent = await application_service.send(packet)
        return sent

    async def send_application_size(self, width: int, height: int) -> bool:
        return await self.send_application(
            NotifyTerminalSize(self.session_identity, width, height)
        )

    async def send_stdin(self, data: bytes) -> bool:
        return await self.send_application(SessionData(self.key, data))

    async def send_web_bytes(self, data: bytes) -> bool:
        web_client = self.web_client_service
        if web_client is None:
            return False
        return await web_client.send_bytes(data)

    async def send_ping(self, data: str) -> bool:
        return await self.send_application(RoutePing(self.key, data))

    async def send_focus(self) -> bool:
        """Send a focus packet to the app."""
        return await self.send_application(Focus(self.key))

    async def send_blur(self) -> bool:
        """Send a blur packet to the app."""
        return await self.send_application(Blur(self.key))


class Router:
    """Stores and manages routes."""

    def __init__(
        self,
        web_clients: Registry[identity.WebClientIdentity, WebClientService],
        app_clients: Registry[identity.ApplicationClientIdentity, ApplicationService],
    ) -> None:
        self.web_clients = web_clients
        self.app_clients = app_clients

        self._routes: dict[RouteKey, Route] = {}
        self._routes_by_application: defaultdict[
            identity.ApplicationClientIdentity, set[RouteKey]
        ] = defaultdict(set)
        self._routes_by_web: defaultdict[identity.WebClientIdentity, set[RouteKey]] = (
            defaultdict(set)
        )

    def _new_route_key(self) -> RouteKey:
        """Generate a new route key which doesn't conflict.

        Returns:
            RouteKey: Unique Route key.
        """

        def generate() -> str:
            """Generate a route key."""
            return identity.generate(ROUTE_KEY_SIZE)

        # Ensure route key hasn't been used
        while (route_key := RouteKey(generate())) in self._routes:
            pass
        return route_key

    def get_route(self, route_key: RouteKey) -> Route | None:
        """Get a route with the given key.

        Args:
            route_key: Route key.

        Returns:
            Route: A route object.
        """
        return self._routes.get(route_key, None)

    def add_route(
        self,
        session_identity: identity.SessionIdentity,
        web_identity: identity.WebClientIdentity,
        application_client_identity: identity.ApplicationClientIdentity,
    ) -> Route:
        """Add a new route.

        Args:
            web_identity: Identity of the web client.
            application_client_identity: Identity of the application client.

        Returns:
            The new route.
        """
        assert identity.is_qualified(
            web_identity,
            identity.QUALIFY_WEB_CLIENT,
        )
        assert identity.is_qualified(
            application_client_identity,
            identity.QUALIFY_APPLICATION_CLIENT,
        )
        route_key = self._new_route_key()
        route = Route(
            self, route_key, session_identity, web_identity, application_client_identity
        )
        self._routes[route_key] = route
        self._routes_by_application[application_client_identity].add(route_key)
        self._routes_by_web[web_identity].add(route_key)
        return route

    def remove_route(self, route_key: RouteKey) -> None:
        """Remove a route with the route_index.

        Args:
            route_index: A route index.
        """
        route = self._routes.pop(route_key, None)
        if route is not None:
            route_key = route.key
            self._routes_by_application[route.application].discard(route_key)
            self._routes_by_web[route.web].discard(route_key)
