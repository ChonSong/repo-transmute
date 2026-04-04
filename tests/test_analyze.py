"""Tests for analyze_dependencies()."""

import pytest
from pathlib import Path

from repo_transmute.pipeline.coordinator import analyze_dependencies


class TestAnalyzeDependencies:
    def test_returns_required_keys(self, tmp_path):
        """All required keys must be present."""
        # Create a minimal Python file
        (tmp_path / "main.py").write_text("def f(): pass\n")
        deps = analyze_dependencies(tmp_path)

        assert "file_count" in deps
        assert "imports" in deps
        assert "external" in deps
        assert "internal" in deps
        assert "third_party" in deps

    def test_file_count_includes_source_files(self, tmp_path):
        """file_count reflects the number of source files."""
        (tmp_path / "a.py").write_text("def f(): pass\n")
        (tmp_path / "b.py").write_text("def g(): pass\n")
        deps = analyze_dependencies(tmp_path)
        assert deps["file_count"] == 2

    def test_third_party_key_is_list_not_set(self, tmp_path):
        """third_party must be a list (JSON-serializable), not a set."""
        (tmp_path / "main.py").write_text(
            "import requests\n"
            "from . import local\n"
        )
        deps = analyze_dependencies(tmp_path)
        # Must be list, not set — sets aren't JSON-serializable
        assert isinstance(deps.get("third_party"), list), \
            f"third_party should be list, got {type(deps.get('third_party'))}"
        assert "requests" in deps["third_party"]

    def test_external_is_list(self, tmp_path):
        """external must be a list, not a set."""
        (tmp_path / "main.py").write_text("import pip:foo\n")
        deps = analyze_dependencies(tmp_path)
        assert isinstance(deps.get("external"), list)

    def test_internal_is_list(self, tmp_path):
        """internal must be a list, not a set."""
        (tmp_path / "main.py").write_text("from . import foo\n")
        deps = analyze_dependencies(tmp_path)
        assert isinstance(deps.get("internal"), list)

    def test_no_third_party_when_only_stdlib(self, tmp_path):
        """stdlib modules don't appear in third_party."""
        (tmp_path / "main.py").write_text(
            "import os\n"
            "import sys\n"
            "from typing import List\n"
        )
        deps = analyze_dependencies(tmp_path)
        assert deps["third_party"] == []

    def test_relative_imports_are_internal(self, tmp_path):
        """Relative imports (. prefix) are classified as internal."""
        (tmp_path / "main.py").write_text(
            "from . import foo\n"
            "from .sub import bar\n"
        )
        deps = analyze_dependencies(tmp_path)
        assert any("." in imp for imp in deps["internal"])

    def test_npm_prefix_external(self, tmp_path):
        """npm: prefix counted as external."""
        (tmp_path / "main.js").write_text("const x = require('npm:react')\n")
        deps = analyze_dependencies(tmp_path)
        assert "npm:react" in deps["external"]

    def test_result_is_json_serializable(self, tmp_path):
        """analyze_dependencies output must be JSON-serializable."""
        (tmp_path / "main.py").write_text("import requests\n")
        import json
        deps = analyze_dependencies(tmp_path)
        # Should not raise
        json.dumps(deps)
