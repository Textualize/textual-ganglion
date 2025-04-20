from typing import Generic, Iterator, TypeVar

import rich.repr

IdentityType = TypeVar("IdentityType")
ServiceType = TypeVar("ServiceType")


@rich.repr.auto
class Registry(Generic[IdentityType, ServiceType]):
    """A container for services."""

    def __init__(self) -> None:
        self._services: dict[IdentityType, ServiceType] = {}

    def __rich_repr__(self) -> rich.repr.Result:
        yield self._services

    def __len__(self) -> int:
        return len(self._services)

    def __iter__(self) -> Iterator[ServiceType]:
        return iter(self._services.values())

    def clear(self) -> None:
        self._services.clear()

    def add_service(self, identity: IdentityType, service: ServiceType) -> None:
        assert identity not in self._services
        self._services[identity] = service

    def remove_service(self, identity: IdentityType) -> None:
        self._services.pop(identity, None)

    def get(self, identity: IdentityType) -> ServiceType | None:
        return self._services.get(identity, None)
