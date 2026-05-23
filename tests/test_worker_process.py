from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import yaml

from aiteamos_worker import run_worker_once
from aiteamos_workspace import create_model_profile, create_run, create_task, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"
MANUAL_PROFILE = "manual-worker-process"


class WorkerProcessTest(unittest.TestCase):
    def test_worker_service_consumes_selected_run_without_api_server(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run_id = _create_ready_worker_run(workspace)

            result = run_worker_once(workspace, run_id=run_id, write_event=True)

            self.assertEqual(result["process"], "aiteamos_worker")
            self.assertEqual(result["selectedRun"], run_id)
            self.assertEqual(result["status"], "consumed")
            self.assertTrue(result["eventWritten"])
            self.assertIn("aiteamos_api.context.build_context_capsule", result["sharedImports"])

            updated = load_workspace(workspace)
            event_types = [event["type"] for event in updated.run_events[run_id]]
            self.assertIn("worker.queue.consumed", event_types)

    def test_repo_launcher_starts_worker_process_and_polls_workspace_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run_id = _create_ready_worker_run(workspace)

            completed = subprocess.run(
                [str(REPO_ROOT / "aiteamos"), "worker", "--workspace", str(workspace), "--run", run_id, "--once", "--write-event"],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env=_test_env(),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["process"], "aiteamos_worker")
            self.assertEqual(payload["selectedRun"], run_id)
            self.assertEqual(payload["status"], "consumed")


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _create_ready_worker_run(workspace: Path) -> str:
    _install_local_model_profile(workspace)
    task = create_task(
        workspace,
        title="Standalone worker process smoke",
        assigned_member=BACKEND_MEMBER,
        assignment=BACKEND_ASSIGNMENT,
        execution_mode="managed_llm",
        acceptance=["worker process consumes the run from the local queue"],
    )
    run = create_run(workspace, task_id=task.object_id, model_profile=MANUAL_PROFILE, mode="managed_llm")
    return run.object_id


def _install_local_model_profile(workspace: Path) -> None:
    create_model_profile(
        workspace,
        name=MANUAL_PROFILE,
        provider="local",
        model="manual",
        gateway="manual",
        invocation={"fixtureResponse": "worker process fixture"},
        capabilities=["managed_llm", "coding"],
        default_for_members=[BACKEND_MEMBER],
        default_for_assignments=[BACKEND_ASSIGNMENT],
    )
    profile_path = workspace / "execution_profiles" / "digital" / f"{BACKEND_MEMBER}.yaml"
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    spec = data.setdefault("spec", {})
    spec["defaultModelProfile"] = MANUAL_PROFILE
    allowed = spec.setdefault("allowedModelProfiles", [])
    if MANUAL_PROFILE not in allowed:
        allowed.append(MANUAL_PROFILE)
    profile_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _test_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = [
        str(REPO_ROOT / "packages" / "schema"),
        str(REPO_ROOT / "packages" / "workspace"),
        str(REPO_ROOT / "services" / "api"),
        str(REPO_ROOT / "services" / "worker"),
        str(REPO_ROOT),
    ]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    return env


if __name__ == "__main__":
    unittest.main()
