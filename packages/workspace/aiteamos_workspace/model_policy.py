from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import os

from aiteamos_schema import BudgetPolicy, ModelProfile, Run

from .loader import WorkspaceIndex, load_workspace
from .model_pricing import estimate_profile_call_cost_usd
from .permissions import env_var_action, explain_effective_permissions


def estimate_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


def resolve_run_model_profile(index: WorkspaceIndex, run: Run) -> tuple[str | None, str | None]:
    if run.spec.modelProfile:
        return run.spec.modelProfile, "run"

    member = index.members.get(run.spec.member)
    profile = _execution_profile(index, run.spec.member, member.spec.kind if member else None)
    if profile is not None and getattr(profile.spec, "defaultModelProfile", None):
        return profile.spec.defaultModelProfile, "execution-profile"

    for profile_id, model_profile in sorted(index.model_profiles.items()):
        if run.spec.assignment and run.spec.assignment in model_profile.spec.defaultForAssignments:
            return profile_id, "assignment-default"
        if run.spec.member in model_profile.spec.defaultForMembers:
            return profile_id, "member-default"
    return None, None


def evaluate_model_policy(
    workspace_or_index: str | Path | WorkspaceIndex,
    run_id: str,
    *,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
    fallback_attempt: bool = False,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    run = index.runs[run_id]
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    def check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
        if status == "fail":
            blockers.append(message)
        elif status == "warn":
            warnings.append(message)

    profile_id, profile_source = resolve_run_model_profile(index, run)
    profile = _workspace_model_profile(index, profile_id, check)
    policy = _select_budget_policy(index, run_id)
    usage = _collect_usage(index, run_id)
    estimates: dict[str, Any] = {
        "inputTokens": max(0, int(estimated_input_tokens or 0)),
        "outputTokens": max(0, int(estimated_output_tokens or 0)),
    }
    estimates["costUsd"] = estimate_profile_call_cost_usd(
        profile,
        input_tokens=estimates["inputTokens"],
        output_tokens=estimates["outputTokens"],
    )

    if profile is not None:
        _check_provider_secret(profile, check)
        _check_provider_secret_permission(index, run, profile, check)
        if _is_local_manual(profile):
            check("budget-policy", "pass", "Local/manual model profile does not require provider budget enforcement.")
        elif policy is None:
            check("budget-policy", "fail", "No BudgetPolicy applies to this managed provider run.")
        else:
            check("budget-policy", "pass", f"BudgetPolicy {policy.object_id} applies to this run.")
            _check_cost_estimate(policy, estimates["costUsd"], check)
            _check_budget_limits(policy, usage, estimates, index, run_id, check)
            _check_fallback_policy(policy, usage, fallback_attempt, check)

    return {
        "run": run_id,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "ready": not blockers,
        "status": "READY" if not blockers else "BLOCKED",
        "summary": "Model policy allows execution." if not blockers else f"Model policy blocked execution: {blockers[0]}",
        "profile": profile.object_id if profile else profile_id,
        "profileSource": profile_source if profile else None,
        "policy": policy.object_id if policy else None,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "usage": usage,
        "estimates": estimates,
        "fallbackAttempt": fallback_attempt,
    }


def enforce_model_policy(
    workspace_or_index: str | Path | WorkspaceIndex,
    run_id: str,
    *,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
    fallback_attempt: bool = False,
) -> tuple[ModelProfile, dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    decision = evaluate_model_policy(
        index,
        run_id,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        fallback_attempt=fallback_attempt,
    )
    if not decision["ready"]:
        raise ValueError(decision["summary"])
    profile_id = decision["profile"]
    if not profile_id or profile_id not in index.model_profiles:
        raise ValueError("Model policy did not resolve a workspace model profile.")
    return index.model_profiles[profile_id], decision


def model_policy_event(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy": decision.get("policy"),
        "profile": decision.get("profile"),
        "checks": decision.get("checks", []),
        "blockers": decision.get("blockers", []),
        "usage": decision.get("usage", {}),
        "estimates": decision.get("estimates", {}),
        "fallbackAttempt": decision.get("fallbackAttempt", False),
    }


def _workspace_model_profile(index: WorkspaceIndex, profile_id: str | None, check: Any) -> ModelProfile | None:
    if not profile_id:
        check("model-source", "fail", "Run has no model profile selected or resolvable from member/assignment defaults.")
        return None
    if profile_id not in index.model_profiles:
        check("model-source", "fail", f"Model profile {profile_id} must be defined in .aiteamos/model_profiles before execution.")
        return None
    profile = index.model_profiles[profile_id]
    check("model-source", "pass", f"Model profile {profile_id} is defined in workspace manifests.")
    return profile


def _check_provider_secret(profile: ModelProfile, check: Any) -> None:
    if _is_local_manual(profile):
        check("provider-secret", "pass", "Local/manual profile does not require a provider secret.")
        return
    secret_env = _provider_secret_env(profile)
    if not secret_env:
        check("provider-secret", "pass", "Model profile does not declare a provider secret requirement.")
        return
    if os.environ.get(secret_env):
        check("provider-secret", "pass", f"Required provider secret env {secret_env} is present.")
    else:
        check("provider-secret", "fail", f"Required provider secret env {secret_env} is missing.")


def _check_provider_secret_permission(index: WorkspaceIndex, run: Run, profile: ModelProfile, check: Any) -> None:
    if _is_local_manual(profile):
        check("provider-secret-permission", "pass", "Local/manual profile does not require provider secret permission.")
        return
    secret_env = _provider_secret_env(profile)
    if not secret_env:
        check("provider-secret-permission", "pass", "No provider secret env is declared for permission evaluation.")
        return
    decision = explain_effective_permissions(
        index,
        member=run.spec.member,
        project=run.spec.project,
        assignment=run.spec.assignment,
        action=env_var_action(secret_env, "use"),
        non_interactive=True,
    )
    canonical = decision["normalizedAction"]["canonical"]
    if decision["decision"] == "allow" and not decision["blockers"]:
        check("provider-secret-permission", "pass", f"Provider secret use is allowed by effective permissions: {canonical}.")
    else:
        check("provider-secret-permission", "fail", f"Provider secret use denied by effective permissions: {canonical} ({decision['reason']}).")


def _provider_secret_env(profile: ModelProfile) -> str | None:
    secret_env = profile.spec.secretEnv
    if profile.spec.provider.lower() == "openai" and not secret_env:
        return "OPENAI_API_KEY"
    return secret_env


def _select_budget_policy(index: WorkspaceIndex, run_id: str) -> BudgetPolicy | None:
    run = index.runs[run_id]
    candidates: list[tuple[int, str, BudgetPolicy]] = []
    for policy in index.budget_policies.values():
        scope = policy.spec.scope
        if scope.task and scope.task != run.spec.task:
            continue
        if scope.project and scope.project != run.spec.project:
            continue
        if scope.member and scope.member != run.spec.member:
            continue
        if scope.assignment and scope.assignment != run.spec.assignment:
            continue
        if not any([scope.task, scope.project, scope.member, scope.assignment]):
            continue
        score = 0
        if scope.project:
            score += 1
        if scope.member:
            score += 2
        if scope.assignment:
            score += 3
        if scope.task:
            score += 8
        candidates.append((score, policy.object_id, policy))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _check_budget_limits(
    policy: BudgetPolicy,
    usage: dict[str, Any],
    estimates: dict[str, Any],
    index: WorkspaceIndex,
    run_id: str,
    check: Any,
) -> None:
    limits = policy.spec.limits
    projected_input = int(usage["inputTokens"]) + estimates["inputTokens"]
    projected_output = int(usage["outputTokens"]) + estimates["outputTokens"]
    projected_total = projected_input + projected_output
    estimated_cost_usd = estimates.get("costUsd")
    projected_run_cost = float(usage["costUsd"]) + (float(estimated_cost_usd) if estimated_cost_usd is not None else 0.0)
    projected_retries = int(usage["retries"])
    soft_status = "fail" if policy.spec.enforcement.onSoftLimit == "stop-run" else "warn"

    usd_messages: list[str] = []
    if limits.maxUsdPerRun is not None:
        if float(usage["costUsd"]) >= limits.maxUsdPerRun:
            usd_messages.append(f"run cost {usage['costUsd']} has reached maxUsdPerRun {limits.maxUsdPerRun}")
        elif estimated_cost_usd is not None and projected_run_cost > limits.maxUsdPerRun:
            usd_messages.append(f"projected run cost {round(projected_run_cost, 8)} would exceed maxUsdPerRun {limits.maxUsdPerRun}")
    if limits.maxUsdPerDay is not None:
        daily = _daily_cost(index, run_id)
        if daily >= limits.maxUsdPerDay:
            usd_messages.append(f"daily cost {daily} has reached maxUsdPerDay {limits.maxUsdPerDay}")
        elif estimated_cost_usd is not None and daily + float(estimated_cost_usd) > limits.maxUsdPerDay:
            usd_messages.append(f"projected daily cost {round(daily + float(estimated_cost_usd), 8)} would exceed maxUsdPerDay {limits.maxUsdPerDay}")
    if usd_messages:
        check("budget-usd", "fail", "; ".join(usd_messages))
    else:
        check("budget-usd", "pass", "USD budget limits allow another model call.")

    soft_usd_messages: list[str] = []
    if limits.softUsdPerRun is not None and float(usage["costUsd"]) >= limits.softUsdPerRun:
        soft_usd_messages.append(f"run cost {usage['costUsd']} has reached softUsdPerRun {limits.softUsdPerRun}")
    elif limits.softUsdPerRun is not None and estimated_cost_usd is not None and projected_run_cost > limits.softUsdPerRun:
        soft_usd_messages.append(f"projected run cost {round(projected_run_cost, 8)} would exceed softUsdPerRun {limits.softUsdPerRun}")
    if limits.softUsdPerDay is not None:
        daily = _daily_cost(index, run_id)
        if daily >= limits.softUsdPerDay:
            soft_usd_messages.append(f"daily cost {daily} has reached softUsdPerDay {limits.softUsdPerDay}")
        elif estimated_cost_usd is not None and daily + float(estimated_cost_usd) > limits.softUsdPerDay:
            soft_usd_messages.append(f"projected daily cost {round(daily + float(estimated_cost_usd), 8)} would exceed softUsdPerDay {limits.softUsdPerDay}")
    if soft_usd_messages:
        check("soft-budget-usd", soft_status, _soft_limit_message(policy, "; ".join(soft_usd_messages)))
    elif limits.softUsdPerRun is not None or limits.softUsdPerDay is not None:
        check("soft-budget-usd", "pass", "Soft USD budget limits have not been reached.")

    token_messages: list[str] = []
    if limits.maxInputTokensPerRun is not None and projected_input > limits.maxInputTokensPerRun:
        token_messages.append(f"projected input tokens {projected_input} exceed maxInputTokensPerRun {limits.maxInputTokensPerRun}")
    if limits.maxOutputTokensPerRun is not None and projected_output > limits.maxOutputTokensPerRun:
        token_messages.append(f"projected output tokens {projected_output} exceed maxOutputTokensPerRun {limits.maxOutputTokensPerRun}")
    if token_messages:
        check("budget-tokens", "fail", "; ".join(token_messages))
    else:
        check("budget-tokens", "pass", f"Projected token use {projected_total} is within policy limits.")

    soft_token_messages: list[str] = []
    if limits.softInputTokensPerRun is not None and projected_input > limits.softInputTokensPerRun:
        soft_token_messages.append(f"projected input tokens {projected_input} exceed softInputTokensPerRun {limits.softInputTokensPerRun}")
    if limits.softOutputTokensPerRun is not None and projected_output > limits.softOutputTokensPerRun:
        soft_token_messages.append(f"projected output tokens {projected_output} exceed softOutputTokensPerRun {limits.softOutputTokensPerRun}")
    if soft_token_messages:
        check("soft-budget-tokens", soft_status, _soft_limit_message(policy, "; ".join(soft_token_messages)))
    elif limits.softInputTokensPerRun is not None or limits.softOutputTokensPerRun is not None:
        check("soft-budget-tokens", "pass", "Projected token use is within soft policy limits.")

    if limits.maxRetriesPerRun is not None and usage["attempts"] > 0 and projected_retries >= limits.maxRetriesPerRun:
        check("budget-retries", "fail", f"Retry count {projected_retries} has reached maxRetriesPerRun {limits.maxRetriesPerRun}.")
    else:
        check("budget-retries", "pass", "Retry budget allows another attempt.")

    if limits.softRetriesPerRun is not None and usage["attempts"] > 0 and projected_retries >= limits.softRetriesPerRun:
        check("soft-budget-retries", soft_status, _soft_limit_message(policy, f"retry count {projected_retries} has reached softRetriesPerRun {limits.softRetriesPerRun}"))
    elif limits.softRetriesPerRun is not None:
        check("soft-budget-retries", "pass", "Retry count is within soft policy limits.")

    requests_per_minute = policy.spec.rateLimit.requestsPerMinute
    if requests_per_minute is not None and _recent_started_calls(index, window=timedelta(minutes=1)) >= requests_per_minute:
        check("rate-limit", "fail", f"Rate limit requestsPerMinute {requests_per_minute} has been reached.")
    else:
        check("rate-limit", "pass", "Rate limit allows another model call.")


def _check_cost_estimate(policy: BudgetPolicy, estimated_cost_usd: float | None, check: Any) -> None:
    if not _policy_has_usd_limits(policy):
        return
    if estimated_cost_usd is None:
        check("cost-estimate", "warn", "ModelProfile has no pricing; USD budget checks use recorded costs only.")
        return
    check("cost-estimate", "pass", f"Estimated model call cost is {estimated_cost_usd} USD.")


def _policy_has_usd_limits(policy: BudgetPolicy) -> bool:
    limits = policy.spec.limits
    return any(
        value is not None
        for value in [
            limits.softUsdPerRun,
            limits.softUsdPerDay,
            limits.maxUsdPerRun,
            limits.maxUsdPerDay,
        ]
    )


def _soft_limit_message(policy: BudgetPolicy, message: str) -> str:
    action = policy.spec.enforcement.onSoftLimit
    if action == "stop-run":
        return f"{message}; onSoftLimit=stop-run blocks execution."
    return f"{message}; onSoftLimit=warn allows execution with warning."


def _check_fallback_policy(policy: BudgetPolicy, usage: dict[str, Any], fallback_attempt: bool, check: Any) -> None:
    fallback = policy.spec.fallback
    if not fallback_attempt:
        check("fallback-policy", "pass", "No fallback attempt requested.")
        return
    if not fallback.allowModelFallback:
        check("fallback-policy", "fail", "Model fallback is disabled by BudgetPolicy.")
        return
    if usage["fallbacks"] >= fallback.maxFallbacksPerRun:
        check(
            "fallback-policy",
            "fail",
            f"Fallback count {usage['fallbacks']} has reached maxFallbacksPerRun {fallback.maxFallbacksPerRun}.",
        )
        return
    check("fallback-policy", "pass", "Fallback policy allows this fallback attempt.")


def _collect_usage(index: WorkspaceIndex, run_id: str) -> dict[str, Any]:
    run = index.runs[run_id]
    profile_id, _ = resolve_run_model_profile(index, run)
    profile = index.model_profiles.get(profile_id or "")
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cost_usd = 0.0
    attempts = 0
    fallbacks = 0
    for event in index.run_events.get(run_id, []):
        event_type = str(event.get("type") or "")
        if event_type == "model.call.started":
            attempts += 1
            if _is_fallback_event(event):
                fallbacks += 1
        if event_type != "model.call.completed":
            continue
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        event_input_tokens = _int_from(usage, "input_tokens", "prompt_tokens", "inputTokens", "promptTokens") or 0
        event_output_tokens = _int_from(usage, "output_tokens", "completion_tokens", "outputTokens", "completionTokens") or 0
        input_tokens += event_input_tokens
        output_tokens += event_output_tokens
        total_tokens += _int_from(usage, "total_tokens", "totalTokens") or 0
        event_cost = _float_from(event, "cost_usd", "costUsd") or _float_from(usage, "cost_usd", "costUsd")
        if event_cost is None:
            event_cost = estimate_profile_call_cost_usd(
                profile,
                input_tokens=event_input_tokens,
                output_tokens=event_output_tokens,
            )
        cost_usd += event_cost or 0.0
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
        "costUsd": round(cost_usd, 8),
        "attempts": attempts,
        "retries": max(0, attempts - 1),
        "fallbacks": fallbacks,
    }


def _daily_cost(index: WorkspaceIndex, run_id: str) -> float:
    run = index.runs[run_id]
    today = datetime.now(timezone.utc).date()
    total = 0.0
    for candidate in index.runs.values():
        if candidate.spec.project != run.spec.project:
            continue
        profile_id, _ = resolve_run_model_profile(index, candidate)
        profile = index.model_profiles.get(profile_id or "")
        for event in index.run_events.get(candidate.object_id, []):
            if event.get("type") != "model.call.completed" or _event_date(event) != today:
                continue
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            event_cost = _float_from(event, "cost_usd", "costUsd") or _float_from(usage, "cost_usd", "costUsd")
            if event_cost is None:
                event_cost = estimate_profile_call_cost_usd(
                    profile,
                    input_tokens=_int_from(usage, "input_tokens", "prompt_tokens", "inputTokens", "promptTokens") or 0,
                    output_tokens=_int_from(usage, "output_tokens", "completion_tokens", "outputTokens", "completionTokens") or 0,
                )
            total += event_cost or 0.0
    return round(total, 8)


def _recent_started_calls(index: WorkspaceIndex, *, window: timedelta) -> int:
    cutoff = datetime.now(timezone.utc) - window
    count = 0
    for events in index.run_events.values():
        for event in events:
            if event.get("type") != "model.call.started":
                continue
            ts = _event_datetime(event)
            if ts and ts >= cutoff:
                count += 1
    return count


def _event_date(event: dict[str, Any]) -> Any:
    ts = _event_datetime(event)
    return ts.date() if ts else None


def _event_datetime(event: dict[str, Any]) -> datetime | None:
    raw = event.get("ts")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_from(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _float_from(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _is_fallback_event(event: dict[str, Any]) -> bool:
    return event.get("fallback") is True or event.get("isFallback") is True or bool(event.get("fallbackFrom"))


def _is_local_manual(profile: ModelProfile) -> bool:
    return profile.spec.provider.lower() == "local" and profile.spec.model == "manual"


def _execution_profile(index: WorkspaceIndex, member_id: str | None, member_kind: str | None) -> Any | None:
    if not member_id or not member_kind:
        return None
    stores = {
        "digital": index.digital_execution_profiles,
        "human": index.human_collaboration_profiles,
        "hybrid": index.hybrid_execution_profiles,
        "service": index.service_account_profiles,
    }
    return stores.get(member_kind, {}).get(member_id)
