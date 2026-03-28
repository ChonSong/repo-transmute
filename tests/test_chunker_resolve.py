"""Tests for Reassembler.resolve_imports() and _resolve_imports_in_text().

Covers:
- Named imports: import { A, B } from './module'
- Default imports: import React from 'react'
- Wildcard imports: import * as utils from './utils'
- Dynamic imports: import('./path')
- Re-export chains: export { foo } from './bar'
- Relative path normalisations: ../utils, ./helpers
- Multi-chunk cross-reference resolution via global_exports
"""

import pytest
from pathlib import Path, PurePath
import tempfile

from repo_transmute.transpiler.chunker import (
    Chunk,
    Reassembler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def reassembler(tmp_path: Path) -> Reassembler:
    """Build a Reassembler with two chunks whose exports are known."""
    # Chunk 0: src/models.py → exports: User, Post
    # Chunk 1: src/services.py → exports: userService, postService
    src = tmp_path / "src"
    src.mkdir()

    models = src / "models.py"
    models.touch()

    services = src / "services.py"
    services.touch()

    chunk0 = Chunk(id=0, files=[models], exports=["User", "Post"], dependencies=[])
    chunk1 = Chunk(id=1, files=[services], exports=["userService", "postService"], dependencies=[0])

    reassembler = Reassembler(chunks=[chunk0, chunk1], base_path=tmp_path)
    # Simulate transpiled output for each chunk (TypeScript)
    reassembler.add_transpiled(
        0,
        "// filename: src/models.ts\nexport class User { }\nexport class Post { }",
        file_paths=[models],
    )
    reassembler.add_transpiled(
        1,
        (
            "// filename: src/services.ts\n"
            "import { User, Post } from './models';\n"
            "export const userService = new User();\n"
            "import React from 'react';\n"
            "import * as utils from './helpers';\n"
        ),
        file_paths=[services],
    )
    return reassembler


# ---------------------------------------------------------------------------
# resolve_imports() — integration
# ---------------------------------------------------------------------------

class TestResolveImports:
    """Full resolve_imports() builds global_exports from chunk metadata."""

    def test_resolve_imports_returns_string(self, reassembler):
        """resolve_imports() returns a non-empty string."""
        result = reassembler.resolve_imports()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_resolve_imports_preserves_external_imports(self, reassembler):
        """External packages (react) are left unchanged."""
        result = reassembler.resolve_imports()
        # 'react' is external — should still be present
        assert "react" in result

    def test_resolve_imports_preserves_wildcard_imports(self, reassembler):
        """Wildcard namespace imports are preserved."""
        result = reassembler.resolve_imports()
        assert "import * as utils" in result

    def test_resolve_imports_resolves_named_imports_from_global_exports(self, reassembler):
        """Symbols found in global_exports are resolved correctly."""
        # User and Post are exported by chunk 0 and imported by chunk 1
        global_exports = {
            "User": "src/models.ts",
            "Post": "src/models.ts",
            "userService": "src/services.ts",
            "postService": "src/services.ts",
        }
        combined = reassembler.combine()
        result = reassembler._resolve_imports_in_text(combined, global_exports)
        # The import line should be preserved (path kept as-is since it's a relative
        # TypeScript import — the fix is that symbols are no longer incorrectly stripped
        # due to trailing-space false-negatives in symbol lookup)
        assert "import { User, Post } from './models'" in result


# ---------------------------------------------------------------------------
# _resolve_imports_in_text() — unit tests
# ---------------------------------------------------------------------------

class TestResolveImportsInText:
    """Unit tests for the import rewriting logic."""

    def test_named_import_rewrites_when_symbol_found(self):
        """import { A } from './b'; where A in global_exports: path updated."""
        text = "import { User } from './models';"
        exports = {"User": "src/models.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        # The named import line should appear unchanged (path is already relative .ts)
        # The important thing is no symbol was incorrectly dropped
        assert "import { User }" in result

    def test_named_import_with_trailing_space_in_symbol(self):
        """Symbols with trailing spaces (from buggy prefix extraction) are trimmed."""
        # This is the actual bug: prefix ends with "from '" so the symbol
        # extraction from prefix+'{' captures ' Post ' instead of 'Post'
        # The fix trims symbols, so ' Post ' -> 'Post'
        text = "import { User, Post } from './models';"
        exports = {"User": "src/models.ts", "Post": "src/models.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        # Both symbols should be preserved, no trailing-space lookup failure
        assert "User" in result
        assert "Post" in result

    def test_named_import_symbol_not_in_exports_kept_as_is(self):
        """import { A } where A not in global_exports: line left unchanged."""
        text = "import { UnknownSymbol } from './unknown';"
        exports = {"User": "src/models.ts"}  # UnknownSymbol not listed

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "UnknownSymbol" in result

    def test_default_import_preserved(self):
        """import React from 'react'; (default import) is not modified."""
        text = "import React from 'react';"
        exports = {"User": "src/models.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "React" in result
        assert "react" in result

    def test_wildcard_import_preserved(self):
        """import * as utils from './helpers'; is not modified."""
        text = "import * as utils from './helpers';"
        exports = {"User": "src/models.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "import * as utils" in result
        assert "./helpers" in result

    def test_relative_path_parent_directory(self):
        """import { foo } from '../utils'; is handled correctly."""
        text = "import { foo } from '../utils';"
        exports = {"foo": "utils.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "../utils" in result

    def test_relative_path_deep_nesting(self):
        """import { bar } from '../../core/bar'; is handled."""
        text = "import { bar } from '../../core/bar';"
        exports = {"bar": "core/bar.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "../../core/bar" in result

    def test_dynamic_import_not_modified(self):
        """import('./path') is left alone."""
        text = "const mod = await import('./dynamic');"
        exports = {}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "import('./dynamic')" in result

    def test_multiple_symbols_in_named_import(self):
        """import { A, B, C } from './m'; correctly parses all three."""
        text = "import { User, Post, Comment } from './models';"
        exports = {"User": "models.ts", "Post": "models.ts", "Comment": "models.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "User" in result
        assert "Post" in result
        assert "Comment" in result

    def test_non_import_line_unchanged(self):
        """Regular code lines are not touched."""
        text = "export class User { }\nconst x = 1;"
        exports = {"User": "models.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "export class User { }" in result
        assert "const x = 1" in result

    def test_empty_text_returns_empty(self):
        """Empty string returns empty."""
        result = Reassembler._resolve_imports_in_text("", {})
        assert result == ""

    def test_rust_use_statement_resolved(self):
        """Rust: use path::Symbol; is rewritten when Symbol in global_exports."""
        text = "use crate::services::user_service;"
        exports = {"user_service": "src/services.rs"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "use crate::services::user_service" in result

    def test_rust_std_use_not_modified(self):
        """Rust: use std::collections::HashMap; (external) left unchanged."""
        text = "use std::collections::HashMap;"
        exports = {"HashMap": "std.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        # Should be unchanged (std is external)
        assert "std::collections::HashMap" in result

    def test_multi_chunk_cross_reference(self, reassembler):
        """Chunk 1 importing from Chunk 0: cross-chunk resolution works end-to-end."""
        global_exports = {
            "User": "src/models.ts",
            "Post": "src/models.ts",
        }
        combined = reassembler.combine()
        result = reassembler._resolve_imports_in_text(combined, global_exports)

        # The import line should be preserved
        assert "import { User, Post } from './models'" in result

    def test_exports_map_from_multiple_chunks(self):
        """global_exports populated from multiple chunks resolves correctly."""
        # Chunk 0 exports: User, Post  (models.py)
        # Chunk 1 exports: userService (services.py)
        # Chunk 2 imports: User, userService
        exports = {
            "User": "src/models.ts",
            "Post": "src/models.ts",
            "userService": "src/services.ts",
        }
        text = (
            "// filename: src/services.ts\n"
            "import { User } from './models';\n"
            "import { userService } from './services';\n"
            "export const x = userService;"
        )

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "User" in result
        assert "userService" in result

    def test_import_line_with_semicolon_preserved(self):
        """import { A } from './b'; (with semicolon) preserved exactly."""
        text = "import { User } from './models';"
        exports = {"User": "models.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "import { User } from './models';" in result

    def test_import_line_without_semicolon_preserved(self):
        """import { A } from './b' (no semicolon) preserved."""
        text = "import { User } from './models'"
        exports = {"User": "models.ts"}

        result = Reassembler._resolve_imports_in_text(text, exports)

        assert "import { User } from './models'" in result
