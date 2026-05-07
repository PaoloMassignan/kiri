from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from src.store.summary_store import SummaryStore
from src.store.symbol_store import SymbolStore

# Python/indentation-based stub markers
_BODY_STUB = "# [PROTECTED: implementation is confidential]"
# Curly-brace languages (Java, Go, Rust, C, C++, C#, JS, TS)
_BRACE_BODY_STUB = "// [PROTECTED: implementation is confidential]"

# Template for matching a Python/indentation-based function or class block.
# Matches from the first decorator (if any) or def/class line to the next
# top-level statement.  @[^\n]* captures the full decorator line including
# any arguments, e.g. @cache(ttl=30) or @property.
_FUNC_BLOCK_PATTERN = (
    r"^((?:@[^\n]*\n)*"                                    # zero or more @decorator lines
    r"(?:async\s+)?def\s+{name}\b"                         # def {name} header
    r"|(?:@[^\n]*\n)*"                                     # zero or more @decorator lines
    r"class\s+{name}\b)"                                   # or class {name} header
    r".*?"                                                   # body (non-greedy)
    r"(?=\n(?!\s)|\Z)"                                      # until next top-level or EOF
)

# Maps file extension to the comment style used in stub replacements
_EXT_TO_COMMENT: dict[str, str] = {
    ".py": "#",
    ".js": "//", ".ts": "//", ".tsx": "//",
    ".java": "//", ".go": "//", ".rs": "//",
    ".c": "//", ".cc": "//", ".cpp": "//", ".cxx": "//",
    ".cs": "//",
}


@lru_cache(maxsize=256)
def _block_re(name: str) -> re.Pattern[str]:
    """Return a compiled regex that matches a Python function/class block for *name*."""
    return re.compile(
        _FUNC_BLOCK_PATTERN.replace("{name}", re.escape(name)),
        re.MULTILINE | re.DOTALL,
    )


@lru_cache(maxsize=256)
def _numbered_def_re(name: str) -> re.Pattern[str]:
    """Match a function/class def line prefixed with a line number (e.g. '1: def foo')."""
    return re.compile(
        rf'^(\d+):\s*(?:(?:async\s+)?def\s+{re.escape(name)}\b|class\s+{re.escape(name)}\b)',
        re.MULTILINE,
    )


_NUMBERED_LINE_STRIP_RE = re.compile(r'^\d+:[ \t]?', re.MULTILINE)


@lru_cache(maxsize=256)
def _symbol_re(name: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(name)}\b")


def _is_numeric(symbol: str) -> bool:
    try:
        float(symbol)
        return True
    except ValueError:
        return False


@dataclass
class RedactedSpan:
    symbol: str
    original: str
    replacement: str


@dataclass
class RedactionResult:
    redacted_prompt: str
    was_redacted: bool
    redacted_spans: list[RedactedSpan] = field(default_factory=list)


class RedactionEngine:
    def __init__(
        self,
        summary_store: SummaryStore,
        symbol_store: SymbolStore,
    ) -> None:
        self._summaries = summary_store
        self._symbols = symbol_store

    def redact(self, prompt: str) -> RedactionResult:
        matched_symbols = self._symbols.scan(prompt)
        if not matched_symbols:
            return RedactionResult(redacted_prompt=prompt, was_redacted=False)

        result_prompt = prompt
        spans: list[RedactedSpan] = []

        for symbol in matched_symbols:
            # 0. Handle line-numbered file content (e.g. OpenCode's Read tool: "1: def foo")
            numbered = self._try_redact_numbered_python_block(result_prompt, symbol)
            if numbered is not None:
                original, replacement = numbered
                result_prompt = result_prompt.replace(original, replacement, 1)
                spans.append(
                    RedactedSpan(symbol=symbol, original=original, replacement=replacement)
                )
                continue

            # 1. Try Python/indentation-based matching first
            match = _block_re(symbol).search(result_prompt)
            if match:
                original = match.group(0)
                replacement = self._python_stub(original, symbol)
                result_prompt = (
                    result_prompt[:match.start()] + replacement + result_prompt[match.end():]
                )
                spans.append(
                    RedactedSpan(symbol=symbol, original=original, replacement=replacement)
                )
                continue

            # 2. Try curly-brace matching (Java, Go, Rust, C, C++, C#, JS, TS)
            brace_span = self._find_brace_block(result_prompt, symbol)
            if brace_span is not None:
                start, end = brace_span
                original = result_prompt[start:end]
                replacement = self._brace_stub(original, symbol)
                result_prompt = result_prompt[:start] + replacement + result_prompt[end:]
                spans.append(
                    RedactedSpan(symbol=symbol, original=original, replacement=replacement)
                )
                continue

            # 3. Fallback: replace inline occurrence of the symbol name.
            # Skip numeric literals — they are matched by L2 for detection but
            # replacing "1.7" inline creates mangled prompts when no code block
            # is present (the number is already gone if a block was redacted).
            if _is_numeric(symbol):
                continue
            if _symbol_re(symbol).search(result_prompt):
                result_prompt = _symbol_re(symbol).sub(
                    f"[PROTECTED:{symbol}]", result_prompt, count=1
                )
                spans.append(RedactedSpan(
                    symbol=symbol,
                    original=symbol,
                    replacement=f"[PROTECTED:{symbol}]",
                ))

        return RedactionResult(
            redacted_prompt=result_prompt,
            was_redacted=len(spans) > 0,
            redacted_spans=spans,
        )

    # ------------------------------------------------------------------
    # Numbered-line content (OpenCode "N: code" format)
    # ------------------------------------------------------------------

    def _try_redact_numbered_python_block(
        self, prompt: str, symbol: str
    ) -> tuple[str, str] | None:
        """Handle file content where each line is prefixed with 'N: ' (e.g. OpenCode Read tool).

        Finds the function/class block, strips the line-number prefixes, generates
        the stub via _python_stub, and returns (original_text, stub).
        Returns None if no numbered def line is found for *symbol*.
        """
        m = _numbered_def_re(symbol).search(prompt)
        if m is None:
            return None

        # Walk line-by-line from the def line, collecting the full block.
        # A block ends when we encounter a numbered line whose content is non-empty
        # and starts with a non-whitespace character (= new top-level statement).
        line_start = prompt.rfind('\n', 0, m.start())
        line_start = line_start + 1 if line_start >= 0 else 0

        found_def = False
        block_end = line_start

        for lm in re.finditer(r'^(\d+):[ \t]?(.*)', prompt[line_start:], re.MULTILINE):
            content = lm.group(2)
            abs_end = line_start + lm.end()
            if not found_def:
                if re.match(
                    rf'(?:(?:async\s+)?def\s+{re.escape(symbol)}\b|class\s+{re.escape(symbol)}\b)',
                    content,
                ):
                    found_def = True
                    block_end = abs_end
                continue
            if not content.strip():
                block_end = abs_end
            elif content[0].isspace():
                block_end = abs_end
            else:
                break

        if not found_def:
            return None

        original = prompt[line_start:block_end]
        stripped = _NUMBERED_LINE_STRIP_RE.sub('', original)
        stub = self._python_stub(stripped, symbol)
        return (original, stub)

    # ------------------------------------------------------------------
    # Python (indentation-based) stub
    # ------------------------------------------------------------------

    def _python_stub(self, block: str, symbol: str) -> str:
        """Preserve the def/class signature line; replace the indented body with a stub.

        With Ollama summary:
            def compute_dynamic_price(base_price: float, ...) -> float:
                # [PROTECTED] compute_dynamic_price
                # Purpose: Adjusts price based on demand and stock levels.
                ...

        No summary available:
            def _weighted_sum(components):
                # [PROTECTED: implementation is confidential]
                ...
        """
        first_newline = block.find("\n")
        if first_newline == -1:
            return _BODY_STUB

        signature_line = block[:first_newline]

        indent = "    "
        for line in block[first_newline + 1:].splitlines():
            if line.strip():
                indent = line[: len(line) - len(line.lstrip())]
                break

        # Use the summary if one was generated; fall back to the generic stub.
        summary = self._find_summary(symbol)
        if summary:
            indented = "\n".join(
                f"{indent}{line.lstrip()}" if line.strip() else ""
                for line in summary.splitlines()
            )
            return f"{signature_line}\n{indented}\n{indent}..."

        return f"{signature_line}\n{indent}{_BODY_STUB}\n{indent}..."

    # ------------------------------------------------------------------
    # Curly-brace (Java / Go / Rust / C / C++ / C# / JS / TS) stub
    # ------------------------------------------------------------------

    def _find_brace_block(self, prompt: str, symbol: str) -> tuple[int, int] | None:
        """Return (start, end) of the first curly-brace block that contains *symbol*.

        *start* points to the beginning of the declaration line; *end* is the
        character position after the closing ``}``.  Returns None if no such
        block is found.
        """
        for m in _symbol_re(symbol).finditer(prompt):
            sym_pos = m.start()

            # The opening brace must appear within 10 lines after the symbol
            brace_open = prompt.find("{", sym_pos)
            if brace_open == -1:
                continue
            if prompt[sym_pos:brace_open].count("\n") > 10:
                continue

            # Walk backwards to the start of the declaration line
            decl_start = prompt.rfind("\n", 0, sym_pos)
            decl_start = decl_start + 1 if decl_start >= 0 else 0

            # Balance braces to find the closing }
            depth = 1
            i = brace_open + 1
            while i < len(prompt) and depth > 0:
                c = prompt[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                i += 1

            if depth == 0:
                return (decl_start, i)

        return None

    def _brace_stub(self, block: str, symbol: str) -> str:
        """Keep the function header (up to and including ``{``); replace body with stub.

        With Ollama summary:
            float computePrice(float base, float demand) {
                // [PROTECTED] computePrice
                // Purpose: Adjusts price based on demand.
            }

        No summary available:
            float _scale(float raw) {
                // [PROTECTED: implementation is confidential]
            }
        """
        brace_pos = block.find("{")
        if brace_pos == -1:
            return block

        header = block[: brace_pos + 1]

        # Infer body indentation from the first non-empty line after the opening brace
        indent = "    "
        for line in block[brace_pos + 1 :].splitlines():
            if line.strip():
                indent = line[: len(line) - len(line.lstrip())]
                break

        # Use the summary if one was generated; fall back to the generic stub.
        summary = self._find_summary(symbol)
        if summary:
            summary_lines = [
                line.lstrip().removeprefix("#").removeprefix("//").strip()
                for line in summary.splitlines()
                if line.strip()
            ]
            body = "\n".join(f"{indent}// {ln}" for ln in summary_lines if ln)
            return f"{header}\n{body}\n}}"

        return f"{header}\n{indent}{_BRACE_BODY_STUB}\n}}"

    # ------------------------------------------------------------------
    # Summary lookup
    # ------------------------------------------------------------------

    def _find_summary(self, symbol: str) -> str | None:
        """Look up a summary for *symbol*, preferring manual overrides.

        Priority: manual__ entries > ollama entries.
        Manual entries are set via ``kiri summary set`` and keyed as
        ``manual__<symbol>``; they represent a deliberate human correction
        and always win over Ollama-generated ones.
        """
        # 1. Check for a manual override first
        manual = self._summaries.get(f"manual__{symbol}")
        if manual:
            return manual

        # 2. Fall back to Ollama-generated entries that mention the symbol
        for chunk_id in self._summaries.all_chunk_ids():
            if chunk_id.startswith("manual__"):
                continue
            summary = self._summaries.get(chunk_id)
            if summary and symbol in summary:
                return summary
        return None
