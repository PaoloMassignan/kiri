from __future__ import annotations

from pathlib import Path

import pytest

# --- helpers ------------------------------------------------------------------


def write_file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --- basic output -------------------------------------------------------------


def test_chunker_returns_at_least_one_chunk(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "x = 1\ny = 2\nz = 3\n")

    result = chunk(f)

    assert len(result) >= 1


def test_chunker_chunk_text_covers_file_content(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "x = 1\ny = 2\nz = 3\n")

    result = chunk(f)
    combined = "\n".join(c.text for c in result)

    assert "x = 1" in combined
    assert "y = 2" in combined


# --- doc_id format ------------------------------------------------------------


def test_chunker_doc_id_uses_stem_not_full_path(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "risk_scorer.py", "def foo():\n    pass\n")

    result = chunk(f)

    for c in result:
        assert "/" not in c.doc_id
        assert "\\" not in c.doc_id
        assert c.doc_id.startswith("risk_scorer__")


def test_chunker_doc_id_index_is_sequential(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "\n".join(
        f"def func_{i}():\n    return {i}\n" for i in range(5)
    )
    f = write_file(tmp_path, "engine.py", content)

    result = chunk(f)

    for i, c in enumerate(result):
        assert c.chunk_index == i
        assert c.doc_id == f"engine__{i}"


# --- source_file --------------------------------------------------------------


def test_chunker_source_file_matches_input_path(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "def foo():\n    pass\n")

    result = chunk(f)

    assert all(c.source_file == str(f) for c in result)


# --- Python block splitting ---------------------------------------------------


def test_chunker_splits_on_def_boundaries(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "def foo():\n"
        "    return 1\n"
        "\n"
        "def bar():\n"
        "    return 2\n"
    )
    f = write_file(tmp_path, "engine.py", content)

    result = chunk(f)

    texts = [c.text for c in result]
    assert any("def foo" in t for t in texts)
    assert any("def bar" in t for t in texts)


def test_chunker_splits_on_class_boundaries(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "class Foo:\n"
        "    x = 1\n"
        "\n"
        "class Bar:\n"
        "    y = 2\n"
    )
    f = write_file(tmp_path, "engine.py", content)

    result = chunk(f)

    texts = [c.text for c in result]
    assert any("class Foo" in t for t in texts)
    assert any("class Bar" in t for t in texts)


def test_chunker_each_chunk_contains_its_block_header(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "def compute():\n"
        "    x = 1\n"
        "    return x\n"
    )
    f = write_file(tmp_path, "engine.py", content)

    result = chunk(f)

    assert any("def compute" in c.text for c in result)


# --- short chunk merging ------------------------------------------------------


def test_chunker_each_function_is_a_chunk(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "def long_func():\n"
        "    x = 1\n"
        "    y = 2\n"
        "    z = 3\n"
        "\n"
        "def tiny():\n"
        "    pass\n"
    )
    f = write_file(tmp_path, "engine.py", content)

    result = chunk(f)

    # with semantic chunking each function is its own chunk
    names = [c.name for c in result if c.name]
    assert "long_func" in names
    assert "tiny" in names


# --- long chunk splitting -----------------------------------------------------


def test_chunker_splits_chunks_over_2000_chars(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    # one function with a very long body
    body = "\n".join(f"    x_{i} = {i}" for i in range(200))
    content = f"def huge_func():\n{body}\n"
    f = write_file(tmp_path, "engine.py", content)

    result = chunk(f)

    assert all(len(c.text) <= 2000 for c in result)


# --- non-code files -----------------------------------------------------------


def test_chunker_splits_markdown_on_blank_lines(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "# Title\n"
        "First paragraph with some text.\n"
        "\n"
        "Second paragraph with more text.\n"
        "\n"
        "Third paragraph here.\n"
    )
    f = write_file(tmp_path, "readme.md", content)

    result = chunk(f)

    assert len(result) >= 2


def test_chunker_handles_empty_file(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "empty.py", "")

    result = chunk(f)

    assert result == []


# --- extract_numeric_constants — C# regression --------------------------------
# Regression: the old query used (equals_value_clause) which is not a valid
# node type in tree-sitter-c-sharp; it raised QueryError on any .cs file.


def test_extract_numeric_constants_csharp_does_not_raise(tmp_path: Path) -> None:
    """extract_numeric_constants must not raise on a valid .cs file."""
    from src.indexer.chunker import extract_numeric_constants

    f = write_file(
        tmp_path,
        "Pricing.cs",
        "namespace Billing {\n"
        "    public class PricingEngine {\n"
        "        private const decimal DiscountRate = 0.0325m;\n"
        "        private const decimal TierPremium  = 2.47m;\n"
        "    }\n"
        "}\n",
    )

    result = extract_numeric_constants(f)

    values = [v for v, _ in result]
    assert pytest.approx(0.0325, rel=1e-4) in values
    assert pytest.approx(2.47,   rel=1e-4) in values


def test_extract_numeric_constants_csharp_integer(tmp_path: Path) -> None:
    """Integer constants in C# are also extracted."""
    from src.indexer.chunker import extract_numeric_constants

    f = write_file(
        tmp_path,
        "Config.cs",
        "public class Config {\n"
        "    private const int MaxRetries = 42;\n"
        "}\n",
    )

    result = extract_numeric_constants(f)

    values = [v for v, _ in result]
    assert 42.0 in values


def test_extract_numeric_constants_csharp_negative(tmp_path: Path) -> None:
    """Negative numeric constants in C# are extracted via prefix_unary_expression."""
    from src.indexer.chunker import extract_numeric_constants

    f = write_file(
        tmp_path,
        "Constants.cs",
        "public class Constants {\n"
        "    private const double Adjustment = -3.14;\n"
        "}\n",
    )

    result = extract_numeric_constants(f)

    values = [v for v, _ in result]
    assert pytest.approx(-3.14, rel=1e-4) in values
