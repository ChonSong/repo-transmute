"""Lightweight assumption extraction from LLM outputs and code chunks.

Uses a focused prompt to extract stated and implied assumptions from:
- LLM transpilation outputs
- Code chunk metadata
- Tool call results
- Self-correction events

Designed to be fast: uses a minimal prompt, no heavy parsing.
For harder cases (implicit belief inference), delegates to the LLM.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class Assumptions:
    """Container for extracted assumptions."""
    explicit: List[str]
    implicit: List[str]
    confidence: float  # 0.0–1.0; low confidence = may need LLM fallback
    source_snippet: str  # The text the assumptions were extracted from


class AssumptionExtractor:
    """Extracts explicit and implicit assumptions from text.

    Strategy:
    1. Fast regex/pass for explicit assumption markers
    2. If confidence is low, flag for LLM-based extraction
    3. Return structured Assumptions object
    """

    # Patterns indicating explicit assumption statements
    EXPLICIT_PATTERNS = [
        re.compile(r"(?i)assuming\s+that\s+(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"(?i)assume\s+(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"(?i)I\s+am\s+assuming\s+(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"(?i)we\s+assume\s+(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"(?i)it\s+is\s+assumed\s+that\s+(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"(?i)under\s+the\s+assumption\s+(?:that\s+)?(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"(?i)given\s+that\s+(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"(?i)based\s+on\s+the\s+assumption\s+(?:that\s+)?(.+?)(?:\.|$)", re.MULTILINE),
        # Code-adjacent patterns
        re.compile(r"#\s*assume\s+(.+)", re.MULTILINE),
        re.compile(r"//\s*assume\s+(.+)", re.MULTILINE),
    ]

    # Patterns indicating the agent is uncertain or flagging something
    UNCERTAINTY_PATTERNS = [
        re.compile(r"(?i)I\s+am\s+not\s+sure\s+(?:if\s+)?(.+)", re.MULTILINE),
        re.compile(r"(?i)uncertain\s+about\s+(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"(?i)if\s+this\s+assumption\s+holds:\s*(.+?)(?:\n|$)", re.MULTILINE),
        re.compile(r"(?i)assuming\s+this\s+is\s+correct:\s*(.+?)(?:\n|$)", re.MULTILINE),
    ]

    # Patterns indicating context dependency (things the agent is relying on)
    DEPENDENCY_PATTERNS = [
        re.compile(r"depends\s+on\s+(?:the\s+)?(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"requires\s+(?:that\s+)?(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"this\s+relies\s+on\s+(?:the\s+)?(.+?)(?:\.|$)", re.MULTILINE),
        re.compile(r"based\s+on\s+(?:the\s+fact\s+that\s+)?(.+?)(?:,\s+|$)", re.MULTILINE),
    ]

    def extract(self, text: str, context_hint: Optional[str] = None) -> Assumptions:
        """Extract assumptions from text.

        Args:
            text: The source text (LLM output, code, tool result, etc.)
            context_hint: Optional hint about what type of content this is
                          (e.g. "transpilation_output", "tool_result", "self_correction")

        Returns:
            Assumptions with explicit, implicit, confidence, and source_snippet
        """
        if not text or not text.strip():
            return Assumptions(explicit=[], implicit=[], confidence=0.0, source_snippet=text or "")

        # Extract explicit assumptions
        explicit = []
        for pattern in self.EXPLICIT_PATTERNS:
            matches = pattern.findall(text)
            explicit.extend([m.strip().rstrip(".") for m in matches if m.strip()])

        # Extract uncertainty/flagged assumptions
        uncertainty = []
        for pattern in self.UNCERTAINTY_PATTERNS:
            matches = pattern.findall(text)
            uncertainty.extend([m.strip().rstrip(".") for m in matches if m.strip()])

        # Extract context dependencies
        dependencies = []
        for pattern in self.DEPENDENCY_PATTERNS:
            matches = pattern.findall(text)
            dependencies.extend([m.strip().rstrip(".") for m in matches if m.strip()])

        # Combine explicit statements + flagged uncertain statements as explicit
        all_explicit = list({a for a in explicit + uncertainty + dependencies if a})

        # Confidence: high if we found explicit patterns, low otherwise
        confidence = min(1.0, len(all_explicit) * 0.25 + 0.1)

        # Implicit assumptions are not extracted here — too unreliable without LLM
        # Flag for LLM-based extraction if confidence is low and text is substantial
        implicit: List[str] = []
        if confidence < 0.5 and len(text) > 200:
            implicit = ["[LLM_FALLBACK_NEEDED]"]

        return Assumptions(
            explicit=all_explicit,
            implicit=implicit,
            confidence=confidence,
            source_snippet=text[:500]  # Store first 500 chars as reference
        )

    def extract_from_code_chunk(
        self,
        source_code: str,
        target_lang: str,
        chunk_metadata: Optional[Dict[str, Any]] = None
    ) -> Assumptions:
        """Extract assumptions from a transpiled code chunk.

        For RepoTransmute's pipeline, this identifies assumptions the LLM
        made about type mappings, API compatibility, and dependency structure.

        Args:
            source_code: The transpiled output code
            target_lang: The target language (typescript, python, go, rust)
            chunk_metadata: Optional dict with chunk_id, file_paths, function_count

        Returns:
            Assumptions object
        """
        assumptions = self.extract(source_code)

        # Add language-specific implicit assumptions based on common pitfalls
        lang_pitfalls = {
            "typescript": [
                "Types are preserved at runtime via type annotations only — no runtime type checking",
                "Optional fields may be undefined at runtime",
                "TypeScript generics are erased at runtime",
            ],
            "python": [
                "Python has no type enforcement at runtime unless explicit checks exist",
                "GIL prevents true multi-threaded parallelism",
                "Python 3 vs Python 2 differences may not be handled",
            ],
            "go": [
                "Go uses nil for uninitialized pointers — None comparisons must use '== nil'",
                "Go has no exceptions — errors are returned as values",
                "Go requires explicit error handling — ignoring errors is a code smell",
            ],
            "rust": [
                "Rust has no null — Option<T> must be unwrapped",
                "Rust lifetimes are static — no runtime overhead",
                "Rust errors are handled via Result<T, E> — not exceptions",
            ],
        }

        # Only add pitfalls if the code actually uses those constructs
        code_lower = source_code.lower()
        relevant_pitfalls = []
        for lang, pitfalls in lang_pitfalls.items():
            if lang in code_lower or target_lang == lang:
                for pitfall in pitfalls:
                    # Light heuristic: check for related keywords
                    if lang == "go" and ("none" in code_lower or "none" in pitfall.lower()):
                        relevant_pitfalls.append(pitfall)
                    elif lang == "rust" and ("option" in code_lower or "none" in pitfall.lower()):
                        relevant_pitfalls.append(pitfall)
                    elif lang == "typescript" and ("any" in code_lower or "interface" in code_lower):
                        relevant_pitfalls.append(pitfall)

        if relevant_pitfalls and assumptions.confidence < 0.8:
            assumptions.explicit.extend(relevant_pitfalls[:2])

        if chunk_metadata:
            assumptions.source_snippet = (
                f"chunk_id={chunk_metadata.get('chunk_id','?')} "
                f"files={chunk_metadata.get('file_count',0)} "
                f"functions={chunk_metadata.get('function_count',0)}"
            )

        return assumptions

    def needs_llm_fallback(self, assumptions: Assumptions) -> bool:
        """Check if assumptions need LLM-based deep extraction."""
        return "[LLM_FALLBACK_NEEDED]" in assumptions.implicit

    def build_llm_extraction_prompt(self, text: str, context: str = "") -> str:
        """Build a prompt for LLM-based assumption extraction.

        Use this when fast extraction confidence is low and the text
        is substantial enough to warrant LLM inference.

        Args:
            text: The source text
            context: Optional context about what this is (e.g. "pipeline pass 2 output")

        Returns:
            A prompt string suitable for LLM extraction
        """
        return f"""Extract all assumptions from the following {context or "text"}.

An "assumption" is any statement that:
1. Takes something as given without proof (e.g., "X is the case")
2. Depends on external state not present in the text
3. Makes a generalization from limited data
4. Uses an API or library without verifying availability

Format: Return a JSON object with two keys:
- "explicit": list of clearly stated assumptions
- "implicit": list of assumptions that are implied but not stated

Be precise. Do not over-interpret. If no assumptions can be found, return empty lists.

--- Content ---
{text[:3000]}
--- End Content ---"""
