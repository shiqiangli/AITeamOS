"""Scoped task context assembly for runtime execution requests."""

from __future__ import annotations

import re
from typing import Any

from .employee_load_service import employee_current_load, employee_current_loads
from .execution_contract import ScopedTaskContext
from .memory_service import MemorySearchResult, recall_memory_records
from .ticket_service import employee_work_ledger, get_ticket, list_tickets, ticket_backend_status, ticket_assets_for_ticket


class ExecutionContextService:
    def build(
        self,
        *,
        message: str,
        employee: dict[str, Any],
        employee_profiles: list[dict[str, Any]] | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
        ticket_keys: list[str],
        memory_refs: list[dict[str, Any]],
        selected_ai_engine: str,
        stale_memory_refs: list[dict[str, Any]] | None = None,
    ) -> ScopedTaskContext:
        ticket: dict[str, Any] = {}
        related_tickets: list[dict[str, Any]] = []
        prior_evidence: list[dict[str, Any]] = []
        relevant_assets: list[dict[str, Any]] = []
        asset_relationship_hints: list[dict[str, Any]] = []
        setup_blockers: list[dict[str, Any]] = []
        ticket_backend: dict[str, Any] = {}
        tickets: list[Any] = []

        try:
            backend_status = ticket_backend_status()
            ticket_backend = backend_status.model_dump(mode="json")
            if backend_status.status == "setup_blocked":
                setup_blockers.append(
                    {
                        "kind": "ticket_backend",
                        "reason": "plane_setup_blocker",
                        "detail": backend_status.detail,
                        "setup_required": backend_status.setup_required,
                    }
                )
            else:
                try:
                    tickets = list_tickets()
                except Exception as exc:
                    setup_blockers.append({"kind": "ticket", "reason": "ticket_search_failed", "detail": str(exc)})
        except Exception as exc:
            setup_blockers.append({"kind": "ticket_backend", "reason": "status_error", "detail": str(exc)})

        if ticket_keys:
            try:
                item = next((ticket for ticket in tickets if ticket.id == ticket_keys[0]), None)
                if item is None:
                    item = get_ticket(ticket_keys[0])
            except Exception as exc:
                item = None
                setup_blockers.append({"kind": "ticket", "reason": "ticket_lookup_failed", "detail": str(exc)})
            if item is not None:
                ticket = item.model_dump(mode="json")
                prior_evidence = [
                    {"ticket_id": item.id, "report_id": report.id, "evidence": report.evidence, "report_type": report.report_type}
                    for report in item.reports
                    if report.evidence
                ]
                relevant_assets = self._relevant_assets_for_ticket(item.id)
                asset_relationship_hints = self._asset_relationship_hints(relevant_assets)
                relevant_assets = self._active_assets_from_relationship_hints(relevant_assets, asset_relationship_hints)
        related_tickets = self._related_tickets(
            message=message,
            employee=employee,
            tickets=tickets,
            current_ticket_id=str(ticket.get("id") or ""),
        )

        try:
            recalled_memories = self._recalled_memories(
                message=message,
                employee_id=str(employee.get("id") or ""),
                ticket_keys=ticket_keys,
                explicit_refs=memory_refs,
            )
            stale_memory_hints = self._stale_memory_hints(
                message=message,
                employee_id=str(employee.get("id") or ""),
                ticket_keys=ticket_keys,
            )
            stale_memory_hints = self._dedupe_stale_memory_hints(
                [*stale_memory_hints, *(stale_memory_refs or [])]
            )
        except Exception as exc:
            detail = str(exc)
            setup_blockers.append(
                {
                    "kind": "memory",
                    "reason": "graphiti_recall_failed" if "graphiti" in detail.lower() else "memory_recall_failed",
                    "detail": detail,
                }
            )
            recalled_memories = []
            stale_memory_hints = []
        recall_trace = [self._recall_trace_entry(message, ticket_keys, employee, ref) for ref in recalled_memories]
        return ScopedTaskContext(
            task_summary=message,
            ticket=ticket,
            employee=employee,
            employee_profiles=employee_profiles or [],
            recent_messages=self._recent_messages(recent_messages),
            relevant_assets=relevant_assets,
            recalled_memories=recalled_memories,
            prior_evidence=prior_evidence,
            approval_policy_summary={"selected_ai_engine": selected_ai_engine},
            exclusions=[
                "raw secrets",
                "raw permission authority",
                "raw terminal logs",
                "unrelated global memory dumps",
            ],
            recall_trace=recall_trace,
            setup_blockers=setup_blockers,
            universal_context=self._universal_context(
                message=message,
                employee=employee,
                employee_profiles=employee_profiles or [],
                selected_ai_engine=selected_ai_engine,
                ticket=ticket,
                related_tickets=related_tickets,
                prior_evidence=prior_evidence,
                relevant_assets=relevant_assets,
                asset_relationship_hints=asset_relationship_hints,
                recalled_memories=recalled_memories,
                stale_memory_hints=stale_memory_hints,
                recall_trace=recall_trace,
                ticket_backend=ticket_backend,
                setup_blockers=setup_blockers,
            ),
        )

    def _recent_messages(self, recent_messages: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for item in recent_messages or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            history.append({"role": role, "content": content})
        return history[-12:]

    def _recalled_memories(
        self,
        *,
        message: str,
        employee_id: str,
        ticket_keys: list[str],
        explicit_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        recalled: list[dict[str, Any]] = [ref for ref in explicit_refs if isinstance(ref, dict)]
        seen = {str(ref.get("memory_id") or ref.get("asset_id") or "").strip() for ref in recalled}
        recall_query = self._recall_query(message)

        def add(results: list[MemorySearchResult], *, reason: str) -> None:
            for result in results:
                memory_id = str(result.provenance.get("asset_id") or result.id).strip()
                if not memory_id or memory_id in seen:
                    continue
                seen.add(memory_id)
                recalled.append(self._memory_result_ref(result, memory_id=memory_id, reason=reason))

        add(
            recall_memory_records(
                employee_id=employee_id,
                query=recall_query,
                ticket_keys=ticket_keys,
                limit=5,
            ),
            reason="approved Memory matched the current Ticket scope",
        )
        if len(recalled) < 5:
            add(
                recall_memory_records(
                    employee_id=employee_id,
                    query=recall_query,
                    ticket_keys=[],
                    limit=5 - len(recalled),
                ),
                reason="approved Memory matched the scoped task query",
        )
        return recalled[:5]

    def _stale_memory_hints(
        self,
        *,
        message: str,
        employee_id: str,
        ticket_keys: list[str],
    ) -> list[dict[str, Any]]:
        try:
            from .memory_service import list_memory_candidates
        except Exception:
            return []
        query_terms = set(self._recall_query(message).lower().split())
        hints: list[dict[str, Any]] = []
        for candidate in list_memory_candidates():
            if candidate.status not in {"stale", "superseded"}:
                continue
            if candidate.employee_ids and employee_id and employee_id not in candidate.employee_ids:
                continue
            if ticket_keys and candidate.scope_kind == "ticket" and candidate.scope_ref not in ticket_keys:
                continue
            haystack = " ".join([candidate.content, " ".join(candidate.tags), candidate.source_ref, candidate.scope_ref]).lower()
            if query_terms and not query_terms.issubset(set(haystack.split())):
                continue
            latest_review = candidate.provenance.get("latest_review") if isinstance(candidate.provenance, dict) else {}
            hints.append(
                {
                    "memory_id": candidate.id,
                    "asset_id": candidate.id,
                    "content": candidate.content[:600],
                    "status": candidate.status,
                    "source_kind": candidate.source_kind,
                    "source_ref": candidate.source_ref,
                    "scope_kind": candidate.scope_kind,
                    "scope_ref": candidate.scope_ref,
                    "tags": candidate.tags,
                    "exclusion_reason": (
                        str(latest_review.get("reason") or "")
                        or f"Memory candidate is marked {candidate.status} and must not be recalled as active context."
                    ),
                    "superseded_by_candidate_id": str(candidate.provenance.get("superseded_by_candidate_id") or ""),
                    "provenance": candidate.provenance,
                    "source_confidence": 0.2,
                }
            )
            if len(hints) >= 5:
                break
        return hints

    def _dedupe_stale_memory_hints(self, hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hint in hints:
            if not isinstance(hint, dict):
                continue
            key = str(
                hint.get("memory_id")
                or hint.get("asset_id")
                or hint.get("graphiti_result_id")
                or hint.get("source_ref")
                or ""
            ).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(hint)
        return deduped

    def _recall_query(self, message: str) -> str:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]+", message)
        ignored = {
            "report",
            "ticket",
            "create",
            "created",
            "validate",
            "validation",
            "passed",
            "failed",
            "with",
            "for",
            "the",
            "and",
            "use",
            "using",
            "alex",
            "clara",
            "peter",
        }
        selected = [
            word.lower()
            for word in words
            if len(word) > 2 and word.lower() not in ignored and not re.match(r"^[a-z]+-\d+$", word.lower())
        ]
        return " ".join(selected[:8]).strip() or message[:120]

    def _related_tickets(
        self,
        *,
        message: str,
        employee: dict[str, Any],
        tickets: list[Any],
        current_ticket_id: str,
    ) -> list[dict[str, Any]]:
        query = self._recall_query(message)
        query_terms = {term for term in query.lower().split() if len(term) > 2}
        employee_id = str(employee.get("id") or "").strip().lower()
        scored: list[tuple[int, Any]] = []
        for item in tickets:
            ticket_id = str(getattr(item, "id", "") or "")
            if not ticket_id or ticket_id == current_ticket_id:
                continue
            haystack = " ".join(
                [
                    ticket_id,
                    str(getattr(item, "title", "") or ""),
                    str(getattr(item, "description", "") or ""),
                    str(getattr(item, "ticket_type", "") or ""),
                    str(getattr(item, "status", "") or ""),
                    str(getattr(item, "assigned_employee_id", "") or ""),
                    str(getattr(item, "validation_employee_id", "") or ""),
                ]
            ).lower()
            score = sum(2 for term in query_terms if term in haystack)
            if employee_id and employee_id in haystack:
                score += 1
            if ticket_id.lower() in message.lower():
                score += 4
            if score <= 0:
                continue
            scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], str(getattr(pair[1], "id", ""))))
        return [self._ticket_context_ref(item, relation="related", confidence=min(0.95, 0.5 + score * 0.08)) for score, item in scored[:5]]

    def _memory_result_ref(self, result: MemorySearchResult, *, memory_id: str, reason: str) -> dict[str, Any]:
        return {
            "memory_id": memory_id,
            "asset_id": memory_id,
            "content": result.content,
            "source": result.source,
            "source_kind": result.source_kind,
            "source_ref": result.source_ref,
            "scope_kind": result.scope_kind,
            "scope_ref": result.scope_ref,
            "memory_type": result.memory_type,
            "employee_ids": result.employee_ids,
            "tags": result.tags,
            "confidence": result.score if result.score is not None else 0.7,
            "provenance": result.provenance,
            "graphiti_episode_id": result.graphiti_episode_id or "",
            "graphiti_recalled": result.source == "graphiti",
            "graphiti_backed": bool(result.graphiti_episode_id),
            "recall_reason": reason,
        }

    def _universal_context(
        self,
        *,
        message: str,
        employee: dict[str, Any],
        employee_profiles: list[dict[str, Any]],
        selected_ai_engine: str,
        ticket: dict[str, Any],
        related_tickets: list[dict[str, Any]],
        prior_evidence: list[dict[str, Any]],
        relevant_assets: list[dict[str, Any]],
        asset_relationship_hints: list[dict[str, Any]],
        recalled_memories: list[dict[str, Any]],
        stale_memory_hints: list[dict[str, Any]],
        recall_trace: list[dict[str, Any]],
        ticket_backend: dict[str, Any],
        setup_blockers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        employee_context = self._employee_context(employee, employee_profiles)
        ticket_context = {
            "current_ticket": self._ticket_dict_ref(ticket, relation="current") if ticket else {},
            "related_tickets": related_tickets,
            "prior_evidence": [self._evidence_ref(item) for item in prior_evidence[:6]],
            "provenance": {
                "source_kind": "ticket_service",
                "source_ref": str(ticket.get("id") or "related_ticket_search") if ticket else "related_ticket_search",
                "scope_kind": "ticket" if ticket else "workspace",
                "scope_ref": str(ticket.get("id") or "aiteamos") if ticket else "aiteamos",
            },
            "source_confidence": 0.9 if ticket else 0.65 if related_tickets else 0.0,
        }
        asset_context = {
            "relevant_assets": [self._asset_ref(item) for item in relevant_assets[:8]],
            "relationship_hints": [self._asset_relationship_hint_ref(item) for item in asset_relationship_hints[:8]],
            "provenance": {
                "source_kind": "ticket_asset_projection",
                "source_ref": str(ticket.get("id") or ""),
                "scope_kind": "ticket" if ticket else "workspace",
                "scope_ref": str(ticket.get("id") or "aiteamos"),
            },
            "source_confidence": 0.85 if relevant_assets else 0.0,
        }
        memory_context = {
            "recalled_memories": [self._memory_context_ref(item) for item in recalled_memories[:8]],
            "stale_memory_hints": [self._stale_memory_hint_ref(item) for item in stale_memory_hints[:8]],
            "recall_trace": recall_trace[:8],
            "provenance": {
                "source_kind": "memory_service",
                "source_ref": "recall_memory_records",
                "scope_kind": "ticket" if ticket else "employee",
                "scope_ref": str(ticket.get("id") or employee.get("id") or ""),
            },
            "source_confidence": max([float(item.get("confidence") or 0) for item in recalled_memories], default=0.0),
        }
        backend_context = {
            "ticket_backend": ticket_backend,
            "selected_ai_engine": selected_ai_engine,
            "setup_blockers": setup_blockers[:6],
            "provenance": {
                "source_kind": "system_status",
                "source_ref": "ticket_backend_status",
                "scope_kind": "workspace",
                "scope_ref": "aiteamos",
            },
            "source_confidence": 1.0 if ticket_backend else 0.0,
        }
        provenance_summary = [
            self._provenance_summary("employee", employee_context.get("selected_employee", {})),
            self._provenance_summary("employee_work_history", employee_context.get("work_history", {})),
            self._provenance_summary("ticket", ticket_context.get("current_ticket", {})),
            *[self._provenance_summary("related_ticket", item) for item in related_tickets[:3]],
            *[self._provenance_summary("asset", item) for item in asset_context["relevant_assets"][:3]],
            *[self._provenance_summary("memory", item) for item in memory_context["recalled_memories"][:3]],
        ]
        provenance_summary = [item for item in provenance_summary if item.get("source_ref")]
        return {
            "version": "universal_context.v1",
            "summary": {
                "task_summary": message[:240],
                "employee_id": str(employee.get("id") or ""),
                "selected_ai_engine": selected_ai_engine,
                "ticket_id": str(ticket.get("id") or ""),
                "related_ticket_count": len(related_tickets),
                "relevant_asset_count": len(relevant_assets),
                "asset_relationship_hint_count": len(asset_relationship_hints),
                "recalled_memory_count": len(recalled_memories),
                "prior_evidence_count": len(prior_evidence),
                "setup_blocker_count": len(setup_blockers),
            },
            "employee_context": employee_context,
            "ticket_context": ticket_context,
            "asset_context": asset_context,
            "memory_context": memory_context,
            "backend_context": backend_context,
            "provenance_summary": provenance_summary[:12],
            "retrieval_audit": self._retrieval_audit(
                employee_context=employee_context,
                ticket_context=ticket_context,
                asset_context=asset_context,
                memory_context=memory_context,
                backend_context=backend_context,
                setup_blockers=setup_blockers,
            ),
        }

    def _relevant_assets_for_ticket(self, ticket_id: str) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        try:
            from .asset_candidate_service import list_asset_records

            for record in list_asset_records(status="approved"):
                payload = record.model_dump(mode="json")
                if self._asset_ticket_id(payload) == ticket_id:
                    assets.append(payload)
        except Exception:
            pass
        try:
            assets.extend(asset.model_dump(mode="json") for asset in ticket_assets_for_ticket(ticket_id))
        except Exception:
            pass
        return self._dedupe_assets(assets)

    def _asset_relationship_hints(self, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {self._asset_id(asset): asset for asset in assets if self._asset_id(asset)}
        hints: list[dict[str, Any]] = []
        for source in assets:
            source_id = self._asset_id(source)
            if not source_id:
                continue
            relationships = source.get("relationships") if isinstance(source.get("relationships"), list) else []
            for relationship in relationships:
                if not isinstance(relationship, dict):
                    continue
                relationship_type = str(relationship.get("type") or relationship.get("relationship_type") or "").strip().lower()
                if relationship_type not in {"supersedes", "conflicts_with"}:
                    continue
                target_id = self._relationship_target_asset_id(relationship)
                target = by_id.get(target_id)
                if not target:
                    continue
                status = "superseded" if relationship_type == "supersedes" else "conflicted"
                reason = str(
                    relationship.get("reason")
                    or relationship.get("detail")
                    or relationship.get("summary")
                    or f"{source_id} {relationship_type} {target_id}"
                )
                hints.append(
                    {
                        "asset_id": target_id,
                        "source_asset_id": source_id,
                        "target_asset_id": target_id,
                        "relationship_type": relationship_type,
                        "status": status,
                        "title": str(target.get("title") or target_id),
                        "content": str(target.get("content") or "")[:600],
                        "exclusion_reason": (
                            f"Approved Asset relationship marks {target_id} as {status}: {reason}"
                        ),
                        "superseded_by_asset_id": source_id if relationship_type == "supersedes" else "",
                        "conflicted_by_asset_id": source_id if relationship_type == "conflicts_with" else "",
                        "relationship": relationship,
                        "provenance": {
                            "source_kind": "asset_relationship",
                            "source_ref": source_id,
                            "scope_kind": "asset",
                            "scope_ref": target_id,
                            "relationship_type": relationship_type,
                            "source_asset_id": source_id,
                            "target_asset_id": target_id,
                        },
                        "source_confidence": float(relationship.get("confidence") or 0.35),
                    }
                )
        return self._dedupe_asset_relationship_hints(hints)

    def _active_assets_from_relationship_hints(
        self,
        assets: list[dict[str, Any]],
        hints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        excluded_ids = {
            str(hint.get("target_asset_id") or hint.get("asset_id") or "").strip()
            for hint in hints
            if str(hint.get("status") or "") in {"superseded", "conflicted"}
        }
        return [asset for asset in assets if self._asset_id(asset) not in excluded_ids]

    def _dedupe_asset_relationship_hints(self, hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for hint in hints:
            key = (
                str(hint.get("source_asset_id") or ""),
                str(hint.get("relationship_type") or ""),
                str(hint.get("target_asset_id") or hint.get("asset_id") or ""),
            )
            if not all(key) or key in seen:
                continue
            seen.add(key)
            deduped.append(hint)
        return deduped

    def _dedupe_assets(self, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for asset in assets:
            asset_id = self._asset_id(asset)
            key = asset_id or str(asset.get("id") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(asset)
        return deduped

    def _employee_context(self, employee: dict[str, Any], employee_profiles: list[dict[str, Any]]) -> dict[str, Any]:
        profile = self._employee_profile(employee, employee_profiles)
        profile_by_id = {
            str(item.get("id") or "").strip().lower(): item
            for item in employee_profiles
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        employee_loads = employee_current_loads(
            list(profile_by_id.keys()),
            base_loads={
                employee_id: item.get("current_load")
                for employee_id, item in profile_by_id.items()
                if isinstance(item.get("current_load"), dict)
            },
        )
        skill_ids = self._string_items(profile.get("skills")) or self._string_items(employee.get("skills"))
        skill_refs = self._string_items(profile.get("skill_refs")) or skill_ids
        skill_titles = self._string_items(employee.get("skill_titles"))
        permissions = self._string_items(profile.get("permissions")) or self._string_items(employee.get("permissions"))
        capability_tags = self._string_items(profile.get("capability_tags")) or skill_refs
        permission_policy = profile.get("permission_policy") if isinstance(profile.get("permission_policy"), dict) else {}
        handoff_policy = profile.get("handoff_policy") if isinstance(profile.get("handoff_policy"), dict) else {}
        selected_employee_id = str(employee.get("id") or profile.get("id") or "")
        current_load = employee_loads.get(selected_employee_id.strip().lower()) or employee_current_load(
            selected_employee_id,
            base_load=profile.get("current_load") if isinstance(profile.get("current_load"), dict) else {},
        )
        work_history = self._employee_work_history_context(selected_employee_id)
        selected = {
            "employee_id": selected_employee_id,
            "display_name": str(employee.get("display_name") or profile.get("display_name") or ""),
            "role": str(employee.get("role") or profile.get("role") or ""),
            "summary": str(employee.get("summary") or profile.get("summary") or ""),
            "skill_ids": skill_ids,
            "skill_refs": skill_refs,
            "skill_titles": skill_titles,
            "permissions": permissions,
            "capability_tags": capability_tags,
            "personality_tags": self._personality_tags(profile),
            "memory_scopes": self._string_items(profile.get("memory_scopes")),
            "preferred_runtime": str(profile.get("preferred_runtime") or ""),
            "permission_policy": {
                "permissions": permissions,
                **permission_policy,
            },
            "handoff_policy": handoff_policy,
            "current_load": current_load,
            "work_history_summary": work_history.get("summary", {}),
            "provenance": {
                "source_kind": "employee_profile",
                "source_ref": str(profile.get("id") or employee.get("id") or ""),
                "scope_kind": "employee",
                "scope_ref": str(profile.get("id") or employee.get("id") or ""),
            },
            "source_confidence": 1.0 if profile else 0.75,
        }
        return {
            "selected_employee": selected,
            "work_history": work_history,
            "available_employee_refs": [
                {
                    "employee_id": str(profile.get("id") or ""),
                    "display_name": str(profile.get("display_name") or profile.get("id") or ""),
                    "role": str(profile.get("role") or ""),
                    "skill_refs": self._string_items(profile.get("skill_refs")) or self._string_items(profile.get("skills")),
                    "capability_tags": self._string_items(profile.get("capability_tags")),
                    "preferred_runtime": str(profile.get("preferred_runtime") or ""),
                    "current_load": employee_loads.get(str(profile.get("id") or "").strip().lower())
                    or employee_current_load(
                        str(profile.get("id") or ""),
                        base_load=profile.get("current_load") if isinstance(profile.get("current_load"), dict) else {},
                    ),
                    "provenance": {
                        "source_kind": "employee_profile",
                        "source_ref": str(profile.get("id") or ""),
                        "scope_kind": "employee",
                        "scope_ref": str(profile.get("id") or ""),
                    },
                    "source_confidence": 0.95,
                }
                for profile in employee_profiles[:12]
                if isinstance(profile, dict) and str(profile.get("id") or "").strip()
            ],
        }

    def _employee_work_history_context(self, employee_id: str) -> dict[str, Any]:
        normalized = employee_id.strip()
        provenance = {
            "source_kind": "employee_work_ledger",
            "source_ref": normalized,
            "scope_kind": "employee",
            "scope_ref": normalized,
        }
        if not normalized:
            return {
                "summary": {"employee_id": "", "source": "employee_work_ledger"},
                "refs": {},
                "blockers": [
                    {
                        "kind": "employee_work_history",
                        "reason": "missing_employee_id",
                        "detail": "Employee work history needs a selected employee id.",
                    }
                ],
                "provenance": provenance,
                "source_confidence": 0.0,
            }
        try:
            ledger = employee_work_ledger(normalized)
        except Exception as exc:
            return {
                "summary": {"employee_id": normalized, "source": "employee_work_ledger"},
                "refs": {},
                "blockers": [
                    {
                        "kind": "employee_work_history",
                        "reason": "employee_work_ledger_failed",
                        "detail": str(exc),
                    }
                ],
                "provenance": provenance,
                "source_confidence": 0.0,
            }

        current_tickets = [self._work_ticket_ref(item, relation="current") for item in ledger.current_tickets[:5]]
        current_ticket_ids = {item["ticket_id"] for item in current_tickets if item.get("ticket_id")}
        historical_tickets = [
            self._work_ticket_ref(item, relation="historical")
            for item in ledger.historical_tickets
            if str(getattr(item, "ticket_id", "") or "") not in current_ticket_ids
        ][:5]
        runtime_runs = [self._runtime_run_ref(item) for item in ledger.runtime_runs[:5]]
        quality_feedback = [self._quality_feedback_ref(item) for item in ledger.quality_feedback[:5]]
        asset_candidates = [self._asset_work_ref(item) for item in ledger.asset_candidates[:5]]
        approved_assets = [self._asset_work_ref(item) for item in ledger.approved_assets[:5]]
        contribution = ledger.contribution if isinstance(ledger.contribution, dict) else {}
        summary = {
            "employee_id": normalized,
            "source": "employee_work_ledger",
            "current_ticket_count": len(ledger.current_tickets),
            "historical_ticket_count": len(ledger.historical_tickets),
            "report_count": len(ledger.reports),
            "validation_count": len(ledger.validations),
            "blocked_count": len(ledger.blocked_records),
            "handoff_count": len(ledger.handoffs),
            "asset_candidate_count": len(ledger.asset_candidates),
            "approved_asset_count": len(ledger.approved_assets),
            "asset_review_count": len(ledger.asset_reviews),
            "runtime_run_count": len(ledger.runtime_runs),
            "quality_feedback_count": len(ledger.quality_feedback),
            "tool_event_count": int(contribution.get("tool_event_count") or 0),
            "recent_runtime_status": runtime_runs[0]["status"] if runtime_runs else "",
            "recent_quality_feedback_status": quality_feedback[0]["status"] if quality_feedback else "",
        }
        has_history = any(
            int(summary.get(key) or 0) > 0
            for key in (
                "current_ticket_count",
                "historical_ticket_count",
                "report_count",
                "handoff_count",
                "asset_candidate_count",
                "approved_asset_count",
                "runtime_run_count",
                "quality_feedback_count",
            )
        )
        return {
            "summary": summary,
            "refs": {
                "current_tickets": current_tickets,
                "historical_tickets": historical_tickets,
                "recent_reports": [self._ticket_report_ref(item) for item in ledger.reports[:5]],
                "blocked_records": [self._ticket_report_ref(item) for item in ledger.blocked_records[:5]],
                "handoffs": [self._handoff_ref(item) for item in ledger.handoffs[:5]],
                "asset_candidates": asset_candidates,
                "approved_assets": approved_assets,
                "asset_reviews": [self._asset_review_ref(item) for item in ledger.asset_reviews[:5]],
                "runtime_runs": runtime_runs,
                "quality_feedback": quality_feedback,
            },
            "blockers": [],
            "provenance": provenance,
            "source_confidence": 0.85 if has_history else 0.45,
        }

    def _work_ticket_ref(self, item: Any, *, relation: str) -> dict[str, Any]:
        return {
            "ticket_id": str(getattr(item, "ticket_id", "") or ""),
            "title": str(getattr(item, "title", "") or ""),
            "status": str(getattr(item, "status", "") or ""),
            "role": str(getattr(item, "role", "") or ""),
            "updated_at": str(getattr(item, "updated_at", "") or ""),
            "next_action": str(getattr(item, "next_action", "") or ""),
            "relation": relation,
        }

    def _ticket_report_ref(self, item: Any) -> dict[str, Any]:
        return {
            "ticket_id": str(getattr(item, "ticket_id", "") or ""),
            "ticket_title": str(getattr(item, "ticket_title", "") or ""),
            "report_id": str(getattr(item, "report_id", "") or ""),
            "report_type": str(getattr(item, "report_type", "") or ""),
            "evidence_refs": [str(ref) for ref in getattr(item, "evidence", []) if str(ref)],
            "created_at": str(getattr(item, "created_at", "") or ""),
        }

    def _handoff_ref(self, item: dict[str, Any]) -> dict[str, Any]:
        event = item.get("event") if isinstance(item.get("event"), dict) else {}
        actor = event.get("actor") if isinstance(event.get("actor"), dict) else {}
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        return {
            "ticket_id": str(item.get("ticket_id") or ""),
            "title": str(item.get("title") or ""),
            "event_type": str(event.get("type") or ""),
            "actor_employee_id": str(actor.get("id") or ""),
            "assigned_employee_id": str(data.get("assigned_employee_id") or ""),
            "assigned_role": str(data.get("assigned_role") or ""),
            "source_run_id": str(data.get("source_run_id") or ""),
            "created_at": str(event.get("created_at") or ""),
        }

    def _asset_work_ref(self, item: Any) -> dict[str, Any]:
        return {
            "asset_id": str(getattr(item, "asset_id", "") or ""),
            "candidate_id": str(getattr(item, "candidate_id", "") or ""),
            "asset_type": str(getattr(item, "asset_type", "") or ""),
            "title": str(getattr(item, "title", "") or ""),
            "status": str(getattr(item, "status", "") or ""),
            "review_state": str(getattr(item, "review_state", "") or ""),
            "scope_kind": str(getattr(item, "scope_kind", "") or ""),
            "scope_ref": str(getattr(item, "scope_ref", "") or ""),
            "source_ticket_id": str(getattr(item, "source_ticket_id", "") or ""),
            "source_run_id": str(getattr(item, "source_run_id", "") or ""),
            "source_ref": str(getattr(item, "source_ref", "") or ""),
            "updated_at": str(getattr(item, "updated_at", "") or ""),
        }

    def _asset_review_ref(self, item: Any) -> dict[str, Any]:
        return {
            "review_id": str(getattr(item, "review_id", "") or ""),
            "candidate_id": str(getattr(item, "candidate_id", "") or ""),
            "asset_id": str(getattr(item, "asset_id", "") or ""),
            "status": str(getattr(item, "status", "") or ""),
            "reviewer_employee_id": str(getattr(item, "reviewer_employee_id", "") or ""),
            "relation_to_employee": str(getattr(item, "relation_to_employee", "") or ""),
            "updated_at": str(getattr(item, "updated_at", "") or ""),
        }

    def _runtime_run_ref(self, item: Any) -> dict[str, Any]:
        return {
            "request_id": str(getattr(item, "request_id", "") or ""),
            "run_id": str(getattr(item, "run_id", "") or ""),
            "session_key": str(getattr(item, "session_key", "") or ""),
            "ticket_id": str(getattr(item, "ticket_id", "") or ""),
            "action": str(getattr(item, "action", "") or ""),
            "executor_id": str(getattr(item, "executor_id", "") or ""),
            "status": str(getattr(item, "status", "") or ""),
            "trace_ref": str(getattr(item, "trace_ref", "") or ""),
            "artifact_count": int(getattr(item, "artifact_count", 0) or 0),
            "evidence_count": int(getattr(item, "evidence_count", 0) or 0),
            "tool_event_count": int(getattr(item, "tool_event_count", 0) or 0),
            "memory_candidate_count": int(getattr(item, "memory_candidate_count", 0) or 0),
            "latency_ms": int(getattr(item, "latency_ms", 0) or 0),
            "total_cost": float(getattr(item, "total_cost", 0.0) or 0.0),
            "started_at": str(getattr(item, "started_at", "") or ""),
            "finished_at": str(getattr(item, "finished_at", "") or ""),
        }

    def _quality_feedback_ref(self, item: Any) -> dict[str, Any]:
        return {
            "id": str(getattr(item, "id", "") or ""),
            "kind": str(getattr(item, "kind", "") or ""),
            "status": str(getattr(item, "status", "") or ""),
            "summary": str(getattr(item, "summary", "") or ""),
            "source_ref": str(getattr(item, "source_ref", "") or ""),
            "reviewer_employee_id": str(getattr(item, "reviewer_employee_id", "") or ""),
            "ticket_id": str(getattr(item, "ticket_id", "") or ""),
            "created_at": str(getattr(item, "created_at", "") or ""),
        }

    def _employee_profile(self, employee: dict[str, Any], employee_profiles: list[dict[str, Any]]) -> dict[str, Any]:
        employee_id = str(employee.get("id") or "").strip().lower()
        for profile in employee_profiles:
            if isinstance(profile, dict) and str(profile.get("id") or "").strip().lower() == employee_id:
                return profile
        return employee

    def _personality_tags(self, profile: dict[str, Any]) -> list[str]:
        explicit = self._string_items(profile.get("personality_tags"))
        if explicit:
            return explicit
        personality = profile.get("personality")
        if isinstance(personality, str):
            return [part.strip() for part in re.split(r"[,;/，；、]|\band\b", personality) if part.strip()]
        return self._string_items(personality)

    def _ticket_context_ref(self, ticket: Any, *, relation: str, confidence: float) -> dict[str, Any]:
        provider_ref = getattr(ticket, "provider_ref", None)
        return {
            "ticket_id": str(getattr(ticket, "id", "") or ""),
            "title": str(getattr(ticket, "title", "") or ""),
            "status": str(getattr(ticket, "status", "") or ""),
            "ticket_type": str(getattr(ticket, "ticket_type", "") or ""),
            "assigned_employee_id": str(getattr(ticket, "assigned_employee_id", "") or ""),
            "validation_employee_id": str(getattr(ticket, "validation_employee_id", "") or ""),
            "relation": relation,
            "provider_ref": provider_ref.model_dump(mode="json") if hasattr(provider_ref, "model_dump") else None,
            "provenance": {
                "source_kind": "ticket",
                "source_ref": str(getattr(ticket, "id", "") or ""),
                "scope_kind": "ticket",
                "scope_ref": str(getattr(ticket, "id", "") or ""),
            },
            "source_confidence": confidence,
        }

    def _ticket_dict_ref(self, ticket: dict[str, Any], *, relation: str) -> dict[str, Any]:
        return {
            "ticket_id": str(ticket.get("id") or ""),
            "title": str(ticket.get("title") or ""),
            "status": str(ticket.get("status") or ""),
            "ticket_type": str(ticket.get("ticket_type") or ""),
            "assigned_employee_id": str(ticket.get("assigned_employee_id") or ""),
            "validation_employee_id": str(ticket.get("validation_employee_id") or ""),
            "relation": relation,
            "provider_ref": ticket.get("provider_ref") if isinstance(ticket.get("provider_ref"), dict) else None,
            "provenance": {
                "source_kind": "ticket",
                "source_ref": str(ticket.get("id") or ""),
                "scope_kind": "ticket",
                "scope_ref": str(ticket.get("id") or ""),
            },
            "source_confidence": 1.0,
        }

    def _asset_ref(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        asset_id = self._asset_id(item)
        source_ticket_id = self._asset_ticket_id(item)
        source_employee_id = str(
            item.get("source_employee_id")
            or item.get("owner_employee_id")
            or provenance.get("source_employee_id")
            or metadata.get("source_employee_id")
            or ""
        ).strip()
        return {
            "asset_id": asset_id,
            "asset_type": str(item.get("kind") or item.get("asset_type") or ""),
            "title": str(item.get("title") or asset_id),
            "status": str(item.get("status") or ""),
            "source_ticket_id": source_ticket_id,
            "source_employee_id": source_employee_id,
            "assigned_employees": self._string_items(item.get("assigned_employees")),
            "scopes": self._string_items(item.get("scopes")),
            "provenance": {
                **provenance,
                "source_kind": str(provenance.get("source_kind") or item.get("source_kind") or "ticket_asset_record"),
                "source_ref": asset_id,
                "scope_kind": "ticket" if source_ticket_id else "asset",
                "scope_ref": source_ticket_id or asset_id,
            },
            "source_confidence": 0.85,
        }

    def _asset_id(self, item: dict[str, Any]) -> str:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        return str(item.get("asset_id") or metadata.get("asset_id") or item.get("id") or "").strip()

    def _asset_ticket_id(self, item: dict[str, Any]) -> str:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        if str(item.get("source_ticket_id") or "").strip():
            return str(item.get("source_ticket_id") or "").strip()
        if str(provenance.get("source_ticket_id") or "").strip():
            return str(provenance.get("source_ticket_id") or "").strip()
        if str(metadata.get("source_ticket_id") or "").strip():
            return str(metadata.get("source_ticket_id") or "").strip()
        if str(item.get("scope_kind") or "").strip() == "ticket":
            return str(item.get("scope_ref") or "").strip()
        return str(metadata.get("derived_from_ticket_id") or "").strip()

    def _relationship_target_asset_id(self, relationship: dict[str, Any]) -> str:
        direct = str(relationship.get("target_asset_id") or "").strip()
        if direct:
            return direct
        target_kind = str(relationship.get("target_kind") or relationship.get("target_type") or "").strip().lower()
        if target_kind == "asset":
            return str(relationship.get("target_ref") or relationship.get("target") or "").strip()
        return ""

    def _memory_context_ref(self, item: dict[str, Any]) -> dict[str, Any]:
        memory_id = str(item.get("memory_id") or item.get("asset_id") or "").strip()
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        return {
            "memory_id": memory_id,
            "asset_id": str(item.get("asset_id") or memory_id),
            "content": str(item.get("content") or "")[:600],
            "source": str(item.get("source") or ""),
            "memory_type": str(item.get("memory_type") or ""),
            "tags": self._string_items(item.get("tags")),
            "graphiti_episode_id": str(item.get("graphiti_episode_id") or ""),
            "graphiti_recalled": bool(item.get("graphiti_recalled")),
            "recall_reason": str(item.get("recall_reason") or ""),
            "provenance": {
                **provenance,
                "source_kind": str(provenance.get("source_kind") or item.get("source_kind") or "memory"),
                "source_ref": str(provenance.get("source_ref") or item.get("source_ref") or memory_id),
                "scope_kind": str(provenance.get("scope_kind") or item.get("scope_kind") or "memory"),
                "scope_ref": str(provenance.get("scope_ref") or item.get("scope_ref") or memory_id),
            },
            "source_confidence": float(item.get("confidence") or 0.7),
        }

    def _stale_memory_hint_ref(self, item: dict[str, Any]) -> dict[str, Any]:
        memory_id = str(item.get("memory_id") or item.get("asset_id") or "").strip()
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        return {
            "memory_id": memory_id,
            "asset_id": str(item.get("asset_id") or memory_id),
            "content": str(item.get("content") or "")[:600],
            "status": str(item.get("status") or ""),
            "tags": self._string_items(item.get("tags")),
            "exclusion_reason": str(item.get("exclusion_reason") or ""),
            "superseded_by_candidate_id": str(item.get("superseded_by_candidate_id") or ""),
            "source": str(item.get("source") or ""),
            "graphiti_episode_id": str(item.get("graphiti_episode_id") or ""),
            "graphiti_result_id": str(item.get("graphiti_result_id") or ""),
            "graphiti_backed": bool(item.get("graphiti_backed") or item.get("graphiti_episode_id")),
            "provenance": {
                **provenance,
                "source_kind": str(provenance.get("source_kind") or item.get("source_kind") or "memory"),
                "source_ref": str(provenance.get("source_ref") or item.get("source_ref") or memory_id),
                "scope_kind": str(provenance.get("scope_kind") or item.get("scope_kind") or "memory"),
                "scope_ref": str(provenance.get("scope_ref") or item.get("scope_ref") or memory_id),
            },
            "source_confidence": float(item.get("source_confidence") or 0.2),
        }

    def _asset_relationship_hint_ref(self, item: dict[str, Any]) -> dict[str, Any]:
        asset_id = str(item.get("asset_id") or item.get("target_asset_id") or "").strip()
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        return {
            "asset_id": asset_id,
            "target_asset_id": str(item.get("target_asset_id") or asset_id),
            "source_asset_id": str(item.get("source_asset_id") or ""),
            "relationship_type": str(item.get("relationship_type") or ""),
            "status": str(item.get("status") or ""),
            "title": str(item.get("title") or asset_id),
            "content": str(item.get("content") or "")[:600],
            "exclusion_reason": str(item.get("exclusion_reason") or ""),
            "superseded_by_asset_id": str(item.get("superseded_by_asset_id") or ""),
            "conflicted_by_asset_id": str(item.get("conflicted_by_asset_id") or ""),
            "provenance": {
                **provenance,
                "source_kind": str(provenance.get("source_kind") or "asset_relationship"),
                "source_ref": str(provenance.get("source_ref") or item.get("source_asset_id") or ""),
                "scope_kind": str(provenance.get("scope_kind") or "asset"),
                "scope_ref": str(provenance.get("scope_ref") or asset_id),
            },
            "source_confidence": float(item.get("source_confidence") or 0.35),
        }

    def _evidence_ref(self, item: dict[str, Any]) -> dict[str, Any]:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        ticket_id = str(item.get("ticket_id") or "")
        report_id = str(item.get("report_id") or "")
        return {
            "ticket_id": ticket_id,
            "report_id": report_id,
            "report_type": str(item.get("report_type") or ""),
            "evidence_refs": [str(ref) for ref in evidence if str(ref).strip()][:8],
            "provenance": {
                "source_kind": "ticket_report_evidence",
                "source_ref": report_id,
                "scope_kind": "ticket",
                "scope_ref": ticket_id,
            },
            "source_confidence": 0.9 if evidence else 0.0,
        }

    def _provenance_summary(self, kind: str, item: dict[str, Any]) -> dict[str, Any]:
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        return {
            "kind": kind,
            "source_kind": str(provenance.get("source_kind") or ""),
            "source_ref": str(provenance.get("source_ref") or ""),
            "scope_kind": str(provenance.get("scope_kind") or ""),
            "scope_ref": str(provenance.get("scope_ref") or ""),
            "source_confidence": item.get("source_confidence", 0),
        }

    def _string_items(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _recall_trace_entry(
        self,
        message: str,
        ticket_keys: list[str],
        employee: dict[str, Any],
        ref: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "query": message[:240],
            "scope": ticket_keys[:1] or [employee.get("id", "")],
            "source_asset": ref.get("memory_id") or ref.get("asset_id") or "",
            "reason": ref.get("recall_reason") or "approved Memory matched scoped task context",
            "confidence": ref.get("confidence", 0),
            "graphiti_recalled": bool(ref.get("graphiti_recalled")),
            "graphiti_backed": bool(ref.get("graphiti_backed") or ref.get("graphiti_episode_id")),
            "graphiti_episode_id": ref.get("graphiti_episode_id") or "",
        }

    def _retrieval_audit(
        self,
        *,
        employee_context: dict[str, Any],
        ticket_context: dict[str, Any],
        asset_context: dict[str, Any],
        memory_context: dict[str, Any],
        backend_context: dict[str, Any],
        setup_blockers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        selected: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []

        selected_employee = employee_context.get("selected_employee")
        if isinstance(selected_employee, dict):
            selected.append(self._audit_ref("employee", selected_employee, "selected Employee identity"))
        work_history = employee_context.get("work_history")
        if isinstance(work_history, dict) and work_history.get("source_confidence"):
            selected.append(self._audit_ref("employee_work_history", work_history, "Employee Ticket/runtime work ledger"))
        else:
            excluded.append(self._audit_exclusion("employee_work_history", "employee_work_ledger", "no Employee work ledger context"))

        current_ticket = ticket_context.get("current_ticket")
        if isinstance(current_ticket, dict) and current_ticket:
            selected.append(self._audit_ref("ticket", current_ticket, "current Ticket binding"))
        else:
            excluded.append(self._audit_exclusion("ticket", "current_ticket", "no current Ticket binding"))

        related_tickets = ticket_context.get("related_tickets") if isinstance(ticket_context.get("related_tickets"), list) else []
        selected.extend(self._audit_ref("related_ticket", item, "related Ticket query match") for item in related_tickets if isinstance(item, dict))
        if not related_tickets:
            excluded.append(self._audit_exclusion("related_ticket", "related_ticket_search", "no related Ticket scored above zero"))

        assets = asset_context.get("relevant_assets") if isinstance(asset_context.get("relevant_assets"), list) else []
        selected.extend(self._audit_ref("asset", item, "Ticket-scoped approved Asset") for item in assets if isinstance(item, dict))
        if not assets:
            excluded.append(self._audit_exclusion("asset", "ticket_asset_projection", "no Ticket-scoped approved Asset"))
        relationship_hints = asset_context.get("relationship_hints") if isinstance(asset_context.get("relationship_hints"), list) else []
        for item in relationship_hints:
            if isinstance(item, dict):
                excluded.append(
                    self._audit_exclusion(
                        "asset",
                        str(item.get("asset_id") or item.get("target_asset_id") or ""),
                        str(item.get("exclusion_reason") or "Asset relationship excluded this Asset from active context"),
                    )
                )

        memories = memory_context.get("recalled_memories") if isinstance(memory_context.get("recalled_memories"), list) else []
        selected.extend(self._audit_ref("memory", item, str(item.get("recall_reason") or "approved Memory recall")) for item in memories if isinstance(item, dict))
        if not memories:
            excluded.append(self._audit_exclusion("memory", "recall_memory_records", "no approved Memory matched query and scope"))
        stale_memory_hints = memory_context.get("stale_memory_hints") if isinstance(memory_context.get("stale_memory_hints"), list) else []
        for item in stale_memory_hints:
            if isinstance(item, dict):
                excluded.append(
                    self._audit_exclusion(
                        "memory",
                        str(item.get("memory_id") or item.get("asset_id") or ""),
                        str(item.get("exclusion_reason") or "stale or superseded Memory was excluded from active recall"),
                    )
                )

        for blocker in setup_blockers[:6]:
            if isinstance(blocker, dict):
                excluded.append(
                    self._audit_exclusion(
                        str(blocker.get("kind") or "provider"),
                        str(blocker.get("provider") or blocker.get("reason") or "provider_blocker"),
                        str(blocker.get("detail") or blocker.get("reason") or "provider blocker"),
                    )
                )

        ticket_backend = backend_context.get("ticket_backend") if isinstance(backend_context.get("ticket_backend"), dict) else {}
        return {
            "schema": "context_retrieval_audit.v1",
            "selected": selected[:20],
            "excluded": excluded[:20],
            "selected_count": len(selected),
            "excluded_count": len(excluded),
            "provider_blocker_count": len(setup_blockers),
            "backend_ticket_status": str(ticket_backend.get("status") or ""),
        }

    def _audit_ref(self, kind: str, item: dict[str, Any], reason: str) -> dict[str, Any]:
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        source_ref = str(
            item.get("ticket_id")
            or item.get("asset_id")
            or item.get("memory_id")
            or item.get("employee_id")
            or provenance.get("source_ref")
            or ""
        ).strip()
        return {
            "kind": kind,
            "source_ref": source_ref,
            "score": float(item.get("source_confidence") or item.get("confidence") or 0),
            "reason": reason,
            "provenance": provenance,
        }

    def _audit_exclusion(self, kind: str, source_ref: str, reason: str) -> dict[str, Any]:
        return {
            "kind": kind,
            "source_ref": source_ref,
            "score": 0.0,
            "exclusion_reason": reason,
        }
