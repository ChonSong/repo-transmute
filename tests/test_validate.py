"""Tests for validate.py — real-tool validation (tsc, cargo check, go build, py_compile)."""

import json
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from repo_transmute.transpiler.validate import (
    TestResult,
    _detect_test_framework,
    _parse_pytest_output,
    _parse_jest_output,
    _parse_go_test_output,
    run_tests,
    _run_python_tests,
    _run_js_tests,
    _run_go_tests,
    _run_rust_tests,
    ValidationResult,
    validate_typescript,
    validate_rust,
    validate_go,
    validate_python,
    validate,
)


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_success_true(self):
        r = ValidationResult(success=True, output="all good")
        assert r.success is True
        assert r.output == "all good"
        assert r.error == ""

    def test_success_false(self):
        r = ValidationResult(success=False, error="something broke")
        assert r.success is False
        assert "something broke" in str(r)

    def test_str_success(self):
        r = ValidationResult(success=True)
        assert "✅" in str(r)

    def test_str_failure(self):
        r = ValidationResult(success=False, error="tsc failed")
        assert "❌" in str(r)


# ---------------------------------------------------------------------------
# validate_typescript
# ---------------------------------------------------------------------------

class TestValidateTypeScript:
    def test_file_not_found(self):
        r = validate_typescript(Path("/nonexistent/file.ts"))
        assert r.success is False
        assert "not found" in r.error.lower()

    def test_tsc_not_installed(self, tmp_path):
        f = tmp_path / "x.ts"
        f.write_text("export const x = 1;")

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("tsc not found")):
            r = validate_typescript(f)

        assert r.success is False
        assert "not installed" in r.error.lower()

    def test_tsc_timeout(self, tmp_path):
        f = tmp_path / "x.ts"
        f.write_text("export const x = 1;")

        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("tsc", 60)):
            r = validate_typescript(f)

        assert r.success is False
        assert "timed out" in r.error.lower()

    def test_tsc_returns_zero_is_success(self, tmp_path):
        f = tmp_path / "x.ts"
        f.write_text("export const x: number = 1;")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = validate_typescript(f)

        assert r.success is True

    def test_tsc_returns_nonzero_is_failure(self, tmp_path):
        f = tmp_path / "x.ts"
        f.write_text("export const x: number = 'string';")  # type error

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Type 'string' is not assignable to type 'number'."
        mock_result.stdout = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = validate_typescript(f)

        assert r.success is False
        assert "string" in r.error


# ---------------------------------------------------------------------------
# validate_python
# ---------------------------------------------------------------------------

class TestValidatePython:
    def test_file_not_found(self):
        r = validate_python(Path("/nonexistent/file.py"))
        assert r.success is False
        assert "not found" in r.error.lower()

    def test_py_compile_success(self, tmp_path):
        f = tmp_path / "valid.py"
        f.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = validate_python(f)

        assert r.success is True

    def test_py_compile_syntax_error(self, tmp_path):
        f = tmp_path / "invalid.py"
        f.write_text("def broken(\n    return 42\n")  # syntax error

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "SyntaxError: bad syntax"

        with patch.object(subprocess, "run", return_value=mock_result):
            r = validate_python(f)

        assert r.success is False
        assert "SyntaxError" in r.error

    def test_python_not_installed(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("x = 1\n")

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("python3 not found")):
            r = validate_python(f)

        assert r.success is False
        assert "not installed" in r.error.lower()


# ---------------------------------------------------------------------------
# validate_rust
# ---------------------------------------------------------------------------

class TestValidateRust:
    def test_file_not_found(self):
        r = validate_rust(Path("/nonexistent/file.rs"))
        assert r.success is False
        assert "not found" in r.error.lower()

    def test_cargo_not_installed(self, tmp_path):
        f = tmp_path / "x.rs"
        f.write_text("fn main() {}")

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("cargo not found")):
            r = validate_rust(f)

        assert r.success is False
        assert "not installed" in r.error.lower()

    def test_cargo_timeout(self, tmp_path):
        f = tmp_path / "x.rs"
        f.write_text("fn main() {}")

        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("cargo", 120)):
            r = validate_rust(f)

        assert r.success is False
        assert "timed out" in r.error.lower()

    def test_cargo_check_success(self, tmp_path):
        f = tmp_path / "x.rs"
        f.write_text("fn main() {}\n")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = validate_rust(f)

        assert r.success is True

    def test_cargo_check_fails(self, tmp_path):
        f = tmp_path / "x.rs"
        f.write_text("fn main() { unknown_sym }")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error: cannot find value `unknown_sym`"
        mock_result.stdout = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = validate_rust(f)

        assert r.success is False
        assert "cannot find" in r.error


# ---------------------------------------------------------------------------
# validate_go
# ---------------------------------------------------------------------------

class TestValidateGo:
    def test_file_not_found(self):
        r = validate_go(Path("/nonexistent/file.go"))
        assert r.success is False
        assert "not found" in r.error.lower()

    def test_go_not_installed(self, tmp_path):
        f = tmp_path / "x.go"
        f.write_text("package main\n\nfunc main() {}\n")

        with patch.object(subprocess, "run", side_effect=FileNotFoundError("go not found")):
            r = validate_go(f)

        assert r.success is False
        assert "not installed" in r.error.lower()

    def test_go_timeout(self, tmp_path):
        f = tmp_path / "x.go"
        f.write_text("package main\n\nfunc main() {}\n")

        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("go", 60)):
            r = validate_go(f)

        assert r.success is False
        assert "timed out" in r.error.lower()

    def test_go_build_success(self, tmp_path):
        f = tmp_path / "main.go"
        f.write_text("package main\n\nfunc main() {}\n")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = ""

        with patch.object(subprocess, "run", return_value=mock_result) as mock_run:
            r = validate_go(f)

        assert r.success is True
        # Verify go build was called with -o /dev/null
        call_args = mock_run.call_args
        assert call_args[0][0] == ["go", "build", "-o", "/dev/null", str(f)]

    def test_go_build_fails(self, tmp_path):
        f = tmp_path / "main.go"
        f.write_text("package main\n\nvar undefinedVar int\n\nfunc main() {}\n")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "undefined: undefinedVar"
        mock_result.stdout = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = validate_go(f)

        assert r.success is False
        assert "undefined" in r.error


# ---------------------------------------------------------------------------
# validate (dispatcher)
# ---------------------------------------------------------------------------

class TestValidateDispatcher:
    def test_dispatches_typescript(self, tmp_path):
        f = tmp_path / "x.ts"
        f.write_text("export const x = 1;")

        with patch("repo_transmute.transpiler.validate.validate_typescript",
                   return_value=ValidationResult(success=True)) as mock:
            r = validate(f, "typescript")
            mock.assert_called_once_with(f)

    def test_dispatches_ts_short(self, tmp_path):
        f = tmp_path / "x.ts"
        f.write_text("export const x = 1;")
        with patch("repo_transmute.transpiler.validate.validate_typescript",
                   return_value=ValidationResult(success=True)) as mock:
            r = validate(f, "ts")
            mock.assert_called_once()

    def test_dispatches_python(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("x = 1\n")
        with patch("repo_transmute.transpiler.validate.validate_python",
                   return_value=ValidationResult(success=True)) as mock:
            r = validate(f, "python")
            mock.assert_called_once_with(f)

    def test_dispatches_python_short(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("x = 1\n")
        with patch("repo_transmute.transpiler.validate.validate_python",
                   return_value=ValidationResult(success=True)) as mock:
            r = validate(f, "py")
            mock.assert_called_once()

    def test_dispatches_rust(self, tmp_path):
        f = tmp_path / "x.rs"
        f.write_text("fn main() {}")
        with patch("repo_transmute.transpiler.validate.validate_rust",
                   return_value=ValidationResult(success=True)) as mock:
            r = validate(f, "rust")
            mock.assert_called_once_with(f)

    def test_dispatches_go(self, tmp_path):
        f = tmp_path / "x.go"
        f.write_text("package main\n\nfunc main() {}\n")
        with patch("repo_transmute.transpiler.validate.validate_go",
                   return_value=ValidationResult(success=True)) as mock:
            r = validate(f, "go")
            mock.assert_called_once_with(f)

    def test_dispatches_go_long(self, tmp_path):
        f = tmp_path / "x.go"
        f.write_text("package main\n\nfunc main() {}\n")
        with patch("repo_transmute.transpiler.validate.validate_go",
                   return_value=ValidationResult(success=True)) as mock:
            r = validate(f, "golang")
            mock.assert_called_once_with(f)

    def test_unsupported_language(self):
        r = validate(Path("x.xyz"), "cobol")
        assert r.success is False
        assert "unsupported" in r.error.lower()


# ---------------------------------------------------------------------------
# TestResult
# ---------------------------------------------------------------------------

class TestTestResult:
    def test_success_with_counts(self):
        r = TestResult(success=True, passed=10, failed=0, errors=0)
        assert r.total == 10
        assert r.success is True
        assert "10" in str(r)

    def test_failure_with_counts(self):
        r = TestResult(success=False, passed=8, failed=2, errors=1)
        assert r.total == 11
        assert r.success is False
        assert "2" in str(r)
        assert "8 passed" in str(r)

    def test_str_success(self):
        r = TestResult(success=True, passed=5)
        assert "✅" in str(r)

    def test_str_failure(self):
        r = TestResult(success=False, passed=5, failed=1)
        assert "❌" in str(r)


# ---------------------------------------------------------------------------
# _detect_test_framework
# ---------------------------------------------------------------------------

class TestDetectTestFramework:
    def test_detects_pytest_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        assert _detect_test_framework(tmp_path) == "pytest"

    def test_detects_pytest_from_conftest(self, tmp_path):
        (tmp_path / "conftest.py").write_text("import pytest\n")
        assert _detect_test_framework(tmp_path) == "pytest"

    def test_detects_pytest_from_pytest_ini(self, tmp_path):
        (tmp_path / "pytest.ini").write_text("[pytest]\n")
        assert _detect_test_framework(tmp_path) == "pytest"

    def test_detects_vitest_from_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest run"}})
        )
        assert _detect_test_framework(tmp_path) == "vitest"

    def test_detects_jest_from_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}})
        )
        assert _detect_test_framework(tmp_path) == "jest"

    def test_returns_none_when_no_test_script(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        assert _detect_test_framework(tmp_path) is None

    def test_returns_none_for_empty_dir(self, tmp_path):
        assert _detect_test_framework(tmp_path) is None


# ---------------------------------------------------------------------------
# _parse_pytest_output
# ---------------------------------------------------------------------------

class TestParsePytestOutput:
    def test_parses_passed(self):
        output = "collected 5 items\n\n test_a.py::test_x PASSED [20%]\n===== 5 passed in 0.10s ====="
        r = _parse_pytest_output(output)
        assert r.success is True
        assert r.passed == 5
        assert r.failed == 0
        assert r.errors == 0

    def test_parses_mixed(self):
        output = "3 passed, 1 failed in 1.2s"
        r = _parse_pytest_output(output)
        assert r.success is False
        assert r.passed == 3
        assert r.failed == 1

    def test_parses_errors(self):
        output = "2 passed, 1 error"
        r = _parse_pytest_output(output)
        assert r.success is False
        assert r.errors == 1


# ---------------------------------------------------------------------------
# _parse_jest_output
# ---------------------------------------------------------------------------

class TestParseJestOutput:
    def test_parses_json_success(self):
        output = '{\n  "numPassingTests": 4,\n  "numFailingTests": 0\n}'
        r = _parse_jest_output(output)
        assert r.success is True
        assert r.passed == 4

    def test_parses_json_failure(self):
        output = '{\n  "numPassingTests": 3,\n  "numFailingTests": 2\n}'
        r = _parse_jest_output(output)
        assert r.success is False
        assert r.passed == 3
        assert r.failed == 2

    def test_parses_text_passed(self):
        output = "Test Suites: 1 passed, 2 total\nTests: 5 passed"
        r = _parse_jest_output(output)
        assert r.success is True
        assert r.passed == 5

    def test_parses_text_failed(self):
        output = "Tests: 3 passed, 1 failed"
        r = _parse_jest_output(output)
        assert r.success is False
        assert r.passed == 3
        assert r.failed == 1


# ---------------------------------------------------------------------------
# _parse_go_test_output
# ---------------------------------------------------------------------------

class TestParseGoTestOutput:
    def test_parses_ok_summary(self):
        output = "ok  \tpath/to/pkg  0.005s\n"
        r = _parse_go_test_output(output)
        assert r.success is True

    def test_parses_fail_summary(self):
        output = "FAIL\tpath/to/pkg\t0.001s\n--- FAIL: TestFoo (0.00s)"
        r = _parse_go_test_output(output)
        assert r.success is False

    def test_parses_pass_fail_lines(self):
        output = "--- PASS: TestFoo (0.00s)\n--- PASS: TestBar (0.00s)\n--- FAIL: TestBaz (0.00s)"
        r = _parse_go_test_output(output)
        assert r.success is False
        assert r.passed == 2
        assert r.failed == 1


# ---------------------------------------------------------------------------
# run_tests — dispatch
# ---------------------------------------------------------------------------

class TestRunTests:
    def test_runs_python_via_pytest(self, tmp_path):
        (tmp_path / "conftest.py").write_text("")
        (tmp_path / "test_foo.py").write_text("def test_foo(): pass\n")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "1 passed"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result) as mock_run:
            r = run_tests(tmp_path, "python")
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert "pytest" in args or "pytest" in " ".join(args)

    def test_runs_go_via_go_test(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example\n")
        (tmp_path / "example_test.go").write_text("package example\n\nfunc TestFoo(t *testing.T) {}\n")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok  \texample  0.001s\n"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result) as mock_run:
            r = run_tests(tmp_path, "go")
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert args[0] == "go"

    def test_runs_rust_via_cargo_test(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'example'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src/lib.rs").write_text("")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests/test_foo.rs").write_text("#[test] fn test_foo() {}")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test result: ok. 1 passed"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result) as mock_run:
            r = run_tests(tmp_path, "rust")
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert args[0] == "cargo"

    def test_unsupported_language_returns_error(self, tmp_path):
        r = run_tests(tmp_path, "cobol")
        assert r.success is False
        assert "cobol" in r.error


# ---------------------------------------------------------------------------
# run_tests — Python
# ---------------------------------------------------------------------------

class TestRunPythonTests:
    def test_python_not_installed(self, tmp_path):
        with patch.object(subprocess, "run", side_effect=FileNotFoundError()):
            r = _run_python_tests(tmp_path, None, 30)
        assert r.success is False
        assert "not installed" in r.error.lower()

    def test_python_timeout(self, tmp_path):
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("pytest", 30)):
            r = _run_python_tests(tmp_path, None, 30)
        assert r.success is False
        assert "timed out" in r.error.lower()

    def test_python_pytest_passes(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "3 passed in 0.5s"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = _run_python_tests(tmp_path, None, 30)

        assert r.success is True
        assert r.passed == 3

    def test_python_pytest_fails(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "2 passed, 1 failed"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = _run_python_tests(tmp_path, None, 30)

        assert r.success is False
        assert r.failed == 1


# ---------------------------------------------------------------------------
# run_tests — JavaScript
# ---------------------------------------------------------------------------

class TestRunJSTests:
    def test_js_npm_not_installed(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        with patch.object(subprocess, "run", side_effect=FileNotFoundError()):
            r = _run_js_tests(tmp_path, None, 60)
        assert r.success is False
        assert "not installed" in r.error.lower()

    def test_js_vitest_passes(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}))
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Tests: 4 passed"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = _run_js_tests(tmp_path, None, 60)

        assert r.success is True
        assert r.passed == 4

    def test_js_jest_passes(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"numPassingTests": 2, "numFailingTests": 0}'
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = _run_js_tests(tmp_path, None, 60)

        assert r.success is True
        assert r.passed == 2


# ---------------------------------------------------------------------------
# run_tests — Go
# ---------------------------------------------------------------------------

class TestRunGoTests:
    def test_go_no_gomod(self, tmp_path):
        r = _run_go_tests(tmp_path, None, 60)
        assert r.success is False
        assert "go.mod" in r.error

    def test_go_not_installed(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example\n")
        with patch.object(subprocess, "run", side_effect=FileNotFoundError()):
            r = _run_go_tests(tmp_path, None, 60)
        assert r.success is False
        assert "not installed" in r.error.lower()

    def test_go_test_passes(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example\n")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok  \texample  0.001s\n"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = _run_go_tests(tmp_path, None, 60)

        assert r.success is True

    def test_go_test_fails(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example\n")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "FAIL\texample\n--- FAIL: TestFoo (0.00s)"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = _run_go_tests(tmp_path, None, 60)

        assert r.success is False
        assert r.failed >= 1


# ---------------------------------------------------------------------------
# run_tests — Rust
# ---------------------------------------------------------------------------

class TestRunRustTests:
    def test_rust_no_cargo_toml(self, tmp_path):
        r = _run_rust_tests(tmp_path, None, 120)
        assert r.success is False
        assert "Cargo.toml" in r.error

    def test_rust_not_installed(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n")
        with patch.object(subprocess, "run", side_effect=FileNotFoundError()):
            r = _run_rust_tests(tmp_path, None, 120)
        assert r.success is False
        assert "not installed" in r.error.lower()

    def test_rust_test_passes(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test result: ok. 2 passed"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            r = _run_rust_tests(tmp_path, None, 120)

        assert r.success is True

    def test_rust_test_fails(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "test result: FAILED"
        mock_result.stderr = "cargo: test failed"

        with patch.object(subprocess, "run", return_value=mock_result):
            r = _run_rust_tests(tmp_path, None, 120)

        assert r.success is False
