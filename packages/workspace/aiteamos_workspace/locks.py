from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
import json
import os
import shutil


@contextmanager
def workspace_lock(workspace_root: Path, name: str, metadata: dict[str, Any] | None = None) -> Iterator[None]:
    lock_dir = workspace_root / "locks" / name
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_dir.mkdir()
    except FileExistsError as exc:
        raise RuntimeError(f"lock already held: {name}") from exc
    payload = {
        "name": name,
        "pid": os.getpid(),
        "acquiredAt": _now(),
        **(metadata or {}),
    }
    (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
    (lock_dir / "lock.json").write_text(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    try:
        yield
    finally:
        shutil.rmtree(lock_dir, ignore_errors=True)


def lock_status(workspace_root: Path, name: str) -> dict[str, Any]:
    lock_dir = workspace_root / "locks" / name
    if not lock_dir.exists():
        return {"name": name, "held": False}
    payload: dict[str, Any] = {"name": name, "held": True, "path": str(lock_dir)}
    lock_json = lock_dir / "lock.json"
    if lock_json.exists():
        try:
            data = json.loads(lock_json.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                payload.update(data)
        except json.JSONDecodeError:
            payload["error"] = "lock.json is invalid"
    pid_path = lock_dir / "pid"
    if "pid" not in payload and pid_path.exists():
        try:
            payload["pid"] = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            payload["pid"] = pid_path.read_text(encoding="utf-8").strip()
    acquired_at = _parse_time(str(payload.get("acquiredAt") or ""))
    if acquired_at:
        payload["ageSeconds"] = max(0.0, (datetime.now().astimezone() - acquired_at).total_seconds())
    pid = payload.get("pid")
    payload["pidAlive"] = _pid_alive(pid) if isinstance(pid, int) else None
    return payload


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
