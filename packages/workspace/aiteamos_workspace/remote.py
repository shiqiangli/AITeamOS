from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
import json
import os
import shutil


REMOTE_WORKSPACE_KIND = "WorkspaceManifestBundle"
REMOTE_WORKSPACE_CACHE_ENV = "AITEAMOS_REMOTE_WORKSPACE_CACHE"
S3_MIRROR_ENV = "AITEAMOS_REMOTE_WORKSPACE_S3_MIRROR"
S3_ENDPOINT_ENV = "AITEAMOS_REMOTE_WORKSPACE_S3_ENDPOINT"


@dataclass(frozen=True)
class RemoteWorkspaceFile:
    path: str
    sha256: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class RemoteWorkspaceBundle:
    reference: str
    backend: str
    files: tuple[RemoteWorkspaceFile, ...]
    manifest_bytes: bytes


def is_remote_workspace_ref(value: str | Path) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https", "s3"}


def remote_workspace_cache_root() -> Path:
    configured = os.environ.get(REMOTE_WORKSPACE_CACHE_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(".aiteamos") / "indexes" / "remote_workspaces"


def materialize_remote_workspace(reference: str | Path, cache_root: str | Path | None = None) -> Path:
    bundle = _load_remote_manifest(str(reference))
    target_root = Path(cache_root).expanduser().resolve() if cache_root else remote_workspace_cache_root().resolve()
    cache_key = sha256(str(reference).encode("utf-8") + b"\0" + bundle.manifest_bytes).hexdigest()[:24]
    materialized = target_root / cache_key
    if materialized.exists():
        shutil.rmtree(materialized)
    materialized.mkdir(parents=True, exist_ok=True)

    for item in bundle.files:
        safe_path = _safe_relative_path(item.path)
        data = _fetch_remote_file(bundle.reference, bundle.backend, item.path)
        digest = sha256(data).hexdigest()
        if item.sha256 and digest != item.sha256:
            raise ValueError(f"remote workspace file {item.path} sha256 mismatch")
        if item.size is not None and len(data) != item.size:
            raise ValueError(f"remote workspace file {item.path} size mismatch")
        destination = materialized / safe_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    if not (materialized / "workspace.yaml").exists():
        raise ValueError("remote workspace manifest must include workspace.yaml")
    return materialized


def build_workspace_manifest_bundle(workspace_root: str | Path, *, backend: str) -> dict[str, Any]:
    if backend not in {"http", "https", "s3"}:
        raise ValueError(f"unsupported remote workspace backend {backend}")
    root = Path(workspace_root)
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith("indexes/"):
            continue
        data = path.read_bytes()
        files.append({"path": relative, "sha256": sha256(data).hexdigest(), "size": len(data)})
    return {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": REMOTE_WORKSPACE_KIND,
        "metadata": {"id": root.name or "workspace"},
        "spec": {"backend": backend, "files": files},
    }


def _load_remote_manifest(reference: str) -> RemoteWorkspaceBundle:
    manifest_bytes = _fetch_remote_bytes(reference)
    try:
        payload = json.loads(manifest_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"remote workspace manifest {reference} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"remote workspace manifest {reference} must be a JSON object")
    if payload.get("kind") != REMOTE_WORKSPACE_KIND:
        raise ValueError(f"remote workspace manifest {reference} must use kind {REMOTE_WORKSPACE_KIND}")
    spec = payload.get("spec")
    if not isinstance(spec, dict):
        raise ValueError(f"remote workspace manifest {reference} requires spec")
    parsed = urlparse(reference)
    backend = str(spec.get("backend") or parsed.scheme)
    if backend not in {"http", "https", "s3"}:
        raise ValueError(f"unsupported remote workspace backend {backend}")
    files_value = spec.get("files")
    if not isinstance(files_value, list) or not files_value:
        raise ValueError(f"remote workspace manifest {reference} requires non-empty spec.files")
    files: list[RemoteWorkspaceFile] = []
    for entry in files_value:
        if not isinstance(entry, dict):
            raise ValueError("remote workspace file entries must be objects")
        path = entry.get("path")
        if not isinstance(path, str):
            raise ValueError("remote workspace file entries require path")
        _safe_relative_path(path)
        digest = entry.get("sha256")
        if digest is not None and (not isinstance(digest, str) or len(digest) != 64):
            raise ValueError(f"remote workspace file {path} has invalid sha256")
        size = entry.get("size")
        if size is not None and (not isinstance(size, int) or size < 0):
            raise ValueError(f"remote workspace file {path} has invalid size")
        files.append(RemoteWorkspaceFile(path=path, sha256=digest, size=size))
    return RemoteWorkspaceBundle(
        reference=reference,
        backend=backend,
        files=tuple(files),
        manifest_bytes=manifest_bytes,
    )


def _fetch_remote_file(manifest_reference: str, backend: str, path: str) -> bytes:
    parsed = urlparse(manifest_reference)
    if backend in {"http", "https"}:
        base = manifest_reference.rsplit("/", 1)[0] + "/"
        return _fetch_remote_bytes(urljoin(base, quote(path, safe="/")))
    if backend == "s3":
        return _fetch_s3_file(parsed, path)
    raise ValueError(f"unsupported remote workspace backend {backend}")


def _fetch_remote_bytes(reference: str) -> bytes:
    parsed = urlparse(reference)
    if parsed.scheme in {"http", "https"}:
        request = Request(reference, headers={"Accept": "application/json, application/yaml, text/plain"})
        with urlopen(request, timeout=10) as response:
            return response.read()
    if parsed.scheme == "s3":
        return _fetch_s3_file(parsed, "")
    raise ValueError(f"unsupported remote workspace reference {reference}")


def _fetch_s3_file(manifest_uri: Any, relative_path: str) -> bytes:
    bucket = manifest_uri.netloc
    manifest_key = manifest_uri.path.lstrip("/")
    if not bucket or not manifest_key:
        raise ValueError("s3 remote workspace references must include bucket and key")
    key_prefix = manifest_key.rsplit("/", 1)[0] if "/" in manifest_key else ""
    key = f"{key_prefix}/{relative_path}".strip("/") if relative_path else manifest_key

    mirror = os.environ.get(S3_MIRROR_ENV)
    if mirror:
        path = Path(mirror).expanduser().resolve() / bucket / key
        if not path.is_file():
            raise FileNotFoundError(f"S3 mirror object not found: s3://{bucket}/{key}")
        return path.read_bytes()

    endpoint = os.environ.get(S3_ENDPOINT_ENV)
    if endpoint:
        base = endpoint.rstrip("/") + f"/{quote(bucket, safe='')}/"
        return _fetch_remote_bytes(urljoin(base, quote(key, safe="/")))

    raise ValueError(
        f"s3 remote workspace {manifest_uri.geturl()} requires {S3_MIRROR_ENV} or {S3_ENDPOINT_ENV}"
    )


def _safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not value or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe remote workspace path {value!r}")
    return path
