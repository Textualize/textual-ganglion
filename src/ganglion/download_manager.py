from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from typing import AsyncGenerator
from ganglion.application_service import ApplicationService
from ganglion.context import get_router
from ganglion.identity import ApplicationClientIdentity
from ganglion.packets import RequestDeliverChunk

from ganglion.router import RouteKey


log = logging.getLogger("textual-serve")

DOWNLOAD_TIMEOUT = 15
DOWNLOAD_CHUNK_SIZE = 1024 * 64  # 64 KB


@dataclass
class Download:
    route_key: RouteKey
    """The route key for identifying the route."""

    delivery_key: str
    """The delivery key for identifying the download."""

    file_name: str
    """The name of the file."""

    open_method: str
    """The method to open the file with 'browser' or 'download'."""

    mime_type: str
    """The MIME type of the file."""

    encoding: str | None = None
    """The encoding of the content. Will be None if the content is binary."""

    incoming_chunks: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    """Queue which incoming file chunks are placed on for consumption from download handler."""


class DownloadError(Exception):
    """Exception raised when a download fails."""


class DownloadManager:
    """Class which manages downloads for the server.

    Serves as the link between the web server and app processes during downloads.

    A single server has a single download manager, which manages all downloads for all
    running app processes.
    """

    def __init__(self):
        self._active_downloads: dict[str, Download] = {}
        """A dictionary of active downloads.

        When a delivery key is received in a meta packet, it is added to this set.
        When the user hits the "/download/{key}" endpoint, we ensure the key is in
        this set and start the download by requesting chunks from the app process.

        When the download is complete, the app process sends a "deliver_file_end"
        meta packet, and we remove the key from this set.
        """

    async def create_download(
        self,
        *,
        route_key: RouteKey,
        delivery_key: str,
        file_name: str,
        open_method: str,
        mime_type: str,
        encoding: str | None = None,
    ) -> None:
        """Prepare for a new download.

        Args:
            route_key: The route key to start the download for.
            delivery_key: The delivery key to start the download for.
            file_name: The name of the file to download.
            open_method: The method to open the file with.
            mime_type: The MIME type of the file.
        """
        log.info(f"Creating download for delivery key {delivery_key!r}")
        self._active_downloads[delivery_key] = Download(
            route_key,
            delivery_key,
            file_name,
            open_method,
            mime_type,
            encoding,
        )

    async def download(self, delivery_key: str) -> AsyncGenerator[bytes, None]:
        """Download a file from the given app service.

        Args:
            delivery_key: The delivery key to download.
        """
        log.info(f"Starting download for delivery key {delivery_key!r}")
        try:
            download = self._active_downloads[delivery_key]
        except KeyError as error:
            raise DownloadError(
                f"No active download for delivery key {delivery_key!r}"
            ) from error

        app_service = await self._get_app_service(delivery_key)
        if not app_service:
            raise DownloadError(
                f"No app service found for delivery key {delivery_key!r}"
            )

        incoming_chunks = download.incoming_chunks
        while True:
            # Request another chunk of the file from the app service.
            send_result = await app_service.send(
                RequestDeliverChunk(
                    route_key=download.route_key,
                    delivery_key=delivery_key,
                    chunk_size=DOWNLOAD_CHUNK_SIZE,
                )
            )
            if not send_result:
                log.warning(
                    f"Stream for delivery key {delivery_key!r} is closed or closing, stopping download."
                )
                del self._active_downloads[delivery_key]
                break

            # Wait for the chunk to be received from the app service.
            try:
                chunk = await asyncio.wait_for(
                    incoming_chunks.get(), timeout=DOWNLOAD_TIMEOUT
                )
            except asyncio.TimeoutError:
                log.warning(
                    f"Timeout waiting for chunk for delivery key {delivery_key!r}"
                )
                chunk = None

            if not chunk:
                # Empty chunk - the app process has finished sending the file.
                incoming_chunks.task_done()
                del self._active_downloads[delivery_key]
                break
            else:
                incoming_chunks.task_done()
                yield chunk

    async def chunk_received(self, delivery_key: str, chunk: bytes | str) -> None:
        """Handle a chunk received from the app service for a download.

        Args:
            delivery_key: The delivery key that the chunk was received for.
            chunk: The chunk that was received. The chunk may be bytes or a string
                depending on whether the user is sending binary data or text data.
        """
        download = self._active_downloads.get(delivery_key)

        # Download may have been cancelled in the time between requesting the chunk
        # and receiving it, so we cannot guarantee the chunk is for an active download.
        if download:
            if isinstance(chunk, str):
                try:
                    chunk = chunk.encode(download.encoding or "utf-8")
                except UnicodeEncodeError as error:
                    raise DownloadError(
                        f"Error encoding chunk for delivery key {delivery_key!r}"
                    ) from error
            await download.incoming_chunks.put(chunk)

    async def _get_app_service(self, delivery_key: str) -> ApplicationService | None:
        """Get the app service that the given delivery key is linked to.

        Args:
            delivery_key: The delivery key to get the app service for.
        """
        for key in self._active_downloads.keys():
            if key == delivery_key:
                route_key = self._active_downloads[key].route_key
                router = get_router()
                route = router.get_route(route_key)
                if route:
                    return route.application_service
        else:
            # The key supplied is not a valid delivery key, meaning the download
            # may be finished or never started.
            raise DownloadError(f"No active download for delivery key {delivery_key!r}")

    async def get_download_metadata(self, delivery_key: str) -> Download:
        """Get the metadata for a download.

        Args:
            delivery_key: The delivery key to get the metadata for.
        """
        download = self._active_downloads.get(delivery_key)
        if not download:
            raise DownloadError(f"No active download for delivery key {delivery_key!r}")
        return download

    async def cancel_app_downloads(
        self, app_identity: ApplicationClientIdentity
    ) -> None:
        """Cancel all downloads for the given app service.

        Args:
            app_service: The app service to cancel downloads for.
        """
        for download in self._active_downloads.values():
            route_key = download.route_key
            router = get_router()
            route = router.get_route(route_key)
            if (
                route
                and route.application_service
                and route.application_service.identity == app_identity
            ):
                await download.incoming_chunks.put(None)
