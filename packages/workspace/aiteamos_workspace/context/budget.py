from __future__ import annotations

from typing import Any


def _model_and_budget(index: Any, model_profile: str | None) -> str:
    lines: list[str] = []
    if model_profile and model_profile in index.model_profiles:
        profile = index.model_profiles[model_profile]
        lines.extend(
            [
                f"- Profile: `{model_profile}`",
                f"- Provider: {profile.spec.provider}",
                f"- Model: {profile.spec.model}",
                f"- Gateway: {profile.spec.gateway}",
                f"- Capabilities: {', '.join(profile.spec.capabilities) or 'unspecified'}",
                f"- Invocation: {profile.spec.invocation or {}}",
                f"- Secret env: {profile.spec.secretEnv or 'none'} (value is never included)",
            ]
        )
    elif model_profile:
        lines.append(f"- Profile: `{model_profile}` is not present in workspace model_profiles.")
    else:
        lines.append("- No model profile selected.")
    if index.budget_policies:
        lines.append("- Budget policies:")
        for policy in sorted(index.budget_policies.values(), key=lambda item: item.object_id):
            lines.append(f"  - `{policy.object_id}` scope={policy.spec.scope} limits={policy.spec.limits}")
    else:
        lines.append("- No explicit budget policy manifests found.")
    return "\n".join(lines)


def _budget_decision_manifest(
    index: Any,
    *,
    project: str,
    member_id: str,
    assignment_id: str | None,
    task_id: str,
    model_profile: str | None,
) -> dict[str, Any]:
    policies: list[dict[str, Any]] = []
    selected: tuple[int, str] | None = None
    for policy in sorted(index.budget_policies.values(), key=lambda item: item.object_id):
        specificity = _budget_policy_specificity(policy.spec.scope)
        applies = _budget_policy_applies(policy.spec.scope, project=project, member_id=member_id, assignment_id=assignment_id, task_id=task_id)
        if applies and (selected is None or (-specificity, policy.object_id) < (-selected[0], selected[1])):
            selected = (specificity, policy.object_id)
        policies.append(
            {
                "id": policy.object_id,
                "scope": policy.spec.scope.model_dump(mode="json", exclude_none=True),
                "limits": policy.spec.limits.model_dump(mode="json", exclude_none=True),
                "rateLimit": policy.spec.rateLimit.model_dump(mode="json", exclude_none=True),
                "fallback": policy.spec.fallback.model_dump(mode="json", exclude_none=True),
                "enforcement": policy.spec.enforcement.model_dump(mode="json", exclude_none=True),
                "applies": applies,
                "specificity": specificity,
            }
        )
    return {
        "modelProfile": model_profile,
        "applicablePolicy": selected[1] if selected else None,
        "policies": policies,
    }


def _budget_policy_applies(scope: Any, *, project: str, member_id: str, assignment_id: str | None, task_id: str) -> bool:
    if scope.project and scope.project != project:
        return False
    if scope.member and scope.member != member_id:
        return False
    if scope.assignment and scope.assignment != assignment_id:
        return False
    if scope.task and scope.task != task_id:
        return False
    return any([scope.project, scope.member, scope.assignment, scope.task])


def _budget_policy_specificity(scope: Any) -> int:
    score = 0
    if scope.project:
        score += 1
    if scope.member:
        score += 2
    if scope.assignment:
        score += 4
    if scope.task:
        score += 8
    return score
