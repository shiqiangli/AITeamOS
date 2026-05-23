from __future__ import annotations

from datetime import datetime
from fnmatch import fnmatch
from typing import Any


SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
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
SAFE_ARTIFACT_REDACTION_MODES = {"applied", "redacted", "required", "sanitize", "sanitized"}
DESTRUCTIVE_BASH_PATTERNS = [
    "rm -rf",
    "sudo ",
    "curl *|*sh",
    "wget *|*sh",
    "git push",
    "git reset --hard",
    "git clean -fd",
    "npm publish",
    "twine upload",
]


def risk_assessment_from_permission_decision(
    decision: dict[str, Any],
    *,
    provider: str | None = None,
    classifier: str = "aiteamos.local.permission-risk",
    classifier_version: str = "v1",
) -> dict[str, Any]:
    action = dict(decision.get("normalizedAction") or decision.get("action") or {})
    signals: list[dict[str, Any]] = []

    _add_action_signals(signals, action)
    _add_permission_decision_signals(signals, decision)

    risk_level = _max_severity(signals)
    assessment = {
        "classifier": classifier,
        "classifierVersion": classifier_version,
        "provider": provider or _provider_from_action(action),
        "riskLevel": risk_level,
        "recommendedDecision": _recommended_decision(risk_level),
        "requiresHumanReview": SEVERITY_ORDER[risk_level] >= SEVERITY_ORDER["medium"],
        "evaluatedAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "summary": _summary(risk_level, signals),
        "action": action,
        "signals": signals,
        "metadata": {
            "policyDecision": decision.get("decision"),
            "policyReason": decision.get("reason"),
            "nonInteractive": decision.get("nonInteractive"),
            "selectedPolicyIds": decision.get("selectedPolicyIds", []),
        },
    }
    return {key: value for key, value in assessment.items() if value is not None}


def _add_action_signals(signals: list[dict[str, Any]], action: dict[str, Any]) -> None:
    explicit_risk = str(action.get("risk") or "").lower()
    if explicit_risk in {"low", "medium", "high", "critical"}:
        _add_signal(signals, "explicit-risk", explicit_risk, "PermissionAction declared an explicit risk level.", {"risk": explicit_risk})

    tool = str(action.get("tool") or "")
    value = str(action.get("value") or "")
    path = str(action.get("path") or "")
    operation = str(action.get("operation") or "").lower()

    if tool in {"Read", "Edit", "Write"} and path:
        for pattern in DEFAULT_SENSITIVE_PATHS:
            if _path_matches(pattern, path):
                severity = "critical" if tool in {"Edit", "Write"} else "high"
                _add_signal(signals, "sensitive-path", severity, f"{tool} targets a sensitive path.", {"path": path, "pattern": pattern})

    if tool == "EnvVar":
        env_name = str(action.get("envVar") or value.split(":", 1)[0] or "")
        is_secret = any(fnmatch(env_name, pattern) for pattern in DEFAULT_SENSITIVE_ENV_PATTERNS)
        if operation in {"read", "export", "write"}:
            severity = "critical" if is_secret else "high"
            _add_signal(signals, "env-secret-exposure", severity, "Environment variable value exposure or mutation is sensitive.", {"envVar": env_name, "operation": operation})
        elif operation == "use" and is_secret:
            _add_signal(signals, "provider-secret-use", "medium", "Provider secret use is allowed only as opaque runtime input.", {"envVar": env_name, "operation": operation})

    if tool == "ArtifactStore":
        export_policy = str(action.get("exportPolicy") or "").lower()
        redaction = str(action.get("redactionMode") or "").lower()
        retention = str(action.get("retentionPolicy") or "").lower()
        sensitivity = str(action.get("sensitivity") or "").lower()
        if operation in {"export", "publish"} and redaction not in SAFE_ARTIFACT_REDACTION_MODES:
            _add_signal(signals, "unredacted-artifact-export", "high", "Artifact export requires an explicit safe redaction mode.", {"operation": operation})
        if export_policy == "include" and redaction not in SAFE_ARTIFACT_REDACTION_MODES:
            _add_signal(signals, "artifact-include-without-redaction", "high", "Artifact include export requires redaction.", {"exportPolicy": export_policy})
        if sensitivity in {"confidential", "secret"} and redaction not in SAFE_ARTIFACT_REDACTION_MODES:
            _add_signal(signals, "sensitive-artifact-without-redaction", "high", "Sensitive artifacts require redaction before sharing.", {"sensitivity": sensitivity})
        if retention in {"forever", "indefinite", "permanent"}:
            _add_signal(signals, "unbounded-artifact-retention", "medium", "Unbounded artifact retention needs review.", {"retentionPolicy": retention})

    if tool == "Bash":
        lowered = value.lower()
        for pattern in DESTRUCTIVE_BASH_PATTERNS:
            if fnmatch(lowered, f"*{pattern}*"):
                severity = "critical" if pattern in {"rm -rf", "git reset --hard", "git clean -fd"} else "high"
                _add_signal(signals, "dangerous-bash", severity, "Bash command matches a destructive or publishing pattern.", {"pattern": pattern})

    if tool in {"WebFetch", "WebSearch", "Network"}:
        _add_signal(signals, "external-access", "medium", "External web or network access crosses the workspace boundary.", {"tool": tool, "target": value})

    if tool.startswith("mcp__"):
        severity = "high" if any(word in tool.lower() for word in ["create", "update", "write", "delete", "merge", "publish", "admin"]) else "medium"
        _add_signal(signals, "mcp-external-tool", severity, "External MCP tool use requires scoped authorization.", {"tool": tool, "target": value})

    if tool == "Connector":
        op = operation or str(value).rsplit(":", 1)[-1].lower()
        severity = "high" if op in {"write", "create", "update", "delete", "merge", "publish", "admin"} else "medium"
        _add_signal(signals, "connector-scope", severity, "Connector operations cross an external service boundary.", {"connector": action.get("connector"), "operation": op})


def _add_permission_decision_signals(signals: list[dict[str, Any]], decision: dict[str, Any]) -> None:
    blockers = list(decision.get("blockers") or [])
    if blockers:
        _add_signal(signals, "permission-blocker", "high", "Permission evaluator returned blockers.", {"blockers": blockers})
    missing = list(decision.get("missingPolicyIds") or [])
    if missing:
        _add_signal(signals, "missing-policy", "high", "Referenced permission policies are missing.", {"missingPolicyIds": missing})
    sensitive = list(decision.get("sensitiveMatches") or [])
    if sensitive:
        _add_signal(signals, "sensitive-match", "high", "Permission evaluator matched a sensitive resource.", {"sensitiveMatches": sensitive})
    reason = str(decision.get("reason") or "")
    if "ask converted to deny" in reason or "non-interactive" in reason:
        _add_signal(signals, "non-interactive-deny", "medium", "A non-interactive session converted ask to deny.", {"reason": reason})


def _add_signal(signals: list[dict[str, Any]], name: str, severity: str, reason: str, evidence: dict[str, Any]) -> None:
    signals.append({"name": name, "severity": severity, "reason": reason, "evidence": evidence})


def _max_severity(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "low"
    return max((str(signal.get("severity") or "low") for signal in signals), key=lambda value: SEVERITY_ORDER.get(value, 1))


def _recommended_decision(risk_level: str) -> str:
    if risk_level == "critical":
        return "deny"
    if risk_level in {"medium", "high"}:
        return "ask"
    return "allow"


def _summary(risk_level: str, signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "No elevated risk signals were detected by the local classifier."
    names = ", ".join(signal["name"] for signal in signals[:4])
    return f"Local classifier rated this action {risk_level} based on: {names}."


def _provider_from_action(action: dict[str, Any]) -> str | None:
    if action.get("connector"):
        return str(action["connector"])
    tool = str(action.get("tool") or "")
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        if len(parts) >= 2:
            return f"mcp:{parts[1]}"
    if action.get("domain"):
        return str(action["domain"])
    return None


def _path_matches(pattern: str, path: str) -> bool:
    candidates = {path, path.lstrip("/")}
    patterns = {pattern, pattern.lstrip("/")}
    return any(fnmatch(candidate, item) for candidate in candidates for item in patterns)
