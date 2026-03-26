"""Tests for LLM output cleaning, import validation, and post-processing."""

import pytest
from repo_transmute.transpiler.llm import Transpiler, KNOWN_BUILTINS, KNOWN_NPM_PACKAGES


# ---------------------------------------------------------------------------
# _is_invalid_import
# ---------------------------------------------------------------------------

class TestIsInvalidImport:
    """_is_invalid_import must correctly classify known-good vs known-bad modules."""

    @pytest.mark.parametrize("module", [
        "json", "regex", "re",
        "system", "sys", "os", "builtins",
        "functools", "itertools", "collections", "dataclasses",
        "typing", "types", "inspect", "ast", "io", "contextlib",
    ])
    def test_python_stdlib_flagged_as_invalid(self, module):
        t = Transpiler()
        assert t._is_invalid_import(module) is True, f"{module} should be flagged invalid"

    def test_async_is_valid_npm_package(self):
        """async is a real npm package — must not be flagged as invalid."""
        t = Transpiler()
        assert t._is_invalid_import("async") is False

    def test_asyncio_is_valid_npm_package(self):
        """asyncio is a published npm package — must not be flagged as invalid."""
        t = Transpiler()
        assert t._is_invalid_import("asyncio") is False

    @pytest.mark.parametrize("module", [
        "react", "react-dom", "lodash", "zod", "axios", "swr",
        "express", "fastify", "vitest", "jest",
        "fs", "crypto", "stream", "http", "https", "events",
    ])
    def test_known_npm_and_node_builtins_accepted(self, module):
        t = Transpiler()
        assert t._is_invalid_import(module) is False, f"{module} should be accepted"

    def test_path_is_node_builtin_accepted(self):
        """path is a Node.js built-in — must be accepted."""
        t = Transpiler()
        assert t._is_invalid_import("path") is False

    def test_scoped_package_strips_prefix(self):
        t = Transpiler()
        assert t._is_invalid_import("@types/node") is False
        assert t._is_invalid_import("@babel/core") is False

    def test_path_suffix_stripped(self):
        t = Transpiler()
        assert t._is_invalid_import("lodash/map") is False


# ---------------------------------------------------------------------------
# _fix_invalid_imports
# ---------------------------------------------------------------------------

class TestFixInvalidImports:
    """Invalid imports replaced with warning comments, code preserved."""

    def _code_lines(self, result):
        """Strip warning comment lines to get only actual code lines."""
        return [l for l in result.split("\n") if not l.startswith("// ⚠️")]

    def test_json_import_removed_but_code_preserved(self):
        t = Transpiler()
        code = 'import * as json from "json";\nexport const x = 1;'
        result = t._fix_invalid_imports(code)
        code_only = self._code_lines(result)
        assert "json" not in "\n".join(code_only)
        assert "export const x = 1;" in "\n".join(code_only)
        assert "⚠️" in result

    def test_regex_import_removed_but_code_preserved(self):
        t = Transpiler()
        code = 'import * as re from "regex";\nexport function foo(): void { }'
        result = t._fix_invalid_imports(code)
        code_only = self._code_lines(result)
        assert "regex" not in "\n".join(code_only)
        assert "foo" in "\n".join(code_only)

    def test_os_and_sys_removed_but_code_preserved(self):
        t = Transpiler()
        code = 'import * as os from "os";\nimport * as sys from "sys";\nexport const x = 1;'
        result = t._fix_invalid_imports(code)
        code_only = self._code_lines(result)
        assert "os" not in "\n".join(code_only)
        assert "sys" not in "\n".join(code_only)
        assert "export const x = 1;" in "\n".join(code_only)

    def test_react_kept(self):
        t = Transpiler()
        code = 'import { useState } from "react";\nexport const x = 1;'
        result = t._fix_invalid_imports(code)
        code_only = self._code_lines(result)
        assert "react" in "\n".join(code_only)
        assert "⚠️" not in result

    def test_python_from_import_removed_warning_but_code_preserved(self):
        """Python from...import → warning comment + removed; valid TS code preserved."""
        t = Transpiler()
        code = "from os import path\nconst x = 1;"
        result = t._fix_invalid_imports(code)
        # Python import replaced with warning comment, not present in code lines
        code_only = self._code_lines(result)
        assert code_only == ["const x = 1;"]
        assert "⚠️" in result
        assert "from os" not in "\n".join(code_only)

    def test_python_bare_import_removed_warning_but_code_preserved(self):
        """Python bare import → warning comment + removed; valid TS code preserved."""
        t = Transpiler()
        code = "import os\nimport sys\nconst x = 1;"
        result = t._fix_invalid_imports(code)
        code_only = self._code_lines(result)
        assert code_only == ["const x = 1;"]
        assert "⚠️" in result
        assert "import os" not in "\n".join(code_only)
        assert "import sys" not in "\n".join(code_only)

    def test_valid_js_named_import_unchanged(self):
        t = Transpiler()
        code = 'import { useEffect } from "react";\nexport function Foo() { }'
        result = t._fix_invalid_imports(code)
        code_only = self._code_lines(result)
        assert "useEffect" in "\n".join(code_only)
        assert "Foo" in "\n".join(code_only)


# ---------------------------------------------------------------------------
# _post_clean — full pipeline
# ---------------------------------------------------------------------------

class TestPostClean:
    """End-to-end output cleaning: thinking tags, markdown, docstrings, imports, etc."""

    def test_strips_think_tags(self):
        t = Transpiler()
        code = "<think> ignore this</think>\nexport const x = 1;"
        result = t._post_clean(code, "typescript")
        assert "<think>" not in result
        assert "export const x = 1;" in result

    def test_strips_thought_tags(self):
        t = Transpiler()
        code = "<thought>ignore this</thought>\nexport function foo(): void { }"
        result = t._post_clean(code, "typescript")
        assert "export function foo" in result

    def test_strips_markdown_fences(self):
        t = Transpiler()
        code = "```typescript\nexport const x = 1;\n```"
        result = t._post_clean(code, "typescript")
        assert "```" not in result
        assert "export const x = 1;" in result

    def test_strips_triple_quote_docstrings(self):
        t = Transpiler()
        code = '"""\nThis is a docstring\n"""\nexport const x = 1;'
        result = t._post_clean(code, "typescript")
        assert '"""' not in result
        assert "export const x = 1;" in result

    def test_removes_python_import_lines_preserves_ts(self):
        """Python import lines stripped; valid TS code preserved."""
        t = Transpiler()
        code = "from os import path\nconst x = 1;"
        result = t._post_clean(code, "typescript")
        code_lines = [l for l in result.split("\n") if not l.startswith("// ⚠️")]
        assert "from os" not in "\n".join(code_lines)
        assert "const x = 1;" in "\n".join(code_lines)

    def test_strips_python_all_variable(self):
        t = Transpiler()
        code = "__all__ = ['foo', 'bar']\nexport function foo(): void { }"
        result = t._post_clean(code, "typescript")
        assert "__all__" not in result
        assert "foo" in result

    def test_short_but_valid_typescript_preserved(self):
        t = Transpiler()
        valid_short = [
            "const x = 1;",
            "export function foo(): void { }",
            "interface Bar { }",
            "export const x = 1;",
            "export type Foo = string;",
            "export interface X { }",
        ]
        for code in valid_short:
            result = t._post_clean(code, "typescript")
            assert len(result) > 0, f"Should preserve: {code!r}"
            assert "⚠️" not in result

    def test_empty_output_raises(self):
        t = Transpiler()
        with pytest.raises(ValueError, match="emptied"):
            t._post_clean("", "typescript")

    def test_whitespace_only_raises(self):
        t = Transpiler()
        with pytest.raises(ValueError, match="emptied"):
            t._post_clean("   ", "typescript")

    def test_narrative_no_code_raises(self):
        """Pure narrative with no code tokens raises ValueError."""
        t = Transpiler()
        with pytest.raises(ValueError, match="gibberish|emptied"):
            t._post_clean("Here is the transpiled code for you:", "typescript")

    def test_removes_invented_json_import_keeps_global(self):
        """Invented import * as json removed; JSON global kept."""
        t = Transpiler()
        code = 'import * as json from "json";\nconst obj = JSON.parse("{}");'
        result = t._post_clean(code, "typescript")
        assert "JSON.parse" in result
        code_lines = [l for l in result.split("\n") if not l.startswith("// ⚠️")]
        joined = "\n".join(code_lines)
        assert "import * as json" not in joined

    def test_invented_os_import_removed(self):
        """Invented import * as os removed with warning."""
        t = Transpiler()
        code = 'import * as os from "os";\nexport const x = 1;'
        result = t._post_clean(code, "typescript")
        assert "⚠️" in result
        code_lines = [l for l in result.split("\n") if not l.startswith("// ⚠️")]
        assert "export const x = 1;" in "\n".join(code_lines)
