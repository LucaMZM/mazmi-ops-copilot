"""Structure-aware chunking (``structured_v2``).

The previous splitter (``rag.split_text``, kept as ``flat_v1``) collapses all
whitespace and cuts every ~1,200 characters, so headings, list items and table rows
can be split mid-way and a chunk carries no indication of the section it belongs to.

This splitter:

* recognises Markdown headings, numbered headings ("2.1 Solicitud") and short
  all-caps titles, and keeps a heading path ("Vacaciones › Solicitud") as metadata;
* treats paragraphs, list items and table rows as indivisible blocks;
* starts a new chunk at every heading and packs consecutive blocks of the same
  section up to ``max_chars``;
* repeats the section heading line (verbatim document text) at the start of each
  chunk of that section so retrieval sees the context, and repeats a table's header
  row when a table spans several chunks;
* falls back to sentence splitting with overlap only for single blocks longer than
  ``max_chars``.

Content is always text taken from the document; nothing is paraphrased or invented.
Page numbers come only from the extractor (PDF); other formats keep ``page=None``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+){0,3})\.?\s+([A-ZÁÉÍÓÚÑ][^.!?;:]{1,78})$")
LIST_ITEM = re.compile(r"^\s*(?:[-*•+]|\d+[.)]|[a-z][.)])\s+\S")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


@dataclass(frozen=True)
class Block:
    kind: str  # heading | text | list | table
    text: str
    path: tuple[str, ...]
    heading: str | None  # verbatim heading line of the current section


@dataclass(frozen=True)
class StructuredChunk:
    content: str
    section: str | None


def _caps_heading(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return (
        4 <= len(line) <= 60
        and len(letters) >= 4
        and all(c.isupper() for c in letters)
        and not line.endswith((".", ",", ";"))
    )


def _heading(line: str) -> tuple[int, str] | None:
    if match := MD_HEADING.match(line):
        return len(match[1]), match[2].strip()
    if (match := NUMBERED_HEADING.match(line)) and (
        "." in match[1] or len(match[2].split()) <= 6
    ):  # "1. Introducción" or "2.1 Solicitud", not a long numbered list item.
        return min(match[1].count(".") + 1, 6), line.strip()
    if _caps_heading(line):
        return 1, line.strip()
    return None


def parse_blocks(text: str, path: tuple[str, ...] = ()) -> tuple[list[Block], tuple[str, ...]]:
    """Return blocks and the heading path at the end (to continue across PDF pages)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ").split("\n")
    levels: list[tuple[int, str, str]] = [(i + 1, title, title) for i, title in enumerate(path)]
    blocks: list[Block] = []
    current: list[str] = []
    kind: str | None = None

    def state():
        return tuple(t for _, t, _ in levels), (levels[-1][2] if levels else None)

    def flush():
        nonlocal current, kind
        if current:
            joined = "\n".join(current) if kind == "table" else " ".join(current)
            section_path, heading = state()
            blocks.append(Block(kind or "text", joined, section_path, heading))
        current, kind = [], None

    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            flush()
            continue
        found = _heading(line) if kind != "table" else None
        if found and len(line) <= 120:
            flush()
            level, title = found
            levels = [entry for entry in levels if entry[0] < level] + [(level, title, line)]
            section_path, heading = state()
            blocks.append(Block("heading", line, section_path, heading))
            continue
        if TABLE_ROW.match(line) or (kind == "table" and TABLE_RULE.match(line)):
            line_kind = "table"
        elif LIST_ITEM.match(raw):
            line_kind = "list"
        else:
            line_kind = "text"
        continuation = kind == "list" and line_kind == "text" and raw[:1] in {" ", "\t"}
        if line_kind == "list" or (current and line_kind != kind and not continuation):
            flush()
        current.append(line)
        kind = kind if continuation else line_kind
    flush()
    return blocks, tuple(t for _, t, _ in levels)


def _sentences(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split one oversized block at sentence boundaries, with bounded overlap."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    current = ""
    for part in parts:
        while len(part) > max_chars:  # A single gigantic "sentence": hard cut on spaces.
            cut = part.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            if current:
                pieces.append(current)
                current = ""
            pieces.append(part[:cut].strip())
            part = part[cut:].strip()
        if current and len(current) + 1 + len(part) > max_chars:
            pieces.append(current)
            tail = current[-overlap:]
            space = tail.find(" ")
            current = (tail[space + 1 :] + " " if 0 <= space < len(tail) - 1 else "") + part
            if len(current) > max_chars:
                current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def chunk_blocks(blocks: list[Block], max_chars: int = 1200, overlap: int = 200):
    chunks: list[StructuredChunk] = []
    body: list[str] = []
    prefix: str | None = None
    section: str | None = None
    table_header: str | None = None

    def emit():
        nonlocal body
        if body:
            lines = ([prefix] if prefix else []) + body
            chunks.append(StructuredChunk("\n".join(lines), section))
        body = []

    def size():
        return sum(len(x) + 1 for x in body) + (len(prefix) + 1 if prefix else 0)

    for block in blocks:
        if block.kind == "heading":
            emit()
            prefix, section = block.heading, " › ".join(block.path)[:300] or None
            table_header = None
            continue
        if block.heading != prefix:  # Content before the first heading of a page, etc.
            emit()
            prefix = block.heading
            section = " › ".join(block.path)[:300] or None
        budget = max_chars - (len(prefix) + 1 if prefix else 0)
        if block.kind == "table":
            rows = block.text.split("\n")
            header = rows[0]
            if len(rows) > 1 and TABLE_RULE.match(rows[1]):
                header = rows[0] + "\n" + rows[1]
                rows = rows[2:]
            else:
                rows = rows[1:]
            table_header = header
            if size() + len(header) + 1 > max_chars:
                emit()
            body.append(header)
            for row in rows:
                if size() + len(row) + 1 > max_chars:
                    emit()
                    body.append(table_header)
                body.append(row[:budget])
            continue
        if len(block.text) > budget:
            emit()
            for piece in _sentences(block.text, budget, overlap):
                body.append(piece)
                emit()
            continue
        if size() + len(block.text) + 1 > max_chars:
            emit()
        body.append(block.text)
    emit()
    return chunks


def structured_chunks(
    pages: list[tuple[int | None, str]], max_chars: int = 1200, overlap: int = 200
) -> list[tuple[int | None, StructuredChunk]]:
    """Chunk every page, carrying the heading path across page breaks."""
    out: list[tuple[int | None, StructuredChunk]] = []
    path: tuple[str, ...] = ()
    for page, text in pages:
        blocks, path = parse_blocks(text, path)
        # Headings without body text never become chunks on their own.
        page_chunks = [c for c in chunk_blocks(blocks, max_chars, overlap) if c.content.strip()]
        out.extend((page, chunk) for chunk in page_chunks)
    return out
