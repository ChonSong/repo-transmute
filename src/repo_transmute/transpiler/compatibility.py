"""Compatibility checking for transpilation."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Language(Enum):
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    PYTHON = "python"
    RUST = "rust"
    GO = "go"
    JAVA = "java"
    RUBY = "ruby"
    PHP = "php"
    CSHARP = "csharp"
    UNKNOWN = "unknown"


class TargetLanguage(Enum):
    TYPESCRIPT = "typescript"
    PYTHON = "python"
    RUST = "rust"
    GO = "go"
    REACT = "react"  # React/TSX component migration
    CSS = "css"  # CSS/theme migration


@dataclass
class CompatibilityResult:
    compatible: bool
    recommended_target: Optional[str]
    confidence: float  # 0.0 - 1.0
    warnings: list
    complexity_score: int  # 1-10


# Routing table: source -> (target, confidence, reason)
ROUTING_TABLE = {
    Language.JAVASCRIPT: (TargetLanguage.TYPESCRIPT, 0.95, "Direct mapping, same ecosystem"),
    Language.TYPESCRIPT: (TargetLanguage.TYPESCRIPT, 0.98, "Same language, type-safe"),
    Language.PYTHON: (TargetLanguage.PYTHON, 0.90, "Keep in same language"),
    Language.GO: (TargetLanguage.GO, 0.85, "Keep Go for Go"),
    Language.RUST: (None, 0.0, "Already Rust - keep as-is"),
    Language.JAVA: (TargetLanguage.PYTHON, 0.6, "Consider Python as alternative"),
    Language.RUBY: (TargetLanguage.PYTHON, 0.5, "Major transformation - high risk"),
    Language.PHP: (TargetLanguage.PYTHON, 0.5, "Major transformation - high risk"),
    Language.CSHARP: (TargetLanguage.RUST, 0.6, "Microsoft ecosystem to Rust"),
    Language.UNKNOWN: (None, 0.0, "Cannot determine source language"),
}

# Frontend migration routing table
# (source_framework, source_style) -> (target, confidence, reason)
FRONTEND_ROUTING_TABLE = {
    ("react", "tailwind"): (TargetLanguage.REACT, 0.95, "React + Tailwind → React, direct migration"),
    ("react", "css-vars"): (TargetLanguage.REACT, 0.90, "React + CSS vars → React, theme mapping needed"),
    ("react", "styled-components"): (TargetLanguage.REACT, 0.85, "React + styled-components → React, style system change"),
    ("react", "css-modules"): (TargetLanguage.REACT, 0.85, "React + CSS modules → React, style system change"),
    ("next.js", "tailwind"): (TargetLanguage.REACT, 0.80, "Next.js → React SPA, SSR features lost"),
    ("tanstack-start", "tailwind"): (TargetLanguage.REACT, 0.80, "TanStack Start → React SPA, SSR features lost"),
    ("vue", "tailwind"): (TargetLanguage.REACT, 0.70, "Vue → React, paradigm shift needed"),
    ("angular", "typescript"): (TargetLanguage.REACT, 0.60, "Angular → React, major paradigm shift"),
}


# Complexity thresholds
COMPLEXITY_THRESHOLDS = {
    "low": 5,      # < 5 files, < 20 functions
    "medium": 15,  # < 15 files, < 100 functions
    "high": 30,    # < 30 files, < 500 functions
    "very_high": 9999,  # above = skip
}


def calculate_complexity(file_count: int, function_count: int, dep_count: int = 0) -> int:
    """Calculate complexity score 1-10."""
    score = 1
    
    # File count contribution
    if file_count > 100:
        score += 3
    elif file_count > 20:
        score += 2
    elif file_count > 5:
        score += 1
    
    # Function count contribution
    if function_count > 500:
        score += 3
    elif function_count > 100:
        score += 2
    elif function_count > 20:
        score += 1
    
    # Dependency contribution
    if dep_count > 50:
        score += 2
    elif dep_count > 10:
        score += 1
    
    return min(score, 10)


def check_compatibility(
    source_lang: str,
    target_lang: Optional[str] = None,
    file_count: int = 0,
    function_count: int = 0,
    dep_count: int = 0
) -> CompatibilityResult:
    """Check if transpilation is recommended.
    
    Args:
        source_lang: Detected source language
        target_lang: Optional desired target (if None, auto-recommend)
        file_count: Number of source files
        function_count: Number of functions
        dep_count: Number of dependencies
        
    Returns:
        CompatibilityResult with recommendation
    """
    warnings = []
    
    # Normalize source language
    source = _normalize_language(source_lang)
    
    # Get routing recommendation
    if source in ROUTING_TABLE:
        recommended, confidence, reason = ROUTING_TABLE[source]
        if recommended is None:
            return CompatibilityResult(
                compatible=False,
                recommended_target=None,
                confidence=confidence,
                warnings=[f"Source is {source_lang} - no transpilation needed"],
                complexity_score=calculate_complexity(file_count, function_count, dep_count)
            )
    else:
        return CompatibilityResult(
            compatible=False,
            recommended_target=None,
            confidence=0.0,
            warnings=[f"Unknown language: {source_lang}"],
            complexity_score=calculate_complexity(file_count, function_count, dep_count)
        )
    
    # Check if target matches recommendation
    if target_lang:
        target_normalized = _normalize_language(target_lang)
        if recommended and target_normalized != recommended.value:
            warnings.append(
                f"Target {target_lang} differs from recommended {recommended.value}. "
                f"Confidence: {confidence - 0.2:.0%}"
            )
            confidence -= 0.2
        actual_target = target_lang
    else:
        actual_target = recommended.value if recommended else None
        warnings.append(f"Recommended: {recommended.value} ({reason})")
    
    # Complexity check
    complexity = calculate_complexity(file_count, function_count, dep_count)
    if complexity >= 8:
        warnings.append(
            f"High complexity ({complexity}/10) - transpilation may be incomplete"
        )
        confidence -= 0.3
    elif complexity >= 5:
        warnings.append(f"Medium complexity ({complexity}/10)")
    
    # Confidence floor
    confidence = max(confidence, 0.0)
    
    return CompatibilityResult(
        compatible=confidence >= 0.5,
        recommended_target=actual_target,
        confidence=confidence,
        warnings=warnings,
        complexity_score=complexity
    )


def _normalize_language(lang: str) -> Language:
    """Normalize language string to enum."""
    lang_lower = lang.lower().strip()
    
    # JavaScript variants
    if lang_lower in ("javascript", "js", "jsx"):
        return Language.JAVASCRIPT
    
    # TypeScript variants
    if lang_lower in ("typescript", "ts", "tsx"):
        return Language.TYPESCRIPT
    
    # Python
    if lang_lower in ("python", "py"):
        return Language.PYTHON
    
    # Rust
    if lang_lower in ("rust", "rs"):
        return Language.RUST
    
    # Go
    if lang_lower in ("go", "golang"):
        return Language.GO
    
    # Java
    if lang_lower in ("java"):
        return Language.JAVA
    
    # Ruby
    if lang_lower in ("ruby", "rb"):
        return Language.RUBY
    
    # PHP
    if lang_lower in ("php"):
        return Language.PHP
    
    # C#
    if lang_lower in ("csharp", "c#", "cs"):
        return Language.CSHARP
    
    return Language.UNKNOWN


def get_recommended_target(source_lang: str) -> Optional[str]:
    """Get recommended target language for a source."""
    source = _normalize_language(source_lang)
    if source in ROUTING_TABLE:
        recommended, _, _ = ROUTING_TABLE[source]
        if recommended:
            return recommended.value
    return None


def check_frontend_compatibility(
    source_framework: str,
    source_style: str,
    target_framework: str = "react",
    component_count: int = 0,
    has_ssr: bool = False,
) -> CompatibilityResult:
    """Check frontend migration compatibility.
    
    Args:
        source_framework: Source frontend framework (react, next.js, vue, etc.)
        source_style: Source CSS approach (tailwind, css-vars, styled-components, etc.)
        target_framework: Target framework (default: react)
        component_count: Number of components to migrate
        has_ssr: Whether source uses server-side rendering
    
    Returns:
        CompatibilityResult with migration recommendation
    """
    warnings = []
    key = (source_framework.lower(), source_style.lower())
    
    if key in FRONTEND_ROUTING_TABLE:
        recommended, confidence, reason = FRONTEND_ROUTING_TABLE[key]
        warnings.append(reason)
    else:
        # Default: assume React → React with style change
        recommended = TargetLanguage.REACT
        confidence = 0.75
        warnings.append(
            f"No specific routing for {source_framework}/{source_style}. "
            f"Assuming React-to-React migration with style adaptation."
        )
    
    # SSR warning
    if has_ssr:
        confidence -= 0.15
        warnings.append(
            "Source uses SSR — SSR-specific features will be lost in SPA migration. "
            "Consider client-side data fetching patterns."
        )
    
    # Complexity penalty
    if component_count > 50:
        confidence -= 0.2
        warnings.append(f"High component count ({component_count}) — migration may be incomplete")
    elif component_count > 20:
        confidence -= 0.1
        warnings.append(f"Medium component count ({component_count})")
    
    confidence = max(confidence, 0.0)
    
    return CompatibilityResult(
        compatible=confidence >= 0.5,
        recommended_target=recommended.value if recommended else None,
        confidence=confidence,
        warnings=warnings,
        complexity_score=min(10, max(1, component_count // 5)),
    )
