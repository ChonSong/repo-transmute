"""Tests for transpiler/compatibility.py."""

import pytest
from repo_transmute.transpiler.compatibility import (
    Language,
    TargetLanguage,
    CompatibilityResult,
    calculate_complexity,
    check_compatibility,
    get_recommended_target,
    _normalize_language,
)


# ---------------------------------------------------------------------------
# Language / TargetLanguage enums
# ---------------------------------------------------------------------------

class TestLanguageEnum:
    @pytest.mark.parametrize("variant,expected", [
        ("javascript", Language.JAVASCRIPT),
        ("js",          Language.JAVASCRIPT),
        ("jsx",         Language.JAVASCRIPT),
        ("JAVASCRIPT",  Language.JAVASCRIPT),
        ("TypeScript",  Language.TYPESCRIPT),
        ("typescript",  Language.TYPESCRIPT),
        ("ts",          Language.TYPESCRIPT),
        ("tsx",         Language.TYPESCRIPT),
        ("python",      Language.PYTHON),
        ("py",          Language.PYTHON),
        ("rust",        Language.RUST),
        ("rs",          Language.RUST),
        ("go",          Language.GO),
        ("golang",      Language.GO),
        ("java",        Language.JAVA),
        ("ruby",        Language.RUBY),
        ("rb",          Language.RUBY),
        ("php",         Language.PHP),
        ("csharp",      Language.CSHARP),
        ("c#",          Language.CSHARP),
        ("cs",          Language.CSHARP),
        ("unknownlang", Language.UNKNOWN),
        # Empty string is invalid → falls through to UNKNOWN
        ("",            Language.UNKNOWN),
    ])
    def test_normalize_language(self, variant, expected):
        assert _normalize_language(variant) == expected


class TestTargetLanguageEnum:
    def test_values(self):
        assert TargetLanguage.TYPESCRIPT.value == "typescript"
        assert TargetLanguage.PYTHON.value == "python"
        assert TargetLanguage.RUST.value == "rust"
        assert TargetLanguage.GO.value == "go"


# ---------------------------------------------------------------------------
# CompatibilityResult dataclass
# ---------------------------------------------------------------------------

class TestCompatibilityResult:
    def test_fields(self):
        r = CompatibilityResult(
            compatible=True,
            recommended_target="typescript",
            confidence=0.95,
            warnings=["low complexity"],
            complexity_score=3,
        )
        assert r.compatible is True
        assert r.recommended_target == "typescript"
        assert r.confidence == 0.95
        assert r.warnings == ["low complexity"]
        assert r.complexity_score == 3

    def test_defaults(self):
        r = CompatibilityResult(
            compatible=False, recommended_target=None,
            confidence=0.0, warnings=[], complexity_score=1,
        )
        assert r.compatible is False
        assert r.recommended_target is None
        assert r.confidence == 0.0
        assert r.complexity_score == 1


# ---------------------------------------------------------------------------
# calculate_complexity
# ---------------------------------------------------------------------------

class TestCalculateComplexity:
    def test_tiny_repo(self):
        # tiny: < 5 files, < 20 functions, < 10 deps
        assert calculate_complexity(2, 5) == 1

    def test_small_repo(self):
        # small: 5-20 files, 20-100 functions
        score = calculate_complexity(10, 50)
        assert score >= 2

    def test_large_repo(self):
        # large: > 20 files, > 100 functions
        score = calculate_complexity(50, 300)
        assert score >= 4

    def test_very_large_repo(self):
        # very large: >100 files, >500 functions, >50 deps
        score = calculate_complexity(150, 800, dep_count=60)
        assert score >= 6

    def test_max_score_never_exceeds_10(self):
        # Even pathological inputs are capped at 10
        for fc, fnc, dc in [
            (999, 9999, 999),
            (200, 2000, 200),
            (1000, 5000, 500),
        ]:
            assert calculate_complexity(fc, fnc, dc) <= 10

    def test_dependencies_add_score(self):
        base = calculate_complexity(5, 50, dep_count=0)
        with_deps = calculate_complexity(5, 50, dep_count=60)
        assert with_deps > base


# ---------------------------------------------------------------------------
# check_compatibility
# ---------------------------------------------------------------------------

class TestCheckCompatibility:
    def test_js_to_ts_high_confidence(self):
        r = check_compatibility("javascript")
        assert r.compatible is True
        assert r.recommended_target == "typescript"
        assert r.confidence >= 0.9

    def test_ts_to_ts_highest_confidence(self):
        r = check_compatibility("typescript")
        assert r.compatible is True
        assert r.recommended_target == "typescript"
        assert r.confidence >= 0.95

    def test_python_to_python(self):
        r = check_compatibility("python")
        assert r.compatible is True
        assert r.recommended_target == "python"
        assert r.confidence >= 0.85

    def test_rust_already_rust(self):
        r = check_compatibility("rust")
        assert r.compatible is False
        assert r.recommended_target is None
        assert any("no transpilation needed" in w.lower() for w in r.warnings)

    def test_go_stays_go(self):
        r = check_compatibility("go")
        assert r.compatible is True
        assert r.recommended_target == "go"
        assert r.confidence >= 0.8

    def test_java_routing(self):
        # Java→Python: 0.6 base confidence
        r = check_compatibility("java")
        assert r.recommended_target == "python"

    def test_unknown_language(self):
        r = check_compatibility("cobol")
        assert r.compatible is False
        assert r.recommended_target is None
        assert any("unknown" in w.lower() for w in r.warnings)

    def test_target_matches_recommendation_no_warning(self):
        # target=typescript on JS repo matches recommended → no "differs" warning
        r = check_compatibility("javascript", target_lang="typescript")
        assert r.compatible is True
        assert not any("differs" in w.lower() for w in r.warnings)

    def test_target_differs_from_recommendation(self):
        # target=rust on JS repo differs from recommended TS → warning + 0.2 penalty
        r = check_compatibility("javascript", target_lang="rust")
        assert any("differs" in w.lower() for w in r.warnings)
        assert r.confidence < 0.95

    def test_high_complexity_warning(self):
        # complexity score 8+ adds a "high complexity" warning
        r = check_compatibility("javascript", file_count=150, function_count=800, dep_count=60)
        assert any("high complexity" in w.lower() for w in r.warnings)

    def test_confidence_floor_is_zero(self):
        # Very high complexity + poor match should not go negative
        r = check_compatibility(
            "ruby", target_lang="rust",
            file_count=200, function_count=1000,
        )
        assert r.confidence >= 0.0


# ---------------------------------------------------------------------------
# get_recommended_target
# ---------------------------------------------------------------------------

class TestGetRecommendedTarget:
    @pytest.mark.parametrize("source,expected", [
        ("javascript", "typescript"),
        ("js",         "typescript"),
        ("typescript", "typescript"),
        ("python",     "python"),
        ("py",         "python"),
        ("go",         "go"),
        ("rust",       None),
        ("ruby",       "python"),
        ("unknown",    None),
        ("cobol",      None),
    ])
    def test_recommended_target(self, source, expected):
        assert get_recommended_target(source) == expected
