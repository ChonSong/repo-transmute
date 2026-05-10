"""Generate fix prompts from vision feedback."""

from __future__ import annotations

from repo_transmute.v2.models import VisionResult, ComponentDef


def generate_fix_prompt(
    component: ComponentDef,
    vision_result: VisionResult,
    current_code: str,
) -> str:
    """Generate a fix prompt based on vision feedback.
    
    Creates a targeted prompt that tells the LLM exactly what to fix
    based on the vision model's analysis.
    """
    prompt = f"""Fix the following component to match the source design.

CURRENT MIGRATED CODE:
```
{current_code}
```

ISSUES DETECTED:
"""
    for issue in vision_result.issues:
        prompt += f"- {issue}\n"
    
    prompt += "\nSUGGESTED FIXES:\n"
    for suggestion in vision_result.suggestions:
        prompt += f"- {suggestion}\n"
    
    prompt += "\nGenerate ONLY the fixed code. No explanations."
    return prompt
