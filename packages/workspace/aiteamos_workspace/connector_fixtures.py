from __future__ import annotations

from pathlib import Path
from typing import Any
import sys


def connector_adapter_fixture_issues() -> list[dict[str, str]]:
    _ensure_builtin_connector_path()
    from aiteamos_connectors import discover_connector_packages, evaluate_connector_adapter_fixture

    issues: list[dict[str, str]] = []
    discovery = discover_connector_packages()
    for discovery_error in discovery.errors:
        issues.append(discovery_error.as_issue())
    for package in discovery.packages:
        for fixture in package.fixtures:
            result = evaluate_connector_adapter_fixture(fixture)
            if result.passed:
                continue
            issues.append(
                {
                    "kind": "connector_adapter_fixture",
                    "severity": "error",
                    "message": (
                        f"connector adapter fixture {package.name}/{result.id} failed: "
                        f"{'; '.join(result.failures)}"
                    ),
                    "ref": f"{package.name}:{result.id}",
                }
            )
    return issues


def connector_adapter_fixture_records() -> list[dict[str, Any]]:
    _ensure_builtin_connector_path()
    from aiteamos_connectors import discover_connector_packages, evaluate_connector_adapter_fixture

    records: list[dict[str, Any]] = []
    discovery = discover_connector_packages()
    for package in discovery.packages:
        for fixture in package.fixtures:
            record = evaluate_connector_adapter_fixture(fixture).as_dict()
            record["package"] = package.name
            record["packageSource"] = package.source
            records.append(record)
    return records


def connector_package_discovery_records() -> dict[str, Any]:
    _ensure_builtin_connector_path()
    from aiteamos_connectors import discover_connector_packages

    return discover_connector_packages().as_dict()


def _ensure_builtin_connector_path() -> None:
    packages_dir = Path(__file__).resolve().parents[2]
    connectors_dir = packages_dir / "connectors"
    if connectors_dir.exists() and str(connectors_dir) not in sys.path:
        sys.path.insert(0, str(connectors_dir))
