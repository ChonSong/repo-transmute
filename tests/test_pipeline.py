"""Tests for PipelineCoordinator — transpile_chunk, reassembler, validation."""

import pytest
import tempfile
import yaml
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

from repo_transmute.blueprint import Blueprint
from repo_transmute.blueprint.extractor import Function, DataStructure
from repo_transmute.pipeline.coordinator import (
    PipelineCoordinator,
    IntegrationValidator,
    generate_module_tests,
    ValidationReport,
    PipelineResult,
)
from repo_transmute.transpiler.chunker import Chunk, Reassembler, chunk_repository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_functions():
    return [
        Function(
            name="add",
            signature="(a: int, b: int)",
            file="math_ops.py",
            line=1,
            async_flag=False,
            docstring="Add two numbers",
            decorators=["staticmethod"],
            body="def add(a, b):\n    return a + b",
        ),
        Function(
            name="multiply",
            signature="(x, y)",
            file="math_ops.py",
            line=10,
            async_flag=False,
            docstring=None,
            decorators=[],
            body="def multiply(x, y):\n    return x * y",
        ),
    ]


@pytest.fixture
def sample_data_structures():
    return [
        DataStructure(
            name="Config",
            type="class",
            file="config.py",
            line=5,
            fields=["host", "port"],
            docstring="Application configuration",
            methods=[
                Function(
                    name="load",
                    signature="()",
                    file="config.py",
                    line=10,
                    async_flag=False,
                    docstring=None,
                    decorators=[],
                    body="def load(self):\n    pass",
                )
            ],
        )
    ]


@pytest.fixture
def sample_blueprint(sample_functions, sample_data_structures):
    return Blueprint(
        repo="test-repo",
        language="python",
        functions=sample_functions,
        data_structures=sample_data_structures,
    )


@pytest.fixture
def sample_chunks(tmp_path):
    """Two chunks with a dependency relationship."""
    (tmp_path / "math_ops.py").write_text("def add(a, b): return a + b\ndef multiply(x, y): return x * y\n")
    (tmp_path / "config.py").write_text("class Config:\n    def __init__(self): self.host = 'localhost'\n")

    chunk0 = Chunk(
        id=0,
        files=[tmp_path / "math_ops.py"],
        imports=["os", "sys"],
        exports=["add", "multiply"],
        dependencies=[],
    )
    chunk1 = Chunk(
        id=1,
        files=[tmp_path / "config.py"],
        imports=["os"],
        exports=["Config"],
        dependencies=[0],
    )
    return [chunk0, chunk1]


# ---------------------------------------------------------------------------
# IntegrationValidator
# ---------------------------------------------------------------------------

from repo_transmute.transpiler.validate import ValidationResult
class TestIntegrationValidator:
    def test_validate_ts_imports_missing_extension_is_flagged(self):
        """Missing extension on relative import is correctly flagged."""
        v = IntegrationValidator(target_lang="typescript")
        code = "import { foo } from './bar';"  # no extension
        result = v.validate_imports(code)
        assert result is False
        assert any("Missing extension" in e for e in v.import_errors)

    def test_validate_ts_imports_valid_js_extension(self):
        """Relative imports with .js extension are valid."""
        v = IntegrationValidator(target_lang="typescript")
        code = "import { foo } from './bar.js';"
        assert v.validate_imports(code) is True

    def test_validate_ts_imports_valid_ts_extension(self):
        """Relative imports with .ts extension are valid."""
        v = IntegrationValidator(target_lang="typescript")
        code = "import { foo } from './bar.ts';"
        assert v.validate_imports(code) is True

    def test_validate_ts_imports_npm_package(self):
        """npm package imports (no relative path) are not flagged."""
        v = IntegrationValidator(target_lang="typescript")
        code = "import { foo } from 'lodash';\nimport { bar } from '@org/lib';"
        assert v.validate_imports(code) is True

    def test_validate_ts_imports_deep_relative(self):
        """Deep relative paths with no extension are flagged."""
        v = IntegrationValidator(target_lang="typescript")
        code = "import { foo } from '../../../utils/helper';"
        result = v.validate_imports(code)
        assert result is False

    def test_validate_ts_types_any_usage(self):
        v = IntegrationValidator(target_lang="typescript")
        code = "function foo(x: any): any { return x; }"
        result = v.validate_types(code)
        assert result is False
        assert any("'any'" in e for e in v.type_errors)

    def test_validate_ts_types_no_any(self):
        v = IntegrationValidator(target_lang="typescript")
        code = "function foo(x: string): string { return x; }"
        assert v.validate_types(code) is True

    def test_validate_ts_types_no_type_definitions(self):
        """A class-only file (no interface/type) is flagged as missing type definitions."""
        v = IntegrationValidator(target_lang="typescript")
        code = "class Foo { }"  # no interface, no type
        result = v.validate_types(code)
        assert result is False
        assert any("No type definitions" in e for e in v.type_errors)

    def test_validate_ts_types_interface_ok(self):
        """A class with an interface is fine."""
        v = IntegrationValidator(target_lang="typescript")
        code = "interface IFoo { }\nclass Foo implements IFoo { }"
        assert v.validate_types(code) is True

    def test_validate_python_imports_via_public_api(self):
        """Use public validate_imports() to check Python code; _validate_python_imports
        is called internally and populates import_errors."""
        v = IntegrationValidator(target_lang="python")
        code = "import os\nfrom typing import Optional"
        result = v.validate_imports(code)
        assert result is True
        assert v.import_errors == []

    def test_validate_python_imports_invalid_module_via_public_api(self):
        """Invalid module name is flagged via public validate_imports()."""
        v = IntegrationValidator(target_lang="python")
        code = "import 123invalid"
        result = v.validate_imports(code)
        assert result is False

    def test_generate_report(self):
        v = IntegrationValidator(target_lang="typescript")
        v.import_errors = ["Missing extension"]
        v.type_errors = ["Found 2 'any' type annotations"]
        report = v.generate_report()
        assert report.import_valid is False
        assert report.type_valid is False
        assert len(report.errors) == 2
        assert report.is_valid is False

    # -----------------------------------------------------------------------
    # Go validation
    # -----------------------------------------------------------------------
    def test_go_validate_imports_missing_package(self):
        v = IntegrationValidator(target_lang="go")
        code = "func main() {}"
        result = v.validate_imports(code)
        assert result is False
        assert any("package declaration" in e for e in v.import_errors)

    def test_go_validate_imports_bare_unquoted(self):
        v = IntegrationValidator(target_lang="go")
        code = 'package main\nimport os\nimport "fmt"'
        result = v.validate_imports(code)
        assert result is False
        assert any("Unquoted import" in e for e in v.import_errors)

    def test_go_validate_imports_python_from_import(self):
        v = IntegrationValidator(target_lang="go")
        code = 'package main\nfrom os import getcwd'
        result = v.validate_imports(code)
        assert result is False
        assert any("Python-style" in e for e in v.import_errors)

    def test_go_validate_imports_valid(self):
        v = IntegrationValidator(target_lang="go")
        code = 'package main\nimport "fmt"\nimport "os"'
        result = v.validate_imports(code)
        assert result is True
        assert len(v.import_errors) == 0

    def test_go_validate_types_none_comparison(self):
        v = IntegrationValidator(target_lang="go")
        code = 'package main\nfunc main() { if x == None {} }'
        result = v.validate_types(code)
        assert result is False
        assert any("== nil" in e for e in v.type_errors)

    def test_go_validate_types_ts_style_annotations(self):
        v = IntegrationValidator(target_lang="go")
        code = 'package main\nvar name: string = "test"'
        result = v.validate_types(code)
        assert result is False
        assert any("TypeScript type syntax" in e for e in v.type_errors)

    def test_go_validate_types_unexported_func(self):
        v = IntegrationValidator(target_lang="go")
        code = 'package main\nfunc lowercase() {}'
        result = v.validate_types(code)
        assert result is False
        assert any("unexported" in e.lower() for e in v.type_errors)

    def test_go_validate_types_valid(self):
        v = IntegrationValidator(target_lang="go")
        code = 'package main\nfunc Exported() {}\ntype MyStruct struct {}'
        result = v.validate_types(code)
        assert result is True
        assert len(v.type_errors) == 0


# ---------------------------------------------------------------------------
# Reassembler
# ---------------------------------------------------------------------------

class TestReassembler:
    def test_combine_empty(self, sample_chunks):
        r = Reassembler(sample_chunks, Path("/tmp"))
        assert r.combine() == ""

    def test_combine_single_chunk(self, sample_chunks):
        r = Reassembler(sample_chunks, Path("/tmp"))
        r.add_transpiled(0, "export function add(a: number, b: number): number { return a + b; }")
        combined = r.combine()
        # Code is preserved (no chunk header anymore, just code)
        assert "add" in combined
        # No chunk header comment in new format
        assert "Chunk 0" not in combined

    def test_combine_respects_chunk_order(self, sample_chunks):
        """Dependency order: chunk 1 depends on chunk 0, so 0 should come first."""
        r = Reassembler(sample_chunks, Path("/tmp"))
        r.add_transpiled(0, "// chunk0")
        r.add_transpiled(1, "// chunk1")
        combined = r.combine()
        idx0 = combined.index("chunk0")
        idx1 = combined.index("chunk1")
        assert idx0 < idx1

    def test_topological_sort_respects_dependencies(self, sample_chunks):
        r = Reassembler(sample_chunks, Path("/tmp"))
        r.add_transpiled(0, "// 0")
        r.add_transpiled(1, "// 1")
        order = r._topological_sort()
        assert order.index(0) < order.index(1)

    def test_topological_sort_circular_fallback(self, sample_chunks):
        """If circular, should fall back to remaining order."""
        sample_chunks[0].dependencies = [1]
        sample_chunks[1].dependencies = [0]
        r = Reassembler(sample_chunks, Path("/tmp"))
        r.add_transpiled(0, "// 0")
        r.add_transpiled(1, "// 1")
        order = r._topological_sort()
        assert set(order) == {0, 1}

    def test_write_files_no_chunks(self, sample_chunks, tmp_path):
        r = Reassembler(sample_chunks, tmp_path)
        written = r.write_files(tmp_path / "out", "ts")
        assert written == {}

    def test_write_files_with_filemarker(self, sample_chunks, tmp_path):
        """Output with // filename: markers is split into separate files."""
        r = Reassembler(sample_chunks, tmp_path)
        code = """// filename: math/ops.ts
export function add(a: number): void { }
---FILE_SEPARATOR---
// filename: config.ts
export class Config { }"""
        r.add_transpiled(0, code)
        written = r.write_files(tmp_path / "out", "ts")
        assert len(written) == 2

    def test_write_files_func_pattern(self, sample_chunks, tmp_path):
        """Output with no filename marker but a detected function goes to generated/<name>."""
        r = Reassembler(sample_chunks, tmp_path)
        code = "export function foo(): void { }"
        r.add_transpiled(0, code)
        written = r.write_files(tmp_path / "out", "ts")
        # Function name detected → writes to generated/foo.ts
        assert len(written) == 1
        assert any("foo" in str(p) or "generated" in str(p) for p in written.values())

    def test_write_files_class_pattern(self, sample_chunks, tmp_path):
        """Output with no filename marker but a class uses the class name."""
        r = Reassembler(sample_chunks, tmp_path)
        code = "export class MyHandler { }"
        r.add_transpiled(0, code)
        written = r.write_files(tmp_path / "out", "ts")
        assert len(written) == 1
        assert "MyHandler" in list(written.keys())[0]

    def test_write_files_fallback_writes_combined(self, sample_chunks, tmp_path):
        """Output with no filename, no function, and no class uses combined_output fallback."""
        r = Reassembler(sample_chunks, tmp_path)
        # Use a comment string that has NO class or function keyword
        code = "// This is a plain comment with no code keywords at all"
        r.add_transpiled(0, code)
        written = r.write_files(tmp_path / "out", "ts")
        combined_path = tmp_path / "out" / "combined_output.ts"
        assert combined_path.exists()

    def test_get_chunk_order(self, sample_chunks):
        r = Reassembler(sample_chunks, Path("/tmp"))
        r.add_transpiled(0, "// 0")
        r.add_transpiled(1, "// 1")
        order = r.get_chunk_order()
        assert order == [0, 1]

    def test_resolve_imports_resolves_cross_chunk_symbols(self, sample_chunks, tmp_path):
        """resolve_imports rewrites internal import paths using global_exports built from chunk exports."""
        r = Reassembler(sample_chunks, tmp_path)
        # Chunk 0 exports 'add', 'multiply'; Chunk 1 exports 'Config'
        r.add_transpiled(0, "// filename: math_ops.ts\nfunction add(a, b) { return a + b; }")
        r.add_transpiled(1, "// filename: config.ts\nfunction Config() { }")
        resolved = r.resolve_imports()
        assert "function add" in resolved
        assert "function Config" in resolved

    def test_write_files_multiple_chunks_with_filemarkers(self, sample_chunks, tmp_path):
        """write_files correctly writes each chunk's // filename: content to separate files."""
        r = Reassembler(sample_chunks, tmp_path)
        r.add_transpiled(0, "// filename: math/ops.ts\nexport function add(a: number): void { }")
        r.add_transpiled(1, "// filename: config.ts\nexport class Config { }")
        written = r.write_files(tmp_path / "out", "ts")
        assert len(written) == 2
        assert (tmp_path / "out" / "math" / "ops.ts").exists()
        assert (tmp_path / "out" / "config.ts").exists()

    def test_write_files_combined_output_is_not_chunk_header(self, sample_chunks, tmp_path):
        """write_files output files must not contain # ===== Chunk N: ... ===== headers."""
        r = Reassembler(sample_chunks, tmp_path)
        r.add_transpiled(0, "// filename: foo.ts\nexport function foo(): void { }")
        written = r.write_files(tmp_path / "out", "ts")
        foo_path = tmp_path / "out" / "foo.ts"
        assert foo_path.exists()
        content = foo_path.read_text()
        # The chunk header comment must not appear in the output file
        assert "# ===== Chunk" not in content
        assert "Chunk 0" not in content

    def test_combine_with_no_explicit_filename(self, sample_chunks, tmp_path):
        """Transpiled chunk with no // filename marker but a class uses class-name path."""
        r = Reassembler(sample_chunks, tmp_path)
        r.add_transpiled(0, "export class FooBar { }")
        written = r.write_files(tmp_path / "out", "ts")
        assert len(written) == 1
        # Class name "FooBar" should be in the path
        written_paths = list(written.keys())
        assert any("FooBar" in p or "generated" in p for p in written_paths)



# ---------------------------------------------------------------------------
# PipelineCoordinator.transpile_chunk
# ---------------------------------------------------------------------------

class TestPipelineCoordinatorTranspileChunk:
    def test_transpile_chunk_serializes_blueprint_to_yaml_file(self, sample_chunks, tmp_path):
        """The temp file written by transpile_chunk must be valid YAML with all fields."""
        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        chunk0 = sample_chunks[0]

        captured_yaml = {}

        def capture_transpile(path, target, output_dir=None):
            # Read the YAML before the path is deleted by the caller's finally block
            with open(path) as f:
                captured_yaml["data"] = yaml.safe_load(f)
            return "// filename: test.ts\nexport function test(): void { }"

        coord.transpiler.transpile = capture_transpile

        result = coord.transpile_chunk(chunk0, tmp_path, "python", None)

        assert "blueprint" in captured_yaml["data"]
        bp = captured_yaml["data"]["blueprint"]
        assert "functions" in bp
        assert bp["repo"] == tmp_path.name
        # Functions from math_ops.py should be in the blueprint
        func_names = [f["name"] for f in bp["functions"]]
        assert "add" in func_names or "multiply" in func_names

    def test_transpile_chunk_returns_string(self, sample_chunks, tmp_path):
        """transpile_chunk must return a non-empty string."""
        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        chunk0 = sample_chunks[0]
        coord.transpiler.transpile = lambda path, target, output_dir=None: ("// output", ValidationResult(success=True))
        result = coord.transpile_chunk(chunk0, tmp_path, "python", None)
        code, vr = result; assert isinstance(code, str) and len(code) > 0

    def test_transpile_chunk_handles_all_languages(self, sample_chunks, tmp_path):
        """JavaScript chunks should use the JS extractor without crashing."""
        js_file = tmp_path / "test.js"
        js_file.write_text("export function hello() { return 'hi'; }")
        js_chunk = Chunk(id=99, files=[js_file], imports=[], exports=[], dependencies=[])

        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        coord.transpiler.transpile = lambda path, target, output_dir=None: ("// ts", ValidationResult(success=True))
        result = coord.transpile_chunk(js_chunk, tmp_path, "javascript", None)
        code, vr = result; assert isinstance(code, str)

    def test_transpile_chunk_skips_unreadable_files(self, sample_chunks, tmp_path):
        """Files that can't be parsed should be skipped, not crash."""
        bad_file = tmp_path / "broken.py"
        bad_file.write_text("def <<<broken syntax<<<")
        chunk = Chunk(id=0, files=[bad_file], imports=[], exports=[], dependencies=[])

        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        coord.transpiler.transpile = lambda path, target, output_dir=None: ("// ok", ValidationResult(success=True))
        result = coord.transpile_chunk(chunk, tmp_path, "python", None)
        code, vr = result; assert isinstance(code, str)

    def test_transpile_chunk_includes_data_structures(self, sample_chunks, tmp_path):
        """Blueprint should include data_structures extracted from class files."""
        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        # chunk1 = config.py which has Config class
        chunk1 = sample_chunks[1]

        captured_yaml = {}

        def capture_transpile(path, target, output_dir=None):
            with open(path) as f:
                captured_yaml["data"] = yaml.safe_load(f)
            return "// filename: test.ts"

        coord.transpiler.transpile = capture_transpile
        result = coord.transpile_chunk(chunk1, tmp_path, "python", None)

        bp = captured_yaml["data"]["blueprint"]
        assert "data_structures" in bp
        ds_names = [ds["name"] for ds in bp["data_structures"]]
        assert "Config" in ds_names


# ---------------------------------------------------------------------------
# generate_module_tests
# ---------------------------------------------------------------------------

class TestGenerateModuleTests:
    def test_generate_js_tests_basic(self, tmp_path):
        ts_file = tmp_path / "math.ts"
        ts_file.write_text("export function add(a: number, b: number): number { return a + b; }")
        result = generate_module_tests([ts_file], "typescript")
        assert "describe" in result
        assert "it(" in result
        assert "vitest" in result

    def test_generate_python_tests_basic(self, tmp_path):
        py_file = tmp_path / "math_ops.py"
        py_file.write_text("def add(a, b): return a + b\ndef multiply(x, y): return x * y\n")
        result = generate_module_tests([py_file], "python")
        assert "pytest" in result
        assert "test_add" in result or "test_multiply" in result

    def test_generate_python_tests_class(self, tmp_path):
        py_file = tmp_path / "config.py"
        py_file.write_text("class Config:\n    def __init__(self): pass\n")
        result = generate_module_tests([py_file], "python")
        assert "TestConfig" in result

    def test_generate_rust_tests_basic(self, tmp_path):
        rs_file = tmp_path / "math.rs"
        rs_file.write_text("#[test]\nfn test_add() { assert!(true); }")
        result = generate_module_tests([rs_file], "rust")
        assert "#[cfg(test)]" in result
        assert "test_add" in result

    def test_generate_unsupported_lang(self, tmp_path):
        # Go is now supported — use an unsupported language like COBOL
        cobol_file = tmp_path / "main.cbl"
        cobol_file.write_text("       IDENTIFICATION DIVISION.")
        result = generate_module_tests([cobol_file], "cobol")
        assert "not supported" in result


# ---------------------------------------------------------------------------
# chunk_repository
# ---------------------------------------------------------------------------

class TestChunkRepository:
    def test_chunks_are_created(self, tmp_path):
        (tmp_path / "a.py").write_text("def a(): pass\n")
        (tmp_path / "b.py").write_text("def b(): pass\n")
        chunks = chunk_repository(tmp_path, max_functions=30)
        assert len(chunks) == 1  # both fit in one chunk

    def test_chunks_respect_max_functions(self, tmp_path):
        for i in range(3):
            (tmp_path / f"f{i}.py").write_text(f"def func{i}(): pass\n")
        chunks = chunk_repository(tmp_path, max_functions=1)
        assert len(chunks) == 3  # one per file

    def test_chunks_exclude_venv(self, tmp_path):
        """venv directories must be excluded from chunking."""
        (tmp_path / "main.py").write_text("def main(): pass\n")
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "module.py").write_text("def hidden(): pass\n")
        chunks = chunk_repository(tmp_path, max_functions=30)
        all_files = [f for c in chunks for f in c.files]
        venv_files = [f for f in all_files if "venv" in f.parts]
        assert len(venv_files) == 0

    def test_chunks_exclude_pycache(self, tmp_path):
        """__pycache__ directories must be excluded from chunking."""
        (tmp_path / "main.py").write_text("def main(): pass\n")
        pc = tmp_path / "__pycache__"
        pc.mkdir()
        (pc / "main.pyc").write_text("")
        chunks = chunk_repository(tmp_path, max_functions=30)
        all_files = [f for c in chunks for f in c.files]
        pc_files = [f for f in all_files if "__pycache__" in f.parts]
        assert len(pc_files) == 0

    def test_chunks_group_by_directory(self, tmp_path):
        """Files in the same directory are grouped together."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("def init(): pass\n")
        (pkg / "utils.py").write_text("def util(): pass\n")
        chunks = chunk_repository(tmp_path, max_functions=30)
        # Both files should be in the same chunk (same module)
        assert len(chunks) == 1
        assert len(chunks[0].files) == 2


# ---------------------------------------------------------------------------
# ValidationReport dataclass
# ---------------------------------------------------------------------------

class TestValidationReport:
    def test_is_valid_true(self):
        report = ValidationReport(import_valid=True, type_valid=True)
        assert report.is_valid is True

    def test_is_valid_false_import(self):
        report = ValidationReport(import_valid=False, type_valid=True)
        assert report.is_valid is False

    def test_is_valid_false_type(self):
        report = ValidationReport(import_valid=True, type_valid=False)
        assert report.is_valid is False


# ---------------------------------------------------------------------------
# PipelineCoordinator — write_files integration
# ---------------------------------------------------------------------------

class TestPipelineCoordinatorWriteFiles:
    """Tests for PipelineCoordinator.transpile_all_chunks calling write_files()."""

    def test_transpile_all_chunks_calls_write_files(self, sample_chunks, tmp_path):
        """transpile_all_chunks must return written_paths from reassembler.write_files()."""
        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        coord.transpiler.transpile = lambda path, target, output_dir=None: (
            "// filename: test.ts\nexport function test(): void { }"
        )

        from repo_transmute.transpiler.chunker import Reassembler
        original = Reassembler.write_files
        captured_calls = []

        def capturing_write_files(self, output_dir, file_ext="ts"):
            result = original(self, output_dir, file_ext)
            captured_calls.append(result)
            return result

        Reassembler.write_files = capturing_write_files
        try:
            combined, processed, total, written, failed = coord.transpile_all_chunks(
                repo_path=tmp_path,
                language="python",
                output_dir=tmp_path / "out"
            )
            # written is the 4th return value — must be a list
            assert isinstance(written, list), f"expected list, got {type(written)}"
            # captured_calls[0] is the dict from write_files; written should be list(captured_calls[0].values())
            if captured_calls:
                expected = [str(p) for p in captured_calls[0].values()]
                assert written == expected, f"expected {expected}, got {written}"
        finally:
            Reassembler.write_files = original

    def test_transpile_all_chunks_no_output_dir_returns_empty_list(self, sample_chunks, tmp_path):
        """When output_dir is None, write_files returns {} → written=[]."""
        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        coord.transpiler.transpile = lambda path, target, output_dir=None: (
            "// filename: test.ts\nexport function test(): void { }"
        )

        combined, processed, total, written, failed = coord.transpile_all_chunks(
            repo_path=tmp_path,
            language="python",
            output_dir=None
        )
        assert isinstance(written, list)
        assert written == [], f"expected [] when output_dir=None, got {written}"

    def test_pipeline_result_has_files_written_field(self):
        """PipelineResult dataclass must include files_written."""
        from dataclasses import fields
        field_names = [f.name for f in fields(PipelineResult)]
        assert "files_written" in field_names

    def test_pipeline_result_has_test_result_field(self):
        """PipelineResult dataclass must include test_result (SuiteResult)."""
        from dataclasses import fields
        field_names = [f.name for f in fields(PipelineResult)]
        assert "test_result" in field_names

    def test_pipeline_result_test_result_is_suite_result_type(self):
        """PipelineResult.test_result field has correct Optional[SuiteResult] type."""
        from typing import get_type_hints
        hints = get_type_hints(PipelineResult)
        # The type annotation for test_result should reference SuiteResult
        # We check the field annotation via __dataclass_fields__
        import typing
        field = PipelineResult.__dataclass_fields__["test_result"]
        # The annotation is Optional["SuiteResult"]; check it contains SuiteResult
        ann = str(field.type)
        assert "SuiteResult" in ann, f"Expected SuiteResult in type annotation, got: {ann}"

    def test_write_files_returns_correct_extension(self):
        """_get_extension() returns the right file extension per target language."""
        coord_ts = PipelineCoordinator(target_lang="typescript")
        assert coord_ts._get_extension() == "ts"

        coord_rs = PipelineCoordinator(target_lang="rust")
        assert coord_rs._get_extension() == "rs"

        coord_py = PipelineCoordinator(target_lang="python")
        assert coord_py._get_extension() == "py"

    def test_write_files_handles_none_output_dir(self, sample_chunks, tmp_path):
        """Reassembler.write_files must not crash when output_dir is None."""
        from repo_transmute.transpiler.chunker import Reassembler
        chunk0 = sample_chunks[0]
        r = Reassembler([chunk0], tmp_path)
        r.add_transpiled(0, "// filename: test.ts\nexport function test(): void { }")
        # Must not raise
        result = r.write_files(None, "ts")
        assert result == {}

    def test_transpile_all_chunks_write_files_receives_correct_extension(self, sample_chunks, tmp_path):
        """write_files is called with the target-language extension."""
        coord = PipelineCoordinator(target_lang="rust", max_passes=1)
        coord.transpiler.transpile = lambda path, target, output_dir=None: (
            "// filename: lib.rs\npub fn test() { }"
        )

        from repo_transmute.transpiler.chunker import Reassembler
        original = Reassembler.write_files
        captured_exts = []

        def capturing_write_files(self, output_dir, file_ext="ts"):
            captured_exts.append(file_ext)
            return original(self, output_dir, file_ext)

        Reassembler.write_files = capturing_write_files
        try:
            combined, processed, total, written, failed = coord.transpile_all_chunks(
                repo_path=tmp_path,
                language="python",
                output_dir=tmp_path / "out"
            )
            assert "rs" in captured_exts, f"expected 'rs' extension, got {captured_exts}"
        finally:
            Reassembler.write_files = original
    def test_transpile_all_chunks_progress_callback_invoked(self, tmp_path):
        from repo_transmute.transpiler.chunker import Chunk
        chunk_a = Chunk(id=0, files=[], imports=[], exports=[], dependencies=[])
        chunk_b = Chunk(id=1, files=[], imports=[], exports=[], dependencies=[])

        coord = PipelineCoordinator(target_lang='rust', max_passes=1)
        coord.transpiler.transpile = lambda path, target, output_dir=None: '// filename: lib.rs'

        with patch('repo_transmute.pipeline.coordinator.chunk_repository') as mock_cr:
            mock_cr.return_value = [chunk_a, chunk_b]
            calls = []
            coord.transpile_all_chunks(
                repo_path=tmp_path,
                language='python',
                output_dir=tmp_path / 'out',
                progress_callback=lambda idx, total, msg: calls.append((idx, total, msg))
            )
            assert len(calls) == 2
            assert calls[0] == (1, 2, 'Processing chunk 1/2')
            assert calls[1] == (2, 2, 'Processing chunk 2/2')

    def test_run_full_pipeline_accepts_progress_callback(self, tmp_path):
        coord = PipelineCoordinator(target_lang='rust', max_passes=1)
        with patch.object(coord, 'transpile_all_chunks') as mock_tac,              patch.object(coord, 'validator') as mock_validator,              patch('repo_transmute.pipeline.coordinator.clone_repo') as mock_clone:
            repo_cache = tmp_path / 'cache' / 'owner__repo'
            mock_clone.return_value = repo_cache
            repo_cache.mkdir(parents=True)
            mock_tac.return_value = ('', 0, 0, [])
            mock_validator.generate_report.return_value = MagicMock()
            result = coord.run_full_pipeline(
                repo='owner/repo',
                cache_dir=tmp_path / 'cache',
                output_dir=tmp_path / 'out',
                progress_callback=lambda idx, total, msg: None,
            )
            mock_tac.assert_called_once()
            _, kwargs = mock_tac.call_args
            assert 'progress_callback' in kwargs

    def test_pipeline_cli_passes_max_functions_to_coordinator(self, tmp_path):
        """Verify --max-functions / -f CLI option is passed to PipelineCoordinator."""
        from unittest.mock import patch, MagicMock
        from click.testing import CliRunner
        from repo_transmute.cli import pipeline

        coord_init_kwargs = {}
        original_init = PipelineCoordinator.__init__

        def capturing_init(self, *args, **kwargs):
            coord_init_kwargs.update(kwargs)
            return original_init(self, *args, **kwargs)

        with patch.object(PipelineCoordinator, '__init__', capturing_init), \
             patch.object(PipelineCoordinator, 'run_full_pipeline') as mock_run:
            mock_run.return_value = MagicMock(success=False, error='')
            runner = CliRunner()
            result = runner.invoke(pipeline, [
                'owner/repo',
                '--max-functions', '15',
                '-c', str(tmp_path / 'cache'),
                '-o', str(tmp_path / 'out'),
            ])
            assert 'max_functions_per_chunk' in coord_init_kwargs
            assert coord_init_kwargs['max_functions_per_chunk'] == 15

    def test_pipeline_cli_max_functions_short_option(self, tmp_path):
        """Verify -f short option works for --max-functions."""
        from unittest.mock import patch, MagicMock
        from click.testing import CliRunner
        from repo_transmute.cli import pipeline

        coord_init_kwargs = {}
        original_init = PipelineCoordinator.__init__

        def capturing_init(self, *args, **kwargs):
            coord_init_kwargs.update(kwargs)
            return original_init(self, *args, **kwargs)

        with patch.object(PipelineCoordinator, '__init__', capturing_init), \
             patch.object(PipelineCoordinator, 'run_full_pipeline') as mock_run:
            mock_run.return_value = MagicMock(success=False, error='')
            runner = CliRunner()
            result = runner.invoke(pipeline, [
                'owner/repo',
                '-f', '7',
                '-c', str(tmp_path / 'cache'),
                '-o', str(tmp_path / 'out'),
            ])
            assert coord_init_kwargs.get('max_functions_per_chunk') == 7

    def test_pipeline_cli_default_max_functions(self, tmp_path):
        """Verify default max_functions_per_chunk is 30 when not specified."""
        from unittest.mock import patch, MagicMock
        from click.testing import CliRunner
        from repo_transmute.cli import pipeline

        coord_init_kwargs = {}
        original_init = PipelineCoordinator.__init__

        def capturing_init(self, *args, **kwargs):
            coord_init_kwargs.update(kwargs)
            return original_init(self, *args, **kwargs)

        with patch.object(PipelineCoordinator, '__init__', capturing_init), \
             patch.object(PipelineCoordinator, 'run_full_pipeline') as mock_run:
            mock_run.return_value = MagicMock(success=False, error='')
            runner = CliRunner()
            result = runner.invoke(pipeline, [
                'owner/repo',
                '-c', str(tmp_path / 'cache'),
                '-o', str(tmp_path / 'out'),
            ])
            assert coord_init_kwargs.get('max_functions_per_chunk') == 30


# ---------------------------------------------------------------------------
# CLI — transpile command individual chunk support
# ---------------------------------------------------------------------------

    def test_run_full_pipeline_calls_run_tests_when_output_files_exist(self, tmp_path):
        """run_full_pipeline should call run_tests on the output directory after validation."""
        from unittest.mock import patch, MagicMock
        from repo_transmute.transpiler.validate import SuiteResult

        coord = PipelineCoordinator(target_lang="typescript")

        # Create a mock output file so output_files is non-empty
        output_file = tmp_path / "name_test.ts"
        output_file.write_text("export const x = 1;")

        mock_suite_result = SuiteResult(success=True, passed=5, failed=0, errors=0)

        with patch.object(coord, 'transpile_all_chunks') as mock_transpile,              patch('repo_transmute.pipeline.coordinator.run_tests') as mock_run_tests,              patch('repo_transmute.pipeline.coordinator.extract_all') as mock_extract,              patch('repo_transmute.pipeline.coordinator.clone_repo') as mock_clone:

            mock_transpile.return_value = (
                "transpiled_code", 1, 1, [str(output_file)], []
            )
            mock_extract.return_value = MagicMock()
            mock_clone.return_value = tmp_path
            mock_run_tests.return_value = mock_suite_result

            result = coord.run_full_pipeline(
                repo="owner/name",
                cache_dir=tmp_path,
                output_dir=tmp_path,
            )

            # Verify run_tests was called
            mock_run_tests.assert_called_once()
            call_args = mock_run_tests.call_args
            assert call_args.kwargs['project_root'] == tmp_path
            assert call_args.kwargs['language'] == 'typescript'
            assert call_args.kwargs['timeout'] == 120

            # Verify test_result is in the returned PipelineResult
            assert result.test_result == mock_suite_result

    def test_run_full_pipeline_skips_tests_when_no_output_files(self, tmp_path):
        """run_full_pipeline should skip run_tests when no transpiled output files exist."""
        from unittest.mock import patch, MagicMock

        coord = PipelineCoordinator(target_lang="typescript")

        with patch.object(coord, 'transpile_all_chunks') as mock_transpile,              patch('repo_transmute.pipeline.coordinator.run_tests') as mock_run_tests,              patch('repo_transmute.pipeline.coordinator.extract_all') as mock_extract,              patch('repo_transmute.pipeline.coordinator.clone_repo') as mock_clone:

            mock_transpile.return_value = (
                "transpiled_code", 1, 1, [], []  # empty written_paths
            )
            mock_extract.return_value = MagicMock()
            mock_clone.return_value = tmp_path

            result = coord.run_full_pipeline(
                repo="owner/name",
                cache_dir=tmp_path,
                output_dir=tmp_path,
            )

            # Verify run_tests was NOT called
            mock_run_tests.assert_not_called()
            assert result.test_result is None




class TestTranspileCommandChunkMode:
    """Tests for repo-transmute transpile --repo owner/repo --chunk-id N."""

    def test_transpile_chunk_mode_requires_chunk_id_with_repo(self, tmp_path):
        """--repo without --chunk-id must error."""
        from click.testing import CliRunner
        from repo_transmute.cli import transpile

        runner = CliRunner()
        with patch("repo_transmute.cli.clone_repo"):
            result = runner.invoke(transpile, ["--repo", "owner/repo"])
            assert result.exit_code != 0
            assert "chunk-id" in result.output.lower()

    def test_transpile_chunk_mode_transpiles_correct_chunk(self, tmp_path):
        """transpile --repo X --chunk-id Y calls transpile_chunk with chunks[Y]."""
        from click.testing import CliRunner
        from repo_transmute.cli import transpile, _transpile_single_chunk

        cache = tmp_path / "cache"
        cache.mkdir()
        cached = cache / "owner__repo"
        cached.mkdir()
        (cached / "mod.py").write_text("def f(): pass\n")

        captured = {}

        def fake_transpile_chunk(chunk, repo_path, language, output_dir=None):
            captured["chunk_id"] = chunk.id
            captured["num_files"] = len(chunk.files)
            return "// transpiled"

        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        with patch.object(coord, "transpile_chunk", fake_transpile_chunk), \
             patch("repo_transmute.cli.PipelineCoordinator", return_value=coord):
            _transpile_single_chunk(
                repo="owner/repo",
                chunk_id=0,
                target="typescript",
                output_dir=tmp_path / "out",
                cache_dir=cache,
                model="MiniMax-M2.7",
                max_functions=30,
            )

        assert captured.get("chunk_id") == 0
        assert captured.get("num_files") == 1

    def test_transpile_chunk_mode_invalid_chunk_id_errors(self, tmp_path):
        """chunk-id out of range must error with the valid range."""
        from click.testing import CliRunner
        from repo_transmute.cli import transpile

        cache = tmp_path / "cache"
        cache.mkdir()
        cached = cache / "owner__repo"
        cached.mkdir()
        (cached / "mod.py").write_text("def f(): pass\n")

        runner = CliRunner()
        with patch("repo_transmute.cli.PipelineCoordinator") as MockCoord:
            MockCoord.return_value.transpile_chunk = lambda *a, **kw: "// out"
            result = runner.invoke(transpile, [
                "--repo", "owner/repo", "--chunk-id", "0",
                "--cache-dir", str(cache),
                "--output-dir", str(tmp_path / "out"),
            ])
            # chunk-id 0 should work (only 1 chunk exists)
            assert result.exit_code == 0, f"chunk 0 should succeed: {result.output}"

        # Out of range
        with patch("repo_transmute.cli.PipelineCoordinator") as MockCoord:
            MockCoord.return_value.transpile_chunk = lambda *a, **kw: "// out"
            result = runner.invoke(transpile, [
                "--repo", "owner/repo", "--chunk-id", "99",
                "--cache-dir", str(cache),
                "--output-dir", str(tmp_path / "out"),
            ])
            assert result.exit_code != 0, f"chunk 99 should fail: {result.output}"
            assert "out of range" in result.output.lower()


    def test_transpile_chunk_mode_saves_output_file(self, tmp_path):
        """When output_dir is set, transpiled code is written to chunkNNN.ext."""
        from repo_transmute.cli import _transpile_single_chunk

        cache = tmp_path / "cache"
        cache.mkdir()
        cached = cache / "owner__repo"
        cached.mkdir()
        (cached / "mod.py").write_text("def f(): pass\n")

        out_dir = tmp_path / "out"

        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        coord.transpile_chunk = lambda *a, **kw: "// filename: test.ts\nexport function f(): void { }"
        with patch("repo_transmute.cli.PipelineCoordinator", return_value=coord):
            _transpile_single_chunk(
                repo="owner/repo",
                chunk_id=0,
                target="typescript",
                output_dir=out_dir,
                cache_dir=cache,
                model="MiniMax-M2.7",
                max_functions=30,
            )

        # File is saved
        saved = list(out_dir.glob("chunk000.ts"))
        assert len(saved) == 1
        assert "export function f" in saved[0].read_text()

    def test_transpile_blueprint_mode_still_works(self, tmp_path):
        """transpile <blueprint.yaml> (no --repo) should call transpile_with_llm."""
        from click.testing import CliRunner
        from repo_transmute.cli import transpile

        blueprint_file = tmp_path / "bp.yaml"
        blueprint_file.write_text("""
version: '1.0'
source:
  repo: test
  language: python
blueprint:
  functions:
    - name: hello
      signature: () -> str
      file: hello.py
      line: 1
""")

        with patch("repo_transmute.cli.transpile_with_llm", return_value="// hello") as mock_llm:
            runner = CliRunner()
            result = runner.invoke(transpile, [str(blueprint_file)])
            assert result.exit_code == 0
            mock_llm.assert_called_once()
