"""Retry migration with improved context."""

from __future__ import annotations

from repo_transmute.v2.models import ComponentDef, TargetStack


def retry_migration(
    component: ComponentDef,
    target_stack: TargetStack,
    context: dict,
    max_retries: int = 3,
) -> str | None:
    """Retry migration with accumulated feedback.
    
    Each retry adds:
    - Build errors from previous attempt
    - Vision feedback from previous attempt
    - Fix suggestions from vision model
    """
    from repo_transmute.v2.migrate.codegen import generate_component
    
    for attempt in range(max_retries):
        component.fix_attempts = attempt + 1
        
        code = generate_component(
            component=component,
            target_stack=target_stack,
            context=context,
        )
        
        if code:
            return code
    
    return None
