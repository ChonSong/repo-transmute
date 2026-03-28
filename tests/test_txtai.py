"""Tests for the TXTAI integration module.

Run with:
    pytest tests/test_txtai.py -v

These tests do NOT require a real LLM or GPU — they use:
- txtai's in-process Embeddings (CPU, no GPU needed)
- The default all-MiniLM-L6-v2 sentence-transformer model
- Mock data for BlueprintIndexer
"""

import json
import tempfile
from pathlib import Path

import pytest

from repo_transmute.blueprint import Blueprint
from repo_transmute.blueprint.extractor import Function, DataStructure
from repo_transmute.txtai import TxtaiClient, BlueprintIndexer, BlueprintSearch
from repo_transmute.txtai.client import TxtaiClient as _C
from repo_transmute.txtai.indexer import BlueprintIndexer as _I, _build_text
from repo_transmute.txtai.search import BlueprintSearch as _S, SearchHit, SearchResults


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_index_dir(tmp_path):
    return tmp_path / "txtai_index"


@pytest.fixture
def mock_blueprint():
    return Blueprint(
        repo="test/repo",
        language="python",
        functions=[
            Function(
                name="get_user",
                signature="(id: int) -> User",
                file="src/services/user.py",
                line=10,
                docstring="Fetch a user by id from the database.",
                body="return db.query(User).get(id)",
            ),
            Function(
                name="create_user",
                signature="(name: str, email: str) -> User",
                file="src/services/user.py",
                line=30,
                docstring="Create a new user.",
                body="return User(name=name, email=email)",
            ),
            Function(
                name="_internal",
                signature="() -> None",
                file="src/services/user.py",
                line=50,
                docstring=None,
            ),
        ],
        data_structures=[
            DataStructure(
                name="User",
                type="class",
                file="src/services/user.py",
                line=1,
                docstring="User model",
                fields=["id", "name", "email"],
                methods=[
                    Function(
                        name="__init__",
                        signature="(name, email)",
                        file="src/services/user.py",
                        line=5,
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def txtai_client(tmp_index_dir):
    """Create a TxtaiClient backed by a temporary index directory."""
    client = TxtaiClient(index_dir=tmp_index_dir)
    yield client
    client.close()


# ---------------------------------------------------------------------------
# TxtaiClient tests
# ---------------------------------------------------------------------------

class TestTxtaiClient:
    def test_index_and_search_roundtrip(self, txtai_client):
        """Indexing a document and searching for it returns the document."""
        docs = [
            {
                "id": "func1",
                "text": "function authenticate check user credentials",
                "repo": "test/repo",
                "language": "python",
                "kind": "function",
            },
            {
                "id": "func2",
                "text": "function process_image resize and compress image",
                "repo": "test/repo",
                "language": "python",
                "kind": "function",
            },
        ]
        txtai_client.index(docs)
        txtai_client.save()

        results = txtai_client.search("authenticate user", limit=5)
        assert len(results) >= 1
        assert any(r["id"] == "func1" for r in results)

    def test_count_returns_indexed(self, txtai_client):
        txtai_client.index([
            {"id": "a", "text": "alpha"},
            {"id": "b", "text": "beta"},
            {"id": "c", "text": "gamma"},
        ])
        assert txtai_client.count() == 3

    def test_delete_removes_document(self, txtai_client):
        txtai_client.index([{"id": "x", "text": "to be deleted"}])
        assert txtai_client.count() == 1
        txtai_client.delete(["x"])
        assert txtai_client.count() == 0

    def test_save_and_reload(self, txtai_client, tmp_index_dir):
        txtai_client.index([{"id": "y", "text": "persistent data"}])
        txtai_client.save()
        txtai_client.close()

        # Reload
        client2 = TxtaiClient(index_dir=tmp_index_dir)
        try:
            client2.load()
            assert client2.count() == 1
            results = client2.search("persistent")
            assert any(r["id"] == "y" for r in results)
        finally:
            client2.close()

    def test_similarity_returns_scores(self, txtai_client):
        texts = [
            "async def fetch_users(db): return db.all()",
            "def parse_json(body): return json.loads(body)",
        ]
        # txtai returns List[Tuple[int, float]] = (text_index, similarity_score)
        scores = txtai_client.similarity(texts, "database query")
        assert isinstance(scores, list)
        assert len(scores) >= 2
        assert all(isinstance(t, tuple) and len(t) == 2 for t in scores)
        assert all(isinstance(idx, int) and isinstance(s, float) for idx, s in scores)


# ---------------------------------------------------------------------------
# BlueprintIndexer tests
# ---------------------------------------------------------------------------

class TestBlueprintIndexer:
    def test_index_blueprint_creates_documents(self, txtai_client, mock_blueprint):
        indexer = BlueprintIndexer(txtai_client)
        stats = indexer.index_blueprint(mock_blueprint, chunk_id=0)

        assert stats.functions_indexed == 3
        assert stats.classes_indexed == 1
        assert stats.documents_created == 4
        assert txtai_client.count() == 4

    def test_index_blueprint_from_yaml(self, tmp_path, txtai_client):
        """Indexing a real YAML blueprint file creates correct documents."""
        import yaml

        bp_data = {
            "version": "1.0",
            "source": {"repo": "foo/bar", "language": "python"},
            "blueprint": {
                "functions": [
                    {
                        "name": "hello",
                        "signature": "(name: str) -> str",
                        "file": "hello.py",
                        "line": 1,
                        "async": False,
                        "docstring": "Return a greeting.",
                        "decorators": [],
                        "body": 'return f"Hi {name}"',
                    }
                ],
                "data_structures": [],
            },
        }

        yaml_path = tmp_path / "foo__bar.yaml"
        with yaml_path.open("w") as f:
            yaml.dump(bp_data, f)

        indexer = BlueprintIndexer(txtai_client)
        stats = indexer.index_blueprint_from_yaml(yaml_path, chunk_id=0)

        assert stats.functions_indexed == 1
        assert stats.classes_indexed == 0
        assert txtai_client.count() == 1

        # Search for it
        results = txtai_client.search("greeting")
        assert len(results) == 1
        assert results[0]["name"] == "hello"

    def test_stats_accumulate_across_multiple_blueprints(
        self, txtai_client, mock_blueprint
    ):
        indexer = BlueprintIndexer(txtai_client)
        indexer.index_blueprint(mock_blueprint, chunk_id=0)
        indexer.index_blueprint(mock_blueprint, chunk_id=1)

        stats = indexer.stats()
        assert stats.functions_indexed == 6  # 3 funcs × 2 chunks
        assert stats.classes_indexed == 2     # 1 class × 2 chunks
        assert stats.documents_created == 8

    def test_build_text_includes_docstring_and_signature(self, mock_blueprint):
        func = mock_blueprint.functions[0]  # get_user
        text = _build_text(func)
        assert "get_user" in text
        assert "signature:" in text
        assert "Fetch a user" in text


# ---------------------------------------------------------------------------
# BlueprintSearch tests
# ---------------------------------------------------------------------------

class TestBlueprintSearch:
    def test_search_returns_search_hit_objects(self, txtai_client):
        txtai_client.index([
            {
                "id": "auth1",
                "text": "function verify_token check JWT token validity",
                "repo": "acme/app",
                "language": "python",
                "kind": "function",
                "name": "verify_token",
                "signature": "(token: str) -> bool",
                "file": "auth.py",
                "line": 20,
                "docstring": "Verify a JWT token.",
                "decorators": ["@app.route"],
            },
        ])

        search = BlueprintSearch(txtai_client)
        results = search.search("JWT token verification")

        assert len(results) == 1
        hit = results.hits[0]
        assert isinstance(hit, SearchHit)
        assert hit.name == "verify_token"
        assert hit.repo == "acme/app"
        assert hit.kind == "function"
        assert hit.score > 0

    def test_results_filter_by_kind(self, txtai_client):
        txtai_client.index([
            {
                "id": "f1",
                "text": "helper function",
                "repo": "x/y",
                "language": "python",
                "kind": "function",
                "name": "helper",
                "signature": "()",
                "file": "a.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
            },
            {
                "id": "c1",
                "text": "service class",
                "repo": "x/y",
                "language": "python",
                "kind": "class",
                "name": "Service",
                "signature": "",
                "file": "b.py",
                "line": 5,
                "docstring": "",
                "decorators": [],
            },
        ])

        search = BlueprintSearch(txtai_client)
        results = search.search("function class", limit=5)

        funcs = results.functions_only()
        classes = results.classes_only()

        assert all(h.kind == "function" for h in funcs.hits)
        assert all(h.kind == "class" for h in classes.hits)

    def test_results_filter_by_repo(self, txtai_client):
        txtai_client.index([
            {
                "id": "r1",
                "text": "database query",
                "repo": "foo/bar",
                "language": "python",
                "kind": "function",
                "name": "query",
                "signature": "()",
                "file": "db.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
            },
            {
                "id": "r2",
                "text": "database connection",
                "repo": "baz/qux",
                "language": "python",
                "kind": "function",
                "name": "connect",
                "signature": "()",
                "file": "db.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
            },
        ])

        search = BlueprintSearch(txtai_client)
        results = search.search("database", limit=10)
        foo_results = results.by_repo("foo/bar")

        assert all(h.repo == "foo/bar" for h in foo_results.hits)

    def test_cross_repo_patterns(self, txtai_client):
        txtai_client.index([
            {
                "id": "cr1",
                "text": "rate limiter throttling API calls",
                "repo": "proj/a",
                "language": "python",
                "kind": "function",
                "name": "rate_limit",
                "signature": "()",
                "file": "a.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
            },
            {
                "id": "cr2",
                "text": "rate limit via token bucket",
                "repo": "proj/b",
                "language": "python",
                "kind": "function",
                "name": "throttle",
                "signature": "()",
                "file": "b.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
            },
        ])

        search = BlueprintSearch(txtai_client)
        patterns = search.cross_repo_patterns("rate limit", limit_per_repo=3)

        assert "proj/a" in patterns
        assert "proj/b" in patterns
        assert len(patterns["proj/a"]) <= 3

    def test_repos_and_languages(self, txtai_client):
        txtai_client.index([
            {
                "id": "rl1",
                "text": "hello world",
                "repo": "a/b",
                "language": "python",
                "kind": "function",
                "name": "hello",
                "signature": "()",
                "file": "h.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
            },
        ])

        search = BlueprintSearch(txtai_client)
        assert "a/b" in search.repos()
        assert "python" in search.languages()


# ---------------------------------------------------------------------------
# NotebookStore tests
# ---------------------------------------------------------------------------

class TestNotebookStore:
    def test_save_and_retrieve_entry(self, tmp_path):
        from repo_transmute.txtai.notebook import NotebookEntry, NotebookStore, PassRecord

        store = NotebookStore(store_dir=tmp_path)
        entry = NotebookEntry(
            uid="foo/bar:chunk0:2026-03-28T00:00:00Z",
            repo="foo/bar",
            chunk_id=0,
            language="python",
            target_lang="typescript",
            blueprint_text="functions:\n  - name: hello",
            passes=[
                PassRecord(
                    pass_number=1,
                    prompt="transpile this",
                    model="MiniMax-M2.7",
                    raw_output="function hello() {}",
                    errors_detected=[],
                    refined_output=None,
                ),
            ],
            final_code="function hello() {}",
            tags=["hello", "sample"],
        )

        store.save(entry)
        retrieved = store.get("foo/bar:chunk0:2026-03-28T00:00:00Z", repo="foo/bar")

        assert retrieved is not None
        assert retrieved.repo == "foo/bar"
        assert retrieved.final_code == "function hello() {}"
        assert retrieved.tags == ["hello", "sample"]
        assert len(retrieved.passes) == 1
        assert retrieved.passes[0].pass_number == 1

    def test_list_by_repo(self, tmp_path):
        from repo_transmute.txtai.notebook import NotebookEntry, NotebookStore, PassRecord

        store = NotebookStore(store_dir=tmp_path)

        for i in range(3):
            entry = NotebookEntry(
                uid=f"foo/bar:chunk{i}:2026-03-28T00:00:00Z",
                repo="foo/bar",
                chunk_id=i,
                language="python",
                target_lang="typescript",
                blueprint_text="",
                passes=[],
                final_code=f"// chunk {i}",
            )
            store.save(entry)

        entries = store.list_by_repo("foo/bar")
        assert len(entries) == 3

    def test_list_by_tag(self, tmp_path):
        from repo_transmute.txtai.notebook import NotebookEntry, NotebookStore, PassRecord

        store = NotebookStore(store_dir=tmp_path)
        entry = NotebookEntry(
            uid="foo/bar:chunk0:2026-03-28T00:00:00Z",
            repo="foo/bar",
            chunk_id=0,
            language="python",
            target_lang="typescript",
            blueprint_text="",
            passes=[],
            final_code="",
            tags=["auth", "api"],
        )
        store.save(entry)

        results = store.list_by_tag("auth")
        assert len(results) == 1
        assert "auth" in results[0].tags

    def test_repos(self, tmp_path):
        from repo_transmute.txtai.notebook import NotebookEntry, NotebookStore, PassRecord

        store = NotebookStore(store_dir=tmp_path)
        for repo in ("a/b", "c/d"):
            entry = NotebookEntry(
                uid=f"{repo}:chunk0:2026-03-28T00:00:00Z",
                repo=repo,
                chunk_id=0,
                language="python",
                target_lang="typescript",
                blueprint_text="",
                passes=[],
                final_code="",
            )
            store.save(entry)

        assert set(store.repos()) == {"a/b", "c/d"}

    def test_from_transpilation_helper(self, tmp_path):
        from repo_transmute.txtai.notebook import NotebookStore, PassRecord

        entry = NotebookStore.from_transpilation(
            store_dir=tmp_path,
            repo="test/repo",
            chunk_id=0,
            language="python",
            target_lang="typescript",
            blueprint_text="version: '1.0'",
            passes=[
                PassRecord(
                    pass_number=1,
                    prompt="convert",
                    model="test",
                    raw_output="x",
                    errors_detected=[],
                )
            ],
            final_code="export const x = 1;",
            tags=["test"],
        )

        assert entry.repo == "test/repo"
        assert entry.chunk_id == 0
        assert entry.final_code == "export const x = 1;"
        assert "test" in entry.tags

        # Retrieve it
        store = NotebookStore(store_dir=tmp_path)
        entries = store.list_by_repo("test/repo")
        assert len(entries) == 1
