from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tree_sitter import Language, Node

_MIN_LINES = 3
_MAX_CHARS = 2000
_BLOCK_PATTERN = re.compile(r"^(def |class |async def )", re.MULTILINE)
_PARAGRAPH_SEP = re.compile(r"\n\s*\n")
_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".java", ".go",
    ".cs", ".cpp", ".c", ".cc", ".cxx", ".rs",
}


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    doc_id: str
    text: str
    source_file: str
    chunk_index: int
    kind: str | None = field(default=None)
    name: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Tree-sitter language registry
# ---------------------------------------------------------------------------

# Node types for semantic *chunking* — splitting a file into indexable units.
# Each entry: node_type -> kind string ("function" | "class" | "method" | ...)
_CHUNK_NODE_TYPES: dict[str, dict[str, str]] = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "javascript": {
        "function_declaration": "function",
        "function_expression": "function",
        "arrow_function": "function",
        "class_declaration": "class",
        "class_expression": "class",
        "method_definition": "method",
        "lexical_declaration": "variable",
        "variable_declaration": "variable",
    },
    "typescript": {
        "function_declaration": "function",
        "function_expression": "function",
        "arrow_function": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "lexical_declaration": "variable",
        "variable_declaration": "variable",
    },
    "java": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_declaration": "method",
        "constructor_declaration": "method",
        "field_declaration": "variable",   # GAP-J1: private static final constants
        "enum_declaration": "class",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "type",
    },
    "rust": {
        "function_item": "function",
        "impl_item": "impl",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "const_item": "variable",   # GAP-RS1: const MAGIC: u32 = 0xCAFE_BABE
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
        "namespace_definition": "namespace",
        "template_declaration": "template",
        "declaration": "variable",   # GAP-CPP1: static const SAMPLE_RATE = 44100.0
    },
    "c_sharp": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_declaration": "method",
        "constructor_declaration": "method",
        "property_declaration": "property",
        "struct_declaration": "struct",
        "enum_declaration": "enum",
        "namespace_declaration": "namespace",
        # NOTE: file_scoped_namespace_declaration (C# 10+) only holds the name token;
        # class/enum declarations are siblings at compilation_unit level — no entry needed.
        "field_declaration": "variable",  # GAP-CS1: private const fields
    },
}

# extension -> language name
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cs": "c_sharp",
}

# Tree-sitter queries for symbol name extraction.
# Each @name capture resolves to the identifier node that IS the symbol name.
_SYMBOL_QUERIES: dict[str, str] = {
    "python": """
        (function_definition name: (identifier) @name)
        (class_definition name: (identifier) @name)
        (assignment left: (identifier) @name)
    """,
    "javascript": """
        (function_declaration name: (identifier) @name)
        (function_expression name: (identifier) @name)
        (class_declaration name: (identifier) @name)
        (class_expression name: (identifier) @name)
        (method_definition name: (property_identifier) @name)
        (lexical_declaration (variable_declarator name: (identifier) @name))
        (variable_declaration (variable_declarator name: (identifier) @name))
    """,
    "typescript": """
        (function_declaration name: (identifier) @name)
        (function_expression name: (identifier) @name)
        (class_declaration name: (type_identifier) @name)
        (method_definition name: (property_identifier) @name)
        (interface_declaration name: (type_identifier) @name)
        (type_alias_declaration name: (type_identifier) @name)
        (lexical_declaration (variable_declarator name: (identifier) @name))
        (variable_declaration (variable_declarator name: (identifier) @name))
    """,
    "java": """
        (class_declaration name: (identifier) @name)
        (interface_declaration name: (identifier) @name)
        (method_declaration name: (identifier) @name)
        (constructor_declaration name: (identifier) @name)
        (field_declaration (variable_declarator name: (identifier) @name))
        (enum_declaration name: (identifier) @name)
    """,
    "go": """
        (function_declaration name: (identifier) @name)
        (method_declaration name: (field_identifier) @name)
        (type_declaration (type_spec name: (type_identifier) @name))
        (const_declaration (const_spec name: (identifier) @name))
        (var_declaration (var_spec name: (identifier) @name))
    """,
    "rust": """
        (function_item name: (identifier) @name)
        (impl_item type: (type_identifier) @name)
        (struct_item name: (type_identifier) @name)
        (enum_item name: (type_identifier) @name)
        (trait_item name: (type_identifier) @name)
        (const_item name: (identifier) @name)
    """,
    "c": """
        (function_definition declarator: (function_declarator declarator: (identifier) @name))
        (struct_specifier name: (type_identifier) @name)
        (enum_specifier name: (type_identifier) @name)
    """,
    "cpp": """
        (function_definition declarator: (function_declarator declarator: (identifier) @name))
        (function_definition declarator: (function_declarator
          declarator: (qualified_identifier name: (identifier) @name)))
        (class_specifier name: (type_identifier) @name)
        (struct_specifier name: (type_identifier) @name)
        (namespace_definition name: (identifier) @name)
        (declaration (init_declarator declarator: (identifier) @name))
    """,
    "c_sharp": """
        (class_declaration name: (identifier) @name)
        (interface_declaration name: (identifier) @name)
        (method_declaration name: (identifier) @name)
        (constructor_declaration name: (identifier) @name)
        (property_declaration name: (identifier) @name)
        (struct_declaration name: (identifier) @name)
        (enum_declaration name: (identifier) @name)
        (namespace_declaration name: (identifier) @name)
        (field_declaration (variable_declaration (variable_declarator (identifier) @name)))
    """,
}

# Tree-sitter queries for numeric constant extraction.
# @name captures the identifier; @rhs captures the right-hand-side value node.
# Note: Go rhs may be wrapped in an expression_list — _parse_numeric_node unwraps it.
_NUMERIC_QUERIES: dict[str, str] = {
    "python":     "(assignment left: (identifier) @name right: _ @rhs)",
    "javascript": """
        (lexical_declaration (variable_declarator name: (identifier) @name value: _ @rhs))
        (variable_declaration (variable_declarator name: (identifier) @name value: _ @rhs))
    """,
    "typescript": """
        (lexical_declaration (variable_declarator name: (identifier) @name value: _ @rhs))
        (variable_declaration (variable_declarator name: (identifier) @name value: _ @rhs))
    """,
    "java":    "(field_declaration (variable_declarator name: (identifier) @name value: _ @rhs))",
    "go":      "(const_declaration (const_spec name: (identifier) @name value: _ @rhs))",
    "rust":    "(const_item name: (identifier) @name value: _ @rhs)",
    "c":       "(declaration (init_declarator declarator: (identifier) @name value: _ @rhs))",
    "cpp":     "(declaration (init_declarator declarator: (identifier) @name value: _ @rhs))",
    "c_sharp": """
        [
          (variable_declarator (identifier) @name (real_literal) @rhs)
          (variable_declarator (identifier) @name (integer_literal) @rhs)
          (variable_declarator (identifier) @name (prefix_unary_expression) @rhs)
        ]
    """,
}


def _get_ts_language(lang_name: str) -> Language | None:
    try:
        from tree_sitter import Language
        if lang_name == "python":
            import tree_sitter_python
            return Language(tree_sitter_python.language())
        if lang_name == "javascript":
            import tree_sitter_javascript
            return Language(tree_sitter_javascript.language())
        if lang_name == "typescript":
            import tree_sitter_typescript
            return Language(tree_sitter_typescript.language_typescript())  # type: ignore[attr-defined,unused-ignore]
        if lang_name == "java":
            import tree_sitter_java
            return Language(tree_sitter_java.language())
        if lang_name == "go":
            import tree_sitter_go
            return Language(tree_sitter_go.language())
        if lang_name == "rust":
            import tree_sitter_rust
            return Language(tree_sitter_rust.language())
        if lang_name == "c":
            import tree_sitter_c
            return Language(tree_sitter_c.language())
        if lang_name == "cpp":
            import tree_sitter_cpp
            return Language(tree_sitter_cpp.language())
        if lang_name == "c_sharp":
            import tree_sitter_c_sharp
            return Language(tree_sitter_c_sharp.language())
    except Exception:
        return None
    return None


def _compile_query(ts_lang: Language, query_str: str) -> Any:
    """Compile a query string using the available tree-sitter API."""
    try:
        from tree_sitter import Query
        return Query(ts_lang, query_str)
    except (ImportError, TypeError):
        # Fallback: pre-0.25 API where language.query() compiles directly
        return ts_lang.query(query_str)  # type: ignore[attr-defined,unused-ignore]


def _iter_captures(query: Any, root: Node) -> list[tuple[Node, str]]:
    """Return (node, capture_name) pairs, handling both tree-sitter API versions."""
    try:
        from tree_sitter import QueryCursor
        raw = QueryCursor(query).captures(root)
    except (ImportError, TypeError):
        raw = query.captures(root)

    if isinstance(raw, dict):
        # {capture_name: [node, ...]}
        return [(node, name) for name, nodes in raw.items() for node in nodes]
    # Pre-0.22: [(node, capture_name), ...]
    return list(raw)


def _iter_matches(query: Any, root: Node) -> list[dict[str, Node]]:
    """Return per-match {capture_name: node} dicts, handling both tree-sitter API versions."""
    try:
        from tree_sitter import QueryCursor
        matches = QueryCursor(query).matches(root)
    except (ImportError, TypeError):
        matches = query.matches(root)

    out: list[dict[str, Node]] = []
    for _, captures in matches:
        row: dict[str, Node] = {}
        for name, val in captures.items():
            row[name] = val[0] if isinstance(val, list) else val
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def extract_symbols(file_path: Path, min_length: int = 9) -> list[str]:
    """
    Extract all named symbols from a source file using tree-sitter AST.

    Returns function names, class names, and module-level private/constant
    variables (starting with ``_`` or all-caps).  Falls back to an empty
    list for unsupported file types.

    min_length: fallback threshold for symbol names without a leading underscore —
    configure via Settings.symbol_min_length; overridden by Ollama filter_symbols() in production.
    """
    ext = file_path.suffix.lower()
    lang_name = _EXT_TO_LANG.get(ext)
    if not lang_name or lang_name not in _SYMBOL_QUERIES:
        return []
    ts_lang = _get_ts_language(lang_name)
    if ts_lang is None:
        return []
    try:
        from tree_sitter import Parser
        src = file_path.read_bytes()
        root = Parser(ts_lang).parse(src).root_node
        query = _compile_query(ts_lang, _SYMBOL_QUERIES[lang_name])
        names: list[str] = []
        for node, _ in _iter_captures(query, root):
            name = src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            if _is_distinctive_symbol(name, min_length):
                names.append(name)
        return list(dict.fromkeys(n for n in names if n))
    except Exception:
        logger.warning("extract_symbols failed for %s", file_path, exc_info=True)
        return []


def _is_distinctive_symbol(name: str, min_length: int = 9) -> bool:
    """
    Syntactic pre-filter: returns True if the name is worth sending to L2.

    - Underscore-prefixed names (_foo, __bar) and ALL_CAPS constants are always kept.
    - All other names are kept only if len >= min_length.

    When Ollama is available, min_length acts as a noise gate (rejects 1–3 char
    tokens) and filter_symbols() makes the real domain/generic classification.
    When Ollama is unavailable, min_length is the only protection — a higher
    value reduces false positives at the cost of missing short proprietary names.
    Default (9) is the conservative fallback; configure via Settings.symbol_min_length.
    """
    if name.startswith("_"):
        return True
    if name.isupper():
        return True
    return len(name) >= min_length


def extract_numeric_constants(file_path: Path) -> list[tuple[float, int]]:
    """
    Extract numeric literal values (with significant-figure counts) from
    assignments whose left-hand side is a distinctive symbol.

    Examples that ARE extracted:
        _W_PAYMENT_HISTORY = 0.341    ->  (0.341, 3)
        _BAND_REJECT = 580            ->  (580.0, 3)
        _A = -3.2174                  ->  (-3.2174, 5)

    Examples that are NOT extracted:
        loop_count = 17               ->  skipped (name not distinctive)
        x = 0                         ->  skipped (name not distinctive)
    """
    ext = file_path.suffix.lower()
    lang_name = _EXT_TO_LANG.get(ext)
    if not lang_name or lang_name not in _NUMERIC_QUERIES:
        return []
    ts_lang = _get_ts_language(lang_name)
    if ts_lang is None:
        return []
    try:
        from tree_sitter import Parser
        src = file_path.read_bytes()
        root = Parser(ts_lang).parse(src).root_node
        query = _compile_query(ts_lang, _NUMERIC_QUERIES[lang_name])
        results: list[tuple[float, int]] = []
        for match in _iter_matches(query, root):
            name_node = match.get("name")
            rhs_node = match.get("rhs")
            if name_node is None or rhs_node is None:
                continue
            name = src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if not _is_distinctive_symbol(name):
                continue
            pair = _parse_numeric_node(rhs_node, src)
            if pair is not None:
                results.append(pair)
        # Require at least 2 significant figures: single-digit integers (3, 5, 10, 100)
        # are too common in natural language to serve as reliable fingerprints.
        results = [(v, sf) for v, sf in results if sf >= 2]
        seen: set[float] = set()
        deduped = []
        for val, sf in results:
            if val not in seen:
                seen.add(val)
                deduped.append((val, sf))
        return deduped
    except Exception:
        logger.warning("extract_numeric_constants failed for %s", file_path, exc_info=True)
        return []


def _parse_numeric_node(node: Node, src: bytes) -> tuple[float, int] | None:
    """Return (float_value, sig_figs) for a numeric literal node, or None."""
    # Go const_spec value may be wrapped in an expression_list node
    if node.type == "expression_list":
        child = node.children[0] if node.children else None
        if child is None:
            return None
        node = child

    if node.type in ("float", "integer", "number",  # "number" covers JS/TS literals
                     "decimal_integer_literal",
                     "decimal_floating_point_literal", "hex_integer_literal",
                     "int_literal", "float_literal",   # Go literals
                     "real_literal", "integer_literal", # GAP-CS3: C# / GAP-RS3: Rust literals
                     "number_literal"):                 # GAP-CPP3: C / C++ literals
        raw = src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        raw_no_sep = raw.replace("_", "")
        # GAP-RS3: hex literals (0x...) — float() can't parse them, and rstrip("fF") would
        # corrupt trailing hex digits like 0x0F → 0x0.  Use regex to extract hex digits only.
        if raw_no_sep.lower().startswith("0x"):
            hex_m = re.match(r"0[xX]([0-9a-fA-F]+)", raw_no_sep)
            if hex_m:
                hex_str = hex_m.group(1)
                try:
                    value = float(int(hex_str, 16))
                    sig = len(hex_str.lstrip("0")) or 1
                    return (value, max(sig, 2))  # hex constants always worth fingerprinting
                except (ValueError, OverflowError):
                    return None
            return None
        # Decimal literal: strip C#/Java type suffixes
        # (m/M=decimal, f/F=float, d/D=double, l/L=long)
        raw_clean = raw_no_sep.rstrip("mMfFdDlLuUiIsz")
        try:
            value = float(raw_clean)
            sf = _sig_figs_from_source(raw)
            return (value, sf)
        except ValueError:
            return None

    if node.type in ("unary_operator", "prefix_unary_expression"):
        # e.g.  -3.2174  or  -5_000m  (prefix_unary_expression = C# node name)
        op_nodes = [c for c in node.children if c.type in ("-", "+")]
        num_nodes = [c for c in node.children if c.type in (
            "float", "integer", "number",
            "decimal_integer_literal",
            "decimal_floating_point_literal",
            "real_literal", "integer_literal",
        )]
        if op_nodes and num_nodes:
            sign = -1.0 if op_nodes[0].type == "-" else 1.0
            inner = _parse_numeric_node(num_nodes[0], src)
            if inner is not None:
                val, sf = inner
                return (sign * val, sf)

    return None


def _sig_figs_from_source(raw: str) -> int:
    """Count significant figures from a numeric literal as written in source code.

    Trailing zeros after the decimal point beyond the last nonzero digit are not
    counted — ``1.00`` and ``1`` both give 1; ``44100`` (integer) gives 5.
    """
    raw = raw.strip().lstrip("+-").replace("_", "")  # Python allows 1_000_000
    raw = raw.rstrip("mMfFdDlLuU")  # strip C#/Java type suffixes (5_000m, 100L, etc.)
    has_decimal = "." in raw
    if "e" in raw.lower():
        raw = raw.lower().split("e")[0]
    digits = raw.replace(".", "")
    stripped = digits.lstrip("0")
    if has_decimal:
        stripped = stripped.rstrip("0")
    return len(stripped) if stripped else 1


def chunk(file_path: Path) -> list[Chunk]:
    if not file_path.is_file():
        return []
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return []

    stem = file_path.stem
    source = str(file_path)
    ext = file_path.suffix.lower()
    lang_name = _EXT_TO_LANG.get(ext)

    if lang_name:
        ts_lang = _get_ts_language(lang_name)
        if ts_lang is not None:
            raw = _split_semantic(text, ts_lang, lang_name)
            split = _split_long_semantic(raw)
            return [
                Chunk(
                    doc_id=f"{stem}__{i}",
                    text=item["text"],
                    source_file=source,
                    chunk_index=i,
                    kind=item["kind"],
                    name=item["name"],
                )
                for i, item in enumerate(split)
            ]

    # fallback: regex splitting (non-code or unsupported language)
    is_code = ext in _CODE_EXTENSIONS
    raw_texts = _split_code(text) if is_code else _split_paragraphs(text)
    merged = _merge_short(raw_texts) if is_code else raw_texts
    split_texts = _split_long(merged)
    return [
        Chunk(
            doc_id=f"{stem}__{i}",
            text=block,
            source_file=source,
            chunk_index=i,
            kind=None,
            name=None,
        )
        for i, block in enumerate(split_texts)
    ]


# ---------------------------------------------------------------------------
# Tree-sitter semantic splitting
# ---------------------------------------------------------------------------


def _node_name(node: Node, src: bytes) -> str | None:
    """Extract the identifier/name child of a node.

    Strategy:
    1. Grammar-defined "name" field (most reliable — works for C#, Java, Go, etc.).
    2. Two-pass scan of direct children: prefer plain identifier over type_identifier
       so Java method declarations (type_identifier "Decision" before identifier "evaluate")
       return the right name.  TypeScript/C# class names are type_identifier and fall
       through to pass 2.
    3. Grandchild lookups for variable_declarator, function_declarator, type_spec.
    """
    def decode(n: Node) -> str:
        return src[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

    # Pass 0: grammar "name" field — handles C# method_declaration where return type
    # and method name are both plain identifier nodes (can't distinguish in pass 1).
    try:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return decode(name_node)
    except Exception:  # noqa: S110
        pass

    first_type_id = None
    for child in node.children:
        if child.type in ("identifier", "property_identifier", "name", "field_identifier"):
            return decode(child)
        if child.type == "type_identifier" and first_type_id is None:
            first_type_id = child
        # JS/TS `lexical_declaration` / Java `field_declaration`: name inside variable_declarator
        if child.type == "variable_declarator":
            for grandchild in child.children:
                if grandchild.type == "identifier":
                    return decode(grandchild)
        # GAP-CS1: C# `field_declaration` has extra variable_declaration wrapper
        if child.type == "variable_declaration":
            for grandchild in child.children:
                if grandchild.type == "variable_declarator":
                    for gc2 in grandchild.children:
                        if gc2.type == "identifier":
                            return decode(gc2)
        # GAP-CPP1: C++ `declaration` → `init_declarator` → `identifier`  (static const X = ...)
        if child.type == "init_declarator":
            for grandchild in child.children:
                if grandchild.type == "identifier":
                    return decode(grandchild)
        # C/C++ `function_definition`: name inside function_declarator
        if child.type == "function_declarator":
            for grandchild in child.children:
                if grandchild.type in ("identifier", "field_identifier"):
                    return decode(grandchild)
                # GAP-CPP1: C++ `BiquadFilter::setCoeffs` — qualified name; return method part
                if grandchild.type == "qualified_identifier":
                    for gc2 in reversed(grandchild.children):
                        if gc2.type in ("identifier", "field_identifier"):
                            return decode(gc2)
        # Go `type_declaration`: name is type_identifier inside type_spec
        if child.type == "type_spec":
            for grandchild in child.children:
                if grandchild.type in ("type_identifier", "identifier"):
                    return decode(grandchild)

    # Fallback: type_identifier covers TS/C# class and interface names.
    if first_type_id is not None:
        return decode(first_type_id)
    return None


def _split_semantic(text: str, language: Language, lang_name: str) -> list[dict[str, Any]]:
    from tree_sitter import Parser
    parser = Parser(language)
    src = text.encode("utf-8")
    tree = parser.parse(src)
    root = tree.root_node

    node_type_map = _CHUNK_NODE_TYPES.get(lang_name, {})
    results: list[dict[str, Any]] = []

    # We walk the top-level children of the root (module/program node).
    # For languages where top-level is a class body (Java), we recurse one level.
    candidates = _collect_candidates(root, src, node_type_map, depth=0)

    if not candidates:
        # fallback: return the whole file as one chunk
        return [{"text": text.strip(), "kind": None, "name": None}]

    # Collect text spans, include leading comments/decorators
    lines = text.splitlines(keepends=True)
    for node, kind, name in candidates:
        start = node.start_point[0]
        end = node.end_point[0]

        # pull in decorators / attributes that immediately precede this node
        prefix_start = _find_prefix_start(lines, start)

        chunk_lines = lines[prefix_start:end + 1]
        chunk_text = "".join(chunk_lines).strip()
        if chunk_text:
            results.append({"text": chunk_text, "kind": kind, "name": name})

    if not results:
        return [{"text": text.strip(), "kind": None, "name": None}]

    return results


# Kinds that act as transparent containers: recurse into them to find fine-grained chunks.
# A container with no inner semantic units is emitted as a single chunk (e.g. empty class).
_CONTAINER_KINDS = frozenset({"class", "interface", "impl", "struct", "namespace"})

# Kinds that are always individual chunks regardless of nesting depth.
_ALWAYS_CHUNK_KINDS = frozenset({"function", "method"})

# Kinds emitted as chunks only at the top level (depth == 0).
# Inside a class they belong to L2 (symbol store), not L1 index.
_TOP_LEVEL_CHUNK_KINDS = frozenset({"variable", "property", "type", "enum"})

# AST node types that wrap semantic children without contributing their own chunk.
_BODY_NODE_TYPES = frozenset({
    "class_body", "declaration_list", "block",
    "source_file", "program", "translation_unit",
    "namespace_body",
    "field_declaration_list",   # C++ class body
})


def _collect_candidates(
    node: Node,
    src: bytes,
    node_type_map: dict[str, str],
    depth: int,
) -> list[tuple[Node, str, str | None]]:
    results: list[tuple[Node, str, str | None]] = []
    for child in node.children:
        if child.type in node_type_map:
            kind = node_type_map[child.type]
            name = _node_name(child, src)
            if kind in _CONTAINER_KINDS:
                # Prefer fine-grained inner chunks (methods, functions).
                inner = _collect_candidates(child, src, node_type_map, depth + 1)
                if inner:
                    results.extend(inner)
                else:
                    # No inner methods — emit the container itself (e.g. data class).
                    results.append((child, kind, name))
            elif kind in _ALWAYS_CHUNK_KINDS:
                results.append((child, kind, name))
            elif depth == 0 and kind in _TOP_LEVEL_CHUNK_KINDS:
                # Top-level variables/types (e.g. `const PLANS = {...}` in TS).
                results.append((child, kind, name))
            # else: variable/property inside a class — lives in L2, not a chunk
        elif child.type == "export_statement":
            # `export function/class/const X` — recurse without incrementing depth
            results.extend(_collect_candidates(child, src, node_type_map, depth))
        elif child.type in _BODY_NODE_TYPES:
            results.extend(_collect_candidates(child, src, node_type_map, depth + 1))
    return results


def _find_prefix_start(lines: list[str], node_start: int) -> int:
    """Walk backwards from node_start to include decorators and blank lines."""
    i = node_start - 1
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith("@") or stripped.startswith("#"):
            i -= 1
        else:
            break
    return max(0, i + 1)


# ---------------------------------------------------------------------------
# Splitting long semantic chunks
# ---------------------------------------------------------------------------


def _split_long_semantic(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        if len(item["text"]) <= _MAX_CHARS:
            result.append(item)
        else:
            # hard-cut preserving kind/name on first piece
            pieces = _hard_cut(item["text"])
            for j, piece in enumerate(pieces):
                result.append({
                    "text": piece,
                    "kind": item["kind"] if j == 0 else None,
                    "name": item["name"] if j == 0 else None,
                })
    return result


# ---------------------------------------------------------------------------
# Legacy regex splitting (fallback)
# ---------------------------------------------------------------------------


def _split_code(text: str) -> list[str]:
    lines = text.splitlines(keepends=True)
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if _BLOCK_PATTERN.match(line) and current:
            blocks.append("".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("".join(current).strip())
    return [b for b in blocks if b]


def _split_paragraphs(text: str) -> list[str]:
    parts = _PARAGRAPH_SEP.split(text)
    return [p.strip() for p in parts if p.strip()]


def _merge_short(blocks: list[str]) -> list[str]:
    if not blocks:
        return []
    result: list[str] = [blocks[0]]
    for block in blocks[1:]:
        lines = [line for line in block.splitlines() if line.strip()]
        if len(lines) < _MIN_LINES:
            result[-1] = result[-1] + "\n\n" + block
        else:
            result.append(block)
    return result


def _split_long(blocks: list[str]) -> list[str]:
    result: list[str] = []
    for block in blocks:
        if len(block) <= _MAX_CHARS:
            result.append(block)
        else:
            result.extend(_break_block(block))
    return result


def _break_block(block: str) -> list[str]:
    parts = _PARAGRAPH_SEP.split(block)
    pieces: list[str] = []
    current = ""
    for part in parts:
        candidate = (current + "\n\n" + part).strip() if current else part.strip()
        if len(candidate) > _MAX_CHARS and current:
            pieces.append(current.strip())
            current = part.strip()
        else:
            current = candidate
    if current:
        pieces.append(current.strip())
    result: list[str] = []
    for piece in pieces:
        if len(piece) <= _MAX_CHARS:
            result.append(piece)
        else:
            result.extend(_hard_cut(piece))
    return [p for p in result if p]


def _hard_cut(block: str) -> list[str]:
    lines = block.splitlines(keepends=True)
    pieces: list[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) > _MAX_CHARS and current:
            pieces.append(current.strip())
            current = line
        else:
            current += line
    if current:
        pieces.append(current.strip())
    return [p for p in pieces if p]
