"""Built-in validation Skill definitions.

These records formalize the minimal Phase 5 validation roles as read-only Skill
assets. Local `.aiteamos/skills/<id>/SKILL.md` files can still override a seed
with the same id.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationSkillDefinition:
    id: str
    title: str
    description: str
    content: str
    owner_roles: tuple[str, ...]

    @property
    def source_ref(self) -> str:
        return f"aiteamos://builtin/validation-skills/{self.id}"


VALIDATION_SKILL_DEFINITIONS: tuple[ValidationSkillDefinition, ...] = (
    ValidationSkillDefinition(
        id="validation-strategy",
        title="Validation Strategy",
        description="Plan Ticket-bound validation scope, evidence requirements, and pass/fail criteria.",
        owner_roles=("AI Team OS Manager", "AI PV", "AI QA / Harness Runner", "AI Release"),
        content="""# Validation Strategy

> Plan Ticket-bound validation scope, evidence requirements, and pass/fail criteria.

## Inputs
- Ticket id, assignee, state, and provider_ref when available.
- Proposed work scope, reports, linked assets, and known risks.
- Required evidence categories for the Ticket type.

## Procedure
1. Confirm the validation request is bound to a Ticket.
2. Define focused checks that can prove the requested change.
3. List required evidence before any validated state transition.
4. Separate blockers from optional follow-up work.

## Output
- Validation scope.
- Required evidence.
- Pass/fail criteria.
- Next assignee or human review need.
""",
    ),
    ValidationSkillDefinition(
        id="evidence-review",
        title="Evidence Review",
        description="Review Ticket reports, evidence, links, and provenance before validation decisions.",
        owner_roles=("AI PV", "AI QA / Harness Runner", "AI Release"),
        content="""# Evidence Review

> Review Ticket reports, evidence, links, and provenance before validation decisions.

## Inputs
- Ticket id and current state.
- Reports, evidence records, asset links, and provider refs.
- Validation requirements attached to the Ticket.

## Procedure
1. Confirm each evidence item links back to the Ticket, run, report, or asset it supports.
2. Check whether evidence is recent enough for the current change.
3. Reject raw trace, raw tool log, secrets, or permission authority as durable memory input.
4. Mark missing or weak evidence as a validation blocker.

## Output
- Evidence accepted.
- Evidence missing.
- Validation blocker summary.
- Durable asset candidates, when approval is appropriate.
""",
    ),
    ValidationSkillDefinition(
        id="regression-check",
        title="Regression Check",
        description="Select and interpret focused regression or harness checks tied to a Ticket.",
        owner_roles=("AI PV", "AI QA / Harness Runner", "AI Release"),
        content="""# Regression Check

> Select and interpret focused regression or harness checks tied to a Ticket.

## Inputs
- Ticket id, changed surface, and expected behavior.
- Allowed local commands or harness evidence.
- Prior reports and known regressions.

## Procedure
1. Pick the smallest focused checks that prove the Ticket outcome.
2. Prefer backend focused tests before broader UI or build checks.
3. Record command, scope, result, and reason in a Ticket report.
4. Escalate flaky or unavailable checks as blockers instead of fabricating proof.

## Output
- Checks selected.
- Pass/fail result.
- Evidence reference.
- Follow-up Ticket or rework recommendation.
""",
    ),
    ValidationSkillDefinition(
        id="product-model-review",
        title="Product Model Review",
        description="Check that changes preserve Ticket-flow-first behavior and Plane/Graphiti boundaries.",
        owner_roles=("AI Team OS Manager", "AI Architect", "AI PV", "AI QA / Harness Runner"),
        content="""# Product Model Review

> Check that changes preserve Ticket-flow-first behavior and Plane/Graphiti boundaries.

## Inputs
- Ticket id, report, evidence, and related product docs.
- Proposed behavior and affected API or UI surfaces.
- Plane and Graphiti provider refs when available.

## Procedure
1. Confirm internal domain language remains Ticket-centered.
2. Confirm work actions bind to Tickets and produce reports or evidence.
3. Confirm Plane-native names stay inside adapter metadata, provider_ref, links, or debug metadata.
4. Confirm only approved durable assets are candidates for Graphiti recall.

## Output
- Product-model pass/fail decision.
- Boundary risks.
- Required rework or human review request.
""",
    ),
)

VALIDATION_SKILL_IDS: tuple[str, ...] = tuple(skill.id for skill in VALIDATION_SKILL_DEFINITIONS)
