"""RAG v2: structured chunking, any-term FTS, per-document diversity, focused quotes."""

import re
from io import BytesIO
from types import SimpleNamespace as NS

from docx import Document
from test_pipeline import api as api  # shared real PostgreSQL fixture

from app import main, rag
from app.chunking import structured_chunks
from app.config import settings
from app.evidence import documentary_answer, focused_quote, normalize

POLICY = """# Política de vacaciones

## Días disponibles
Las vacaciones anuales son 25 días laborables. El primer año se calculan de forma proporcional.

## Solicitud
- Solicita las vacaciones con al menos 10 días de antelación.
- La persona responsable aprueba o rechaza la solicitud.
  La respuesta se registra en el portal.

## Tabla de tramos
| Antigüedad | Días extra |
| --- | --- |
| 5 años | 1 |
| 10 años | 2 |
"""


def test_structured_chunks_keep_sections_lists_and_tables_verbatim():
    chunks = [c for _, c in structured_chunks([(None, POLICY)], max_chars=1200)]
    sections = [c.section for c in chunks]
    assert sections == [
        "Política de vacaciones › Días disponibles",
        "Política de vacaciones › Solicitud",
        "Política de vacaciones › Tabla de tramos",
    ]
    solicitud = chunks[1].content.split("\n")
    assert solicitud[0] == "## Solicitud"
    # The indented continuation stays with its list item; items are never merged.
    assert solicitud[2] == (
        "- La persona responsable aprueba o rechaza la solicitud. La respuesta se registra en "
        "el portal."
    )
    assert "| 10 años | 2 |" in chunks[2].content
    normalized_source = " ".join(POLICY.split())
    for chunk in chunks:
        for line in chunk.content.split("\n"):
            assert " ".join(line.split()) in normalized_source


def test_long_tables_repeat_header_and_chunks_respect_the_limit():
    rows = "\n".join(f"| Centro {i} | {i * 3} plazas |" for i in range(80))
    text = "## Plazas por centro\n| Centro | Plazas |\n| --- | --- |\n" + rows
    chunks = [c for _, c in structured_chunks([(None, text)], max_chars=400)]
    assert len(chunks) > 3
    assert all(len(c.content) <= 400 for c in chunks)
    assert all(c.content.split("\n")[1] == "| Centro | Plazas |" for c in chunks)
    assert all(c.section == "Plazas por centro" for c in chunks)


def test_page_numbers_only_from_extractor_and_heading_path_crosses_pages():
    pages = [(1, "1. Introducción\nTexto de la primera página."), (2, "Continúa en la página dos.")]
    chunks = structured_chunks(pages)
    assert [(page, c.section) for page, c in chunks] == [
        (1, "1. Introducción"),
        (2, "1. Introducción"),
    ]
    assert structured_chunks([(None, "Texto sin páginas.")])[0][0] is None


def test_oversized_paragraph_falls_back_to_sentences_with_limit():
    text = "## Normas\n" + " ".join(f"Norma número {i} del reglamento interno." for i in range(200))
    chunks = [c for _, c in structured_chunks([(None, text)], max_chars=500)]
    assert len(chunks) > 5 and all(len(c.content) <= 500 for c in chunks)


def test_flat_strategy_remains_available(monkeypatch):
    monkeypatch.setattr(settings, "chunking_strategy", "flat_v1")
    chunks = rag.chunk_pages([(None, POLICY)])
    assert all(c.section is None for c in chunks)
    assert chunks[0].content.startswith("# Política de vacaciones ## Días disponibles")


def test_docx_extraction_keeps_document_order_headings_and_tables():
    doc = Document()
    doc.add_heading("Gastos de viaje", level=1)
    doc.add_paragraph("El límite por comida es de 25 euros.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Concepto", "Límite"
    table.cell(1, 0).text, table.cell(1, 1).text = "Hotel", "90 euros"
    doc.add_paragraph("Después de la tabla.")
    buffer = BytesIO()
    doc.save(buffer)
    text = rag.extract_pages("gastos.docx", buffer.getvalue())[0][1]
    order = [text.index(x) for x in ("# Gastos", "25 euros", "| Hotel | 90 euros |", "Después")]
    assert order == sorted(order)


def test_focused_quote_is_literal_and_keeps_adjacent_qualifiers():
    passage = (
        "La empresa publica su calendario laboral en enero. "
        "Las vacaciones anuales son 25 días laborables. "
        "Salvo el primer año, en el que se calculan de forma proporcional. "
        "El comedor abre de 13 a 16 horas. "
        "El aparcamiento tiene 40 plazas asignadas por antigüedad. "
        "Las visitas deben registrarse en recepción."
    )
    quote = focused_quote("¿Cuántos días de vacaciones hay?", passage)
    assert "25 días laborables" in quote and "Salvo el primer año" in quote
    assert "comedor" not in quote and "aparcamiento" not in quote
    for fragment in quote.split(" … "):
        assert fragment.strip(" …") in passage
    # No shared vocabulary: return the whole passage instead of guessing.
    assert focused_quote("¿Quién firma?", passage) == passage


def test_focused_answer_names_origin_and_cites_server_ids():
    client = NS(
        responses=NS(
            create=lambda **kw: NS(
                status="completed",
                output=[],
                output_text='{"status":"sufficient","passage_ids":[1]}',
            )
        )
    )
    source = {
        "content": "## Días disponibles\nLas vacaciones anuales son 25 días laborables.",
        "filename": "vacaciones.md",
        "section": "Política › Días disponibles",
    }
    text, _, meta = documentary_answer(client, "¿Cuántos días de vacaciones hay?", [source])
    assert text == (
        "Según vacaciones.md (Política › Días disponibles):\n"
        "«Las vacaciones anuales son 25 días laborables.» [1]"
    )
    assert meta["evidence_policy"] == "extractive_v5_focused" and meta["citations"] == [1]
    # The assessor input never includes filenames/sections (unchanged model contract).


def test_any_term_fts_finds_natural_questions_that_all_terms_misses(api, monkeypatch):
    api.post(
        "/api/documents",
        files={"file": ("v.md", "Las vacaciones anuales son 25 días laborables.".encode())},
    )
    workspace = api.get("/api/auth/me").json()["workspace_id"]
    question = "¿Cuántos días de vacaciones tengo este año?"
    results = {}
    for mode in ("all_terms_v1", "any_terms_v2"):
        monkeypatch.setattr(settings, "lexical_query_mode", mode)
        meta = {}
        with main.get_conn() as conn:
            rag.retrieve(conn, workspace, question, diagnostics=meta)
        results[mode] = meta["lexical_candidates"]
    assert results == {"all_terms_v1": 0, "any_terms_v2": 1}


def test_per_document_cap_lets_a_second_document_in(api, monkeypatch):
    long_doc = "\n\n".join(
        f"## Acceso {i}\nEl acceso al sistema {i} requiere aprobación del responsable."
        for i in range(10)
    )
    api.post("/api/documents", files={"file": ("acceso.md", long_doc.encode())})
    api.post(
        "/api/documents",
        files={"file": ("auditoria.md", "El acceso queda registrado en auditoría.".encode())},
    )
    workspace = api.get("/api/auth/me").json()["workspace_id"]
    selected = {}
    for cap in (20, 3):
        monkeypatch.setattr(settings, "retrieval_max_chunks_per_document", cap)
        with main.get_conn() as conn:
            rows = rag.retrieve(conn, workspace, "acceso aprobación responsable", limit=4)
        selected[cap] = {r["filename"] for r in rows}
    assert selected[3] == {"acceso.md", "auditoria.md"}
    assert normalize("Acceso") == "acceso"


def test_focused_quote_drops_list_syntax_and_origin_uses_inner_sections():
    client = NS(
        responses=NS(
            create=lambda **kw: NS(
                status="completed",
                output=[],
                output_text='{"status":"sufficient","passage_ids":[1]}',
            )
        )
    )
    content = (
        "### 2.2 Solicitud\n"
        "- Las vacaciones se solicitan con 10 días de antelación en el portal interno.\n"
        "- La persona responsable responde en un máximo de 5 días hábiles laborables.\n"
        "- En los almacenes no se pueden pedir vacaciones durante el inventario anual."
    )
    source = {
        "content": content,
        "filename": "manual.md",
        "section": "Manual › 2. Vacaciones › 2.2 Solicitud",
    }
    text, _, _ = documentary_answer(
        client, "¿Se pueden pedir vacaciones en el inventario?", [source]
    )
    assert text.startswith("Según manual.md (2. Vacaciones › 2.2 Solicitud):\n«")
    quote = text.split("«", 1)[1].rsplit("»", 1)[0]
    assert "- " not in quote and "#" not in quote
    # Literal per unit: every sentence/list item of the quote exists verbatim.
    for fragment in quote.split(" … "):
        for unit in re.split(r"(?<=\.)\s+", fragment.strip(" …")):
            assert unit in content
