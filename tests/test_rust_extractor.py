"""Tests for the Rust extractor (tree-sitter based)."""

import pytest
from pathlib import Path

from repo_transmute.blueprint.rust_extractor import (
    extract_from_rust,
    extract_structs_from_rust,
    extract_enums_from_rust,
    extract_impls_from_rust,
    extract_all_rust,
)
from repo_transmute.blueprint.extractor import Function, DataStructure


FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_RUST = FIXTURES / "sample_rust.rs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def func_names(funcs):
    return sorted([f.name for f in funcs])


def struct_names(structs):
    return sorted([s.name for s in structs])


def enum_names(enums):
    return sorted([e.name for e in enums])


# ---------------------------------------------------------------------------
# extract_from_rust — top-level functions
# ---------------------------------------------------------------------------

class TestExtractRustFunctions:
    def test_finds_standalone_functions(self):
        """Standalone fn declarations are extracted."""
        funcs = extract_from_rust(SAMPLE_RUST)
        names = func_names(funcs)
        assert "add" in names
        assert "greet" in names
        assert "divide" in names

    def test_skips_test_functions(self):
        """Functions inside #[cfg(test)] blocks are excluded."""
        funcs = extract_from_rust(SAMPLE_RUST)
        names = func_names(funcs)
        assert "test_add" not in names
        assert "test_divide_ok" not in names

    def test_async_functions_detected(self):
        funcs = extract_from_rust(SAMPLE_RUST)
        by_name = {f.name: f for f in funcs}
        assert by_name["multiply"].async_flag is True

    def test_functions_have_return_types(self):
        funcs = extract_from_rust(SAMPLE_RUST)
        by_name = {f.name: f for f in funcs}
        assert "i32" in by_name["add"].signature or "i32" in by_name["add"].signature

    def test_functions_have_bodies(self):
        funcs = extract_from_rust(SAMPLE_RUST)
        by_name = {f.name: f for f in funcs}
        # Body should be non-empty for top-level fns
        assert by_name["greet"].body

    def test_no_duplicate_names(self):
        """Each top-level function name appears exactly once in output."""
        funcs = extract_from_rust(SAMPLE_RUST)
        names = [f.name for f in funcs]
        # 'add' appears both as impl method and top-level fn; top-level is standalone
        # The extractor may include impl methods (they are fn_item nodes) — deduplicate by line
        lines = [f.line for f in funcs]
        assert len(names) == len(set(names)), "Duplicate function names found"


# ---------------------------------------------------------------------------
# extract_structs_from_rust
# ---------------------------------------------------------------------------

class TestExtractRustStructs:
    def test_finds_all_structs(self):
        structs = extract_structs_from_rust(SAMPLE_RUST)
        names = struct_names(structs)
        assert "Calculator" in names
        assert "User" in names
        assert "AppState" in names

    def test_struct_fields_extracted(self):
        structs = extract_structs_from_rust(SAMPLE_RUST)
        by_name = {s.name: s for s in structs}
        assert "value" in by_name["Calculator"].fields
        assert "id" in by_name["User"].fields
        assert "users" in by_name["AppState"].fields

    def test_struct_docstring_extracted(self):
        """Doc comments (///) immediately before a struct are captured."""
        structs = extract_structs_from_rust(SAMPLE_RUST)
        by_name = {s.name: s for s in structs}
        # User has /// A user entity.
        assert by_name["User"].docstring is not None
        assert "entity" in by_name["User"].docstring.lower()


# ---------------------------------------------------------------------------
# extract_enums_from_rust
# ---------------------------------------------------------------------------

class TestExtractRustEnums:
    def test_finds_all_enums(self):
        enums = extract_enums_from_rust(SAMPLE_RUST)
        names = enum_names(enums)
        assert "Status" in names
        assert "Page" in names

    def test_simple_variants(self):
        """Simple enum variants (Ok, Pending) are captured."""
        enums = extract_enums_from_rust(SAMPLE_RUST)
        by_name = {e.name: e for e in enums}
        variants = by_name["Status"].fields
        assert any("Ok" in v for v in variants)
        assert any("Pending" in v for v in variants)

    def test_tuple_variants(self):
        """Tuple-style enum variants (Err(String)) are captured."""
        enums = extract_enums_from_rust(SAMPLE_RUST)
        by_name = {e.name: e for e in enums}
        variants = by_name["Status"].fields
        assert any("Err" in v for v in variants)

    def test_struct_variants(self):
        """Struct-style enum variants are captured."""
        enums = extract_enums_from_rust(SAMPLE_RUST)
        by_name = {e.name: e for e in enums}
        variants = by_name["Page"].fields
        assert any("Multi" in v for v in variants)

    def test_enum_docstring(self):
        enums = extract_enums_from_rust(SAMPLE_RUST)
        by_name = {e.name: e for e in enums}
        assert by_name["Status"].docstring is None  # No doc comment before it


# ---------------------------------------------------------------------------
# extract_impls_from_rust
# ---------------------------------------------------------------------------

class TestExtractRustImpls:
    def test_finds_impl_blocks(self):
        impls = extract_impls_from_rust(SAMPLE_RUST)
        names = sorted([i.name for i in impls])
        assert "Calculator" in names
        assert "AppState" in names

    def test_impl_methods_extracted(self):
        """Methods inside impl blocks are correctly extracted."""
        impls = extract_impls_from_rust(SAMPLE_RUST)
        by_name = {i.name: i for i in impls}
        calc_methods = [m.name for m in (by_name["Calculator"].methods or [])]
        assert "new" in calc_methods
        assert "add" in calc_methods
        assert "subtract" in calc_methods

    def test_impl_methods_have_signatures(self):
        impls = extract_impls_from_rust(SAMPLE_RUST)
        by_name = {i.name: i for i in impls}
        app_methods = {m.name: m for m in (by_name["AppState"].methods or [])}
        assert app_methods["new"].signature
        assert app_methods["add_user"].signature
        assert app_methods["get_user"].signature

    def test_impl_methods_have_bodies(self):
        impls = extract_impls_from_rust(SAMPLE_RUST)
        by_name = {i.name: i for i in impls}
        app_methods = {m.name: m for m in (by_name["AppState"].methods or [])}
        # All impl methods should have non-empty bodies
        for m in (by_name["AppState"].methods or []):
            assert m.body, f"Method {m.name} has empty body"


# ---------------------------------------------------------------------------
# extract_all_rust
# ---------------------------------------------------------------------------

class TestExtractAllRust:
    def test_returns_tuple_of_three(self):
        result = extract_all_rust(SAMPLE_RUST)
        assert len(result) == 3

    def test_functions_non_empty(self):
        funcs, structs, imports = extract_all_rust(SAMPLE_RUST)
        assert len(funcs) > 0

    def test_structs_non_empty(self):
        funcs, structs, imports = extract_all_rust(SAMPLE_RUST)
        assert len(structs) > 0

    def test_imports_non_empty(self):
        funcs, structs, imports = extract_all_rust(SAMPLE_RUST)
        assert len(imports) > 0
        assert any("HashMap" in i.module or "std" in i.module for i in imports)
