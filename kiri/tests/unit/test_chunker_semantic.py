from __future__ import annotations

from pathlib import Path

# --- helpers ------------------------------------------------------------------


def write_file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --- Chunk dataclass fields ---------------------------------------------------


def test_chunk_has_kind_field(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "def foo():\n    pass\n")
    result = chunk(f)

    assert hasattr(result[0], "kind")


def test_chunk_has_name_field(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "def foo():\n    pass\n")
    result = chunk(f)

    assert hasattr(result[0], "name")


# --- Python semantic splitting ------------------------------------------------


def test_python_function_chunk_has_kind_function(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "def compute():\n    return 42\n")
    result = chunk(f)

    kinds = [c.kind for c in result]
    assert "function" in kinds


def test_python_function_chunk_has_correct_name(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "def compute():\n    return 42\n")
    result = chunk(f)

    names = [c.name for c in result]
    assert "compute" in names


def test_python_class_chunk_has_kind_class(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "class RiskScorer:\n    pass\n")
    result = chunk(f)

    kinds = [c.kind for c in result]
    assert "class" in kinds


def test_python_class_chunk_has_correct_name(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "class RiskScorer:\n    pass\n")
    result = chunk(f)

    names = [c.name for c in result]
    assert "RiskScorer" in names


def test_python_method_stays_with_class(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "class Scorer:\n"
        "    def score(self, x):\n"
        "        return x * 2\n"
    )
    f = write_file(tmp_path, "engine.py", content)
    result = chunk(f)

    # Fine granularity: the method is its own chunk, not bundled with the class header.
    method_chunks = [c for c in result if c.name == "score"]
    assert method_chunks, "expected a chunk named 'score'"
    assert "def score" in method_chunks[0].text


def test_python_decorator_included_in_chunk(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "@staticmethod\n"
        "def helper():\n"
        "    pass\n"
    )
    f = write_file(tmp_path, "engine.py", content)
    result = chunk(f)

    texts = "\n".join(c.text for c in result)
    assert "@staticmethod" in texts
    assert "def helper" in texts


def test_python_two_functions_in_separate_chunks(tmp_path: Path) -> None:
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

    names = [c.name for c in result if c.name]
    assert "foo" in names
    assert "bar" in names


# --- JavaScript ---------------------------------------------------------------


def test_js_function_declaration_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "function computeScore(x) {\n  return x * 2;\n}\n"
    f = write_file(tmp_path, "engine.js", content)
    result = chunk(f)

    assert any("computeScore" in c.text for c in result)
    assert any(c.kind == "function" for c in result)


def test_js_arrow_function_variable_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "const process = (x) => {\n  return x + 1;\n};\n"
    f = write_file(tmp_path, "engine.js", content)
    result = chunk(f)

    assert any("process" in c.text for c in result)


def test_js_class_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "class RiskEngine {\n  score(x) {\n    return x;\n  }\n}\n"
    f = write_file(tmp_path, "engine.js", content)
    result = chunk(f)

    # Fine granularity: class methods are individual chunks.
    assert any(c.name == "score" for c in result)
    assert any(c.kind == "method" for c in result)


# --- TypeScript ---------------------------------------------------------------


def test_ts_function_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "function greet(name: string): string {\n  return `Hello ${name}`;\n}\n"
    f = write_file(tmp_path, "engine.ts", content)
    result = chunk(f)

    assert any("greet" in c.text for c in result)
    assert any(c.kind == "function" for c in result)


def test_ts_interface_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "interface Scorer {\n  score(x: number): number;\n}\n"
    f = write_file(tmp_path, "engine.ts", content)
    result = chunk(f)

    assert any("Scorer" in c.text for c in result)


# --- Java ---------------------------------------------------------------------


def test_java_method_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "public class RiskScorer {\n"
        "    public int score(int x) {\n"
        "        return x * 2;\n"
        "    }\n"
        "}\n"
    )
    f = write_file(tmp_path, "RiskScorer.java", content)
    result = chunk(f)

    # Fine granularity: method is its own chunk (not bundled into the class chunk).
    assert any(c.name == "score" and c.kind == "method" for c in result)


# --- Go -----------------------------------------------------------------------


def test_go_function_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "package main\n\n"
        "func computeScore(x int) int {\n"
        "    return x * 2\n"
        "}\n"
    )
    f = write_file(tmp_path, "engine.go", content)
    result = chunk(f)

    assert any("computeScore" in c.text for c in result)
    assert any(c.kind == "function" for c in result)


def test_go_method_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "package main\n\n"
        "type Scorer struct{}\n\n"
        "func (s Scorer) Score(x int) int {\n"
        "    return x\n"
        "}\n"
    )
    f = write_file(tmp_path, "engine.go", content)
    result = chunk(f)

    assert any("Score" in c.text for c in result)


# --- Rust ---------------------------------------------------------------------


def test_rust_function_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "fn compute_score(x: i32) -> i32 {\n    x * 2\n}\n"
    f = write_file(tmp_path, "engine.rs", content)
    result = chunk(f)

    assert any("compute_score" in c.text for c in result)
    assert any(c.kind == "function" for c in result)


def test_rust_impl_block_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "struct Scorer;\n\n"
        "impl Scorer {\n"
        "    fn score(&self, x: i32) -> i32 {\n"
        "        x * 2\n"
        "    }\n"
        "}\n"
    )
    f = write_file(tmp_path, "engine.rs", content)
    result = chunk(f)

    # Fine granularity: impl functions are individual chunks.
    assert any(c.name == "score" and c.kind == "function" for c in result)


# --- C -----------------------------------------------------------------------


def test_c_function_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "int compute_score(int x) {\n    return x * 2;\n}\n"
    f = write_file(tmp_path, "engine.c", content)
    result = chunk(f)

    assert any("compute_score" in c.text for c in result)
    assert any(c.kind == "function" for c in result)


# --- C++ ---------------------------------------------------------------------


def test_cpp_function_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "int computeScore(int x) {\n    return x * 2;\n}\n"
    f = write_file(tmp_path, "engine.cpp", content)
    result = chunk(f)

    assert any("computeScore" in c.text for c in result)
    assert any(c.kind == "function" for c in result)


def test_cpp_class_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "class RiskScorer {\n"
        "public:\n"
        "    int score(int x) { return x * 2; }\n"
        "};\n"
    )
    f = write_file(tmp_path, "engine.cpp", content)
    result = chunk(f)

    # Fine granularity: inline methods are extracted as individual chunks.
    assert any(c.name == "score" for c in result)


# --- C# ----------------------------------------------------------------------


def test_csharp_method_is_chunked(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = (
        "public class RiskScorer {\n"
        "    public int Score(int x) {\n"
        "        return x * 2;\n"
        "    }\n"
        "}\n"
    )
    f = write_file(tmp_path, "RiskScorer.cs", content)
    result = chunk(f)

    # Fine granularity: method is its own chunk (not bundled into the class chunk).
    assert any(c.name == "Score" and c.kind == "method" for c in result)


# --- fallback for unknown extensions ------------------------------------------


def test_unknown_extension_falls_back_to_regex(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "some text\n\nmore text\n"
    f = write_file(tmp_path, "data.xyz", content)
    result = chunk(f)

    assert len(result) >= 1
    combined = "\n".join(c.text for c in result)
    assert "some text" in combined


def test_unknown_extension_chunk_kind_is_none(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "some text\n\nmore text\n"
    f = write_file(tmp_path, "data.xyz", content)
    result = chunk(f)

    assert all(c.kind is None for c in result)


# --- existing contract preserved ----------------------------------------------


def test_doc_id_format_preserved(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "risk_scorer.py", "def foo():\n    pass\n")
    result = chunk(f)

    for c in result:
        assert c.doc_id.startswith("risk_scorer__")
        assert "/" not in c.doc_id


def test_source_file_preserved(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "engine.py", "def foo():\n    pass\n")
    result = chunk(f)

    assert all(c.source_file == str(f) for c in result)


def test_chunk_index_is_sequential(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    content = "def a():\n    pass\n\ndef b():\n    pass\n\ndef c():\n    pass\n"
    f = write_file(tmp_path, "engine.py", content)
    result = chunk(f)

    for i, c in enumerate(result):
        assert c.chunk_index == i


def test_empty_file_returns_empty(tmp_path: Path) -> None:
    from src.indexer.chunker import chunk

    f = write_file(tmp_path, "empty.py", "")
    assert chunk(f) == []
