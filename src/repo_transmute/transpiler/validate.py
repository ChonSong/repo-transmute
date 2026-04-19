"""Validation module for transpiled code — real-tool validation and test execution."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of code validation (type-checking / compilation)."""

    success: bool
    output: str = ""
    error: str = ""
    timeout: bool = False

    def __str__(self) -> str:
        if self.timeout:
            return f"⏰ Validation timed out: {self.error}"
        if self.success:
            return "✅ Validation passed"
        return f"❌ Validation failed: {self.error}"


@dataclass
class SuiteResult:
    """Result of running a project's test suite."""

    success: bool
    passed: int = 0
    failed: int = 0
    errors: int = 0
    output: str = ""
    error: str = ""
    timeout: bool = False

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    def __str__(self) -> str:
        if self.timeout:
            return f"⏰ Tests timed out: {self.error}"
        if self.success:
            return f"✅ All {self.passed} tests passed"
        return (
            f"❌ {self.failed} failed, {self.errors} errors, "
            f"{self.passed} passed out of {self.total}"
        )


# ---------------------------------------------------------------------------
# Code validation — single file / project-level
# ---------------------------------------------------------------------------

def _find_tsconfig(start: Path) -> Optional[Path]:
    """Walk upward from start looking for the closest tsconfig.json."""
    current = start.resolve()
    for parent in [current] + list(current.parents):
        candidate = parent / "tsconfig.json"
        if candidate.is_file():
            return candidate
        if parent == parent.parent:
            break
    return None


def _find_package_json(start: Path) -> Optional[Path]:
    """Walk upward from start looking for the closest package.json."""
    current = start.resolve()
    for parent in [current] + list(current.parents):
        candidate = parent / "package.json"
        if candidate.is_file():
            return candidate
        if parent == parent.parent:
            break
    return None


def validate_typescript(file_path: Path) -> ValidationResult:
    """Validate TypeScript using tsc --noEmit.

    Uses project-level validation when a tsconfig.json is found,
    falling back to single-file validation otherwise.
    """
    if not file_path.exists():
        return ValidationResult(success=False, error=f"File not found: {file_path}")

    tsconfig = _find_tsconfig(file_path)

    try:
        if tsconfig:
            result = subprocess.run(
                ["tsc", "--noEmit", "--project", str(tsconfig.parent)],
                capture_output=True, text=True, timeout=120,
            )
        else:
            result = subprocess.run(
                ["tsc", "--noEmit", str(file_path)],
                capture_output=True, text=True, timeout=60,
            )

        if result.returncode == 0:
            return ValidationResult(success=True, output="TypeScript validation passed")
        return ValidationResult(success=False, error=(result.stderr or result.stdout).strip())

    except FileNotFoundError:
        return ValidationResult(success=False, error="TypeScript (tsc) not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(success=False, error="Validation timed out", timeout=True)
    except Exception as e:
        return ValidationResult(success=False, error=str(e))


def validate_python(file_path: Path) -> ValidationResult:
    """Validate Python using py_compile."""
    if not file_path.exists():
        return ValidationResult(success=False, error=f"File not found: {file_path}")

    try:
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return ValidationResult(success=True, output="Python validation passed")
        return ValidationResult(success=False, error=result.stderr.strip())

    except FileNotFoundError:
        return ValidationResult(success=False, error="Python not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(success=False, error="Validation timed out", timeout=True)
    except Exception as e:
        return ValidationResult(success=False, error=str(e))


def validate_rust(file_path: Path) -> ValidationResult:
    """Validate Rust using cargo check."""
    if not file_path.exists():
        return ValidationResult(success=False, error=f"File not found: {file_path}")

    cargo_toml = file_path.parent / "Cargo.toml"

    if not cargo_toml.exists():
        cargo_toml.write_text(
            "[package]\nname = 'temp'\nversion = '0.1.0'\nedition = '2021'\n"
            "[dependencies]\nserde = { version = '1.0', features = ['derive'] }\n"
            "serde_json = '1.0'\n"
        )

    try:
        result = subprocess.run(
            ["cargo", "check"],
            capture_output=True, text=True,
            cwd=file_path.parent, timeout=120,
        )
        if result.returncode == 0:
            return ValidationResult(success=True, output="Rust validation passed")
        return ValidationResult(success=False, error=(result.stderr or result.stdout).strip())

    except FileNotFoundError:
        return ValidationResult(success=False, error="Rust (cargo) not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(success=False, error="Validation timed out", timeout=True)
    except Exception as e:
        return ValidationResult(success=False, error=str(e))


def validate_go(file_path: Path) -> ValidationResult:
    """Validate Go using go build."""
    if not file_path.exists():
        return ValidationResult(success=False, error=f"File not found: {file_path}")

    try:
        result = subprocess.run(
            ["go", "build", "-o", "/dev/null", str(file_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return ValidationResult(success=True, output="Go validation passed")
        return ValidationResult(success=False, error=(result.stderr or result.stdout).strip())

    except FileNotFoundError:
        return ValidationResult(success=False, error="Go (go) not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(success=False, error="Validation timed out", timeout=True)
    except Exception as e:
        return ValidationResult(success=False, error=str(e))


def validate(file_path: Path, language: str) -> ValidationResult:
    """Validate a file based on its language."""
    lang = language.lower()

    if "typescript" in lang or lang in ("ts", "tsx"):
        return validate_typescript(file_path)
    if "rust" in lang:
        return validate_rust(file_path)
    if "python" in lang or lang in ("py", "pyw"):
        return validate_python(file_path)
    if "go" in lang or lang in ("golang",):
        return validate_go(file_path)
    # JavaScript: tsc validates JS as valid TS subset
    if lang in ("javascript", "js", "jsx"):
        return validate_typescript(file_path)

    return ValidationResult(success=False, error=f"Unsupported language: {language}")


# ---------------------------------------------------------------------------
# Test framework detection
# ---------------------------------------------------------------------------

def _detect_test_framework(project_root: Path) -> Optional[str]:
    """Detect which test framework a project uses.

    Checks in order:
    - pytest: pytest.ini, pyproject.toml [tool.pytest], conftest.py
    - vitest: vitest.config.* or "vitest" in package.json test script
    - jest: jest.config.* or "jest" in package.json test script
    - go test: go.mod present
    - cargo test: Cargo.toml present
    """
    project_root = Path(project_root)

    # Python / pytest
    if (project_root / "pytest.ini").exists():
        return "pytest"
    if (project_root / "pyproject.toml").exists():
        content = (project_root / "pyproject.toml").read_text()
        if "[tool.pytest]" in content:
            return "pytest"
    if (project_root / "conftest.py").exists():
        return "pytest"

    # JavaScript / Vitest — check config files first
    for config in ("vitest.config.ts", "vitest.config.js", "vitest.config.mts"):
        if (project_root / config).exists():
            return "vitest"

    # JavaScript / Jest — check config files first
    for config in ("jest.config.ts", "jest.config.js", "jest.config.cjs"):
        if (project_root / config).exists():
            return "jest"

    # Fall back to package.json scripts
    pkg_json = project_root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            test_script = scripts.get("test", "")
            if not test_script:
                return None
            if "vitest" in test_script:
                return "vitest"
            if "jest" in test_script or "react-scripts test" in test_script:
                return "jest"
        except (json.JSONDecodeError, OSError):
            pass

    return None


# ---------------------------------------------------------------------------
# Output parsers
# ---------------------------------------------------------------------------

def _parse_pytest_output(output: str) -> SuiteResult:
    """Parse pytest output to extract pass/fail/error counts."""
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", output)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", output)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", output)) else 0
    success = failed == 0 and errors == 0
    return SuiteResult(success=success, passed=passed, failed=failed, errors=errors, output=output)


def _parse_jest_output(output: str) -> SuiteResult:
    """Parse Jest/Vitest JSON output (or text fallback).

    Handles multiple output formats:
    - Jest JSON: {"numPassingTests": N, "numFailingTests": M}
    - Vitest v4 text: "Tests  N passed (N)" or "Tests  N failed | M passed (N)"
    """
    # Try JSON first (Jest's --json reporter format)
    try:
        match = re.search(r'\{[^}]*"numPassingTests"[^}]*\}', output)
        if match:
            data = json.loads(match.group())
            passed = data.get("numPassingTests", 0)
            failed = data.get("numFailingTests", 0)
            return SuiteResult(success=failed == 0, passed=passed, failed=failed, output=output)
    except (json.JSONDecodeError, AttributeError):
        pass

    # Text fallback — Vitest v4 verbose output format:
    # "Tests  N passed" or "Tests  N failed | M passed" on a single line
    # Also handles: "Test Files  N passed (N)" followed by "Tests  M passed (M)"
    passed_m = re.search(r'Tests\b[^\n]*?(\d+)\s+passed', output)
    failed_m = re.search(r'Tests\b[^\n]*?(\d+)\s+failed', output)
    passed = int(passed_m.group(1)) if passed_m else 0
    failed = int(failed_m.group(1)) if failed_m else 0
    return SuiteResult(success=failed == 0, passed=passed, failed=failed, output=output)


def _parse_go_test_output(output: str) -> SuiteResult:
    """Parse go test output."""
    fail_lines = re.findall(r"^--- FAIL: (\S+)", output, re.MULTILINE)
    pass_lines = re.findall(r"^--- PASS: (\S+)", output, re.MULTILINE)
    failed = len(fail_lines)
    passed = len(pass_lines)

    ok_match = re.search(r"^(ok|FAIL)\s+\S+", output, re.MULTILINE)
    if ok_match:
        success = ok_match.group(1) == "ok" and failed == 0
    else:
        success = failed == 0

    return SuiteResult(success=success, passed=passed, failed=failed, output=output)


# ---------------------------------------------------------------------------
# Test execution — top-level dispatcher
# ---------------------------------------------------------------------------

def run_tests(
    project_root: Path,
    language: str,
    test_files: Optional[List[Path]] = None,
    timeout: int = 120,
) -> SuiteResult:
    """Run the project's test suite for the given language."""
    project_root = Path(project_root)
    lang = language.lower()

    if lang in ("python", "py"):
        return _run_python_tests(project_root, test_files, timeout)
    if lang in ("typescript", "javascript", "ts", "tsx", "js", "jsx"):
        return _run_js_tests(project_root, test_files, timeout)
    if lang == "rust":
        return _run_rust_tests(project_root, test_files, timeout)
    if lang in ("go", "golang"):
        return _run_go_tests(project_root, test_files, timeout)

    return SuiteResult(success=False, error=f"No test runner for language: {language}")


# ---------------------------------------------------------------------------
# Python test execution
# ---------------------------------------------------------------------------

def _run_python_tests(
    project_root: Path,
    test_files: Optional[List[Path]],
    timeout: int,
) -> SuiteResult:
    """Run Python tests via pytest."""
    framework = _detect_test_framework(project_root)
    if framework not in ("pytest", None):
        return SuiteResult(success=False, error=f"Unhandled Python framework: {framework}")

    cmd = ["python3", "-m", "pytest", "--tb=short"]
    if test_files:
        cmd.extend(str(f) for f in test_files)
    else:
        cmd.extend(["--ignore=**.venv/**", "--ignore=**/__pycache__**", "tests/", "test/"])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=project_root, timeout=timeout,
        )
        return _parse_pytest_output(result.stdout + result.stderr)

    except FileNotFoundError:
        return SuiteResult(success=False, error="python3 / pytest not installed")
    except subprocess.TimeoutExpired:
        return SuiteResult(success=False, error=f"Tests timed out after {timeout}s", timeout=True)
    except Exception as e:
        return SuiteResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# JavaScript / TypeScript test execution
# ---------------------------------------------------------------------------

def _run_js_tests(
    project_root: Path,
    test_files: Optional[List[Path]],
    timeout: int,
) -> SuiteResult:
    """Run JavaScript/TypeScript tests via Vitest or Jest.

    Auto-detects the framework using:
    1. Config files (vitest.config.*, jest.config.*)
    2. package.json scripts
    3. npx vitest --passWithNoTests as last resort
    """
    project_root = Path(project_root)

    if not _is_command_available("npm"):
        return SuiteResult(success=False, error="npm not installed")

    framework = _detect_test_framework(project_root)

    if framework == "vitest":
        cmd = ["npx", "vitest", "run", "--reporter=verbose"]
    elif framework == "jest":
        cmd = ["npx", "jest", "--verbose", "--passWithNoTests"]
    else:
        # Auto-detect: try npm run test first, then vitest auto
        pkg_json = project_root / "package.json"
        has_test_script = False
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                has_test_script = bool(pkg.get("scripts", {}).get("test"))
            except (json.JSONDecodeError, OSError):
                pass

        if has_test_script:
            cmd = ["npm", "run", "test", "--", "--passWithNoTests"]
        else:
            cmd = ["npx", "--yes", "vitest", "run", "--passWithNoTests"]

    if test_files:
        cmd.extend(str(f) for f in test_files)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=project_root, timeout=timeout,
        )
        output = result.stdout + result.stderr
        parsed = _parse_jest_output(output)

        if result.returncode != 0 and parsed.success:
            parsed.success = False
            parsed.error = f"Test runner exited with code {result.returncode}"

        return parsed

    except subprocess.TimeoutExpired:
        return SuiteResult(success=False, error=f"Tests timed out after {timeout}s", timeout=True)
    except FileNotFoundError:
        return SuiteResult(success=False, error="npm/npx not installed")
    except Exception as e:
        return SuiteResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Rust test execution
# ---------------------------------------------------------------------------

def _run_rust_tests(
    project_root: Path,
    test_files: Optional[List[Path]],
    timeout: int,
) -> SuiteResult:
    """Run Rust tests via cargo test."""
    project_root = Path(project_root)
    if not (project_root / "Cargo.toml").exists():
        return SuiteResult(success=False, error="No Cargo.toml found in project root")

    cmd = ["cargo", "test"]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=project_root, timeout=timeout,
        )
        output = result.stdout + result.stderr

        # Extract actual test counts from cargo output
        # Format: "test result: ok. N passed; M failed; ..."
        # or: "test result: FAILED. N passed; M failed; ..."
        # Note: FAILED lines also report passed count (tests that passed before failure)
        passed = 0
        failed = 0
        for line in output.splitlines():
            m = re.search(r"test result: (?:ok|FAILED)\. (\d+) passed", line)
            if m:
                n = int(m.group(1))
                passed += n
            # Also extract failed count from FAILED lines
            fm = re.search(r"test result: FAILED\. (?:\d+) passed; (\d+) failed", line)
            if fm:
                failed += int(fm.group(1))
        success = result.returncode == 0

        return SuiteResult(
            success=success, passed=passed, failed=failed,
            output=output, error="" if success else "Some tests failed",
        )

    except FileNotFoundError:
        return SuiteResult(success=False, error="cargo not installed")
    except subprocess.TimeoutExpired:
        return SuiteResult(success=False, error=f"Tests timed out after {timeout}s", timeout=True)
    except Exception as e:
        return SuiteResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Go test execution
# ---------------------------------------------------------------------------

def _run_go_tests(
    project_root: Path,
    test_files: Optional[List[Path]],
    timeout: int,
) -> SuiteResult:
    """Run Go tests via go test."""
    project_root = Path(project_root)
    if not (project_root / "go.mod").exists():
        return SuiteResult(success=False, error="No go.mod found in project root")

    cmd = ["go", "test", "-v", "./..."]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=project_root, timeout=timeout,
        )
        output = result.stdout + result.stderr
        parsed = _parse_go_test_output(output)

        if result.returncode != 0 and parsed.success:
            parsed.success = False
            parsed.error = f"go test exited with code {result.returncode}"

        return parsed

    except FileNotFoundError:
        return SuiteResult(success=False, error="go not installed")
    except subprocess.TimeoutExpired:
        return SuiteResult(success=False, error=f"Tests timed out after {timeout}s", timeout=True)
    except Exception as e:
        return SuiteResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _is_command_available(cmd: str) -> bool:
    """Return True if a command is on PATH."""
    return shutil.which(cmd) is not None
