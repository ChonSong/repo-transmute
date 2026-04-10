"""Tests for dependency/graph.py."""

import tempfile
import pytest
from pathlib import Path

from repo_transmute.dependency.graph import (
    parse_imports,
    DependencyGraph,
    ProcessQueue,
)


# ---------------------------------------------------------------------------
# parse_imports
# ---------------------------------------------------------------------------

class TestParseImports:
    def make(self, content: str) -> Path:
        p = Path(tempfile.mktemp(suffix=".ts"))
        p.write_text(content)
        return p

    def test_named_import(self):
        p = self.make("import { foo } from './bar';\n")
        assert "./bar" in parse_imports(p)

    def test_default_import(self):
        p = self.make("import React from 'react';\n")
        assert "react" in parse_imports(p)

    def test_wildcard_import(self):
        p = self.make("import * as utils from './utils';\n")
        assert "./utils" in parse_imports(p)

    def test_multiple_imports(self):
        p = self.make(
            "import { a } from './a';\n"
            "import { b } from './b';\n"
        )
        imports = parse_imports(p)
        assert "./a" in imports
        assert "./b" in imports

    def test_relative_import(self):
        p = self.make("import x from '../Parent';\n")
        assert "../Parent" in parse_imports(p)

    def test_external_package(self):
        p = self.make("import React from 'react';\n")
        assert "react" in parse_imports(p)

    def test_dynamic_import(self):
        p = self.make("const m = import('./module');\n")
        assert "./module" in parse_imports(p)

    def test_require(self):
        p = self.make("const _ = require('lodash');\n")
        assert "lodash" in parse_imports(p)

    def test_export_from(self):
        p = self.make("export { foo } from './foo';\n")
        assert "./foo" in parse_imports(p)

    def test_export_star(self):
        p = self.make("export * from './utils';\n")
        assert "./utils" in parse_imports(p)

    def test_inline_comment_not_false_positive(self):
        p = self.make("// import { fake } from './fake';\n")
        assert "./fake" not in parse_imports(p)

    def test_multiline_comment_not_false_positive(self):
        p = self.make("/* import { fake } from './fake'; */\n")
        assert "./fake" not in parse_imports(p)

    def test_missing_file(self):
        imports = parse_imports(Path("/nonexistent/file.ts"))
        assert imports == []

    def test_nonexistent_file_path(self):
        imports = parse_imports(Path("/no/such/file.ts"))
        assert imports == []


# ---------------------------------------------------------------------------
# DependencyGraph
# ---------------------------------------------------------------------------

class TestDependencyGraph:
    def test_empty_graph(self):
        g = DependencyGraph()
        assert g.nodes == {}
        assert g.get_import_order() == []

    def test_add_file(self):
        g = DependencyGraph()
        g.add_file(Path("a.ts"), ["./b", "react"])
        assert Path("a.ts") in g.nodes
        assert "./b" in g.nodes[Path("a.ts")]
        assert "react" in g.nodes[Path("a.ts")]

    def test_resolve_import_no_root(self):
        g = DependencyGraph()
        resolved = g.resolve_import(Path("./b"), Path("a.ts"))
        assert resolved is None

    def test_get_import_order_empty(self):
        g = DependencyGraph()
        order = g.get_import_order()
        assert order == []

    def test_get_import_order_single_node(self):
        g = DependencyGraph()
        g.add_file(Path("a.ts"), [])
        order = g.get_import_order()
        assert order == [Path("a.ts")]

    def test_get_chunk_single_file(self):
        g = DependencyGraph()
        entry = Path("a.ts")
        chunk = g.get_chunk(entry)
        assert chunk == [entry]


# ---------------------------------------------------------------------------
# ProcessQueue
# ---------------------------------------------------------------------------

class TestProcessQueue:
    def make_queue(self) -> ProcessQueue:
        fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = fd.name
        fd.close()
        return ProcessQueue(db_path=db_path)

    def test_add_and_get_next(self):
        q = self.make_queue()
        q.add("owner/repo", priority=1)
        item = q.get_next()
        assert item is not None
        assert item["repo"] == "owner/repo"
        assert item["priority"] == 1
        assert item["status"] == "pending"

    def test_get_next_empty_queue(self):
        q = self.make_queue()
        assert q.get_next() is None

    def test_add_multiple_high_priority_first(self):
        q = self.make_queue()
        q.add("low/repo", priority=0)
        q.add("high/repo", priority=10)
        item = q.get_next()
        assert item["repo"] == "high/repo"

    def test_mark_complete(self):
        q = self.make_queue()
        q.add("owner/repo")
        item = q.get_next()
        assert item["repo"] == "owner/repo"
        q.mark_complete("owner/repo")
        status = q.get_status("owner/repo")
        assert status["status"] == "completed"
        assert status["completed_at"] is not None

    def test_get_status_not_found(self):
        q = self.make_queue()
        assert q.get_status("nonexistent/repo") is None

    def test_get_status_after_add(self):
        q = self.make_queue()
        q.add("owner/repo", priority=5)
        status = q.get_status("owner/repo")
        assert status["repo"] == "owner/repo"
        assert status["priority"] == 5
        assert status["status"] == "pending"

    def test_list_pending(self):
        q = self.make_queue()
        q.add("a/repo", priority=1)
        q.add("b/repo", priority=2)
        pending = q.list_pending()
        assert len(pending) == 2
        assert all(p["status"] == "pending" for p in pending)

    def test_re_add_completed_resets_to_pending(self):
        q = self.make_queue()
        q.add("owner/repo")
        q.mark_complete("owner/repo")
        q.add("owner/repo", priority=5)
        item = q.get_next()
        assert item["repo"] == "owner/repo"
        assert item["priority"] == 5

    def test_re_add_pending_preserves_status(self):
        q = self.make_queue()
        q.add("owner/repo", priority=0)
        q.add("owner/repo", priority=5)
        item = q.get_next()
        # Second add with different priority should update
        assert item["priority"] == 5


# ---------------------------------------------------------------------------
# parse_imports — Python
# ---------------------------------------------------------------------------

class TestParseImportsPython:
    def make(self, content: str) -> Path:
        p = Path(tempfile.mktemp(suffix=".py"))
        p.write_text(content)
        return p

    def test_import_module(self):
        p = self.make("import os\nimport sys\n")
        imports = parse_imports(p)
        assert "os" in imports
        assert "sys" in imports

    def test_from_import(self):
        p = self.make("from foo import bar\n")
        assert "foo" in parse_imports(p)

    def test_from_import_nested(self):
        p = self.make("from foo.bar import baz\nfrom a.b.c import d\n")
        imports = parse_imports(p)
        assert "foo.bar" in imports
        assert "a.b.c" in imports

    def test_import_module_alias(self):
        p = self.make("import os as operating_system\n")
        imports = parse_imports(p)
        assert "os" in imports

    def test_comment_not_false_positive(self):
        p = self.make("# import os\nimport sys\n")
        imports = parse_imports(p)
        assert "os" not in imports
        assert "sys" in imports


# ---------------------------------------------------------------------------
# parse_imports — Go
# ---------------------------------------------------------------------------

class TestParseImportsGo:
    def make(self, content: str) -> Path:
        p = Path(tempfile.mktemp(suffix=".go"))
        p.write_text(content)
        return p

    def test_import_single(self):
        p = self.make('package main\nimport "fmt"\n')
        imports = parse_imports(p)
        assert "fmt" in imports

    def test_import_multiple(self):
        p = self.make('package main\nimport "fmt"\nimport "os"\n')
        imports = parse_imports(p)
        assert "fmt" in imports
        assert "os" in imports

    def test_import_block(self):
        p = self.make('package main\nimport (\n  "fmt"\n  "os"\n)\n')
        imports = parse_imports(p)
        assert "fmt" in imports
        assert "os" in imports

    def test_import_aliased(self):
        p = self.make('package main\nimport f "fmt"\n')
        imports = parse_imports(p)
        assert "fmt" in imports


# ---------------------------------------------------------------------------
# DependencyGraph — reverse index
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# DependencyGraph — reverse index
# ---------------------------------------------------------------------------

class TestDependencyGraphReverse:
    def test_reverse_index_basic(self):
        """Test that build_reverse_index correctly maps importers to imported files.

        Uses a real temp directory so resolve_import can find actual files.
        """
        import tempfile, shutil
        tmp = tempfile.mkdtemp()
        root = Path(tmp)

        (root / "a.ts").write_text('import { b } from "./b";')
        (root / "b.ts").write_text("")

        g = DependencyGraph(root=root)
        g.add_file(root / "a.ts", ["./b"])
        g.add_file(root / "b.ts", [])
        g.build_reverse_index()

        # a.ts imports b.ts => b.ts should have a.ts as an importer in reverse index
        assert root / "a.ts" in g.reverse[root / "b.ts"], (
            f"a.ts should be reverse-dependent on b.ts, got {g.reverse}"
        )

        shutil.rmtree(tmp)

    def test_reverse_index_self_ref(self):
        """A file that imports nothing still gets an entry in reverse (empty set)."""
        g = DependencyGraph()
        g.add_file(Path("a.ts"), [])
        g.build_reverse_index()
        # A file with no imports still appears in reverse index (empty set)
        assert Path("a.ts") in g.reverse
        assert g.reverse[Path("a.ts")] == set()

    def test_reverse_index_external_no_resolve(self):
        """External packages that can't be resolved don't pollute reverse index."""
        g = DependencyGraph()
        g.add_file(Path("a.ts"), ["react", "lodash"])
        g.build_reverse_index()
        # Since these can't be resolved locally, reverse should only have self-ref
        assert Path("a.ts") in g.reverse
