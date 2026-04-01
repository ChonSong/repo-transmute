"""Tests for go_test_gen.py — Go test stub generation."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from repo_transmute.transpiler.go_test_gen import (
    _to_test_name,
    _param_names,
    _needs_import,
    _suggest_imports,
    generate_test_stub,
    generate_test_file,
    generate_test_file_for_methods,
    _detect_package_name,
    write_test_files,
)
from repo_transmute.transpiler.go_parser import GoImport


FIXTURE = Path(__file__).parent / "fixtures" / "sample.go"
FIXTURE_COMPLEX = Path(__file__).parent / "fixtures" / "sample_go_complex.go"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestToTestName:
    def test_adds_test_prefix(self):
        assert _to_test_name("Add") == "TestAdd"

    def test_already_has_test_prefix(self):
        assert _to_test_name("TestAdd") == "TestAdd"

    def test_lowercases_second_char(self):
        assert _to_test_name("addNumbers") == "TestAddNumbers"

    def test_single_char_name(self):
        assert _to_test_name("A") == "TestA"


class TestParamNames:
    def test_single_param(self):
        assert _param_names("a int") == ["a"]

    def test_multiple_params(self):
        assert _param_names("a int, b string") == ["a", "b"]

    def test_no_params(self):
        assert _param_names("") == []
        assert _param_names("   ") == []

    def test_with_type_only(self):
        assert _param_names("ctx context.Context") == ["ctx"]


class TestNeedsImport:
    def test_finds_existing_import(self):
        imports = [GoImport(path="fmt"), GoImport(path="os")]
        assert _needs_import(imports, "fmt") is True

    def test_missing_import(self):
        imports = [GoImport(path="fmt")]
        assert _needs_import(imports, "os") is False


class TestSuggestImports:
    def test_suggests_errors_for_error_return(self):
        info = {"signature": "(a int) error", "body": ""}
        assert "errors" in _suggest_imports(info)

    def test_suggests_fmt_for_complex_return(self):
        info = {"signature": "(a int) []string", "body": ""}
        assert "fmt" in _suggest_imports(info)

    def test_suggests_reflect_for_deepequal(self):
        info = {"signature": "(a int) bool", "body": "reflect.DeepEqual(a, b)"}
        assert "reflect" in _suggest_imports(info)

    def test_suggests_json_for_json_body(self):
        info = {"signature": "(a int) string", "body": "json.Unmarshal(data, &v)"}
        assert "encoding/json" in _suggest_imports(info)


# ---------------------------------------------------------------------------
# generate_test_stub
# ---------------------------------------------------------------------------

class TestGenerateTestStub:
    def test_simple_function_no_return(self):
        info = {
            "name": "Add",
            "signature": "(a, b int)",
            "body": "return a + b",
            "is_method": False,
            "receiver": None,
        }
        stub = generate_test_stub(info)
        assert "TestAdd" in stub
        assert "testing.T" in stub

    def test_function_with_return_type(self):
        info = {
            "name": "Add",
            "signature": "(a, b int) int",
            "body": "return a + b",
            "is_method": False,
            "receiver": None,
        }
        stub = generate_test_stub(info)
        assert "var want int" in stub
        assert 'got != want' in stub

    def test_function_returning_error(self):
        info = {
            "name": "ReadFile",
            "signature": "(path string) ([]byte, error)",
            "body": "",
            "is_method": False,
            "receiver": None,
        }
        stub = generate_test_stub(info)
        assert 'got != nil' in stub
        assert 'want nil' in stub

    def test_method_includes_receiver_note(self):
        info = {
            "name": "Greet",
            "signature": "() string",
            "body": "",
            "is_method": True,
            "receiver": "p *Person",
        }
        stub = generate_test_stub(info)
        assert "TestGreet" in stub
        assert "Person" in stub
        assert "receiver" in stub

    def test_no_return_no_params(self):
        info = {
            "name": "Init",
            "signature": "()",
            "body": "",
            "is_method": False,
            "receiver": None,
        }
        stub = generate_test_stub(info)
        assert "TestInit" in stub
        assert "t.Log" in stub  # unimplemented marker


# ---------------------------------------------------------------------------
# _detect_package_name
# ---------------------------------------------------------------------------

class TestDetectPackageName:
    def test_finds_package(self):
        content = "package main\nfunc main() {}"
        assert _detect_package_name(content) == "main"

    def test_handles_package_with_comments(self):
        content = "// comment\npackage fixtures\n"
        assert _detect_package_name(content) == "fixtures"


# ---------------------------------------------------------------------------
# generate_test_file
# ---------------------------------------------------------------------------

class TestGenerateTestFile:
    def test_package_line(self):
        content = generate_test_file(FIXTURE)
        lines = content.splitlines()
        assert any("package fixtures_test" in l for l in lines)

    def test_import_testing(self):
        content = generate_test_file(FIXTURE)
        assert '"testing"' in content

    def test_adds_original_imports(self):
        content = generate_test_file(FIXTURE)
        # The sample.go has "fmt" import
        assert "fmt" in content

    def test_generates_test_for_add(self):
        content = generate_test_file(FIXTURE)
        assert "TestAdd" in content

    def test_generates_test_for_greet(self):
        content = generate_test_file(FIXTURE)
        assert "TestGreet" in content

    def test_excludes_methods(self):
        content = generate_test_file(FIXTURE)
        # Greet as a top-level function should be tested
        # Greet as a method on Person should NOT get a separate test
        # (it's a method, so it goes in generate_test_file_for_methods)
        assert "func (p *Person)" not in content

    def test_filters_to_specific_functions(self):
        content = generate_test_file(FIXTURE, funcs_to_test=["Add"])
        assert "TestAdd" in content
        assert "TestGreet" not in content

    def test_handles_complex_fixture(self):
        content = generate_test_file(FIXTURE_COMPLEX)
        # Should have tests for top-level functions only
        assert "TestAdd" in content
        assert "TestProcessWithCallback" in content
        assert "TestWithDefaults" in content
        assert "TestStringWithBraces" in content
        # Methods should NOT appear as top-level tests
        assert "(p *Person)" not in content
        assert "(c *Config)" not in content


# ---------------------------------------------------------------------------
# generate_test_file_for_methods
# ---------------------------------------------------------------------------

class TestGenerateTestFileForMethods:
    def test_generates_tests_for_person_methods(self):
        content = generate_test_file_for_methods(FIXTURE, "Person")
        assert "TestGreet" in content
        assert "TestSum" in content

    def test_generates_tests_for_config_methods(self):
        content = generate_test_file_for_methods(FIXTURE_COMPLEX, "Config")
        assert "TestLongMethod" in content

    def test_empty_for_unknown_struct(self):
        content = generate_test_file_for_methods(FIXTURE, "UnknownStruct")
        assert "No methods found" in content

    def test_includes_receiver_note(self):
        content = generate_test_file_for_methods(FIXTURE, "Person")
        assert "Person" in content


# ---------------------------------------------------------------------------
# write_test_files
# ---------------------------------------------------------------------------

class TestWriteTestFiles:
    def test_writes_test_file(self, tmp_path: Path):
        # Copy sample.go to tmp dir
        src = FIXTURE
        dst = tmp_path / "sample.go"
        dst.write_text(src.read_text())

        generated = write_test_files(tmp_path)

        assert len(generated) >= 1
        test_file = generated[0]
        assert test_file.exists()
        assert test_file.name == "sample_test.go"
        content = test_file.read_text()
        assert "TestAdd" in content
        assert "TestGreet" in content

    def test_skips_test_files(self, tmp_path: Path):
        # Create a _test.go file — should be skipped
        test_src = tmp_path / "sample_test.go"
        test_src.write_text("package main\n")
        src = tmp_path / "sample.go"
        src.write_text("package main\nfunc Add(a, b int) int { return a + b }")

        generated = write_test_files(tmp_path)

        # Should only generate for sample.go, not sample_test.go
        assert len(generated) == 1
        assert generated[0].name == "sample_test.go"
