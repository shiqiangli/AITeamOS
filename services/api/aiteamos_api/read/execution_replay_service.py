"""Replay views for runtime execution sessions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .execution_approval_service import list_execution_approvals
from .execution_session_store import load_execution_sessions, load_execution_state_snapshot

_SENSITIVE_KEY_PARTS = ("api_key", "authorization", "token", "secret", "password")


class ExecutionReplayService:
    def __init__(self, *, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    def session_replay(self, session_key: str) -> dict[str, Any]:
        sessions = load_execution_sessions(self.workspace_dir)
        session = sessions.get(session_key)
        if not isinstance(session, dict):
            raise KeyError(session_key)
        request_id = str(session.get("last_request_id") or "")
        artifact_record = self._execution_artifacts().get(request_id, {})
        approvals = [
            approval.model_dump(mode="json")
            for approval in list_execution_approvals(workspace_dir=self.workspace_dir)
            if approval.id in set(str(item) for item in session.get("approval_refs", []))
            or approval.source_request.get("request_id") == request_id
            or approval.last_run_request_id == request_id
        ]
        state_snapshots = self._approval_state_snapshots(approvals)
        trace_events = self._trace_events(str(session.get("trace_ref") or ""))
        native_checkpoint_history = self._native_checkpoint_history(session, artifact_record, approvals)
        state_transitions = self._state_transitions(session, state_snapshots, trace_events, native_checkpoint_history)
        timeline = self._timeline(
            session,
            artifact_record if isinstance(artifact_record, dict) else {},
            approvals,
            state_snapshots,
            native_checkpoint_history,
            state_transitions,
            trace_events,
        )
        handoff_summary = self._handoff_policy_summary(
            session=session,
            artifact_record=artifact_record if isinstance(artifact_record, dict) else {},
            state_snapshots=state_snapshots,
            native_checkpoint_history=native_checkpoint_history,
        )
        return self._redact(
            {
                "session": session,
                "execution_artifacts": artifact_record if isinstance(artifact_record, dict) else {},
                "approvals": approvals,
                "state_snapshots": state_snapshots,
                "native_checkpoint_history": native_checkpoint_history,
                "state_transitions": state_transitions,
                "trace_events": trace_events,
                "handoff_summary": handoff_summary,
                "coverage_summary": self._coverage_summary(
                    session=session,
                    artifact_record=artifact_record if isinstance(artifact_record, dict) else {},
                    approvals=approvals,
                    state_snapshots=state_snapshots,
                    native_checkpoint_history=native_checkpoint_history,
                    state_transitions=state_transitions,
                    trace_events=trace_events,
                    timeline=timeline,
                    handoff_summary=handoff_summary,
                ),
                "timeline": timeline,
            }
        )

    def session_timeline(self, session_key: str) -> dict[str, Any]:
        replay = self.session_replay(session_key)
        return {
            "session": replay["session"],
            "timeline": replay["timeline"],
        }

    def _execution_artifacts(self) -> dict[str, Any]:
        return self._load_json(self.workspace_dir / "execution_artifacts.json")

    def _trace_events(self, trace_ref: str) -> list[dict[str, Any]]:
        if not trace_ref:
            return []
        path = Path(trace_ref)
        candidates = [path] if path.is_absolute() else [self.workspace_dir / trace_ref, self.workspace_dir.parent / trace_ref]
        selected = next((item for item in candidates if item.exists() and item.is_file()), None)
        if selected is None:
            return []
        events: list[dict[str, Any]] = []
        try:
            for index, line in enumerate(selected.read_text(encoding="utf-8").splitlines()[:200]):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    payload = {"message": line}
                if isinstance(payload, dict):
                    events.append({"index": index, **payload})
        except OSError:
            return []
        return events

    def _approval_state_snapshots(self, approvals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for approval in approvals:
            source_state_ref = str(approval.get("source_state_ref") or "")
            snapshot = load_execution_state_snapshot(self.workspace_dir, source_state_ref) if source_state_ref else None
            if snapshot is None:
                snapshot = self._load_state_snapshot_ref(str(approval.get("source_state_snapshot_ref") or ""))
            if not isinstance(snapshot, dict):
                continue
            graph_state = snapshot.get("graph_state") if isinstance(snapshot.get("graph_state"), dict) else {}
            snapshots.append(
                {
                    "approval_id": str(approval.get("id") or ""),
                    "source_state_ref": str(snapshot.get("source_state_ref") or source_state_ref),
                    "source_state_snapshot_ref": str(
                        snapshot.get("source_state_snapshot_ref") or approval.get("source_state_snapshot_ref") or ""
                    ),
                    "snapshot_schema": str(snapshot.get("snapshot_schema") or ""),
                    "checkpoint_ref": str(snapshot.get("checkpoint_ref") or approval.get("checkpoint_ref") or ""),
                    "executor_session_ref": str(snapshot.get("executor_session_ref") or approval.get("executor_session_ref") or ""),
                    "current_graph_node": str(snapshot.get("current_graph_node") or approval.get("current_graph_node") or ""),
                    "request_id": str(snapshot.get("request_id") or ""),
                    "status": str(snapshot.get("status") or ""),
                    "approval_request": snapshot.get("approval_request") if isinstance(snapshot.get("approval_request"), dict) else {},
                    "state_summary": self._state_summary(graph_state),
                    "state_delta": self._state_delta(graph_state),
                    "graph_state": graph_state,
                }
            )
        return snapshots

    def _load_state_snapshot_ref(self, snapshot_ref: str) -> dict[str, Any] | None:
        if not snapshot_ref.strip():
            return None
        path = Path(snapshot_ref)
        candidates = [path] if path.is_absolute() else [self.workspace_dir / snapshot_ref, self.workspace_dir.parent / snapshot_ref]
        selected = next((item for item in candidates if item.exists() and item.is_file()), None)
        if selected is None:
            return None
        try:
            payload = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _state_summary(self, graph_state: dict[str, Any]) -> dict[str, Any]:
        request = graph_state.get("execution_request") if isinstance(graph_state.get("execution_request"), dict) else {}
        action_plan = request.get("action_plan") if isinstance(request.get("action_plan"), dict) else {}
        learning_delta = graph_state.get("learning_delta") if isinstance(graph_state.get("learning_delta"), dict) else {}
        checkpoint = learning_delta.get("checkpoint") if isinstance(learning_delta.get("checkpoint"), dict) else {}
        native_interrupts = learning_delta.get("native_interrupts") if isinstance(learning_delta.get("native_interrupts"), list) else []
        return {
            "request_id": str(request.get("request_id") or graph_state.get("request_id") or ""),
            "employee_id": str(request.get("employee_id") or ""),
            "ticket_id": str(request.get("ticket_id") or ""),
            "action": str(action_plan.get("action") or learning_delta.get("action") or ""),
            "current_step": str(graph_state.get("current_step") or ""),
            "tool_event_count": len(graph_state.get("tool_events") or []) if isinstance(graph_state.get("tool_events"), list) else 0,
            "error_count": len(graph_state.get("errors") or []) if isinstance(graph_state.get("errors"), list) else 0,
            "native_interrupt_count": len(native_interrupts),
            "checkpoint_next": checkpoint.get("next") if isinstance(checkpoint.get("next"), list) else [],
        }

    def _state_delta(self, graph_state: dict[str, Any]) -> dict[str, Any]:
        changed_keys: list[str] = []
        for key in ("approval_interrupt", "tool_events", "errors", "learning_delta"):
            value = graph_state.get(key)
            if isinstance(value, (list, dict)) and value:
                changed_keys.append(key)
        return {
            "from": "execution_request",
            "to": str(graph_state.get("current_step") or ""),
            "changed_keys": changed_keys,
            "approval_interrupted": bool(graph_state.get("approval_interrupt")),
            "has_errors": bool(graph_state.get("errors")),
        }

    def _native_checkpoint_history(
        self,
        session: dict[str, Any],
        artifact_record: Any,
        approvals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        checkpoint_path = self._native_checkpoint_path()
        if checkpoint_path is None:
            return []
        thread_ids = self._native_checkpoint_thread_ids(session, artifact_record, approvals)
        if not thread_ids:
            return []
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            from .runtime_executors.langgraph_executor import LangGraphExecutor
        except ImportError:
            return []

        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(f"file:{checkpoint_path}?mode=ro", uri=True, check_same_thread=False)
            saver = SqliteSaver(connection)
            graph = LangGraphExecutor(workspace_dir=self.workspace_dir)._build_graph(saver)
            snapshots: list[dict[str, Any]] = []
            for thread_id in thread_ids:
                previous_values: dict[str, Any] | None = None
                raw_history = list(
                    graph.get_state_history(
                        {"configurable": {"thread_id": thread_id}},
                        limit=24,
                    )
                )
                for snapshot in reversed(raw_history):
                    item = self._native_checkpoint_snapshot(thread_id, snapshot, previous_values)
                    previous_values = item.get("values") if isinstance(item.get("values"), dict) else {}
                    snapshots.append(item)
            for index, item in enumerate(snapshots):
                item["index"] = index
            return snapshots
        except Exception:
            return []
        finally:
            if connection is not None:
                connection.close()

    def _native_checkpoint_path(self) -> Path | None:
        candidates = [
            self.workspace_dir / "langgraph" / "langgraph_checkpoints.sqlite",
            self.workspace_dir / ".aiteamos" / "langgraph" / "langgraph_checkpoints.sqlite",
        ]
        return next((path for path in candidates if path.exists() and path.is_file()), None)

    def _native_checkpoint_thread_ids(
        self,
        session: dict[str, Any],
        artifact_record: Any,
        approvals: list[dict[str, Any]],
    ) -> list[str]:
        candidates: list[str] = []
        for value in (
            session.get("last_request_id"),
            self._checkpoint_thread_id(session.get("checkpoint_ref")),
            self._executor_session_thread_id(session.get("executor_session_ref")),
            self._source_state_thread_id(session.get("source_state_ref")),
        ):
            if value:
                candidates.append(value)
        if isinstance(artifact_record, dict):
            for value in (
                artifact_record.get("request_id"),
                artifact_record.get("run_id"),
                self._checkpoint_thread_id(artifact_record.get("checkpoint_ref")),
                self._executor_session_thread_id(artifact_record.get("executor_session_ref")),
            ):
                if value:
                    candidates.append(value)
        for approval in approvals:
            source_request = approval.get("source_request") if isinstance(approval.get("source_request"), dict) else {}
            for value in (
                source_request.get("request_id"),
                approval.get("last_run_request_id"),
                self._checkpoint_thread_id(approval.get("checkpoint_ref")),
                self._executor_session_thread_id(approval.get("executor_session_ref")),
                self._source_state_thread_id(approval.get("source_state_ref")),
            ):
                if value:
                    candidates.append(value)
        seen: set[str] = set()
        thread_ids: list[str] = []
        for value in candidates:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                thread_ids.append(text)
        return thread_ids[:8]

    def _native_checkpoint_snapshot(self, thread_id: str, snapshot: Any, previous_values: dict[str, Any] | None) -> dict[str, Any]:
        values = getattr(snapshot, "values", {}) if isinstance(getattr(snapshot, "values", {}), dict) else {}
        config = getattr(snapshot, "config", {}) if isinstance(getattr(snapshot, "config", {}), dict) else {}
        parent_config = getattr(snapshot, "parent_config", {}) if isinstance(getattr(snapshot, "parent_config", {}), dict) else {}
        configurable = config.get("configurable", {}) if isinstance(config.get("configurable"), dict) else {}
        parent_configurable = parent_config.get("configurable", {}) if isinstance(parent_config.get("configurable"), dict) else {}
        next_nodes = [str(item) for item in getattr(snapshot, "next", ()) or ()]
        tasks = self._native_checkpoint_tasks(getattr(snapshot, "tasks", ()) or ())
        interrupts = self._native_checkpoint_interrupts(getattr(snapshot, "interrupts", ()) or ())
        return {
            "index": -1,
            "thread_id": thread_id,
            "checkpoint_id": self._first_text(configurable.get("checkpoint_id")),
            "checkpoint_ns": self._first_text(configurable.get("checkpoint_ns")),
            "parent_checkpoint_id": self._first_text(parent_configurable.get("checkpoint_id")),
            "created_at": self._first_text(getattr(snapshot, "created_at", "")),
            "metadata": getattr(snapshot, "metadata", {}) if isinstance(getattr(snapshot, "metadata", {}), dict) else {},
            "next": next_nodes,
            "tasks": tasks,
            "interrupts": interrupts,
            "state_summary": self._state_summary(values),
            "state_delta": self._native_checkpoint_delta(values, previous_values or {}, next_nodes, tasks),
            "values": values,
        }

    def _native_checkpoint_tasks(self, tasks: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for task in tasks if isinstance(tasks, (list, tuple)) else []:
            result = getattr(task, "result", None)
            result_summary = self._state_summary(result) if isinstance(result, dict) else {}
            items.append(
                {
                    "id": self._first_text(getattr(task, "id", "")),
                    "name": self._first_text(getattr(task, "name", "")),
                    "path": [str(item) for item in getattr(task, "path", ()) or ()],
                    "error": self._first_text(getattr(task, "error", "")),
                    "interrupt_count": len(getattr(task, "interrupts", ()) or ()),
                    "result_summary": result_summary,
                }
            )
        return items

    def _native_checkpoint_interrupts(self, interrupts: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for interrupt in interrupts if isinstance(interrupts, (list, tuple)) else []:
            value = getattr(interrupt, "value", None)
            items.append(
                {
                    "id": self._first_text(getattr(interrupt, "id", "")),
                    "value": value if isinstance(value, dict) else {},
                }
            )
        return items

    def _native_checkpoint_delta(
        self,
        values: dict[str, Any],
        previous_values: dict[str, Any],
        next_nodes: list[str],
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        previous_keys = set(previous_values)
        current_keys = set(values)
        changed_keys = sorted(
            key
            for key in current_keys & previous_keys
            if self._stable_json(values.get(key)) != self._stable_json(previous_values.get(key))
        )
        added_keys = sorted(current_keys - previous_keys)
        removed_keys = sorted(previous_keys - current_keys)
        return {
            "from": self._first_text(previous_values.get("current_step")) or "__start__",
            "to": self._first_text(values.get("current_step"), *(next_nodes[:1])) or "__end__",
            "changed_keys": changed_keys,
            "added_keys": added_keys,
            "removed_keys": removed_keys,
            "next": next_nodes,
            "task_names": [self._first_text(task.get("name")) for task in tasks if self._first_text(task.get("name"))],
            "approval_interrupted": bool(values.get("approval_interrupt") or any(task.get("interrupt_count") for task in tasks)),
            "has_errors": bool(values.get("errors") or any(task.get("error") for task in tasks)),
        }

    def _state_transitions(
        self,
        session: dict[str, Any],
        state_snapshots: list[dict[str, Any]],
        trace_events: list[dict[str, Any]],
        native_checkpoint_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        transitions: list[dict[str, Any]] = []
        session_transition = self._session_state_transition(session)
        if session_transition:
            transitions.append(session_transition)
        for snapshot in state_snapshots:
            transition = self._snapshot_state_transition(snapshot)
            if transition:
                transitions.append(transition)
        for checkpoint in native_checkpoint_history:
            transition = self._native_checkpoint_state_transition(checkpoint)
            if transition:
                transitions.append(transition)
        for trace in trace_events:
            transition = self._trace_state_transition(trace, session)
            if transition:
                transitions.append(transition)
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for transition in transitions:
            key = (
                str(transition.get("source_kind") or ""),
                str(transition.get("event") or ""),
                str(transition.get("from") or ""),
                str(transition.get("to") or ""),
                str(transition.get("source_state_ref") or transition.get("checkpoint_ref") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            transition["index"] = len(deduped)
            deduped.append(transition)
        return deduped

    def _session_state_transition(self, session: dict[str, Any]) -> dict[str, Any] | None:
        to_node = self._first_text(session.get("current_graph_node"), session.get("status"))
        checkpoint_ref = self._first_text(session.get("checkpoint_ref"))
        source_state_ref = self._first_text(session.get("source_state_ref"))
        if not any((to_node, checkpoint_ref, source_state_ref)):
            return None
        return {
            "index": -1,
            "kind": "state_transition",
            "event": "execution.state_transition",
            "source_kind": "session",
            "from": "execution_request",
            "to": to_node or "completed",
            "changed_keys": ["session"],
            "checkpoint_ref": checkpoint_ref,
            "executor_session_ref": self._first_text(session.get("executor_session_ref")),
            "source_state_ref": source_state_ref,
            "source_state_snapshot_ref": "",
            "request_id": self._first_text(session.get("last_request_id")),
            "approval_interrupted": bool(session.get("approval_refs")),
            "has_errors": str(session.get("status") or "").lower() in {"failed", "blocked", "error"},
            "summary": {
                "employee_id": self._first_text(session.get("employee_id")),
                "ticket_id": self._first_text(session.get("ticket_id")),
                "status": self._first_text(session.get("status")),
                "tool_event_count": session.get("tool_event_count") if isinstance(session.get("tool_event_count"), int) else 0,
            },
        }

    def _snapshot_state_transition(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        delta = snapshot.get("state_delta") if isinstance(snapshot.get("state_delta"), dict) else {}
        summary = snapshot.get("state_summary") if isinstance(snapshot.get("state_summary"), dict) else {}
        to_node = self._first_text(delta.get("to"), snapshot.get("current_graph_node"), summary.get("current_step"))
        if not to_node:
            return None
        return {
            "index": -1,
            "kind": "state_transition",
            "event": "execution.state_transition",
            "source_kind": "state_snapshot",
            "from": self._first_text(delta.get("from")) or "execution_request",
            "to": to_node,
            "changed_keys": delta.get("changed_keys") if isinstance(delta.get("changed_keys"), list) else [],
            "checkpoint_ref": self._first_text(snapshot.get("checkpoint_ref")),
            "executor_session_ref": self._first_text(snapshot.get("executor_session_ref")),
            "source_state_ref": self._first_text(snapshot.get("source_state_ref")),
            "source_state_snapshot_ref": self._first_text(snapshot.get("source_state_snapshot_ref")),
            "request_id": self._first_text(snapshot.get("request_id"), summary.get("request_id")),
            "approval_id": self._first_text(snapshot.get("approval_id")),
            "approval_interrupted": bool(delta.get("approval_interrupted")),
            "has_errors": bool(delta.get("has_errors")),
            "summary": summary,
        }

    def _native_checkpoint_state_transition(self, checkpoint: dict[str, Any]) -> dict[str, Any] | None:
        delta = checkpoint.get("state_delta") if isinstance(checkpoint.get("state_delta"), dict) else {}
        to_node = self._first_text(delta.get("to"))
        if not to_node:
            return None
        return {
            "index": -1,
            "kind": "state_transition",
            "event": "execution.state_transition",
            "source_kind": "native_checkpoint",
            "from": self._first_text(delta.get("from")) or "__start__",
            "to": to_node,
            "changed_keys": delta.get("changed_keys") if isinstance(delta.get("changed_keys"), list) else [],
            "checkpoint_ref": f"langgraph:{checkpoint.get('thread_id') or ''}",
            "executor_session_ref": f"lg-{checkpoint.get('thread_id') or ''}",
            "source_state_ref": "",
            "source_state_snapshot_ref": self._first_text(checkpoint.get("checkpoint_id")),
            "request_id": self._first_text(checkpoint.get("thread_id")),
            "approval_interrupted": bool(delta.get("approval_interrupted")),
            "has_errors": bool(delta.get("has_errors")),
            "summary": checkpoint.get("state_summary") if isinstance(checkpoint.get("state_summary"), dict) else {},
        }

    def _trace_state_transition(self, trace: dict[str, Any], session: dict[str, Any]) -> dict[str, Any] | None:
        data = trace.get("data") if isinstance(trace.get("data"), dict) else {}
        to_node = self._first_text(
            trace.get("current_graph_node"),
            trace.get("current_step"),
            trace.get("node"),
            data.get("current_graph_node"),
            data.get("current_step"),
            data.get("node"),
        )
        if not to_node:
            return None
        from_node = self._first_text(trace.get("previous_graph_node"), trace.get("previous_step"), data.get("previous_graph_node"), data.get("previous_step"))
        return {
            "index": -1,
            "kind": "state_transition",
            "event": "execution.state_transition",
            "source_kind": "trace",
            "from": from_node or "trace_event",
            "to": to_node,
            "changed_keys": ["trace"],
            "checkpoint_ref": self._first_text(trace.get("checkpoint_ref"), data.get("checkpoint_ref"), session.get("checkpoint_ref")),
            "executor_session_ref": self._first_text(trace.get("executor_session_ref"), data.get("executor_session_ref"), session.get("executor_session_ref")),
            "source_state_ref": self._first_text(trace.get("source_state_ref"), data.get("source_state_ref")),
            "source_state_snapshot_ref": self._first_text(trace.get("source_state_snapshot_ref"), data.get("source_state_snapshot_ref")),
            "request_id": self._first_text(trace.get("request_id"), data.get("request_id"), session.get("last_request_id")),
            "approval_interrupted": False,
            "has_errors": bool(trace.get("error") or data.get("error")),
            "summary": {
                "trace_index": trace.get("index") if isinstance(trace.get("index"), int) else -1,
                "trace_event": self._first_text(trace.get("event"), trace.get("type")),
            },
        }

    def _timeline(
        self,
        session: dict[str, Any],
        artifact_record: dict[str, Any],
        approvals: list[dict[str, Any]],
        state_snapshots: list[dict[str, Any]],
        native_checkpoint_history: list[dict[str, Any]],
        state_transitions: list[dict[str, Any]],
        trace_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = [
            {
                "index": 0,
                "kind": "session",
                "event": "execution.session",
                "title": f"Execution session {session.get('status') or 'unknown'}",
                "at": session.get("updated_at") or "",
                "refs": self._session_refs(session),
                "data": {
                    "checkpoint_ref": session.get("checkpoint_ref") or "",
                    "source_state_ref": session.get("source_state_ref") or "",
                    "current_graph_node": session.get("current_graph_node") or "",
                },
            }
        ]
        for event in session.get("tool_events", []):
            if not isinstance(event, dict):
                continue
            timeline.append(
                {
                    "index": len(timeline),
                    "kind": "tool_event",
                    "event": str(event.get("event") or event.get("tool_name") or "tool_event"),
                    "title": str(event.get("tool_name") or event.get("event") or "Tool event"),
                    "at": session.get("updated_at") or "",
                    "refs": event.get("output_refs") if isinstance(event.get("output_refs"), list) else [],
                    "data": event,
                }
            )
        for artifact in artifact_record.get("artifacts", []) if isinstance(artifact_record.get("artifacts"), list) else []:
            if isinstance(artifact, dict):
                timeline.append(self._artifact_timeline_item("artifact", artifact, session))
        for evidence in artifact_record.get("evidence", []) if isinstance(artifact_record.get("evidence"), list) else []:
            if isinstance(evidence, dict):
                timeline.append(self._artifact_timeline_item("evidence", evidence, session))
        for approval in approvals:
            timeline.append(
                {
                    "index": len(timeline),
                    "kind": "approval",
                    "event": f"approval.{approval.get('status') or 'unknown'}",
                    "title": str(approval.get("id") or "Runtime approval"),
                    "at": approval.get("updated_at") or approval.get("created_at") or "",
                    "refs": [
                        {"kind": "approval", "ref": approval.get("id") or ""},
                        {"kind": "ticket", "ref": approval.get("ticket_id") or ""},
                    ],
                    "data": approval,
                }
            )
            for run in approval.get("run_history", []) if isinstance(approval.get("run_history"), list) else []:
                if isinstance(run, dict):
                    timeline.append(self._approval_run_timeline_item(approval, run))
        for snapshot in state_snapshots:
            timeline.append(
                {
                    "index": len(timeline),
                    "kind": "state_snapshot",
                    "event": "execution.state_snapshot",
                    "title": f"State snapshot {snapshot.get('current_graph_node') or snapshot.get('checkpoint_ref') or 'checkpoint'}",
                    "at": session.get("updated_at") or "",
                    "refs": [
                        {"kind": "approval", "ref": str(snapshot.get("approval_id") or "")},
                        {"kind": "checkpoint", "ref": str(snapshot.get("checkpoint_ref") or "")},
                        {"kind": "state", "ref": str(snapshot.get("source_state_ref") or "")},
                    ],
                    "data": snapshot,
                }
            )
        for checkpoint in native_checkpoint_history:
            timeline.append(
                {
                    "index": len(timeline),
                    "kind": "native_checkpoint",
                    "event": "execution.native_checkpoint",
                    "title": f"LangGraph checkpoint {checkpoint.get('checkpoint_id') or checkpoint.get('thread_id') or 'checkpoint'}",
                    "at": checkpoint.get("created_at") or session.get("updated_at") or "",
                    "refs": [
                        {"kind": "checkpoint", "ref": str(checkpoint.get("checkpoint_id") or "")},
                        {"kind": "request", "ref": str(checkpoint.get("thread_id") or "")},
                    ],
                    "data": checkpoint,
                }
            )
        for transition in state_transitions:
            refs = [
                {"kind": "checkpoint", "ref": str(transition.get("checkpoint_ref") or "")},
                {"kind": "state", "ref": str(transition.get("source_state_ref") or "")},
                {"kind": "state_snapshot", "ref": str(transition.get("source_state_snapshot_ref") or "")},
            ]
            timeline.append(
                {
                    "index": len(timeline),
                    "kind": "state_transition",
                    "event": "execution.state_transition",
                    "title": f"{transition.get('from') or '?'} -> {transition.get('to') or '?'}",
                    "at": session.get("updated_at") or "",
                    "refs": refs,
                    "data": transition,
                }
            )
        for trace in trace_events:
            timeline.append(
                {
                    "index": len(timeline),
                    "kind": "trace",
                    "event": str(trace.get("event") or trace.get("type") or "trace"),
                    "title": str(trace.get("event") or trace.get("message") or "Trace event"),
                    "at": str(trace.get("at") or trace.get("timestamp") or ""),
                    "refs": [],
                    "data": trace,
                }
            )
        for index, item in enumerate(timeline):
            item["index"] = index
        return timeline

    def _coverage_summary(
        self,
        *,
        session: dict[str, Any],
        artifact_record: dict[str, Any],
        approvals: list[dict[str, Any]],
        state_snapshots: list[dict[str, Any]],
        native_checkpoint_history: list[dict[str, Any]],
        state_transitions: list[dict[str, Any]],
        trace_events: list[dict[str, Any]],
        timeline: list[dict[str, Any]],
        handoff_summary: dict[str, Any],
    ) -> dict[str, Any]:
        refs = self._coverage_refs(session, artifact_record, approvals, timeline)
        approval_required = bool(refs["approval_refs"] or approvals or session.get("approval_refs"))
        handoff_present = str(handoff_summary.get("status") or "") not in {"", "not_applicable"}
        handoff_policy = handoff_summary.get("policy") if isinstance(handoff_summary.get("policy"), dict) else {}
        coverage = {
            "ticket": bool(refs["ticket_refs"]),
            "employee": bool(refs["employee_refs"]),
            "runtime": bool(session.get("executor_id") or session.get("executor_session_ref") or session.get("checkpoint_ref")),
            "evidence": bool(refs["evidence_refs"] or artifact_record.get("evidence")),
            "trace": bool(trace_events),
            "state": bool(state_transitions or state_snapshots or native_checkpoint_history),
            "checkpoint": bool(session.get("checkpoint_ref") or state_snapshots or native_checkpoint_history),
            "approval": (not approval_required) or bool(approvals),
            "asset_or_memory": bool(refs["asset_refs"] or refs["memory_refs"]),
            "handoff": handoff_present,
            "handoff_policy": bool(handoff_policy),
        }
        required_keys = ["ticket", "employee", "runtime", "evidence", "trace", "state", "checkpoint", "approval"]
        gaps = [f"{key}_missing" for key in required_keys if not coverage[key]]
        return {
            "schema": "execution_replay_coverage.v1",
            "request_id": self._first_text(session.get("last_request_id"), artifact_record.get("request_id")),
            "session_key": self._first_text(session.get("session_key")),
            "status": self._first_text(session.get("status"), artifact_record.get("status")),
            "coverage": coverage,
            "required_chain_complete": not gaps,
            "gaps": gaps,
            "counts": {
                "timeline_event_count": len(timeline),
                "artifact_count": len(artifact_record.get("artifacts")) if isinstance(artifact_record.get("artifacts"), list) else 0,
                "evidence_count": len(artifact_record.get("evidence")) if isinstance(artifact_record.get("evidence"), list) else 0,
                "approval_count": len(approvals),
                "state_snapshot_count": len(state_snapshots),
                "native_checkpoint_count": len(native_checkpoint_history),
                "state_transition_count": len(state_transitions),
                "trace_event_count": len(trace_events),
                "handoff_ref_count": len(handoff_summary.get("refs")) if isinstance(handoff_summary.get("refs"), list) else 0,
            },
            "refs": refs,
        }

    def _handoff_policy_summary(
        self,
        *,
        session: dict[str, Any],
        artifact_record: dict[str, Any],
        state_snapshots: list[dict[str, Any]],
        native_checkpoint_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        candidate = self._handoff_candidate_from_artifacts(artifact_record)
        source_kind = "execution_artifact"
        if not candidate:
            candidate = self._handoff_candidate_from_checkpoints(native_checkpoint_history)
            source_kind = "native_checkpoint"
        if not candidate:
            candidate = self._handoff_candidate_from_state_snapshots(state_snapshots)
            source_kind = "state_snapshot"
        if not candidate:
            return {
                "schema": "execution_replay_handoff_policy.v1",
                "status": "not_applicable",
                "source_kind": "",
                "refs": [],
                "policy": {},
            }
        return self._normalize_handoff_summary(candidate, session=session, artifact_record=artifact_record, source_kind=source_kind)

    def _handoff_candidate_from_artifacts(self, artifact_record: dict[str, Any]) -> dict[str, Any]:
        artifacts = artifact_record.get("artifacts") if isinstance(artifact_record.get("artifacts"), list) else []
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("kind") == "employee_handoff_request":
                return artifact
        learning_delta = artifact_record.get("learning_delta") if isinstance(artifact_record.get("learning_delta"), dict) else {}
        handoff = learning_delta.get("employee_handoff") if isinstance(learning_delta.get("employee_handoff"), dict) else {}
        return handoff

    def _handoff_candidate_from_checkpoints(self, native_checkpoint_history: list[dict[str, Any]]) -> dict[str, Any]:
        for checkpoint in reversed(native_checkpoint_history):
            values = checkpoint.get("values") if isinstance(checkpoint.get("values"), dict) else {}
            artifact = self._handoff_candidate_from_artifacts({"artifacts": values.get("artifacts")})
            if artifact:
                return artifact
            decision = values.get("handoff_decision") if isinstance(values.get("handoff_decision"), dict) else {}
            if decision.get("should_handoff"):
                summary = values.get("handoff_summary") if isinstance(values.get("handoff_summary"), dict) else {}
                return {"decision": decision, "summary": summary, "ticket_handoff_refs": values.get("ticket_handoff_refs")}
        return {}

    def _handoff_candidate_from_state_snapshots(self, state_snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        for snapshot in reversed(state_snapshots):
            graph_state = snapshot.get("graph_state") if isinstance(snapshot.get("graph_state"), dict) else {}
            learning_delta = graph_state.get("learning_delta") if isinstance(graph_state.get("learning_delta"), dict) else {}
            handoff = learning_delta.get("employee_handoff") if isinstance(learning_delta.get("employee_handoff"), dict) else {}
            if handoff:
                return handoff
        return {}

    def _normalize_handoff_summary(
        self,
        candidate: dict[str, Any],
        *,
        session: dict[str, Any],
        artifact_record: dict[str, Any],
        source_kind: str,
    ) -> dict[str, Any]:
        decision = candidate.get("decision") if isinstance(candidate.get("decision"), dict) else candidate
        summary = candidate.get("summary") if isinstance(candidate.get("summary"), dict) else {}
        policy = decision.get("policy") if isinstance(decision.get("policy"), dict) else {}
        provenance = decision.get("provenance") if isinstance(decision.get("provenance"), dict) else {}
        ticket_id = self._first_text(decision.get("ticket_id"), summary.get("ticket_id"), artifact_record.get("ticket_id"), session.get("ticket_id"))
        source_employee_id = self._first_text(decision.get("from_employee_id"), session.get("employee_id"))
        target_employee_id = self._first_text(decision.get("to_employee_id"), decision.get("target_employee_id"), summary.get("target_employee_id"))
        target_role = self._first_text(decision.get("to_role"), decision.get("target_role"))
        source_request_ref = self._first_text(provenance.get("source_ref"), artifact_record.get("request_id"), session.get("last_request_id"))
        ticket_handoff_refs = candidate.get("ticket_handoff_refs") if isinstance(candidate.get("ticket_handoff_refs"), list) else []
        refs = [
            {"kind": "ticket", "ref": ticket_id},
            {"kind": "employee", "ref": source_employee_id},
            {"kind": "employee", "ref": target_employee_id},
            {"kind": "request", "ref": source_request_ref},
        ]
        refs.extend(item for item in ticket_handoff_refs if isinstance(item, dict))
        return {
            "schema": "execution_replay_handoff_policy.v1",
            "status": self._first_text(summary.get("status"), "employee_handoff_recorded"),
            "source_kind": source_kind,
            "ticket_id": ticket_id,
            "source_employee_id": source_employee_id,
            "source_role": self._first_text(decision.get("from_role")),
            "target_employee_id": target_employee_id,
            "target_role": target_role,
            "lane": self._first_text(decision.get("lane")),
            "confidence": decision.get("confidence"),
            "reason": self._first_text(decision.get("reason"), decision.get("content")),
            "policy": policy,
            "required_memory_scopes": self._string_list(policy.get("required_memory_scopes")),
            "matched_memory_scopes": self._string_list(policy.get("matched_memory_scopes")),
            "available_memory_scopes": self._string_list(policy.get("available_memory_scopes")),
            "memory_scope_match": self._first_text(policy.get("memory_scope_match")),
            "risk_level": self._first_text(policy.get("risk_level")),
            "max_risk_level": self._first_text(policy.get("max_risk_level")),
            "risk_allowed": bool(policy.get("risk_allowed")),
            "policy_aware": bool(policy.get("policy_aware") or policy),
            "provenance": provenance,
            "refs": self._dedupe_refs(refs),
        }

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _dedupe_refs(self, refs: list[dict[str, Any]]) -> list[dict[str, str]]:
        seen: set[tuple[str, str]] = set()
        output: list[dict[str, str]] = []
        for ref in refs:
            kind = self._first_text(ref.get("kind"), ref.get("source_kind"))
            value = self._first_text(ref.get("ref"), ref.get("source_ref"), ref.get("id"))
            key = (kind, value)
            if not kind or not value or key in seen:
                continue
            seen.add(key)
            output.append({"kind": kind, "ref": value})
        return output[:12]

    def _coverage_refs(
        self,
        session: dict[str, Any],
        artifact_record: dict[str, Any],
        approvals: list[dict[str, Any]],
        timeline: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        refs: dict[str, list[str]] = {
            "ticket_refs": [],
            "employee_refs": [],
            "approval_refs": [],
            "asset_refs": [],
            "memory_refs": [],
            "evidence_refs": [],
            "checkpoint_refs": [],
            "state_refs": [],
            "trace_refs": [],
            "request_refs": [],
        }

        def add(bucket: str, value: Any) -> None:
            text = self._first_text(value)
            if text and text not in refs[bucket]:
                refs[bucket].append(text)

        add("ticket_refs", session.get("ticket_id"))
        add("employee_refs", session.get("employee_id"))
        add("checkpoint_refs", session.get("checkpoint_ref"))
        add("state_refs", session.get("source_state_ref"))
        add("trace_refs", session.get("trace_ref"))
        add("request_refs", session.get("last_request_id"))
        for value in session.get("ticket_refs", []) if isinstance(session.get("ticket_refs"), list) else []:
            add("ticket_refs", value)
        for value in session.get("memory_refs", []) if isinstance(session.get("memory_refs"), list) else []:
            add("memory_refs", value)
        for value in session.get("approval_refs", []) if isinstance(session.get("approval_refs"), list) else []:
            add("approval_refs", value)
        for approval in approvals:
            add("approval_refs", approval.get("id"))
            add("ticket_refs", approval.get("ticket_id"))
            add("employee_refs", approval.get("employee_id"))
            add("checkpoint_refs", approval.get("checkpoint_ref"))
            add("state_refs", approval.get("source_state_ref"))
            add("request_refs", _record_get(approval.get("source_request"), "request_id"))
            add("request_refs", approval.get("last_run_request_id"))
        for evidence in artifact_record.get("evidence", []) if isinstance(artifact_record.get("evidence"), list) else []:
            if isinstance(evidence, dict):
                add("evidence_refs", evidence.get("ref") or evidence.get("id") or evidence.get("kind"))
        for artifact in artifact_record.get("artifacts", []) if isinstance(artifact_record.get("artifacts"), list) else []:
            if not isinstance(artifact, dict):
                continue
            kind = self._first_text(artifact.get("kind")).lower()
            ref = artifact.get("ref") or artifact.get("id")
            if "asset" in kind:
                add("asset_refs", ref)
            if "memory" in kind:
                add("memory_refs", ref)
            if "evidence" in kind:
                add("evidence_refs", ref)
        for candidate in artifact_record.get("memory_candidates", []) if isinstance(artifact_record.get("memory_candidates"), list) else []:
            if isinstance(candidate, dict):
                add("memory_refs", candidate.get("id") or candidate.get("memory_id") or candidate.get("candidate_id"))
                add("asset_refs", candidate.get("asset_id"))
        for item in timeline:
            for ref in item.get("refs", []) if isinstance(item.get("refs"), list) else []:
                if not isinstance(ref, dict):
                    continue
                kind = self._first_text(ref.get("kind")).lower()
                value = ref.get("ref")
                if "ticket" in kind:
                    add("ticket_refs", value)
                elif "employee" in kind:
                    add("employee_refs", value)
                elif "approval" in kind:
                    add("approval_refs", value)
                elif "memory" in kind:
                    add("memory_refs", value)
                elif "asset" in kind or "artifact" in kind:
                    add("asset_refs", value)
                elif "evidence" in kind:
                    add("evidence_refs", value)
                elif "checkpoint" in kind:
                    add("checkpoint_refs", value)
                elif "state" in kind:
                    add("state_refs", value)
                elif "request" in kind:
                    add("request_refs", value)
        return {key: values[:12] for key, values in refs.items()}

    def _approval_run_timeline_item(self, approval: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
        status = str(run.get("status") or "unknown")
        return {
            "index": -1,
            "kind": "approval_run",
            "event": f"approval.run.{status}",
            "title": f"{approval.get('id') or 'Runtime approval'} run {status}",
            "at": str(run.get("created_at") or approval.get("updated_at") or approval.get("created_at") or ""),
            "refs": [
                {"kind": "approval", "ref": str(approval.get("id") or "")},
                {"kind": "request", "ref": str(run.get("run_request_id") or "")},
                {"kind": "checkpoint", "ref": str(run.get("checkpoint_ref") or "")},
                {"kind": "state_snapshot", "ref": str(run.get("resume_source_state_snapshot_ref") or "")},
            ],
            "data": {
                "approval_id": str(approval.get("id") or ""),
                "source_state_ref": str(approval.get("source_state_ref") or ""),
                "source_state_snapshot_ref": str(approval.get("source_state_snapshot_ref") or ""),
                **run,
            },
        }

    def _artifact_timeline_item(self, kind: str, payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
        return {
            "index": -1,
            "kind": kind,
            "event": str(payload.get("kind") or kind),
            "title": str(payload.get("kind") or kind),
            "at": session.get("updated_at") or "",
            "refs": [{"kind": kind, "ref": str(payload.get("ref") or payload.get("id") or payload.get("kind") or "")}],
            "data": payload,
        }

    def _session_refs(self, session: dict[str, Any]) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        for kind, key in (("ticket", "ticket_refs"), ("memory", "memory_refs"), ("approval", "approval_refs")):
            for value in session.get(key, []):
                if str(value).strip():
                    refs.append({"kind": kind, "ref": str(value)})
        return refs

    def _first_text(self, *values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _checkpoint_thread_id(self, value: Any) -> str:
        text = self._first_text(value)
        if text.startswith("langgraph:"):
            return text.split(":", 1)[1].strip()
        return ""

    def _executor_session_thread_id(self, value: Any) -> str:
        text = self._first_text(value)
        if text.startswith("lg-"):
            return text.removeprefix("lg-").strip()
        return ""

    def _source_state_thread_id(self, value: Any) -> str:
        parts = self._first_text(value).split("/")
        if len(parts) >= 4 and parts[0] == "state:" and parts[2] == "langgraph":
            return parts[3].strip()
        return ""

    def _stable_json(self, value: Any) -> str:
        try:
            return json.dumps(value, sort_keys=True, default=str)
        except TypeError:
            return str(value)

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                normalized = str(key).lower()
                if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                    redacted[key] = "[redacted]"
                else:
                    redacted[key] = self._redact(item)
            return redacted
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value


def _record_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else ""
