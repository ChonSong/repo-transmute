"""Tests for multi-language chunker support (Go, JS/TS, Rust)."""

import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from repo_transmute.transpiler.chunker import (
    LANG_EXTENSIONS,
    IGNORE_DIRS,
    Chunk,
    chunk_by_files,
    chunk_repository,
    count_functions,
    create_chunks,
    extract_exports,
    extract_imports,
    _find_source_files,
    _count_go_functions,
    _count_js_functions,
    _count_rust_functions,
    _extract_go_imports,
    _extract_js_imports,
    _extract_rust_imports,
    _extract_go_exports,
    _extract_js_exports,
    _extract_rust_exports,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_go_repo(tmp_path):
    """Create a minimal Go repository."""
    # main.go
    (tmp_path / "main.go").write_text(textwrap.dedent("""\
        package main

        import (
            "fmt"
            "myapp/pkg/handler"
        )

        func main() {
            fmt.Println("hello")
            h := handler.NewHandler()
            h.Serve()
        }
    """))

    # pkg/handler/handler.go
    pkg_dir = tmp_path / "pkg" / "handler"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "handler.go").write_text(textwrap.dedent("""\
        package handler

        import "net/http"

        // Handler processes HTTP requests
        type Handler struct {
            Addr string
        }

        // NewHandler creates a Handler
        func NewHandler() *Handler {
            return &Handler{Addr: ":8080"}
        }

        // Serve starts the HTTP server
        func (h *Handler) Serve() error {
            return http.ListenAndServe(h.Addr, nil)
        }
    """))

    # pkg/handler/handler_test.go (should be skipped)
    (pkg_dir / "handler_test.go").write_text(textwrap.dedent("""\
        package handler

        import "testing"

        func TestNewHandler(t *testing.T) {
            h := NewHandler()
            if h == nil {
                t.Fatal("expected non-nil handler")
            }
        }
    """))

    return tmp_path


@pytest.fixture
def tmp_js_repo(tmp_path):
    """Create a minimal JavaScript/TypeScript repository."""
    # index.ts
    (tmp_path / "index.ts").write_text(textwrap.dedent("""\
        import { greet } from "./utils";
        import type { Config } from "./types";
        import * as fs from "fs";

        export function main(config: Config): void {
            console.log(greet("world"));
        }

        export const VERSION = "1.0.0";
    """))

    # utils.ts
    (tmp_path / "utils.ts").write_text(textwrap.dedent("""\
        export function greet(name: string): string {
            return `Hello, ${name}!`;
        }

        export async function delay(ms: number): Promise<void> {
            return new Promise(resolve => setTimeout(resolve, ms));
        }
    """))

    # types.ts
    (tmp_path / "types.ts").write_text(textwrap.dedent("""\
        export interface Config {
            port: number;
            host: string;
        }

        export type Result<T> = { ok: true; value: T } | { ok: false; error: string };
    """))

    # component.tsx
    (tmp_path / "component.tsx").write_text(textwrap.dedent("""\
        import React from "react";
        import { Config } from "./types";

        export class App extends React.Component<Config> {
            render() { return <div>{this.props.host}</div>; }
        }

        export default function Layout() { return <div />; }
    """))

    return tmp_path


@pytest.fixture
def tmp_rust_repo(tmp_path):
    """Create a minimal Rust repository."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "main.rs").write_text(textwrap.dedent("""\
        use crate::parser::parse_input;
        use std::fs;

        pub fn main() {
            let content = fs::read_to_string("input.txt").unwrap();
            let result = parse_input(&content);
            println!("{:?}", result);
        }

        pub struct App {
            name: String,
        }

        pub enum Status {
            Running,
            Stopped,
        }
    """))

    (src / "parser.rs").write_text(textwrap.dedent("""\
        pub fn parse_input(input: &str) -> Vec<String> {
            input.lines().map(|s| s.to_string()).collect()
        }

        pub trait Parsable {
            fn parse(&self) -> String;
        }
    """))

    return tmp_path


# ---------------------------------------------------------------------------
# LANG_EXTENSIONS mapping
# ---------------------------------------------------------------------------

class TestLangExtensions:
    def test_python(self):
        assert ".py" in LANG_EXTENSIONS["python"]

    def test_go(self):
        assert ".go" in LANG_EXTENSIONS["go"]

    def test_javascript(self):
        assert ".js" in LANG_EXTENSIONS["javascript"]
        assert ".jsx" in LANG_EXTENSIONS["javascript"]

    def test_typescript(self):
        assert ".ts" in LANG_EXTENSIONS["typescript"]
        assert ".tsx" in LANG_EXTENSIONS["typescript"]

    def test_rust(self):
        assert ".rs" in LANG_EXTENSIONS["rust"]


# ---------------------------------------------------------------------------
# count_functions — multi-language dispatch
# ---------------------------------------------------------------------------

class TestCountFunctionsGo:
    def test_count_go_functions(self, tmp_go_repo):
        main_go = tmp_go_repo / "main.go"
        assert main_go.exists()
        count = count_functions(main_go)
        # main() func → at least 1
        assert count >= 1

    def test_count_go_structs_and_funcs(self, tmp_go_repo):
        handler_go = tmp_go_repo / "pkg" / "handler" / "handler.go"
        assert handler_go.exists()
        count = count_functions(handler_go)
        # NewHandler, Serve (methods), Handler struct → at least 2
        assert count >= 2


class TestCountFunctionsJS:
    def test_count_js_functions(self, tmp_js_repo):
        utils = tmp_js_repo / "utils.ts"
        count = count_functions(utils)
        # greet + delay = 2
        assert count >= 2

    def test_count_tsx_exports(self, tmp_js_repo):
        comp = tmp_js_repo / "component.tsx"
        count = count_functions(comp)
        # Layout function declaration counts as a function
        assert count >= 1


class TestCountFunctionsRust:
    def test_count_rust_functions(self, tmp_rust_repo):
        main_rs = tmp_rust_repo / "src" / "main.rs"
        count = count_functions(main_rs)
        # main() fn → at least 1
        assert count >= 1

    def test_count_rust_parser(self, tmp_rust_repo):
        parser_rs = tmp_rust_repo / "src" / "parser.rs"
        count = count_functions(parser_rs)
        # parse_input fn → at least 1
        assert count >= 1


class TestCountFunctionsUnknownExt:
    def test_unknown_extension_returns_zero(self, tmp_path):
        unknown = tmp_path / "data.csv"
        unknown.write_text("a,b,c\n1,2,3")
        assert count_functions(unknown) == 0


# ---------------------------------------------------------------------------
# extract_imports — multi-language dispatch
# ---------------------------------------------------------------------------

class TestExtractImportsGo:
    def test_go_imports(self, tmp_go_repo):
        main_go = tmp_go_repo / "main.go"
        imports = extract_imports(main_go)
        # Should find "fmt" and "myapp/pkg/handler"
        assert any("fmt" in imp for imp in imports)
        assert any("handler" in imp for imp in imports)


class TestExtractImportsJS:
    def test_js_imports(self, tmp_js_repo):
        index = tmp_js_repo / "index.ts"
        imports = extract_imports(index)
        # Should find ./utils, ./types, fs
        assert any("utils" in imp for imp in imports)
        assert any("types" in imp for imp in imports)
        assert any("fs" in imp for imp in imports)


class TestExtractImportsRust:
    def test_rust_imports(self, tmp_rust_repo):
        main_rs = tmp_rust_repo / "src" / "main.rs"
        imports = extract_imports(main_rs)
        # Should find crate::parser::parse_input and std::fs
        assert any("parser" in imp for imp in imports)
        assert any("fs" in imp for imp in imports)


# ---------------------------------------------------------------------------
# extract_exports — multi-language dispatch
# ---------------------------------------------------------------------------

class TestExtractExportsGo:
    def test_go_exports(self, tmp_go_repo):
        handler_go = tmp_go_repo / "pkg" / "handler" / "handler.go"
        exports = extract_exports(handler_go)
        # Handler, NewHandler, Serve are PascalCase → exported
        assert "Handler" in exports or "NewHandler" in exports


class TestExtractExportsJS:
    def test_js_exports(self, tmp_js_repo):
        utils = tmp_js_repo / "utils.ts"
        exports = extract_exports(utils)
        assert "greet" in exports
        assert "delay" in exports

    def test_js_tsx_exports(self, tmp_js_repo):
        comp = tmp_js_repo / "component.tsx"
        exports = extract_exports(comp)
        assert "App" in exports

    def test_js_types_exports(self, tmp_js_repo):
        types = tmp_js_repo / "types.ts"
        exports = extract_exports(types)
        assert "Config" in exports
        assert "Result" in exports


class TestExtractExportsRust:
    def test_rust_exports(self, tmp_rust_repo):
        main_rs = tmp_rust_repo / "src" / "main.rs"
        exports = extract_exports(main_rs)
        # pub fn main, pub struct App, pub enum Status
        assert "main" in exports
        assert "App" in exports
        assert "Status" in exports

    def test_rust_parser_exports(self, tmp_rust_repo):
        parser_rs = tmp_rust_repo / "src" / "parser.rs"
        exports = extract_exports(parser_rs)
        assert "parse_input" in exports
        assert "Parsable" in exports


# ---------------------------------------------------------------------------
# _find_source_files
# ---------------------------------------------------------------------------

class TestFindSourceFiles:
    def test_finds_go_files_excluding_tests(self, tmp_go_repo):
        files = _find_source_files(tmp_go_repo, {".go"})
        names = [f.name for f in files]
        assert "main.go" in names
        assert "handler.go" in names
        assert "handler_test.go" not in names

    def test_finds_ts_files(self, tmp_js_repo):
        files = _find_source_files(tmp_js_repo, {".ts", ".tsx"})
        names = [f.name for f in files]
        assert "index.ts" in names
        assert "utils.ts" in names
        assert "component.tsx" in names

    def test_finds_rust_files(self, tmp_rust_repo):
        files = _find_source_files(tmp_rust_repo, {".rs"})
        names = [f.name for f in files]
        assert "main.rs" in names
        assert "parser.rs" in names

    def test_excludes_git_dirs(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("stuff")
        (tmp_path / "main.py").write_text("def foo(): pass")
        files = _find_source_files(tmp_path, {".py"})
        names = [f.name for f in files]
        assert "main.py" in names
        assert "config" not in names

    def test_excludes_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")
        (tmp_path / "app.js").write_text("function main() {}")
        files = _find_source_files(tmp_path, {".js"})
        names = [f.name for f in files]
        assert "app.js" in names
        assert "index.js" not in names


# ---------------------------------------------------------------------------
# chunk_repository — language parameter
# ---------------------------------------------------------------------------

class TestChunkRepositoryMultiLang:
    def test_chunk_go_repo(self, tmp_go_repo):
        chunks = chunk_repository(tmp_go_repo, language="go")
        assert len(chunks) >= 1
        # Should find at least 2 Go files (main.go + handler.go)
        all_files = []
        for c in chunks:
            all_files.extend(c.files)
        go_files = [f for f in all_files if f.suffix == ".go"]
        assert len(go_files) >= 2
        # Should NOT include test files
        test_files = [f for f in all_files if "_test.go" in f.name]
        assert len(test_files) == 0

    def test_chunk_js_repo(self, tmp_js_repo):
        chunks = chunk_repository(tmp_js_repo, language="typescript")
        assert len(chunks) >= 1
        all_files = []
        for c in chunks:
            all_files.extend(c.files)
        ts_files = [f for f in all_files if f.suffix in (".ts", ".tsx")]
        assert len(ts_files) >= 3  # index.ts, utils.ts, types.ts, component.tsx

    def test_chunk_rust_repo(self, tmp_rust_repo):
        chunks = chunk_repository(tmp_rust_repo, language="rust")
        assert len(chunks) >= 1
        all_files = []
        for c in chunks:
            all_files.extend(c.files)
        rs_files = [f for f in all_files if f.suffix == ".rs"]
        assert len(rs_files) >= 2  # main.rs, parser.rs

    def test_chunk_default_language_is_python(self, tmp_path):
        """Without language arg, defaults to Python."""
        (tmp_path / "main.py").write_text("def hello(): pass\ndef world(): pass")
        (tmp_path / "main.go").write_text("package main\nfunc main() {}")
        chunks = chunk_repository(tmp_path)
        all_files = []
        for c in chunks:
            all_files.extend(c.files)
        # Only .py files should be found
        assert all(f.suffix == ".py" for f in all_files)
        assert len(all_files) == 1

    def test_chunk_empty_repo(self, tmp_path):
        """Repo with no matching files returns empty list."""
        (tmp_path / "README.md").write_text("# hello")
        chunks = chunk_repository(tmp_path, language="go")
        assert chunks == []


# ---------------------------------------------------------------------------
# create_chunks — language parameter
# ---------------------------------------------------------------------------

class TestCreateChunksLangParam:
    def test_create_chunks_go_with_imports(self, tmp_go_repo):
        files = _find_source_files(tmp_go_repo, {".go"})
        chunks = create_chunks(files, base_path=tmp_go_repo, language="go")
        assert len(chunks) >= 1
        # At least one chunk should have imports
        all_imports = []
        for c in chunks:
            all_imports.extend(c.imports)
        assert len(all_imports) >= 1  # Go files have imports

    def test_create_chunks_js_with_exports(self, tmp_js_repo):
        files = _find_source_files(tmp_js_repo, {".ts", ".tsx"})
        chunks = create_chunks(files, base_path=tmp_js_repo, language="typescript")
        assert len(chunks) >= 1
        all_exports = []
        for c in chunks:
            all_exports.extend(c.exports)
        # Should find greet, delay, Config, Result, App
        assert len(all_exports) >= 3

    def test_create_chunks_rust_cross_deps(self, tmp_rust_repo):
        files = _find_source_files(tmp_rust_repo, {".rs"})
        chunks = create_chunks(files, base_path=tmp_rust_repo, language="rust")
        # main.rs uses crate::parser, so if chunks are separate, deps should be detected
        if len(chunks) > 1:
            # At least one chunk should have a dependency
            has_dep = any(len(c.dependencies) > 0 for c in chunks)
            assert has_dep, "Expected cross-chunk Rust dependency (crate::parser)"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_go_empty_file(self, tmp_path):
        f = tmp_path / "empty.go"
        f.write_text("package main\n")
        assert count_functions(f) == 0
        assert extract_imports(f) == [] or len(extract_imports(f)) == 0
        assert extract_exports(f) == [] or len(extract_exports(f)) == 0

    def test_js_empty_file(self, tmp_path):
        f = tmp_path / "empty.ts"
        f.write_text("")
        assert count_functions(f) == 0
        assert extract_imports(f) == []
        assert extract_exports(f) == []

    def test_rust_empty_file(self, tmp_path):
        f = tmp_path / "empty.rs"
        f.write_text("")
        assert count_functions(f) == 0
        assert extract_imports(f) == []
        assert extract_exports(f) == []

    def test_nonexistent_file_returns_gracefully(self, tmp_path):
        f = tmp_path / "does_not_exist.go"
        # count_functions should handle missing files
        assert count_functions(f) == 0

    def test_go_regex_fallback_on_bad_ast(self, tmp_path):
        """Go parser might fail on invalid Go; should fallback to regex."""
        f = tmp_path / "bad.go"
        f.write_text("package main\n\nfunc Foo() {}\nfunc Bar() {}\n")
        count = count_functions(f)
        assert count >= 2  # At least Foo and Bar via regex fallback

    def test_js_require_imports(self, tmp_path):
        f = tmp_path / "old.js"
        f.write_text("const fs = require('fs');\nconst path = require('path');\n")
        imports = extract_imports(f)
        assert "fs" in imports
        assert "path" in imports

    def test_js_export_braces(self, tmp_path):
        f = tmp_path / "mod.js"
        f.write_text("export { foo, bar, baz };\n")
        exports = extract_exports(f)
        assert "foo" in exports
        assert "bar" in exports
        assert "baz" in exports

    def test_rust_pub_async_fn(self, tmp_path):
        f = tmp_path / "async.rs"
        f.write_text("pub async fn fetch_data() -> Result<String, Error> {\n    Ok(\"data\".into())\n}\n")
        exports = extract_exports(f)
        assert "fetch_data" in exports
        count = count_functions(f)
        assert count >= 1
