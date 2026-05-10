"""Fallback strategies when vision can't verify."""

from __future__ import annotations

from repo_transmute.v2.models import ComponentDef


def fallback_strategy(
    component: ComponentDef,
    issues: list[str],
) -> dict:
    """Generate fallback strategy when vision verification fails.
    
    Strategies:
    1. Simplify the component (remove complex features, migrate basics first)
    2. Use a different LLM model
    3. Split the component into smaller pieces
    4. Manual review flag
    """
    if component.jsx_complexity > 50:
        return {
            "strategy": "split",
            "reason": "Component too complex for single migration",
            "suggestion": "Break into smaller sub-components and migrate individually",
        }
    
    if "build" in " ".join(issues).lower():
        return {
            "strategy": "fix_build",
            "reason": "Build errors prevent verification",
            "suggestion": "Fix TypeScript/build errors first, then retry vision check",
        }
    
    return {
        "strategy": "manual_review",
        "reason": "Vision verification failed after retries",
        "suggestion": "Flag for manual review",
    }
