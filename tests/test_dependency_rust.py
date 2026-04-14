"""Tests for Rust dependency parsing (use statements, Cargo.toml)."""

import textwrap
from pathlib import Path

import pytest

from repo_transmute.dependency.graph import (
    DependencyGraph,
    parse_cargo_toml,
    parse_go_mod,
    parse_imports,
    _parse_rust_use,
)


# ---------------------------------------------------------------------------
# _parse_rust_use
# ---------------------------------------------------------------------------

class TestParseRustUse:
    def test_simple_use(self):
        code = 'use std::fs;'
        result = _parse_rust_use(code)
        assert result == ['std::fs']

    def test_multiple_simple_uses(self):
        code = textwrap.dedent("""\
            use std::fs;
            use std::io::Read;
            use crate::parser;
        """)
        result = _parse_rust_use(code)
        assert 'std::fs' in result
        assert 'std::io::Read' in result
        assert 'crate::parser' in result

    def test_grouped_use(self):
        code = 'use std::collections::{HashMap, BTreeMap};'
        result = _parse_rust_use(code)
        assert 'std::collections::HashMap' in result
        assert 'std::collections::BTreeMap' in result
        assert len(result) == 2

    def test_super_use(self):
        code = 'use super::module;'
        result = _parse_rust_use(code)
        assert result == ['super::module']

    def test_self_use(self):
        code = 'use self::local_module;'
        result = _parse_rust_use(code)
        assert result == ['self::local_module']

    def test_empty_file(self):
        assert _parse_rust_use('') == []

    def test_mixed_uses(self):
        code = textwrap.dedent("""\
            use std::fs;
            use serde::{Serialize, Deserialize};
            use crate::models::User;
        """)
        result = _parse_rust_use(code)
        assert 'std::fs' in result
        assert 'serde::Serialize' in result
        assert 'serde::Deserialize' in result
        assert 'crate::models::User' in result
        assert len(result) == 4


# ---------------------------------------------------------------------------
# parse_imports — Rust dispatch
# ---------------------------------------------------------------------------

class TestParseImportsRust:
    def test_parse_imports_rust_file(self, tmp_path):
        f = tmp_path / "main.rs"
        f.write_text(textwrap.dedent("""\
            use std::fs;
            use crate::parser::parse_input;
        """))
        result = parse_imports(f)
        assert any('std::fs' in imp for imp in result)
        assert any('parser' in imp for imp in result)

    def test_infer_rust_from_extension(self, tmp_path):
        f = tmp_path / "lib.rs"
        f.write_text("use std::collections::HashMap;")
        result = parse_imports(f)
        assert any('HashMap' in imp for imp in result)


# ---------------------------------------------------------------------------
# parse_cargo_toml
# ---------------------------------------------------------------------------

class TestParseCargoToml:
    def test_basic_deps(self, tmp_path):
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text(textwrap.dedent("""\
            [package]
            name = "myapp"
            version = "0.1.0"

            [dependencies]
            serde = "1.0"
            tokio = { version = "1", features = ["full"] }
            regex = "1"

            [dev-dependencies]
            tempfile = "3"
        """))
        result = parse_cargo_toml(cargo)
        assert 'serde' in result['dependencies']
        assert 'tokio' in result['dependencies']
        assert 'regex' in result['dependencies']
        assert 'tempfile' in result['dev-dependencies']

    def test_no_deps(self, tmp_path):
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text(textwrap.dedent("""\
            [package]
            name = "empty"
            version = "0.1.0"
        """))
        result = parse_cargo_toml(cargo)
        assert result['dependencies'] == []
        assert result['dev-dependencies'] == []

    def test_missing_file(self, tmp_path):
        result = parse_cargo_toml(tmp_path / "nonexistent.toml")
        assert result['dependencies'] == []
        assert result['dev-dependencies'] == []

    def test_workspace_inherit(self, tmp_path):
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text(textwrap.dedent("""\
            [dependencies]
            serde.workspace = true
            clap = { version = "4", features = ["derive"] }
        """))
        result = parse_cargo_toml(cargo)
        assert 'serde' in result['dependencies']
        assert 'clap' in result['dependencies']

    def test_commented_lines_skipped(self, tmp_path):
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text(textwrap.dedent("""\
            [dependencies]
            # old_dep = "1.0"
            serde = "1.0"
        """))
        result = parse_cargo_toml(cargo)
        assert 'serde' in result['dependencies']
        assert '# old_dep' not in str(result['dependencies'])


# ---------------------------------------------------------------------------
# parse_go_mod
# ---------------------------------------------------------------------------

class TestParseGoMod:
    def test_basic_go_mod(self, tmp_path):
        gomod = tmp_path / "go.mod"
        gomod.write_text(textwrap.dedent("""\
            module github.com/user/myapp

            go 1.21

            require (
                github.com/gin-gonic/gin v1.9.0
                golang.org/x/text v0.9.0
            )
        """))
        result = parse_go_mod(gomod)
        assert result['module'] == ['github.com/user/myapp']
        assert result['go'] == ['1.21']
        assert 'github.com/gin-gonic/gin' in result['require']
        assert 'golang.org/x/text' in result['require']

    def test_indirect_deps(self, tmp_path):
        gomod = tmp_path / "go.mod"
        gomod.write_text(textwrap.dedent("""\
            module myapp

            go 1.21

            require (
                github.com/gin-gonic/gin v1.9.0
                github.com/json-iterator/go v1.1.12 // indirect
            )
        """))
        result = parse_go_mod(gomod)
        assert 'github.com/gin-gonic/gin' in result['require']
        assert 'github.com/json-iterator/go' in result['indirect']

    def test_single_line_require(self, tmp_path):
        gomod = tmp_path / "go.mod"
        gomod.write_text(textwrap.dedent("""\
            module myapp

            go 1.21

            require github.com/some/pkg v1.0.0
        """))
        result = parse_go_mod(gomod)
        assert 'github.com/some/pkg' in result['require']

    def test_missing_file(self, tmp_path):
        result = parse_go_mod(tmp_path / "nonexistent")
        assert result['module'] == []
        assert result['require'] == []


# ---------------------------------------------------------------------------
# DependencyGraph — Rust integration
# ---------------------------------------------------------------------------

class TestDependencyGraphRust:
    def test_rust_file_imports(self, tmp_path):
        (tmp_path / "main.rs").write_text("use crate::parser;")
        (tmp_path / "parser.rs").write_text("pub fn parse() {}")

        graph = DependencyGraph(root=tmp_path)
        graph.add_file(tmp_path / "main.rs", ["crate::parser"])
        graph.add_file(tmp_path / "parser.rs", [])

        assert tmp_path / "main.rs" in graph.nodes
        assert len(graph.nodes[tmp_path / "main.rs"]) == 1

    def test_infer_rust_language(self, tmp_path):
        """parse_imports correctly infers rust from .rs extension."""
        f = tmp_path / "lib.rs"
        f.write_text("use std::collections::HashMap;")
        imports = parse_imports(f)
        assert any("HashMap" in imp for imp in imports)
