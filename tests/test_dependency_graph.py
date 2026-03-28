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
