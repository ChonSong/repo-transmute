"""Validation module for transpiled code."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ValidationResult:
    """Result of code validation."""

    success: bool
    output: str = ""
    error: str = ""

    def __str__(self):
        if self.success:
            return "✅ Validation passed"
        return f"❌ Validation failed: {self.error}"


@dataclass
class SuiteResult:
    """Result of running a test suite."""

    success: bool
    passed: int = 0
    failed: int = 0
    errors: int = 0
    output: str = ""
    error: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    def __str__(self):
        if self.success:
            return f"✅ All {self.passed} tests passed"
        return f"❌ {self.failed} failed, {self.errors} errors, {self.passed} passed out of {self.total}"


def validate_typescript(file_path: Path) -> ValidationResult:
    """Validate TypeScript using tsc --noEmit."""
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")

    try:
        result = subprocess.run(
            ["tsc", "--noEmit", str(file_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            return ValidationResult(True, output="TypeScript validation passed")
        else:
            return ValidationResult(False, error=result.stderr or result.stdout)

    except FileNotFoundError:
        return ValidationResult(False, error="TypeScript (tsc) not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(False, error="Validation timed out")
    except Exception as e:
        return ValidationResult(False, error=str(e))


def validate_rust(file_path: Path) -> ValidationResult:
    """Validate Rust using cargo check."""
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")

    # Need to get the cargo project directory
    cargo_toml = file_path.parent / "Cargo.toml"

    # If no Cargo.toml, create a temporary one
    if not cargo_toml.exists():
        cargo_content = """[package]
name = "temp"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
reqwest = { version = "0.11", features = ["json"] }
tokio = { version = "1.0", features = ["full"] }
axum = "0.7"
anyhow = "1.0"
"""
        cargo_toml.write_text(cargo_content)

    try:
        result = subprocess.run(
            ["cargo", "check"],
            capture_output=True,
            text=True,
            cwd=file_path.parent,
            timeout=120,
        )

        if result.returncode == 0:
            return ValidationResult(True, output="Rust validation passed")
        else:
            return ValidationResult(False, error=result.stderr or result.stdout)

    except FileNotFoundError:
        return ValidationResult(False, error="Rust (cargo) not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(False, error="Validation timed out")
    except Exception as e:
        return ValidationResult(False, error=str(e))


def validate_go(file_path: Path) -> ValidationResult:
    """Validate Go using go build."""
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")

    try:
        # go build -o /dev/null compiles without writing an output file
        result = subprocess.run(
            ["go", "build", "-o", "/dev/null", str(file_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            return ValidationResult(True, output="Go validation passed")
        else:
            return ValidationResult(False, error=result.stderr or result.stdout)

    except FileNotFoundError:
        return ValidationResult(False, error="Go (go) not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(False, error="Validation timed out")
    except Exception as e:
        return ValidationResult(False, error=str(e))


def validate_python(file_path: Path) -> ValidationResult:
    """Validate Python using py_compile."""
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")

    try:
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return ValidationResult(True, output="Python validation passed")
        else:
            return ValidationResult(False, error=result.stderr)

    except FileNotFoundError:
        return ValidationResult(False, error="Python not installed")
    except Exception as e:
        return ValidationResult(False, error=str(e))


def validate(file_path: Path, language: str) -> ValidationResult:
    """Validate code based on language.

    Args:
        file_path: Path to the code file
        language: Programming language (typescript, rust, python, go)

    Returns:
        ValidationResult
    """
    lang = language.lower()

    if "typescript" in lang or lang == "ts":
        return validate_typescript(file_path)
    elif "rust" in lang:
        return validate_rust(file_path)
    elif "python" in lang or lang == "py":
        return validate_python(file_path)
    elif "go" in lang:
        return validate_go(file_path)
    else:
        return ValidationResult(False, error=f"Unsupported language: {language}")


# ---------------------------------------------------------------------------
# Test execution
# ---------------------------------------------------------------------------

def _detect_test_framework(project_root: Path) -> Optional[str]:
    """Detect which test framework a project uses.

    Checks in order of preference:
    - pytest: pytest.ini, pyproject.toml [tool.pytest], conftest.py
    - jest: package.json with "test" script using jest, jest.config.js
    - vitest: package.json with "test" script using vitest, vitest.config.js
    - go test: go.mod (always available for Go projects)
    - cargo test: Cargo.toml (always available for Rust projects)

    Returns one of: "pytest", "jest", "vitest", "go", "cargo", None
    """
    # Python / pytest
    if (project_root / "pytest.ini").exists():
        return "pytest"
    if (project_root / "pyproject.toml").exists():
        content = (project_root / "pyproject.toml").read_text()
        if "[tool.pytest]" in content or "[tool.pytest_testmon]" in content:
            return "pytest"
    if (project_root / "conftest.py").exists():
        return "pytest"

    # JavaScript / Jest
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


def _parse_pytest_output(output: str) -> SuiteResult:
    """Parse pytest output to extract pass/fail counts."""
    # pytest output: "3 passed, 1 failed in 0.5s"
    # or: "4 passed in 1.2s"
    # or: "1 error"
    total_match = re.search(r"(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    error_match = re.search(r"(\d+) error", output)

    passed = int(total_match.group(1)) if total_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0
    errors = int(error_match.group(1)) if error_match else 0

    # If only "passed" shown (e.g. "4 passed"), no failures
    success = failed == 0 and errors == 0
    return SuiteResult(success=success, passed=passed, failed=failed, errors=errors, output=output)


def _parse_jest_output(output: str) -> SuiteResult:
    """Parse Jest/Vitest JSON output to extract pass/fail counts."""
    # Jest/Vitest JSON output: {"numPassingTests": N, "numFailingTests": M, ...}
    # May be multi-line and embedded in other text.
    try:
        # Match any JSON object containing numPassingTests
        json_pattern = r'\{[^{}]*"numPassingTests":[^{}]*\}'
        json_match = re.search(json_pattern, output)
        if json_match:
            data = json.loads(json_match.group())
            passed = data.get("numPassingTests", 0)
            failed = data.get("numFailingTests", 0)
            return SuiteResult(success=failed == 0, passed=passed, failed=failed, output=output)
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fall back to text parsing: "Tests: 2 passed, 1 failed"
    passed_match = re.search(r"Tests:\s*(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    passed = int(passed_match.group(1)) if passed_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0
    success = failed == 0
    return SuiteResult(success=success, passed=passed, failed=failed, output=output)

def _parse_go_test_output(output: str) -> SuiteResult:
    """Parse 'go test' output to extract pass/fail counts."""
    # go test output: "ok      path/to/pkg   0.123s"
    # or: "FAIL    path/to/pkg   (cached)"
    # or: "--- FAIL: TestName (0.00s)"
    fail_lines = re.findall(r"^--- FAIL: (\S+)", output, re.MULTILINE)
    pass_lines = re.findall(r"^--- PASS: (\S+)", output, re.MULTILINE)

    failed = len(fail_lines)
    passed = len(pass_lines)

    # Also check summary lines
    ok_match = re.search(r"^(ok|FAIL)\s+\S+", output, re.MULTILINE)
    overall_ok = ok_match.group(1) == "ok" if ok_match else None
    if overall_ok is True and failed == 0:
        success = True
    elif overall_ok is False:
        success = False
    else:
        success = failed == 0

    return SuiteResult(success=success, passed=passed, failed=failed, output=output)


def run_tests(
    project_root: Path,
    language: str,
    test_files: Optional[List[Path]] = None,
    timeout: int = 120,
) -> SuiteResult:
    """Run the project's test suite.

    Detects the appropriate test runner from project files and executes
    the full suite. Only runs on the provided test_files if specified;
    otherwise discovers tests from the project root.

    Args:
        project_root: Root directory of the project
        language: Source language ("typescript", "python", "rust", "go")
        test_files: Optional list of specific test files to run
        timeout: Max seconds to wait (default 120)

    Returns:
        TestResult with pass/fail counts and output
    """
    project_root = Path(project_root)
    lang = language.lower()

    if lang in ("python", "py"):
        return _run_python_tests(project_root, test_files, timeout)
    elif lang in ("typescript", "javascript", "ts", "js"):
        return _run_js_tests(project_root, test_files, timeout)
    elif lang == "rust":
        return _run_rust_tests(project_root, test_files, timeout)
    elif lang in ("go", "golang"):
        return _run_go_tests(project_root, test_files, timeout)
    else:
        return SuiteResult(success=False, error=f"No test runner for language: {language}")


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
        # Discover tests in common locations
        for pattern in ("tests/", "test/", "**/test_*.py"):
            cmd.extend(["--ignore=**.venv/**", pattern])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        parsed = _parse_pytest_output(output)
        return parsed
    except FileNotFoundError:
        return SuiteResult(success=False, error="pytest / python3 not installed")
    except subprocess.TimeoutExpired:
        return SuiteResult(success=False, error=f"Tests timed out after {timeout}s")
    except Exception as e:
        return SuiteResult(success=False, error=str(e))


def _run_js_tests(
    project_root: Path,
    test_files: Optional[List[Path]],
    timeout: int,
) -> SuiteResult:
    """Run JavaScript/TypeScript tests via Jest or Vitest."""
    framework = _detect_test_framework(project_root)

    if framework == "vitest":
        cmd = ["npx", "vitest", "run", "--reporter=verbose"]
    elif framework == "jest":
        cmd = ["npx", "jest", "--verbose"]
    else:
        # Try npx --yes to auto-detect
        cmd = ["npx", "--yes", "jest", "--verbose"]

    if test_files:
        # Jest/Vitest accept file paths directly
        cmd.extend(str(f) for f in test_files)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        parsed = _parse_jest_output(output)
        return parsed
    except FileNotFoundError:
        return SuiteResult(success=False, error="npm/npx not installed")
    except subprocess.TimeoutExpired:
        return SuiteResult(success=False, error=f"Tests timed out after {timeout}s")
    except Exception as e:
        return SuiteResult(success=False, error=str(e))


def _run_rust_tests(
    project_root: Path,
    test_files: Optional[List[Path]],
    timeout: int,
) -> SuiteResult:
    """Run Rust tests via cargo test."""
    if not (project_root / "Cargo.toml").exists():
        return SuiteResult(success=False, error="No Cargo.toml found in project root")

    cmd = ["cargo", "test", "--", "--report-time"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=timeout,
        )
        output = result.stdout + result.stderr

        # Parse test results
        passed = len(re.findall(r"^test result: ok", output, re.MULTILINE))
        failed_lines = re.findall(r"^FAILED.*", output, re.MULTILINE)
        failed = len(failed_lines)
        # For cargo test, any non-zero return means failure
        success = result.returncode == 0

        return SuiteResult(
            success=success,
            passed=passed,
            failed=failed,
            output=output,
            error="" if success else "Some tests failed",
        )
    except FileNotFoundError:
        return SuiteResult(success=False, error="cargo not installed")
    except subprocess.TimeoutExpired:
        return SuiteResult(success=False, error=f"Tests timed out after {timeout}s")
    except Exception as e:
        return SuiteResult(success=False, error=str(e))


def _run_go_tests(
    project_root: Path,
    test_files: Optional[List[Path]],
    timeout: int,
) -> SuiteResult:
    """Run Go tests via go test."""
    if not (project_root / "go.mod").exists():
        return SuiteResult(success=False, error="No go.mod found in project root")

    cmd = ["go", "test", "-v", "./..."]
    if test_files:
        # go test ./... doesn't support per-file; warn but continue
        cmd = ["go", "test", "-v"] + [f"./{f.parent.relative_to(project_root)}" for f in test_files]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        parsed = _parse_go_test_output(output)
        # go test returns non-zero on failure
        if result.returncode != 0 and parsed.success:
            parsed.success = False
            parsed.error = "go test exited with non-zero status"
        return parsed
    except FileNotFoundError:
        return SuiteResult(success=False, error="go not installed")
    except subprocess.TimeoutExpired:
        return SuiteResult(success=False, error=f"Tests timed out after {timeout}s")
    except Exception as e:
        return SuiteResult(success=False, error=str(e))
