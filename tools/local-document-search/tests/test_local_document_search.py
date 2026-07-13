"""Tests for local_document_search.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-import,unused-variable
# pylint: disable=redefined-outer-name
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from local_document_search import (  # noqa: E402
    Document,
    DocumentIndex,
    build_snippets,
    discover_files,
    extract_text_from_file,
    index_directory,
    should_index_file,
    tokenize,
)


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------
class TestTokenize:
    def test_basic(self) -> None:
        assert tokenize("Hello World") == ["hello", "world"]

    def test_numbers(self) -> None:
        # Single digits filtered out (min 2 chars), multi-digit numbers kept
        assert tokenize("Version 12 345") == ["version", "12", "345"]
        # Dots split numbers, single digits filtered out
        assert tokenize("v1.2.3") == ["v1"]

    def test_punctuation(self) -> None:
        assert tokenize("hello, world!") == ["hello", "world"]

    def test_short_tokens_filtered(self) -> None:
        assert tokenize("a bc def") == ["bc", "def"]

    def test_case_insensitive(self) -> None:
        assert tokenize("HELLO hello") == ["hello", "hello"]


# ---------------------------------------------------------------------------
# build_snippets
# ---------------------------------------------------------------------------
class TestBuildSnippets:
    def test_empty(self) -> None:
        assert build_snippets("", ["test"]) == []
        assert build_snippets("text", []) == []

    def test_basic(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        snippets = build_snippets(text, ["fox"])
        assert len(snippets) == 1
        assert "fox" in snippets[0]

    def test_multiple_terms(self) -> None:
        text = "Error: connection timeout. Retry failed. Error: timeout again."
        snippets = build_snippets(text, ["error", "timeout"])
        assert len(snippets) <= 3
        assert any("error" in s.lower() for s in snippets)
        assert any("timeout" in s.lower() for s in snippets)


# ---------------------------------------------------------------------------
# extract_text_from_file
# ---------------------------------------------------------------------------
class TestExtractText:
    def test_txt_file(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("Hello World", encoding="utf-8")
        content, content_hash = extract_text_from_file(f)
        assert content == "Hello World"
        assert len(content_hash) == 16

    def test_markdown_file(self, tmp_path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nContent", encoding="utf-8")
        content, _ = extract_text_from_file(f)
        assert "# Title" in content

    def test_python_file(self, tmp_path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    return 42", encoding="utf-8")
        content, _ = extract_text_from_file(f)
        assert "def foo" in content

    def test_json_file(self, tmp_path) -> None:
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        content, _ = extract_text_from_file(f)
        assert "key" in content

    def test_special_names(self, tmp_path) -> None:
        for name in ["Dockerfile", "Makefile", "README", "LICENSE", "CHANGELOG"]:
            f = tmp_path / name
            f.write_text("content", encoding="utf-8")
            content, _ = extract_text_from_file(f)
            assert content == "content"

    def test_unsupported_extension(self, tmp_path) -> None:
        f = tmp_path / "test.xyz"
        f.write_text("content", encoding="utf-8")
        content, content_hash = extract_text_from_file(f)
        assert content == ""
        assert content_hash == ""


# ---------------------------------------------------------------------------
# should_index_file
# ---------------------------------------------------------------------------
class TestShouldIndexFile:
    def test_size_limit(self, tmp_path) -> None:
        f = tmp_path / "small.txt"
        f.write_text("x" * 1000, encoding="utf-8")
        assert should_index_file(f, [], [], 1)  # 1MB limit

    def test_exceeds_size(self, tmp_path) -> None:
        f = tmp_path / "large.txt"
        f.write_text("x" * (10 * 1024 * 1024), encoding="utf-8")  # 10MB
        assert not should_index_file(f, [], [], 1)  # 1MB limit

    def test_include_patterns(self, tmp_path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x", encoding="utf-8")
        assert should_index_file(f, ["*.py"], [], 10)
        assert not should_index_file(f, ["*.md"], [], 10)

    def test_exclude_patterns(self, tmp_path) -> None:
        f = tmp_path / "test.min.js"
        f.write_text("x", encoding="utf-8")
        assert not should_index_file(f, [], ["*.min.js"], 10)
        assert should_index_file(f, [], ["*.map"], 10)


# ---------------------------------------------------------------------------
# discover_files
# ---------------------------------------------------------------------------
class TestDiscoverFiles:
    def test_basic(self, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.md").write_text("b", encoding="utf-8")
        (tmp_path / "c.py").write_text("c", encoding="utf-8")

        files = list(discover_files(tmp_path, [], [], 10))
        assert len(files) == 3

    def test_excludes_dot_dirs(self, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("x", encoding="utf-8")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.pyc").write_text("x", encoding="utf-8")

        files = list(discover_files(tmp_path, [], [], 10))
        # Should only find a.txt
        assert len(files) == 1
        assert files[0].name == "a.txt"

    def test_include_filter(self, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.md").write_text("b", encoding="utf-8")

        files = list(discover_files(tmp_path, ["*.txt"], [], 10))
        assert len(files) == 1
        assert files[0].name == "a.txt"

    def test_exclude_filter(self, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.min.js").write_text("b", encoding="utf-8")

        files = list(discover_files(tmp_path, [], ["*.min.js"], 10))
        assert len(files) == 1
        assert files[0].name == "a.txt"


# ---------------------------------------------------------------------------
# DocumentIndex
# ---------------------------------------------------------------------------
class TestDocumentIndex:
    def test_add_and_search(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        index = DocumentIndex(db_path)

        doc = Document(
            path="/test/doc1.txt",
            relative_path="doc1.txt",
            extension=".txt",
            size=100,
            modified_time=1234567890.0,
            content_hash="abc123",
        )
        tokens = ["hello", "world", "hello"]
        doc_id = index.add_document(doc, tokens)

        assert doc_id > 0

        results = index.search("hello")
        assert len(results) == 1
        assert results[0].document.path == "/test/doc1.txt"
        assert "hello" in results[0].matched_terms
        assert results[0].score == 2  # frequency

    def test_update_same_content(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        index = DocumentIndex(db_path)

        doc = Document(
            path="/test/doc1.txt",
            relative_path="doc1.txt",
            extension=".txt",
            size=100,
            modified_time=1234567890.0,
            content_hash="abc123",
        )
        tokens = ["hello", "world"]
        id1 = index.add_document(doc, tokens)
        id2 = index.add_document(doc, tokens)  # Same content hash
        assert id1 == id2

    def test_update_changed_content(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        index = DocumentIndex(db_path)

        doc = Document(
            path="/test/doc1.txt",
            relative_path="doc1.txt",
            extension=".txt",
            size=100,
            modified_time=1234567890.0,
            content_hash="abc123",
        )
        index.add_document(doc, ["hello"])
        # Same path, different hash - should update
        doc.content_hash = "def456"
        index.add_document(doc, ["world"])

        results = index.search("world")
        assert len(results) == 1
        assert "world" in results[0].matched_terms
        assert "hello" not in results[0].matched_terms

    def test_remove_document(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        index = DocumentIndex(db_path)

        doc = Document(
            path="/test/doc1.txt",
            relative_path="doc1.txt",
            extension=".txt",
            size=100,
            modified_time=1234567890.0,
            content_hash="abc123",
        )
        index.add_document(doc, ["hello"])

        assert index.remove_document("/test/doc1.txt") is True
        assert index.search("hello") == []
        assert index.remove_document("/test/doc1.txt") is False  # Already removed

    def test_empty_query(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        index = DocumentIndex(db_path)

        doc = Document(
            path="/test/doc1.txt",
            relative_path="doc1.txt",
            extension=".txt",
            size=100,
            modified_time=1234567890.0,
            content_hash="abc123",
        )
        index.add_document(doc, ["hello"])

        assert index.search("") == []
        assert index.search("   ") == []

    def test_stats(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        index = DocumentIndex(db_path)

        stats = index.get_stats()
        assert stats["documents"] == 0
        assert stats["unique_terms"] == 0
        assert stats["postings"] == 0


# ---------------------------------------------------------------------------
# index_directory
# ---------------------------------------------------------------------------
# index_directory
# ---------------------------------------------------------------------------
class TestIndexDirectory:
    def test_basic(self, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
        (tmp_path / "b.md").write_text("foo bar", encoding="utf-8")

        db_path = tmp_path / "index.db"
        index = DocumentIndex(db_path)

        indexed, skipped = index_directory(tmp_path, index, [], [], 10)

        assert indexed == 2
        stats = index.get_stats()
        assert stats["documents"] == 2

    def test_incremental(self, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")

        db_path = tmp_path / "index.db"
        index = DocumentIndex(db_path)

        # First index
        indexed1, skipped1 = index_directory(tmp_path, index, [], [], 10)
        assert indexed1 == 1

        # Second index without changes
        indexed2, skipped2 = index_directory(tmp_path, index, [], [], 10)
        assert indexed2 == 0
        assert skipped2 >= 1

    def test_force_reindex(self, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")

        db_path = tmp_path / "index.db"
        index = DocumentIndex(db_path)

        indexed1, _ = index_directory(tmp_path, index, [], [], 10)
        assert indexed1 == 1

        indexed2, skipped2 = index_directory(
            tmp_path, index, [], [], 10, force_reindex=True
        )
        assert indexed2 == 1
        # With force_reindex, file is reindexed
        assert skipped2 >= 0

    def test_empty_files_skipped(self, tmp_path) -> None:
        (tmp_path / "empty.txt").write_text("", encoding="utf-8")
        (tmp_path / "whitespace.txt").write_text("   \n\t  ", encoding="utf-8")
        (tmp_path / "content.txt").write_text("hello", encoding="utf-8")

        db_path = tmp_path / "index.db"
        index = DocumentIndex(db_path)

        indexed, skipped = index_directory(tmp_path, index, [], [], 10)
        assert indexed == 1
        # Both empty and whitespace-only files are skipped
        assert skipped >= 2

    def test_large_file_skipped(self, tmp_path) -> None:
        (tmp_path / "small.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "large.txt").write_text("x" * (10 * 1024 * 1024), encoding="utf-8")

        db_path = tmp_path / "index.db"
        index = DocumentIndex(db_path)

        indexed, skipped = index_directory(tmp_path, index, [], [], 1)  # 1MB limit
        assert indexed == 1
        assert skipped == 1


# ---------------------------------------------------------------------------
# CLI Integration Tests
# ---------------------------------------------------------------------------
class TestCLI:
    def test_help(self, monkeypatch) -> None:
        import local_document_search as lds

        monkeypatch.setattr(sys, "argv", ["prog", "--help"])
        try:
            lds.main()
        except SystemExit as e:
            assert e.code == 0

    def test_index_command(self, tmp_path, monkeypatch) -> None:
        import local_document_search as lds

        (tmp_path / "test.txt").write_text("hello world", encoding="utf-8")
        index_path = tmp_path / "index.db"

        monkeypatch.setattr(
            sys, "argv", ["prog", "index", str(tmp_path), "--index", str(index_path)]
        )
        exit_code = lds.main()
        assert exit_code == 0
        assert index_path.exists()

    def test_search_command(self, tmp_path, monkeypatch, capsys) -> None:
        import local_document_search as lds

        (tmp_path / "test.txt").write_text("hello world", encoding="utf-8")
        index_path = tmp_path / "index.db"

        # Index first
        monkeypatch.setattr(
            sys, "argv", ["prog", "index", str(tmp_path), "--index", str(index_path)]
        )
        lds.main()

        # Search
        monkeypatch.setattr(
            sys, "argv", ["prog", "search", "hello", "--index", str(index_path)]
        )
        exit_code = lds.main()
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "hello" in captured.out.lower()

    def test_search_json_format(self, tmp_path, monkeypatch, capsys) -> None:
        import local_document_search as lds

        (tmp_path / "test.txt").write_text("hello world", encoding="utf-8")
        index_path = tmp_path / "index.db"

        monkeypatch.setattr(
            sys, "argv", ["prog", "index", str(tmp_path), "--index", str(index_path)]
        )
        lds.main()

        monkeypatch.setattr(
            sys,
            "argv",
            ["prog", "search", "hello", "--index", str(index_path), "--format", "json"],
        )
        lds.main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert "path" in data[0]
        assert "matched_terms" in data[0]

    def test_stats_command(self, tmp_path, monkeypatch, capsys) -> None:
        import local_document_search as lds

        (tmp_path / "test.txt").write_text("hello world", encoding="utf-8")
        index_path = tmp_path / "index.db"

        monkeypatch.setattr(
            sys, "argv", ["prog", "index", str(tmp_path), "--index", str(index_path)]
        )
        lds.main()

        monkeypatch.setattr(sys, "argv", ["prog", "stats", "--index", str(index_path)])
        exit_code = lds.main()
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Documents:" in captured.out

    def test_stats_json_format(self, tmp_path, monkeypatch, capsys) -> None:
        import local_document_search as lds

        (tmp_path / "test.txt").write_text("hello world", encoding="utf-8")
        index_path = tmp_path / "index.db"

        monkeypatch.setattr(
            sys, "argv", ["prog", "index", str(tmp_path), "--index", str(index_path)]
        )
        lds.main()

        monkeypatch.setattr(
            sys,
            "argv",
            ["prog", "stats", "--index", str(index_path), "--format", "json"],
        )
        lds.main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "documents" in data
        assert data["documents"] == 1

    def test_remove_command(self, tmp_path, monkeypatch) -> None:
        import local_document_search as lds

        (tmp_path / "test.txt").write_text("hello world", encoding="utf-8")
        index_path = tmp_path / "index.db"

        monkeypatch.setattr(
            sys, "argv", ["prog", "index", str(tmp_path), "--index", str(index_path)]
        )
        lds.main()

        # Remove
        file_path = str(tmp_path / "test.txt")
        monkeypatch.setattr(
            sys, "argv", ["prog", "remove", file_path, "--index", str(index_path)]
        )
        exit_code = lds.main()
        assert exit_code == 0

        # Verify removed
        index = DocumentIndex(index_path)
        assert index.search("hello") == []


# ---------------------------------------------------------------------------
# Search Result Ranking
# ---------------------------------------------------------------------------
class TestSearchRanking:
    def test_term_frequency_ranking(self, tmp_path) -> None:
        db_path = tmp_path / "index.db"
        index = DocumentIndex(db_path)

        # Doc1: "hello" appears 3 times
        doc1 = Document(
            path="/doc1.txt",
            relative_path="doc1.txt",
            extension=".txt",
            size=100,
            modified_time=1.0,
            content_hash="a",
        )
        index.add_document(doc1, ["hello", "hello", "hello", "world"])

        # Doc2: "hello" appears 1 time
        doc2 = Document(
            path="/doc2.txt",
            relative_path="doc2.txt",
            extension=".txt",
            size=100,
            modified_time=1.0,
            content_hash="b",
        )
        index.add_document(doc2, ["hello", "other"])

        results = index.search("hello")
        assert len(results) == 2
        assert results[0].document.path == "/doc1.txt"
        assert results[1].document.path == "/doc2.txt"

    def test_multi_term_query(self, tmp_path) -> None:
        db_path = tmp_path / "index.db"
        index = DocumentIndex(db_path)

        doc1 = Document(
            path="/doc1.txt",
            relative_path="doc1.txt",
            extension=".txt",
            size=100,
            modified_time=1.0,
            content_hash="a",
        )
        index.add_document(doc1, ["machine", "learning", "python"])

        doc2 = Document(
            path="/doc2.txt",
            relative_path="doc2.txt",
            extension=".txt",
            size=100,
            modified_time=1.0,
            content_hash="b",
        )
        index.add_document(doc2, ["machine", "learning"])

        doc3 = Document(
            path="/doc3.txt",
            relative_path="doc3.txt",
            extension=".txt",
            size=100,
            modified_time=1.0,
            content_hash="c",
        )
        index.add_document(doc3, ["python", "code"])

        # Query with two terms - only doc1 and doc2 match
        results = index.search("machine learning")
        assert len(results) == 2
        # Both terms match doc1 and doc2
        assert set(results[0].matched_terms) == {"learning", "machine"}
        assert set(results[1].matched_terms) == {"learning", "machine"}
