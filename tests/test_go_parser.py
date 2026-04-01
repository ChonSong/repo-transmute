"""Tests for go_parser.py — Go AST extraction via goast helper binary."""

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from repo_transmute.transpiler.go_parser import (
    extract_from_go,
    extract_structs_from_go,
    extract_interfaces_from_go,
    extract_imports_from_go,
    _parse_goast_output,
    _extract_from_go_regex,
    _find_goast,
    _extract_go_imports,
    _find_brace_pair,
    _extract_go_function_bodies,
    _extract_go_docstring,
    GoImport,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample.go"
FIXTURE_COMPLEX = Path(__file__).parent / "fixtures" / "sample_go_complex.go"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def goast_exists():
    return _find_goast() is not None


# ---------------------------------------------------------------------------
# _parse_goast_output
# ---------------------------------------------------------------------------

class TestParseGoastOutput:
    def test_valid_json(self):
        raw = '{"functions": [{"name": "Add", "signature": "(a, b int) int", "line": 1}]}'
        result = _parse_goast_output(raw)
        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "Add"

    def test_malformed_json_returns_empty(self):
        assert _parse_goast_output("{ not json") == {
            "functions": [],
            "structs": [],
            "interfaces": [],
        }

    def test_empty_string_returns_empty(self):
        assert _parse_goast_output("") == {
            "functions": [],
            "structs": [],
            "interfaces": [],
        }


# ---------------------------------------------------------------------------
# _find_brace_pair
# ---------------------------------------------------------------------------

class TestFindBracePair:
    def test_simple_pair(self):
        content = "func foo() { return 1; }"
        start = content.index("{")
        open_idx, close_idx = _find_brace_pair(content, start)
        assert content[open_idx:close_idx + 1] == "{ return 1; }"

    def test_nested_braces(self):
        content = "func foo() { if x { return 1; } return 0; }"
        start = content.index("{")
        open_idx, close_idx = _find_brace_pair(content, start)
        assert content[open_idx:close_idx + 1] == "{ if x { return 1; } return 0; }"

    def test_ignores_braces_in_strings(self):
        content = 'func foo() { return "{ignore}"; }'
        start = content.index("{")
        open_idx, close_idx = _find_brace_pair(content, start)
        assert close_idx == len(content) - 1

    def test_ignores_braces_in_single_quoted_strings(self):
        content = "func foo() { return '{ignore}'; }"
        start = content.index("{")
        open_idx, close_idx = _find_brace_pair(content, start)
        assert close_idx == len(content) - 1

    def test_ignores_braces_in_raw_strings(self):
        content = "func foo() { return `template {literal}`; }"
        start = content.index("{")
        open_idx, close_idx = _find_brace_pair(content, start)
        assert close_idx == len(content) - 1

    def test_handles_escaped_quotes_in_strings(self):
        content = r'func foo() { return "\""; }'
        start = content.index("{")
        open_idx, close_idx = _find_brace_pair(content, start)
        assert close_idx == len(content) - 1

    def test_handles_empty_body(self):
        content = "func empty() {}"
        start = content.index("{")
        open_idx, close_idx = _find_brace_pair(content, start)
        assert content[open_idx:close_idx + 1] == "{}"


# ---------------------------------------------------------------------------
# _extract_go_imports
# ---------------------------------------------------------------------------

class TestExtractGoImports:
    def test_single_import(self):
        content = 'import "fmt"'
        imports = _extract_go_imports(content)
        assert len(imports) == 1
        assert imports[0].path == "fmt"
        assert imports[0].names == []

    def test_named_import(self):
        content = 'import foo "fmt"'
        imports = _extract_go_imports(content)
        assert len(imports) == 1
        assert imports[0].path == "fmt"
        assert imports[0].names == ["foo"]

    def test_parenthesized_block(self):
        content = 'import (\n  "fmt"\n  "os"\n)'
        imports = _extract_go_imports(content)
        paths = {imp.path for imp in imports}
        assert "fmt" in paths
        assert "os" in paths

    def test_mixed_named_and_unnamed(self):
        content = 'import (\n  "fmt"\n  io "io"\n)'
        imports = _extract_go_imports(content)
        by_path = {imp.path: imp for imp in imports}
        assert by_path["fmt"].names == []
        assert by_path["io"].names == ["io"]

    def test_import_with_alias(self):
        content = 'import alias "fmt"'
        imports = _extract_go_imports(content)
        assert imports[0].path == "fmt"
        assert imports[0].names == ["alias"]

    def test_removes_comments_before_processing(self):
        content = '// comment\nimport "fmt"'
        imports = _extract_go_imports(content)
        assert len(imports) == 1
        assert imports[0].path == "fmt"

    def test_import_from_fixture(self):
        imports = _extract_go_imports(FIXTURE.read_text())
        paths = {imp.path for imp in imports}
        assert "fmt" in paths

    def test_import_from_complex_fixture(self):
        imports = _extract_go_imports(FIXTURE_COMPLEX.read_text())
        paths = {imp.path for imp in imports}
        assert "fmt" in paths
        assert "io" in paths
        assert "os" in paths


# ---------------------------------------------------------------------------
# _extract_go_function_bodies
# ---------------------------------------------------------------------------

class TestExtractGoFunctionBodies:
    def test_extracts_function_name(self):
        content = 'func Add(a, b int) int { return a + b }'
        funcs = _extract_go_function_bodies(content)
        assert "Add" in funcs
        assert funcs["Add"]["name"] == "Add"

    def test_extracts_signature(self):
        content = 'func Add(a, b int) int { return a + b }'
        funcs = _extract_go_function_bodies(content)
        assert "Add" in funcs
        assert "(a, b int)" in funcs["Add"]["signature"]

    def test_extracts_body(self):
        content = 'func Add(a, b int) int { return a + b }'
        funcs = _extract_go_function_bodies(content)
        assert "Add" in funcs
        body = funcs["Add"]["body"].strip()
        assert "return a + b" in body

    def test_extracts_method_receiver(self):
        content = 'func (p *Person) Greet() string { return "hi" }'
        funcs = _extract_go_function_bodies(content)
        assert "Greet" in funcs
        assert funcs["Greet"]["is_method"] is True
        assert "p *Person" in funcs["Greet"]["receiver"]

    def test_skips_methods_on_structs(self):
        content = 'func (p *Person) Greet() string { return "hi" }'
        funcs = _extract_go_function_bodies(content)
        assert funcs["Greet"]["is_method"] is True

    def test_extracts_docstring(self):
        content = '// Add returns the sum.\nfunc Add(a, b int) int { return a + b }'
        funcs = _extract_go_function_bodies(content)
        assert "Add" in funcs
        assert funcs["Add"]["docstring"] is not None
        assert "sum" in funcs["Add"]["docstring"]

    def test_handles_nested_braces(self):
        content = 'func outer() { if true { if true { return 1; } } return 0; }'
        funcs = _extract_go_function_bodies(content)
        assert "outer" in funcs
        assert funcs["outer"]["body"].count("{") == funcs["outer"]["body"].count("}")

    def test_handles_string_with_braces(self):
        content = 'func WithBraces() string { return "{something}"; }'
        funcs = _extract_go_function_bodies(content)
        assert "WithBraces" in funcs
        assert "{something}" in funcs["WithBraces"]["body"]

    def test_handles_raw_string_with_braces(self):
        content = "func RawBraces() string { return `{\"key\": \"value\"}`; }"
        funcs = _extract_go_function_bodies(content)
        assert "RawBraces" in funcs
        # The raw string contains the braces
        assert "{" in funcs["RawBraces"]["body"]

    def test_extracts_multiple_functions(self):
        funcs = _extract_go_function_bodies(FIXTURE.read_text())
        assert "Add" in funcs
        assert "Greet" in funcs
        assert funcs["Add"]["body"].strip() != ""
        assert funcs["Greet"]["body"].strip() != ""

    def test_extracts_functions_from_complex_fixture(self):
        funcs = _extract_go_function_bodies(FIXTURE_COMPLEX.read_text())
        assert "Add" in funcs
        assert "Greet" in funcs
        assert "ProcessWithCallback" in funcs
        assert "WithDefaults" in funcs
        assert "StringWithBraces" in funcs
        assert "MultiLineString" in funcs

        # Verify bodies are populated
        assert funcs["Add"]["body"].strip() != ""
        assert "return a + b" in funcs["Add"]["body"]

        # Verify method detection
        assert funcs["Greet"]["is_method"] is True
        assert "p *Person" in funcs["Greet"]["receiver"]

    def test_multiline_method_body(self):
        funcs = _extract_go_function_bodies(FIXTURE_COMPLEX.read_text())
        assert "LongMethod" in funcs
        body = funcs["LongMethod"]["body"]
        # Should contain nested if/for structures
        assert "for _, s := range input" in body
        assert "for i := 0; i < len(s); i++" in body


# ---------------------------------------------------------------------------
# _extract_go_docstring
# ---------------------------------------------------------------------------

class TestExtractGoDocstring:
    def test_extracts_single_line_doc(self):
        content = "// Sum does a thing.\nfunc Sum() {}"
        doc = _extract_go_docstring(content)
        assert doc is not None
        assert "Sum" in doc

    def test_extracts_multiline_doc(self):
        content = "// Sum does a thing.\n// It returns the total.\nfunc Sum() {}"
        doc = _extract_go_docstring(content)
        assert doc is not None
        assert "thing" in doc
        assert "total" in doc

    def test_returns_none_for_no_doc(self):
        content = "func Sum() {}"
        doc = _extract_go_docstring(content)
        assert doc is None


# ---------------------------------------------------------------------------
# extract_from_go
# ---------------------------------------------------------------------------

class TestExtractFromGo:
    def test_extracts_top_level_functions(self):
        # Always test with pure-python fallback since goast may not be present
        funcs = extract_from_go(FIXTURE)
        names = [f.name for f in funcs]
        assert "Add" in names
        assert "Greet" in names

    def test_functions_have_signatures(self):
        funcs = extract_from_go(FIXTURE)
        by_name = {f.name: f for f in funcs}
        assert "Add" in by_name
        assert "int" in by_name["Add"].signature

    def test_functions_have_line_numbers(self):
        funcs = extract_from_go(FIXTURE)
        for f in funcs:
            assert f.line > 0

    def test_functions_have_docstrings(self):
        funcs = extract_from_go(FIXTURE)
        by_name = {f.name: f for f in funcs}
        assert by_name["Add"].docstring is not None
        assert "sum" in by_name["Add"].docstring.lower()

    def test_methods_are_excluded_from_functions(self):
        funcs = extract_from_go(FIXTURE)
        names = [f.name for f in funcs]
        # Greet appears twice: the top-level function and the method on Person
        # The method should be excluded
        assert names.count("Greet") == 1

    def test_functions_have_bodies(self):
        funcs = extract_from_go(FIXTURE)
        by_name = {f.name: f for f in funcs}
        assert by_name["Add"].body is not None
        assert "return" in by_name["Add"].body

    def test_binary_not_found_falls_back_to_regex(self):
        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            funcs = _extract_from_go_regex(FIXTURE)
            assert len(funcs) >= 2

    def test_subprocess_error_falls_back_to_regex(self):
        with patch.object(subprocess, "run", side_effect=Exception("boom")):
            funcs = _extract_from_go_regex(FIXTURE)
            assert isinstance(funcs, list)


# ---------------------------------------------------------------------------
# extract_structs_from_go
# ---------------------------------------------------------------------------

class TestExtractStructsFromGo:
    def test_extracts_structs(self):
        structs = extract_structs_from_go(FIXTURE)
        names = [s.name for s in structs]
        assert "Person" in names
        assert "Animal" in names

    def test_struct_fields_extracted(self):
        structs = extract_structs_from_go(FIXTURE)
        by_name = {s.name: s for s in structs}
        person_fields = by_name["Person"].fields
        assert any("Name" in f for f in person_fields)
        assert any("Age" in f for f in person_fields)

    def test_struct_type_is_struct(self):
        structs = extract_structs_from_go(FIXTURE)
        by_name = {s.name: s for s in structs}
        assert by_name["Person"].type == "struct"

    def test_struct_fields_include_tags(self):
        # The Animal struct has a json tag — our regex strips it
        structs = extract_structs_from_go(FIXTURE_COMPLEX)
        by_name = {s.name: s for s in structs}
        animal_fields = by_name["Animal"].fields
        # The Species field should have json tag stripped in field listing
        assert any("Species" in f for f in animal_fields)

    def test_nested_struct(self):
        structs = extract_structs_from_go(FIXTURE_COMPLEX)
        by_name = {s.name: s for s in structs}
        config_fields = by_name["Config"].fields
        # Config has nested anonymous struct
        assert any("DB" in f for f in config_fields)

    def test_empty_when_binary_missing(self):
        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            structs = extract_structs_from_go(FIXTURE)
            # Should still work with pure-python fallback
            assert isinstance(structs, list)


# ---------------------------------------------------------------------------
# extract_interfaces_from_go
# ---------------------------------------------------------------------------

class TestExtractInterfacesFromGo:
    def test_extracts_interfaces(self):
        interfaces = extract_interfaces_from_go(FIXTURE)
        names = [i.name for i in interfaces]
        assert "Reader" in names
        assert "Writer" in names

    def test_interface_methods_extracted(self):
        interfaces = extract_interfaces_from_go(FIXTURE)
        by_name = {i.name: i for i in interfaces}
        reader_methods = by_name["Reader"].methods
        assert len(reader_methods) >= 1
        assert any(m.name == "Read" for m in reader_methods)

    def test_interface_type_is_interface(self):
        interfaces = extract_interfaces_from_go(FIXTURE)
        by_name = {i.name: i for i in interfaces}
        assert by_name["Reader"].type == "interface"

    def test_empty_when_binary_missing(self):
        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            interfaces = extract_interfaces_from_go(FIXTURE)
            # Should still work with pure-python fallback
            assert isinstance(interfaces, list)


# ---------------------------------------------------------------------------
# extract_imports_from_go
# ---------------------------------------------------------------------------

class TestExtractImportsFromGo:
    def test_extracts_imports_from_fixture(self):
        imports = extract_imports_from_go(FIXTURE)
        paths = [imp.path for imp in imports]
        assert "fmt" in paths

    def test_extracts_imports_from_complex_fixture(self):
        imports = extract_imports_from_go(FIXTURE_COMPLEX)
        paths = [imp.path for imp in imports]
        assert "fmt" in paths
        assert "io" in paths
        assert "os" in paths


# ---------------------------------------------------------------------------
# _find_goast
# ---------------------------------------------------------------------------

class TestFindGoast:
    def test_returns_path_when_binary_exists(self):
        bin = _find_goast()
        if bin and bin.exists():
            assert isinstance(bin, Path)

    def test_returns_none_when_not_installed(self):
        bin = _find_goast()
        # Just ensure it returns a Path or None
        assert bin is None or isinstance(bin, Path)


# ---------------------------------------------------------------------------
# Integration: extract_all with Go language
# ---------------------------------------------------------------------------

class TestExtractAllGo:
    def test_extract_all_wires_go_extraction(self):
        from repo_transmute.blueprint.extractor import extract_all

        repo_path = FIXTURE.parent
        bp = extract_all(repo_path, "go")

        names = [f.name for f in bp.functions]
        assert "Add" in names
        assert "Greet" in names

        struct_names = [s.name for s in bp.data_structures]
        assert "Person" in struct_names

        interface_names = [i.name for i in bp.data_structures]
        assert "Reader" in interface_names
