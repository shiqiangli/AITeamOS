from __future__ import annotations

from fnmatch import fnmatch
from typing import Any
from urllib.parse import urlparse
import re


DEFAULT_SENSITIVE_PATHS = [".env", ".git/**", "*.pem", "*.key", ".mcp.json", ".qoder/**"]
DEFAULT_SENSITIVE_ENV_PATTERNS = [
    "*_API_KEY",
    "*_TOKEN",
    "*_SECRET",
    "*_PASSWORD",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
]
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SAFE_ARTIFACT_REDACTION_MODES = {"applied", "redacted", "required", "sanitize", "sanitized"}


def read_action(path: str) -> dict[str, Any]:
    return {"tool": "Read", "path": path}


def edit_action(path: str) -> dict[str, Any]:
    return {"tool": "Edit", "path": path}


def bash_action(command: str) -> dict[str, Any]:
    return {"tool": "Bash", "command": command}


def web_action(url: str | None = None, *, domain: str | None = None, tool: str = "WebFetch") -> dict[str, Any]:
    return {key: value for key, value in {"tool": tool, "url": url, "domain": domain}.items() if value}


def network_action(domain: str, *, port: int | None = None, protocol: str | None = None) -> dict[str, Any]:
    return {key: value for key, value in {"tool": "Network", "domain": domain, "port": port, "protocol": protocol}.items() if value is not None}


def mcp_action(server: str, tool: str | None = None, *, target: str | None = None) -> dict[str, Any]:
    return {key: value for key, value in {"mcpServer": server, "mcpTool": tool, "target": target}.items() if value}


def env_var_action(name: str, operation: str = "use") -> dict[str, Any]:
    return {"tool": "EnvVar", "envVar": name, "operation": operation}


def connector_action(connector: str, operation: str, *, connector_type: str | None = None, connector_scope: str | None = None) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "tool": "Connector",
            "connector": connector,
            "connectorType": connector_type,
            "connectorScope": connector_scope,
            "operation": operation,
        }.items()
        if value
    }


def artifact_store_action(
    store: str,
    operation: str,
    *,
    artifact_kind: str | None = None,
    retention_policy: str | None = None,
    export_policy: str | None = None,
    redaction_mode: str | None = None,
    sensitivity: str | None = None,
) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "tool": "ArtifactStore",
            "artifactStore": store,
            "operation": operation,
            "artifactKind": artifact_kind,
            "retentionPolicy": retention_policy,
            "exportPolicy": export_policy,
            "redactionMode": redaction_mode,
            "sensitivity": sensitivity,
        }.items()
        if value
    }


def _normalize_action(action: dict[str, Any] | Any) -> dict[str, Any]:
    data = _action_data(action)
    tool = str(data.get("tool") or data.get("name") or data.get("type") or "").strip()
    if not tool and "path" in data:
        tool = "Read"
    if data.get("mcpServer") or data.get("mcpTool") or tool.startswith("mcp__"):
        tool = _mcp_tool_name(tool, data)
    elif data.get("envVar") and not tool:
        tool = "EnvVar"
    elif data.get("connector") and not tool:
        tool = "Connector"
    elif data.get("artifactStore") and not tool:
        tool = "ArtifactStore"
    elif (data.get("domain") or data.get("url")) and not tool:
        tool = "WebFetch"
    value = _action_value(tool, data)
    text = str(value or "").strip()
    path = _normalize_path(text) if tool in {"Read", "Edit", "Write"} or "path" in data else None
    return {
        "tool": tool,
        "value": text,
        "path": path,
        "domain": _domain_value(data),
        "operation": data.get("operation"),
        "resource": data.get("resource"),
        "envVar": data.get("envVar"),
        "connector": data.get("connector"),
        "connectorScope": data.get("connectorScope"),
        "connectorType": data.get("connectorType"),
        "artifactStore": data.get("artifactStore"),
        "artifactKind": data.get("artifactKind"),
        "retentionPolicy": data.get("retentionPolicy"),
        "exportPolicy": data.get("exportPolicy"),
        "redactionMode": data.get("redactionMode"),
        "sensitivity": data.get("sensitivity"),
        "risk": data.get("risk"),
        "metadata": data.get("metadata", {}),
        "canonical": f"{tool}({text})" if tool and text else tool,
    }


def _rule_matches(rule: str, action: dict[str, Any]) -> bool:
    rule = rule.strip()
    tool = action["tool"]
    value = action["value"]
    path = action["path"]
    if not rule or not tool:
        return False
    if rule == "*":
        return True
    rule_tool, rule_value = _parse_rule(rule)
    if _tool_matches(rule_tool, tool):
        if rule_value is None or rule_value == "*":
            return True
        candidate = path if path is not None else value
        return _pattern_matches(rule_value, candidate)
    return False


def _action_data(action: dict[str, Any] | Any) -> dict[str, Any]:
    if hasattr(action, "model_dump"):
        return action.model_dump(mode="json", exclude_none=True)
    return dict(action or {}) if isinstance(action, dict) else {}


def _mcp_tool_name(tool: str, action: dict[str, Any]) -> str:
    if tool.startswith("mcp__"):
        return tool
    server = str(action.get("mcpServer") or "").strip()
    mcp_tool = str(action.get("mcpTool") or "").strip()
    if server and mcp_tool:
        return f"mcp__{server}__{mcp_tool}"
    if server:
        return f"mcp__{server}"
    return tool or "MCP"


def _action_value(tool: str, action: dict[str, Any]) -> str | None:
    if tool in {"Read", "Edit", "Write"}:
        return _first_value(action, "path", "value", "target")
    if tool == "Bash":
        return _first_value(action, "command", "value", "target")
    if tool in {"WebFetch", "WebSearch", "Network"}:
        domain = _domain_value(action)
        if tool == "Network" and domain and action.get("port"):
            return f"{domain}:{action['port']}"
        return domain or _first_value(action, "url", "network", "target", "value")
    if tool == "EnvVar":
        return _compound_value(action, "envVar", "operation") or _first_value(action, "target", "value")
    if tool == "Connector":
        return _connector_value(action) or _first_value(action, "target", "value")
    if tool == "ArtifactStore":
        return _artifact_store_value(action) or _first_value(action, "target", "value")
    if tool.startswith("mcp__"):
        return _first_value(action, "target", "resource", "value")
    return _first_value(action, "value", "path", "command", "target", "mcpTool", "domain", "url", "connector", "artifactStore", "resource")


def _first_value(action: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = action.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _compound_value(action: dict[str, Any], object_key: str, operation_key: str) -> str | None:
    object_id = _first_value(action, object_key)
    operation = _first_value(action, operation_key)
    if object_id and operation:
        return f"{object_id}:{operation}"
    return object_id


def _connector_value(action: dict[str, Any]) -> str | None:
    connector = _first_value(action, "connector")
    operation = _first_value(action, "operation")
    scope = _first_value(action, "connectorScope", "resource")
    if connector and scope and operation:
        return f"{connector}:{scope}:{operation}"
    if connector and operation:
        return f"{connector}:{operation}"
    return connector


def _artifact_store_value(action: dict[str, Any]) -> str | None:
    store = _first_value(action, "artifactStore")
    operation = _first_value(action, "operation")
    if not store:
        return None
    parts = [store]
    if operation:
        parts.append(operation)
    retention = _first_value(action, "retentionPolicy")
    redaction = _first_value(action, "redactionMode")
    export_policy = _first_value(action, "exportPolicy")
    if retention:
        parts.append(f"retention={retention}")
    if export_policy:
        parts.append(f"export={export_policy}")
    if redaction:
        parts.append(f"redaction={redaction}")
    return ":".join(parts)


def _domain_value(action: dict[str, Any]) -> str | None:
    explicit = _first_value(action, "domain", "network")
    if explicit:
        return explicit
    url = _first_value(action, "url")
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/", 1)[0]


def _tool_matches(rule_tool: str, tool: str) -> bool:
    if rule_tool in {"*", tool}:
        return True
    if fnmatch(tool, rule_tool):
        return True
    return rule_tool.startswith("mcp__") and tool.startswith(f"{rule_tool}__")


def _parse_rule(rule: str) -> tuple[str, str | None]:
    if rule.endswith(")") and "(" in rule:
        tool, _, value = rule[:-1].partition("(")
        return tool.strip(), value.strip()
    return rule.strip(), None


def _pattern_matches(pattern: str, value: str | None) -> bool:
    if value is None:
        return False
    candidates = {value, _normalize_path(value), value.lstrip("/"), f"domain:{value}"}
    patterns = {pattern, _normalize_path(pattern), pattern.lstrip("/"), pattern.replace(":*", "*")}
    return any(fnmatch(candidate, item) for candidate in candidates for item in patterns)


def _normalize_path(value: str) -> str:
    if not value:
        return ""
    if value.startswith("//"):
        return value
    return value if value.startswith("/") else f"/{value}"


def _sensitive_matches(policies: list[Any], action: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    path = action["path"]
    if path:
        checked = set(DEFAULT_SENSITIVE_PATHS)
        for pattern in DEFAULT_SENSITIVE_PATHS:
            if _pattern_matches(pattern, path):
                records.append({"policy": "builtin", "pattern": pattern, "reason": "builtin sensitive path"})
        for policy in policies:
            for pattern in policy.spec.sensitivePaths:
                if pattern in checked:
                    continue
                checked.add(pattern)
                if _pattern_matches(pattern, path):
                    records.append({"policy": policy.object_id, "pattern": pattern, "reason": "policy sensitive path"})
    records.extend(_sensitive_env_matches(action))
    records.extend(_sensitive_artifact_matches(action))
    return records


def _sensitive_env_matches(action: dict[str, Any]) -> list[dict[str, Any]]:
    if action["tool"] != "EnvVar":
        return []
    env_name = str(action.get("envVar") or action.get("value") or "").split(":", 1)[0]
    if not env_name or not ENV_NAME_RE.match(env_name):
        return [{"policy": "builtin", "pattern": "EnvVar(invalid)", "reason": "invalid environment variable reference"}]
    operation = str(action.get("operation") or "use").lower()
    if operation == "use":
        return []
    return [
        {"policy": "builtin", "pattern": pattern, "reason": "sensitive environment variable"}
        for pattern in DEFAULT_SENSITIVE_ENV_PATTERNS
        if fnmatch(env_name, pattern)
    ]


def _sensitive_artifact_matches(action: dict[str, Any]) -> list[dict[str, Any]]:
    if action["tool"] != "ArtifactStore":
        return []
    operation = str(action.get("operation") or "").lower()
    export_policy = str(action.get("exportPolicy") or "").lower()
    retention = str(action.get("retentionPolicy") or "").lower()
    redaction = str(action.get("redactionMode") or "").lower()
    sensitivity = str(action.get("sensitivity") or "").lower()
    records: list[dict[str, Any]] = []
    if operation in {"export", "publish"} and redaction not in SAFE_ARTIFACT_REDACTION_MODES:
        records.append({"policy": "builtin", "pattern": "ArtifactStore(export)", "reason": "artifact export requires redaction mode"})
    if export_policy == "include" and redaction not in SAFE_ARTIFACT_REDACTION_MODES:
        records.append({"policy": "builtin", "pattern": "ArtifactStore(exportPolicy=include)", "reason": "artifact include export requires redaction mode"})
    if sensitivity in {"confidential", "secret"} and redaction not in SAFE_ARTIFACT_REDACTION_MODES:
        records.append({"policy": "builtin", "pattern": f"ArtifactStore(sensitivity={sensitivity})", "reason": "sensitive artifact requires redaction mode"})
    if retention in {"forever", "indefinite", "permanent"}:
        records.append({"policy": "builtin", "pattern": f"ArtifactStore(retention={retention})", "reason": "unbounded artifact retention requires approval"})
    return records


__all__ = [
    "artifact_store_action",
    "bash_action",
    "connector_action",
    "edit_action",
    "env_var_action",
    "mcp_action",
    "network_action",
    "read_action",
    "web_action",
]
