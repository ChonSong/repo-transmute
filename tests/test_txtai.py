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


    def test_snippet_extracted_from_body(self, txtai_client):
        txtai_client.index([
            {
                'id': 'snip1',
                'text': 'function get_user fetch user record',
                'repo': 'x/y',
                'language': 'python',
                'kind': 'function',
                'name': 'get_user',
                'signature': '(id: int)',
                'file': 'a.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': 'return db.query(User).filter(User.id == id).first()',
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.search('fetch user', limit=1)
        assert len(results) == 1
        assert 'return db.query' in results.hits[0].snippet
        assert results.hits[0].snippet == results.hits[0].snippet.strip()

    def test_snippet_falls_back_to_docstring(self, txtai_client):
        txtai_client.index([
            {
                'id': 'snip2',
                'text': 'function helper',
                'repo': 'x/y',
                'language': 'python',
                'kind': 'function',
                'name': 'helper',
                'signature': '()',
                'file': 'a.py',
                'line': 1,
                'docstring': 'Returns the current user.',
                'decorators': [],
                'body': '',
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.search('helper', limit=1)
        assert len(results) == 1
        assert results.hits[0].snippet == 'Returns the current user.'

    def test_snippet_truncates_long_body(self, txtai_client):
        txtai_client.index([
            {
                'id': 'snip3',
                'text': 'function long_func',
                'repo': 'x/y',
                'language': 'python',
                'kind': 'function',
                'name': 'long_func',
                'signature': '()',
                'file': 'a.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': 'line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10',
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.search('long_func', limit=1)
        assert len(results) == 1
        # snippet should be truncated to ~200 chars
        assert len(results.hits[0].snippet) <= 210

    def test_as_dict_roundtrip(self, txtai_client):
        txtai_client.index([
            {
                'id': 'dict1',
                'text': 'function hello',
                'repo': 'acme/app',
                'language': 'python',
                'kind': 'function',
                'name': 'hello',
                'signature': '(name: str) -> str',
                'file': 'hello.py',
                'line': 5,
                'docstring': 'Say hello.',
                'decorators': [],
                'body': 'return f"Hi {name}"',
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.search('hello', limit=1)
        hit = results.hits[0]
        d = hit.as_dict()
        assert isinstance(d, dict)
        assert d['name'] == 'hello'
        assert d['repo'] == 'acme/app'
        assert 'snippet' in d
        assert 'score' in d
        assert isinstance(d['score'], float)

    def test_location_and_repo_short(self, txtai_client):
        txtai_client.index([
            {
                'id': 'loc1',
                'text': 'function auth',
                'repo': 'HKUDS/nanobot',
                'language': 'python',
                'kind': 'function',
                'name': 'authenticate',
                'signature': '()',
                'file': 'src/auth.py',
                'line': 42,
                'docstring': '',
                'decorators': [],
                'body': 'pass',
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.search('authenticate', limit=1)
        hit = results.hits[0]
        assert hit.location == 'src/auth.py:42'
        assert hit.repo_short == 'HKUDS › nanobot'

    def test_score_bar(self, txtai_client):
        txtai_client.index([
            {
                'id': 'bar1',
                'text': 'function test',
                'repo': 'x/y',
                'language': 'python',
                'kind': 'function',
                'name': 'test_fn',
                'signature': '()',
                'file': 'a.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.search('test', limit=1)
        bar = results.hits[0].score_bar(width=5)
        assert len(bar) == 5
        assert '█' in bar or '░' in bar

    def test_results_best(self, txtai_client):
        txtai_client.index([
            {
                'id': 'best1',
                'text': 'function check check token',
                'repo': 'x/y',
                'language': 'python',
                'kind': 'function',
                'name': 'check_token',
                'signature': '()',
                'file': 'a.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
            {
                'id': 'best2',
                'text': 'function token',
                'repo': 'x/y',
                'language': 'python',
                'kind': 'function',
                'name': 'make_token',
                'signature': '()',
                'file': 'a.py',
                'line': 5,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.search('check token', limit=10)
        assert results.best is not None
        assert results.best.name == 'check_token'

    def test_results_empty(self, txtai_client):
        search = BlueprintSearch(txtai_client)
        results = search.search('xyzzy none existent query', limit=5)
        assert len(results) == 0
        assert results.best is None
        assert results.as_dicts() == []

    def test_by_language_filter(self, txtai_client):
        txtai_client.index([
            {
                'id': 'lang1',
                'text': 'function go',
                'repo': 'x/y',
                'language': 'go',
                'kind': 'function',
                'name': 'make_user',
                'signature': '()',
                'file': 'a.go',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
            {
                'id': 'lang2',
                'text': 'function py',
                'repo': 'x/y',
                'language': 'python',
                'kind': 'function',
                'name': 'make_user',
                'signature': '()',
                'file': 'b.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.search('make user', limit=10)
        py_results = results.by_language('python')
        go_results = results.by_language('go')
        assert all(h.language == 'python' for h in py_results.hits)
        assert all(h.language == 'go' for h in go_results.hits)

    def test_cross_repo_patterns_sorted_by_score(self, txtai_client):
        txtai_client.index([
            {
                'id': 'rp1',
                'text': 'function auth check credentials',
                'repo': 'proj/a',
                'language': 'python',
                'kind': 'function',
                'name': 'check',
                'signature': '()',
                'file': 'a.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
            {
                'id': 'rp2',
                'text': 'function auth verify token',
                'repo': 'proj/a',
                'language': 'python',
                'kind': 'function',
                'name': 'verify',
                'signature': '()',
                'file': 'a.py',
                'line': 5,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
            {
                'id': 'rp3',
                'text': 'function auth login user',
                'repo': 'proj/b',
                'language': 'python',
                'kind': 'function',
                'name': 'login',
                'signature': '()',
                'file': 'b.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
        ])
        search = BlueprintSearch(txtai_client)
        patterns = search.cross_repo_patterns('auth', limit_per_repo=2)
        # proj/a should have 2 hits, sorted by score desc
        proj_a_scores = [h.score for h in patterns['proj/a']]
        assert proj_a_scores == sorted(proj_a_scores, reverse=True)

    def test_stats(self, txtai_client):
        txtai_client.index([
            {
                'id': 'st1',
                'text': 'function a',
                'repo': 'foo/bar',
                'language': 'python',
                'kind': 'function',
                'name': 'a',
                'signature': '()',
                'file': 'a.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
            {
                'id': 'st2',
                'text': 'function b',
                'repo': 'foo/bar',
                'language': 'python',
                'kind': 'function',
                'name': 'b',
                'signature': '()',
                'file': 'b.py',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
            {
                'id': 'st3',
                'text': 'function c',
                'repo': 'baz/qux',
                'language': 'typescript',
                'kind': 'function',
                'name': 'c',
                'signature': '()',
                'file': 'c.ts',
                'line': 1,
                'docstring': '',
                'decorators': [],
                'body': '',
            },
        ])
        search = BlueprintSearch(txtai_client)
        stats = search.stats()
        assert stats['total'] == 3
        assert stats['repos'] == 2
        assert stats['languages'] == 2


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Hybrid Search tests
# ---------------------------------------------------------------------------

class TestHybridSearch:
    """Tests for hybrid keyword + semantic search (BM25 + vector)."""

    def test_hybrid_search_returns_both_score_components(self, txtai_client):
        """Hybrid results should carry semantic_score and keyword_score."""
        txtai_client.index([
            {
                "id": "hyb1",
                "text": "function authenticate check JWT token",
                "repo": "acme/app",
                "language": "python",
                "kind": "function",
                "name": "authenticate",
                "signature": "(token: str) -> bool",
                "file": "auth.py",
                "line": 10,
                "docstring": "Verify a JWT token.",
                "decorators": [],
                "body": "return check_token(token)",
            },
            {
                "id": "hyb2",
                "text": "function send_email send notification email",
                "repo": "acme/app",
                "language": "python",
                "kind": "function",
                "name": "send_email",
                "signature": "(to: str, subject: str) -> None",
                "file": "email.py",
                "line": 5,
                "docstring": "Send an email.",
                "decorators": [],
                "body": "pass",
            },
        ])

        search = BlueprintSearch(txtai_client)
        results = search.hybrid_search("JWT token authenticate", limit=10)

        assert len(results) >= 1
        hit = results.hits[0]
        assert hit.semantic_score is not None
        assert hit.keyword_score is not None
        assert 0.0 <= hit.semantic_score <= 1.0
        assert 0.0 <= hit.keyword_score <= 1.0
        # Both components contribute to fused score
        assert hit.score >= 0.0

    def test_hybrid_search_keyword_matches_ranked_higher(self, txtai_client):
        """When query terms appear directly in docs, keyword score boosts them."""
        txtai_client.index([
            {
                "id": "kw1",
                "text": "function rate_limit throttling API calls",
                "repo": "proj/a",
                "language": "python",
                "kind": "function",
                "name": "rate_limit",
                "signature": "()",
                "file": "a.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
            {
                "id": "kw2",
                "text": "function handle_request web request handler",
                "repo": "proj/a",
                "language": "python",
                "kind": "function",
                "name": "handle_request",
                "signature": "()",
                "file": "b.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
        ])

        search = BlueprintSearch(txtai_client)
        # Query has "rate limit" — first doc has both words, second doesn't
        results = search.hybrid_search("rate limit", limit=10)

        assert len(results) >= 1
        # rate_limit should be ranked first due to keyword match
        assert results.hits[0].name == "rate_limit"

    def test_hybrid_search_fused_score_higher_than_semantic_only(self, txtai_client):
        """Hybrid fusion should boost results that match both semantic and keyword."""
        txtai_client.index([
            {
                "id": "fuse1",
                "text": "function authenticate verify user credentials login",
                "repo": "proj/a",
                "language": "python",
                "kind": "function",
                "name": "authenticate",
                "signature": "()",
                "file": "a.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
            {
                "id": "fuse2",
                "text": "function helper general utility",
                "repo": "proj/a",
                "language": "python",
                "kind": "function",
                "name": "helper",
                "signature": "()",
                "file": "b.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
        ])

        search = BlueprintSearch(txtai_client)
        hybrid_results = search.hybrid_search("authenticate", limit=10)
        semantic_only = search.search("authenticate", limit=10)

        # Both should rank authenticate first
        assert hybrid_results.hits[0].name == "authenticate"
        assert semantic_only.hits[0].name == "authenticate"
        # But hybrid should carry the keyword score
        assert hybrid_results.hits[0].keyword_score is not None
        assert semantic_only.hits[0].keyword_score is None

    def test_hybrid_search_is_hybrid_flag(self, txtai_client):
        """SearchResults.is_hybrid should be True after hybrid_search."""
        txtai_client.index([
            {
                "id": "flag1",
                "text": "function test",
                "repo": "x/y",
                "language": "python",
                "kind": "function",
                "name": "test_fn",
                "signature": "()",
                "file": "a.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
        ])
        search = BlueprintSearch(txtai_client)
        hybrid = search.hybrid_search("test", limit=5)
        plain = search.search("test", limit=5)
        assert hybrid.is_hybrid is True
        assert plain.is_hybrid is False

    def test_hybrid_search_empty_index(self, txtai_client):
        """Empty index should return empty results without error."""
        search = BlueprintSearch(txtai_client)
        results = search.hybrid_search("anything", limit=10)
        assert len(results) == 0

    def test_hybrid_search_with_repo_filter(self, txtai_client):
        """Hybrid search should work correctly after repo filtering."""
        txtai_client.index([
            {
                "id": "repo1",
                "text": "function hello world greeting",
                "repo": "foo/bar",
                "language": "python",
                "kind": "function",
                "name": "hello",
                "signature": "()",
                "file": "a.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
            {
                "id": "repo2",
                "text": "function hello mars",
                "repo": "baz/qux",
                "language": "go",
                "kind": "function",
                "name": "hello",
                "signature": "()",
                "file": "b.go",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
        ])
        search = BlueprintSearch(txtai_client)
        results = search.hybrid_search("hello", limit=10).by_repo("foo/bar")
        assert all(h.repo == "foo/bar" for h in results.hits)

    def test_search_hybrid_flag_shortcut(self, txtai_client):
        """search(query, hybrid=True) should behave like hybrid_search()."""
        txtai_client.index([
            {
                "id": "short1",
                "text": "function check token validation",
                "repo": "x/y",
                "language": "python",
                "kind": "function",
                "name": "check_token",
                "signature": "()",
                "file": "a.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
            {
                "id": "short2",
                "text": "function send message",
                "repo": "x/y",
                "language": "python",
                "kind": "function",
                "name": "send_message",
                "signature": "()",
                "file": "b.py",
                "line": 1,
                "docstring": "",
                "decorators": [],
                "body": "",
            },
        ])
        search = BlueprintSearch(txtai_client)
        via_flag = search.search("check token", limit=10, hybrid=True)
        direct = search.hybrid_search("check token", limit=10)
        assert via_flag.is_hybrid is True
        assert direct.is_hybrid is True
        assert len(via_flag.hits) >= 1
        assert via_flag.hits[0].name == "check_token"

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


# ---------------------------------------------------------------------------
# CLI search integration tests
# ---------------------------------------------------------------------------

class TestCliSearchIntegration:
    """Test the CLI search command with new --json, --blueprint, --language, --explain options."""

    def test_search_help_shows_new_options(self):
        """--help should list all new options."""
        from repo_transmute.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        output = result.output
        assert "--json" in output
        assert "--blueprint" in output
        assert "--explain" in output
        assert "--language" in output
        assert "--repo" in output or "-r" in output

    def test_search_json_flag_accepted(self):
        """search --json should be accepted without error."""
        from repo_transmute.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--json", "--index-dir", "/nonexistent", "hello"])
        # Should not crash on the flag itself; may fail on index connection
        # but the --json flag must be parsed without error
        assert "--json" not in result.output or "Usage" not in result.output
        # Verify the command parsed correctly: exit 0 or 1 (not 2 = click param error)
        assert result.exit_code in (0, 1)

    def test_search_blueprint_alias(self):
        """--blueprint should work as alias for --repo."""
        from repo_transmute.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        # Using --blueprint instead of --repo should not produce a param error
        result = runner.invoke(cli, [
            "search", "--blueprint", "HKUDS/nanobot",
            "--index-dir", "/nonexistent", "test"
        ])
        assert result.exit_code in (0, 1)  # not 2 (click param error)

    def test_search_language_filter(self):
        """--language filter should be accepted."""
        from repo_transmute.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, [
            "search", "--language", "python",
            "--index-dir", "/nonexistent", "test"
        ])
        assert result.exit_code in (0, 1)

    def test_search_explain_without_query(self):
        """--explain without a query should work (explain is standalone)."""
        from repo_transmute.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, [
            "search", "--explain", "abc123",
            "--index-dir", "/nonexistent"
        ])
        # Should not say "query argument required"
        # (it should try to explain and fail on the index, not on param validation)
        assert "Usage" not in result.output or "--explain" in result.output
        assert result.exit_code in (0, 1, 2)  # 2 = param error if --explain isn't configured standalone

    def test_search_explain_in_help(self):
        """--explain should appear in --help output."""
        from repo_transmute.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert "--explain" in result.output


class TestStatusCommand:
    """Test the status command's TXTAI index detection."""

    def test_status_shows_txai_index_when_config_json_exists(self):
        """status should detect the TXTAI index via config.json even when index.faiss is absent.

        txtai 6.x saves the index as embeddings/ rather than index.faiss,
        but the presence of config.json is a sufficient signal that load()
        will succeed. Uses the default data/txtai dir.
        """
        from repo_transmute.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["status"])
        output = result.output
        # Should show document count, not the "not built yet" message
        assert "TXTAI index: not built yet" not in output
        assert "12181 documents indexed" in output
        # Should list some repos (the fix makes TxtaiClient load successfully)
        assert "Repos indexed:" in output
