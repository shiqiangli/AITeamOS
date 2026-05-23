from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse
from unittest.mock import patch
import json
import tempfile
import unittest

from aiteamos_workspace import (
    build_workspace_manifest_bundle,
    load_workspace,
    rebuild_workspace_indexes,
    resolve_workspace_root,
)


class RemoteWorkspaceTest(unittest.TestCase):
    def test_http_manifest_bundle_loads_through_workspace_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            remote_root = temp_root / "http-root"
            _write_minimal_workspace(remote_root)
            _write_bundle(remote_root, "http")

            uri = "http://remote.test/workspace-manifest.json"
            with patch("aiteamos_workspace.remote.urlopen", _fake_urlopen(remote_root)):
                with patch.dict("os.environ", {"AITEAMOS_REMOTE_WORKSPACE_CACHE": str(temp_root / "cache")}):
                    index = load_workspace(uri)
                    self.assertEqual(index.workspace.spec.mode, "shadow")
                    self.assertEqual(index.project.object_id, "remote-shadow")
                    self.assertTrue(str(index.workspace_root).startswith(str(temp_root / "cache")))
                    self.assertFalse([issue for issue in index.health if issue["severity"] == "error"])

                    rebuild = rebuild_workspace_indexes(
                        uri,
                        db_path=temp_root / "remote.sqlite",
                        vector_path=temp_root / "remote-vector.json",
                    )
                    self.assertTrue(rebuild["derived"])
                    self.assertEqual(rebuild["counts"]["database"]["repositories"], 0)
                    self.assertTrue((temp_root / "remote.sqlite").exists())
                    self.assertTrue((temp_root / "remote-vector.json").exists())

    def test_s3_manifest_bundle_loads_from_explicit_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            mirror_root = temp_root / "s3-mirror"
            remote_root = mirror_root / "aiteamos-test-bucket" / "shadow-workspaces" / "remote-shadow"
            _write_minimal_workspace(remote_root)
            _write_bundle(remote_root, "s3")

            uri = "s3://aiteamos-test-bucket/shadow-workspaces/remote-shadow/workspace-manifest.json"
            with patch.dict(
                "os.environ",
                {
                    "AITEAMOS_REMOTE_WORKSPACE_CACHE": str(temp_root / "cache"),
                    "AITEAMOS_REMOTE_WORKSPACE_S3_MIRROR": str(mirror_root),
                },
            ):
                workspace_root = resolve_workspace_root(uri)
                self.assertTrue((workspace_root / "workspace.yaml").exists())
                index = load_workspace(uri)
                self.assertEqual(index.project.object_id, "remote-shadow")
                self.assertFalse([issue for issue in index.health if issue["severity"] == "error"])

    def test_manifest_bundle_rejects_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            remote_root = temp_root / "http-root"
            _write_minimal_workspace(remote_root)
            payload = build_workspace_manifest_bundle(remote_root, backend="http")
            payload["spec"]["files"].append({"path": "../secret.yaml"})
            (remote_root / "workspace-manifest.json").write_text(json.dumps(payload), encoding="utf-8")

            uri = "http://remote.test/workspace-manifest.json"
            with patch("aiteamos_workspace.remote.urlopen", _fake_urlopen(remote_root)):
                with patch.dict("os.environ", {"AITEAMOS_REMOTE_WORKSPACE_CACHE": str(temp_root / "cache")}):
                    with self.assertRaises(ValueError):
                        load_workspace(uri)


def _write_minimal_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "workspace.yaml").write_text(
        "\n".join(
            [
                "apiVersion: aiteamos.dev/v1alpha1",
                "kind: Workspace",
                "metadata:",
                "  name: remote-shadow",
                "spec:",
                "  mode: shadow",
                "  protocolVersion: aiteamos.dev/v1alpha1",
                "  projectRef: project.yaml",
                "  storage:",
                "    remoteManifestBackend: true",
                "  indexing:",
                "    derivedStatePolicy: rebuildable",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "project.yaml").write_text(
        "\n".join(
            [
                "apiVersion: aiteamos.dev/v1alpha1",
                "kind: Project",
                "metadata:",
                "  name: remote-shadow",
                "spec:",
                "  description: Remote shadow workspace fixture",
                "  workspaceMode: shadow",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_bundle(root: Path, backend: str) -> None:
    payload = build_workspace_manifest_bundle(root, backend=backend)
    (root / "workspace-manifest.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


class _FakeHttpResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


def _fake_urlopen(root: Path):
    def open_request(request: object, timeout: float = 10) -> _FakeHttpResponse:
        url = getattr(request, "full_url", str(request))
        parsed = urlparse(url)
        relative = unquote(parsed.path.lstrip("/"))
        data = (root / relative).read_bytes()
        return _FakeHttpResponse(data)

    return open_request


if __name__ == "__main__":
    unittest.main()
