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
        assert "add" in combined
        assert "Chunk 0" in combined

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
        coord.transpiler.transpile = lambda path, target, output_dir=None: "// output"
        result = coord.transpile_chunk(chunk0, tmp_path, "python", None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_transpile_chunk_handles_all_languages(self, sample_chunks, tmp_path):
        """JavaScript chunks should use the JS extractor without crashing."""
        js_file = tmp_path / "test.js"
        js_file.write_text("export function hello() { return 'hi'; }")
        js_chunk = Chunk(id=99, files=[js_file], imports=[], exports=[], dependencies=[])

        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        coord.transpiler.transpile = lambda path, target, output_dir=None: "// ts"
        result = coord.transpile_chunk(js_chunk, tmp_path, "javascript", None)
        assert isinstance(result, str)

    def test_transpile_chunk_skips_unreadable_files(self, sample_chunks, tmp_path):
        """Files that can't be parsed should be skipped, not crash."""
        bad_file = tmp_path / "broken.py"
        bad_file.write_text("def <<<broken syntax<<<")
        chunk = Chunk(id=0, files=[bad_file], imports=[], exports=[], dependencies=[])

        coord = PipelineCoordinator(target_lang="typescript", max_passes=1)
        coord.transpiler.transpile = lambda path, target, output_dir=None: "// ok"
        result = coord.transpile_chunk(chunk, tmp_path, "python", None)
        assert isinstance(result, str)

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
        go_file = tmp_path / "main.go"
        go_file.write_text("package main")
        result = generate_module_tests([go_file], "go")
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
