"""Deterministic Employee handoff selection for the universal agent."""

from __future__ import annotations

import re
from typing import Any


def choose_employee_for_goal(
    goal: str,
    employee_profiles: list[dict[str, Any]] | None,
    *,
    current_employee_id: str = "",
    required_memory_scopes: list[str] | None = None,
    risk_level: str = "",
) -> dict[str, Any]:
    lane, reason = _goal_lane(goal)
    context = _handoff_context(goal, lane, required_memory_scopes=required_memory_scopes, risk_level=risk_level)
    profiles = [profile for profile in employee_profiles or [] if isinstance(profile, dict)]
    profile_by_id = {_text(profile.get("id")).lower(): profile for profile in profiles if _text(profile.get("id"))}
    scored = sorted(
        [
            (
                _score_profile(profile, lane, current_employee_id=current_employee_id, context=context),
                _text(profile.get("id")),
                profile,
            )
            for profile in profiles
        ],
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    if scored and scored[0][0] > 0:
        score, _, profile = scored[0]
        employee_id = _text(profile.get("id"))
        return {
            "should_handoff": bool(employee_id and employee_id != current_employee_id),
            "target_employee_id": employee_id,
            "target_role": _text(profile.get("role")),
            "display_name": _text(profile.get("display_name")) or employee_id,
            "lane": lane,
            "reason": _decision_reason(reason, profile, lane, context),
            "confidence": min(0.95, 0.55 + score / 10),
            "policy": _decision_policy(profile, score, lane, context),
        }
    fallback = _fallback_for_lane(lane)
    fallback_profile = profile_by_id.get(fallback["target_employee_id"].lower())
    if fallback_profile is not None and not _policy_allows(fallback_profile, lane, context):
        return {
            "should_handoff": False,
            "target_employee_id": "",
            "target_role": "",
            "display_name": "",
            "lane": lane,
            "reason": f"{reason} No eligible Employee accepts this lane under current handoff policy.",
            "confidence": 0.4,
            "policy": {
                "policy_aware": True,
                "blocked_fallback": fallback["target_employee_id"],
                **_context_policy_summary(fallback_profile, context),
            },
        }
    return {
        "should_handoff": bool(fallback["target_employee_id"] and fallback["target_employee_id"] != current_employee_id),
        **fallback,
        "lane": lane,
        "reason": reason,
        "confidence": 0.55,
    }


def _goal_lane(goal: str) -> tuple[str, str]:
    normalized = goal.lower()
    if re.search(r"\b(validate|validation|verify|review|qa|pv|test evidence)\b|验证|复核|测试证据", normalized):
        return "pv", "Goal asks for validation, review, or test evidence."
    if re.search(r"\b(memory|asset|graphiti|docs?|knowledge|recall)\b|记忆|资产|知识库|文档", normalized):
        return "memory_curator", "Goal asks for memory, assets, docs, or knowledge recall."
    if re.search(r"\b(pm|product|plan|roadmap|priority|spec)\b|产品|规划|路线图|需求", normalized):
        return "pm", "Goal asks for product planning or prioritization."
    if re.search(r"\b(implement|code|bug|fix|runtime|backend|frontend|api|test)\b|实现|修复|代码|后端|前端", normalized):
        return "rd", "Goal asks for implementation or engineering work."
    return "pm", "Goal needs coordination before execution."


def _score_profile(profile: dict[str, Any], lane: str, *, current_employee_id: str, context: dict[str, Any]) -> int:
    employee_id = _text(profile.get("id"))
    if not employee_id or employee_id == current_employee_id:
        return -1
    if not _policy_allows(profile, lane, context):
        return -1
    haystack = " ".join(
        [
            employee_id,
            _text(profile.get("display_name")),
            _text(profile.get("role")),
            _text(profile.get("summary")),
            " ".join(_string_items(profile.get("skills"))),
            " ".join(_string_items(profile.get("skill_refs"))),
            " ".join(_string_items(profile.get("capability_tags"))),
            " ".join(_string_items(profile.get("responsibilities"))),
        ]
    ).lower()
    lane_terms = {
        "rd": ("rd", "implement", "engineer", "backend", "frontend", "code", "runtime"),
        "pv": ("pv", "validation", "verify", "qa", "test", "review"),
        "pm": ("pm", "product", "manager", "planning", "roadmap", "spec"),
        "memory_curator": ("memory", "asset", "docs", "knowledge", "graphiti", "curator"),
    }[lane]
    score = sum(2 if term in haystack else 0 for term in lane_terms)
    policy = profile.get("handoff_policy") if isinstance(profile.get("handoff_policy"), dict) else {}
    if lane in _string_items(policy.get("preferred_lanes")):
        score += 4
    if lane in _string_items(policy.get("accepts_lanes")):
        score += 2
    permission_policy = profile.get("permission_policy") if isinstance(profile.get("permission_policy"), dict) else {}
    permission_text = " ".join(_string_items(permission_policy.get("permissions"))).lower()
    if lane == "rd" and any(term in permission_text for term in ("repo", "code", "terminal", "write")):
        score += 2
    if lane == "pv" and any(term in permission_text for term in ("validation", "evidence", "review")):
        score += 2
    scope_match = _memory_scope_match(profile, context)
    if scope_match["matched"]:
        score += min(4, len(scope_match["matched_scopes"]) * 2)
    if lane == "memory_curator" and any(scope in {"global", "aiteamos"} for scope in _profile_memory_scopes(profile)):
        score += 2
    score += _work_history_score(profile, lane, employee_id=employee_id)
    return score - _load_penalty(profile)


def _policy_allows(profile: dict[str, Any], lane: str, context: dict[str, Any]) -> bool:
    policy = profile.get("handoff_policy") if isinstance(profile.get("handoff_policy"), dict) else {}
    if policy.get("can_receive_handoffs") is False:
        return False
    accepted = _string_items(policy.get("accepts_lanes"))
    if accepted and lane not in accepted:
        return False
    blocked = _string_items(policy.get("blocked_lanes")) or _string_items(policy.get("deny_lanes"))
    if lane in blocked:
        return False
    max_active = _safe_int(policy.get("max_active_tickets") or policy.get("max_current_tickets"))
    current_load = profile.get("current_load") if isinstance(profile.get("current_load"), dict) else {}
    if max_active and _safe_int(current_load.get("active_ticket_count")) >= max_active:
        return False
    scope_match = _memory_scope_match(profile, context)
    if not scope_match["allowed"]:
        return False
    risk_match = _risk_boundary_match(profile, context)
    if not risk_match["allowed"]:
        return False
    return True


def _load_penalty(profile: dict[str, Any]) -> int:
    current_load = profile.get("current_load") if isinstance(profile.get("current_load"), dict) else {}
    status = _text(current_load.get("status")).lower()
    penalty = min(4, _safe_int(current_load.get("active_ticket_count")))
    if status == "needs_attention":
        penalty += 6
    elif status == "busy":
        penalty += 3
    elif status == "running":
        penalty += 2
    elif status == "active":
        penalty += 1
    return penalty


def _decision_reason(base_reason: str, profile: dict[str, Any], lane: str, context: dict[str, Any]) -> str:
    current_load = profile.get("current_load") if isinstance(profile.get("current_load"), dict) else {}
    load_status = _text(current_load.get("status"))
    work_history_score = _work_history_score(profile, lane, employee_id=_text(profile.get("id")))
    policy_summary = _context_policy_summary(profile, context)
    if load_status:
        suffix = f"Selected under handoff_policy with current_load={load_status}."
    else:
        suffix = "Selected under handoff_policy."
    if policy_summary.get("memory_scope_match") == "matched":
        suffix = f"{suffix} memory_scope matched."
    if policy_summary.get("risk_allowed") is True and policy_summary.get("risk_level"):
        suffix = f"{suffix} risk_boundary={policy_summary.get('max_risk_level') or 'unbounded'}."
    if work_history_score > 0:
        return f"{base_reason} {suffix} work_history matched this lane."
    return f"{base_reason} {suffix}"


def _decision_policy(profile: dict[str, Any], score: int, lane: str, context: dict[str, Any]) -> dict[str, Any]:
    current_load = profile.get("current_load") if isinstance(profile.get("current_load"), dict) else {}
    employee_id = _text(profile.get("id"))
    work_history = _work_history_summary(profile, employee_id)
    return {
        "policy_aware": True,
        "score": score,
        "active_ticket_count": _safe_int(current_load.get("active_ticket_count")),
        "load_status": _text(current_load.get("status")),
        "work_history_score": _work_history_score(profile, lane, employee_id=employee_id),
        "work_history_summary": {
            "source": _text(work_history.get("source")),
            "current_ticket_count": _safe_int(work_history.get("current_ticket_count")),
            "historical_ticket_count": _safe_int(work_history.get("historical_ticket_count")),
            "report_count": _safe_int(work_history.get("report_count")),
            "validation_count": _safe_int(work_history.get("validation_count")),
            "blocked_count": _safe_int(work_history.get("blocked_count")),
            "asset_candidate_count": _safe_int(work_history.get("asset_candidate_count")),
            "approved_asset_count": _safe_int(work_history.get("approved_asset_count")),
            "asset_review_count": _safe_int(work_history.get("asset_review_count")),
            "runtime_run_count": _safe_int(work_history.get("runtime_run_count")),
            "quality_feedback_count": _safe_int(work_history.get("quality_feedback_count")),
            "recent_runtime_status": _text(work_history.get("recent_runtime_status")),
        },
        **_context_policy_summary(profile, context),
    }


def _work_history_score(profile: dict[str, Any], lane: str, *, employee_id: str) -> int:
    summary = _work_history_summary(profile, employee_id)
    if not summary:
        return 0
    if lane == "rd":
        score = min(
            5,
            _safe_int(summary.get("runtime_run_count"))
            + _safe_int(summary.get("approved_asset_count"))
            + min(2, _safe_int(summary.get("report_count"))),
        )
        if _text(summary.get("recent_runtime_status")).lower() in {"blocked", "failed"}:
            score -= 2
        score -= min(2, _safe_int(summary.get("blocked_count")))
        return score
    if lane == "pv":
        return min(5, (_safe_int(summary.get("validation_count")) * 2) + _safe_int(summary.get("asset_review_count")))
    if lane == "memory_curator":
        return min(
            5,
            _safe_int(summary.get("asset_candidate_count"))
            + _safe_int(summary.get("approved_asset_count"))
            + _safe_int(summary.get("asset_review_count")),
        )
    return min(3, _safe_int(summary.get("historical_ticket_count")) + min(1, _safe_int(summary.get("report_count"))))


def _work_history_summary(profile: dict[str, Any], employee_id: str) -> dict[str, Any]:
    explicit = profile.get("work_history_summary")
    if isinstance(explicit, dict):
        return explicit
    work_history = profile.get("work_history") if isinstance(profile.get("work_history"), dict) else {}
    nested = work_history.get("summary") if isinstance(work_history.get("summary"), dict) else {}
    if nested:
        return nested
    if not employee_id:
        return {}
    try:
        from .ticket_service import employee_work_ledger

        ledger = employee_work_ledger(employee_id)
    except Exception:
        return {}
    return {
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
        "recent_runtime_status": ledger.runtime_runs[0].status if ledger.runtime_runs else "",
    }


def _handoff_context(
    goal: str,
    lane: str,
    *,
    required_memory_scopes: list[str] | None,
    risk_level: str,
) -> dict[str, Any]:
    scopes = _normalize_memory_scopes(required_memory_scopes)
    scopes.extend(scope for scope in _memory_scopes_from_goal(goal, lane) if scope not in scopes)
    risk = _normalize_risk_level(risk_level) or _risk_level_from_goal(goal)
    return {
        "required_memory_scopes": scopes,
        "risk_level": risk,
    }


def _memory_scopes_from_goal(goal: str, lane: str) -> list[str]:
    normalized = goal.lower()
    scopes: list[str] = []
    if re.search(r"\bglobal\b|全局|组织", normalized):
        scopes.append("global")
    if re.search(r"\baiteamos\b|team os|团队系统", normalized):
        scopes.append("aiteamos")
    for match in re.finditer(r"\bemployee[:/\s-]+([a-z0-9_-]+)\b", normalized):
        scopes.append(f"employee:{match.group(1)}")
    if lane == "memory_curator" and not scopes:
        scopes.append("aiteamos")
    return _normalize_memory_scopes(scopes)


def _risk_level_from_goal(goal: str) -> str:
    normalized = goal.lower()
    if re.search(r"\b(production|prod|delete|destructive|credential|secret|billing|payment)\b|生产|删除|密钥|账单", normalized):
        return "critical"
    if re.search(r"\b(deploy|release|migration|write|external|permission|security)\b|部署|发布|迁移|外部|权限|安全", normalized):
        return "high"
    if re.search(r"\b(update|modify|change|approve|review)\b|修改|审批|复核", normalized):
        return "medium"
    return "low"


def _memory_scope_match(profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    required = _normalize_memory_scopes(context.get("required_memory_scopes"))
    available = _profile_memory_scopes(profile)
    if not required:
        return {"allowed": True, "matched": False, "required_scopes": [], "matched_scopes": [], "available_scopes": available}
    if not available:
        return {"allowed": True, "matched": False, "required_scopes": required, "matched_scopes": [], "available_scopes": []}
    matched = [scope for scope in required if _scope_allowed(scope, available)]
    return {
        "allowed": len(matched) == len(required),
        "matched": bool(matched),
        "required_scopes": required,
        "matched_scopes": matched,
        "available_scopes": available,
    }


def _risk_boundary_match(profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    risk = _normalize_risk_level(context.get("risk_level")) or "low"
    policy = profile.get("handoff_policy") if isinstance(profile.get("handoff_policy"), dict) else {}
    max_risk = _normalize_risk_level(
        policy.get("max_risk_level") or policy.get("risk_boundary") or policy.get("max_risk")
    )
    if not max_risk:
        return {"allowed": True, "risk_level": risk, "max_risk_level": ""}
    return {
        "allowed": _risk_rank(risk) <= _risk_rank(max_risk),
        "risk_level": risk,
        "max_risk_level": max_risk,
    }


def _context_policy_summary(profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    scope_match = _memory_scope_match(profile, context)
    risk_match = _risk_boundary_match(profile, context)
    return {
        "required_memory_scopes": scope_match["required_scopes"],
        "matched_memory_scopes": scope_match["matched_scopes"],
        "available_memory_scopes": scope_match["available_scopes"],
        "memory_scope_match": "matched"
        if scope_match["required_scopes"] and scope_match["allowed"]
        else "missing"
        if scope_match["required_scopes"]
        else "not_required",
        "risk_level": risk_match["risk_level"],
        "max_risk_level": risk_match["max_risk_level"],
        "risk_allowed": risk_match["allowed"],
    }


def _profile_memory_scopes(profile: dict[str, Any]) -> list[str]:
    scopes = _normalize_memory_scopes(profile.get("memory_scopes"))
    policy = profile.get("handoff_policy") if isinstance(profile.get("handoff_policy"), dict) else {}
    scopes.extend(scope for scope in _normalize_memory_scopes(policy.get("memory_scopes")) if scope not in scopes)
    return scopes


def _normalize_memory_scopes(value: Any) -> list[str]:
    return [scope.lower() for scope in _string_items(value)]


def _scope_allowed(required_scope: str, available_scopes: list[str]) -> bool:
    if required_scope in available_scopes:
        return True
    if "global" in available_scopes:
        return True
    if required_scope.startswith("employee:") and "employee:*" in available_scopes:
        return True
    return False


def _normalize_risk_level(value: Any) -> str:
    normalized = _text(value).lower().replace("-", "_")
    aliases = {
        "none": "low",
        "safe": "low",
        "normal": "medium",
        "prod": "critical",
        "production": "critical",
    }
    return aliases.get(normalized, normalized) if normalized in {"low", "medium", "high", "critical", *aliases} else ""


def _risk_rank(value: str) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(_normalize_risk_level(value), 1)


def _fallback_for_lane(lane: str) -> dict[str, str]:
    if lane == "rd":
        return {"target_employee_id": "alex", "target_role": "AI RD / Implementer", "display_name": "Alex"}
    if lane == "pv":
        return {"target_employee_id": "peter", "target_role": "AI PV", "display_name": "Peter"}
    if lane == "memory_curator":
        return {"target_employee_id": "clara", "target_role": "AI Team OS Manager", "display_name": "Clara"}
    return {"target_employee_id": "clara", "target_role": "AI Team OS Manager", "display_name": "Clara"}


def _string_items(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else str(value).strip() if value is not None else ""
