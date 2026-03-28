"""Tests for validate.py — real-tool validation (tsc, cargo check, py_compile)."""

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from repo_transmute.transpiler.validate import (
    ValidationResult,
    validate_typescript,
    validate_rust,
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

        # cargo.toml does not exist → would create one; patch to avoid fs deps
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

        # When cargo.toml doesn't exist it tries to write one; patch that too
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

    def test_unsupported_language(self):
        r = validate(Path("x.go"), "go")
        assert r.success is False
        assert "unsupported" in r.error.lower()
