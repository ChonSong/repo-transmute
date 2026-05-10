"""Code generation — LLM-driven component code generation with context assembly."""

from __future__ import annotations

from repo_transmute.v2.models import ComponentDef, TargetStack, Framework


# Migration prompt templates for each source→target combination
MIGRATION_PROMPTS: dict[tuple[Framework, TargetStack], str] = {
    (Framework.REACT, TargetStack.REACT_TS): """You are an expert React/TypeScript developer.
Migrate the following React component to modern React+TypeScript with the target conventions.

SOURCE COMPONENT:
```{framework_source}
{source_code}
```

TARGET REQUIREMENTS:
- Framework: React with TypeScript
- Styling: {style_approach}
- Use functional components with explicit type annotations
- Props should be defined as interfaces
- State should use useState with proper types
- Effects should use useEffect with proper dependency arrays

DEPENDENCY CODE (components this imports):
{dependencies}

BUILD ERRORS (from previous attempt, if any):
{build_errors}

VISION FEEDBACK (from previous attempt, if any):
{vision_feedback}

Generate ONLY the migrated component code. No explanations.""",
}


def generate_component(
    component: ComponentDef,
    target_stack: TargetStack,
    context: dict,
    model: str = "glm-5-turbo",
) -> str:
    """Generate migrated component code using LLM.
    
    Args:
        component: Source component definition
        target_stack: Target stack
        context: Migration context (dependencies, errors, feedback)
        model: LLM model to use
    
    Returns:
        Generated component code
    """
    # Get the appropriate prompt template
    framework = component.framework if component.framework != Framework.UNKNOWN else Framework.REACT
    key = (framework, target_stack)
    
    if key not in MIGRATION_PROMPTS:
        # Fallback to React→React prompt
        key = (Framework.REACT, TargetStack.REACT_TS)
    
    prompt = MIGRATION_PROMPTS[key]
    
    # Format the prompt
    style_approach = context.get("style_system", {}).get("approach", "CSS variables")
    dependencies = context.get("dependencies", {})
    dep_code = "\n\n".join(
        f"// {name}:\n{code}" for name, code in dependencies.items()
    )
    
    formatted = prompt.format(
        framework_source=framework.value,
        source_code=component.full_source,
        style_approach=style_approach,
        dependencies=dep_code if dep_code else "(none)",
        build_errors="\n".join(context.get("build_errors", [])) or "(none)",
        vision_feedback="\n".join(context.get("vision_suggestions", [])) or "(none)",
    )
    
    # Call the LLM
    # For now, use a simple approach — in production this would call the actual LLM API
    return _call_llm(formatted, model)


def _call_llm(prompt: str, model: str) -> str:
    """Call the LLM API to generate code."""
    import subprocess
    import json
    import os
    
    # Use the available LLM API
    api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ZAI_API_KEY")
    if not api_key:
        # Fallback: return the source code as-is (for development)
        return "// TODO: Implement LLM migration\n// Source:\n" + prompt[:200]
    
    # Use the MiniMax API (same as repo-transmute v1)
    try:
        import httpx
        
        response = httpx.post(
            "https://api.minimax.chat/v1/text/chatcompletion_v2",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model if "minimax" in model.lower() else "MiniMax-M2.7",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 8000,
            },
            timeout=120,
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception:
        pass
    
    return ""
