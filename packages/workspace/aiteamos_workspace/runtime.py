from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib.util
import os
import shutil
import subprocess
import sys

from .loader import load_workspace, manifest_to_record


def runtime_status(workspace_path: str | Path) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    profiles = [manifest_to_record(profile) for profile in index.model_profiles.values()]
    secret_refs = _secret_references(profiles)
    return {
        "tools": {
            "git": _command_version(["git", "--version"]),
            "gh": _command_version(["gh", "--version"]),
            "litellm": _python_package_status("litellm"),
        },
        "secrets": [_secret_status(name, refs) for name, refs in secret_refs.items()],
        "process": {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "python": sys.executable,
        },
        "environment": {
            "source": "current-api-process",
            "secretValuesExposed": False,
            "notes": [
                "Secret readiness reflects the environment visible to the running AITEAMOS API process.",
                "If a shell variable was added after the server started, restart `aiteamos serve` from that shell.",
            ],
        },
        "workspace": {
            "root": str(index.workspace_root),
            "project": index.project.object_id,
        },
    }


def _secret_references(profiles: list[dict[str, Any]]) -> dict[str, list[str]]:
    references: dict[str, list[str]] = {}
    for profile in profiles:
        spec = profile.get("spec", {})
        secret_name = spec.get("secretEnv")
        if not secret_name:
            continue
        references.setdefault(str(secret_name), []).append(str(profile.get("id") or profile.get("metadata", {}).get("name") or "unknown"))
    return {name: sorted(set(refs)) for name, refs in sorted(references.items())}


def _secret_status(name: str, profile_refs: list[str]) -> dict[str, Any]:
    present = bool(os.environ.get(name))
    case_variant_present = _case_variant_present(name)
    guidance = f"Start or restart AITEAMOS with `{name}` exported in the API server environment."
    if present:
        guidance = f"`{name}` is present in the current API process environment."
    elif case_variant_present:
        guidance = f"A case-insensitive variant of `{name}` exists, but the exact env name is missing."
    return {
        "name": name,
        "present": present,
        "caseVariantPresent": case_variant_present,
        "referencedBy": profile_refs,
        "source": "current-api-process",
        "guidance": guidance,
    }


def _case_variant_present(name: str) -> bool:
    lowered = name.lower()
    return any(key.lower() == lowered and key != name for key in os.environ)


def _command_version(command: list[str]) -> dict[str, Any]:
    executable = shutil.which(command[0])
    if not executable:
        return {"available": False}
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except Exception as exc:
        return {"available": True, "error": str(exc)}
    first_line = (result.stdout or result.stderr).splitlines()[0] if (result.stdout or result.stderr) else executable
    return {"available": result.returncode == 0, "version": first_line}


def _python_package_status(package: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(package)
    if spec is None:
        return {"available": False}
    return {"available": True}
