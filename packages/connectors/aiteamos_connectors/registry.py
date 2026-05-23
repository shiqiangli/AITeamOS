from __future__ import annotations

from dataclasses import asdict, dataclass, field
from importlib import metadata
from typing import Any, Callable, Iterable, Mapping

from .fixtures import ConnectorAdapterFixture, connector_adapter_fixtures


ENTRY_POINT_GROUP = "aiteamos.connectors"


@dataclass(frozen=True)
class ConnectorPackage:
    name: str
    provider: str
    connector_types: tuple[str, ...]
    fixtures: tuple[ConnectorAdapterFixture, ...] = ()
    version: str | None = None
    source: str = "builtin"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fixtures"] = [fixture.id for fixture in self.fixtures]
        return data


@dataclass(frozen=True)
class ConnectorDiscoveryError:
    source: str
    message: str

    def as_issue(self) -> dict[str, str]:
        return {
            "kind": "connector_package_discovery",
            "severity": "error",
            "message": self.message,
            "ref": self.source,
        }


@dataclass(frozen=True)
class ConnectorDiscoveryResult:
    packages: tuple[ConnectorPackage, ...] = ()
    errors: tuple[ConnectorDiscoveryError, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "packages": [package.as_dict() for package in self.packages],
            "errors": [asdict(error) for error in self.errors],
        }


def connector_package() -> ConnectorPackage:
    return ConnectorPackage(
        name="aiteamos.builtin.github",
        version="0.1.0",
        provider="github",
        connector_types=("git", "issue"),
        fixtures=tuple(connector_adapter_fixtures()),
        source="builtin",
    )


def discover_connector_packages(
    *,
    entry_points: Iterable[Any] | None = None,
    include_builtin: bool = True,
) -> ConnectorDiscoveryResult:
    packages: list[ConnectorPackage] = []
    errors: list[ConnectorDiscoveryError] = []
    if include_builtin:
        packages.append(connector_package())

    for entry_point in sorted(_connector_entry_points(entry_points), key=_entry_point_name):
        source = _entry_point_source(entry_point)
        try:
            loaded = entry_point.load()
            package = _connector_package_from_loaded(loaded, source=source, default_name=_entry_point_name(entry_point))
        except Exception as exc:  # pragma: no cover - message is asserted through a fake entry point.
            errors.append(ConnectorDiscoveryError(source=source, message=f"connector package {source} failed to load: {exc}"))
            continue
        packages.append(package)

    return ConnectorDiscoveryResult(packages=tuple(packages), errors=tuple(errors))


def _connector_entry_points(entry_points: Iterable[Any] | None) -> list[Any]:
    if entry_points is not None:
        return list(entry_points)
    discovered = metadata.entry_points()
    if hasattr(discovered, "select"):
        return list(discovered.select(group=ENTRY_POINT_GROUP))
    return list(discovered.get(ENTRY_POINT_GROUP, []))


def _connector_package_from_loaded(loaded: Any, *, source: str, default_name: str) -> ConnectorPackage:
    candidate = loaded() if callable(loaded) else loaded
    if isinstance(candidate, ConnectorPackage):
        return ConnectorPackage(
            name=candidate.name,
            version=candidate.version,
            provider=candidate.provider,
            connector_types=tuple(candidate.connector_types),
            fixtures=tuple(candidate.fixtures),
            source=source,
        )
    if isinstance(candidate, Mapping):
        return _connector_package_from_mapping(candidate, source=source, default_name=default_name)
    raise TypeError("entry point must return ConnectorPackage or mapping")


def _connector_package_from_mapping(data: Mapping[str, Any], *, source: str, default_name: str) -> ConnectorPackage:
    fixtures = data.get("fixtures") or ()
    provider = str(data.get("provider") or "").strip()
    connector_types = tuple(str(item) for item in (data.get("connectorTypes") or data.get("connector_types") or ()) if str(item))
    if not provider:
        raise ValueError("connector package provider is required")
    if not connector_types:
        raise ValueError("connector package connectorTypes is required")
    return ConnectorPackage(
        name=str(data.get("name") or default_name),
        version=str(data["version"]) if data.get("version") is not None else None,
        provider=provider,
        connector_types=connector_types,
        fixtures=tuple(fixtures),
        source=source,
    )


def _entry_point_name(entry_point: Any) -> str:
    return str(getattr(entry_point, "name", "connector"))


def _entry_point_source(entry_point: Any) -> str:
    group = str(getattr(entry_point, "group", ENTRY_POINT_GROUP))
    return f"{group}:{_entry_point_name(entry_point)}"
