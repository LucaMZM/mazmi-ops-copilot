# Screenshot provenance

## MAZMI 2.0 — 9 November 2026 (`v2-*.png`, used by the README)

Captured with Playwright from the real Next.js production build (127.0.0.1:3000) and FastAPI (127.0.0.1:8010) on a dedicated `mazmi_v2_demo` PostgreSQL 17/pgvector database seeded by `python -m app.demo`. Deterministic demo AI, clearly labelled in every view; all data fictional; no passwords or keys visible. Desktop 1440 × 900, mobile 390 × 844 (no horizontal overflow measured). PNG written directly by the browser, no retouching or compositing. They are successive steps of one walkthrough (the proposal was confirmed before Activity was captured).

## Version 1 captures (historical)

The files below show the previous interface and are kept as historical evidence.


Captured on 20 October 2026 through the real browser, from Next.js production build and FastAPI with a dedicated PostgreSQL/pgvector demo database. Deterministic AI is clearly identified; no vendor requests. All data is fictional, without passwords or API keys.

Six main desktop views and a source inspector at 1440 × 1000; mobile Copilot at 390 × 844, with no horizontal overflow. Captures were visually reviewed. They represent successive steps of one walkthrough, not an immutable snapshot: approval was captured before rejection, and Activity afterwards.

The browser emits JPEG. macOS sips converted these originals to PNG without compositing, retouching or generated content. Originals remain outside Git.

## Real Ollama profile — 22 October 2026

The eight original PNGs above are preserved unchanged. Three additional JPEGs were captured from the real Next production server, FastAPI, native PostgreSQL/pgvector, Qwen3 4B and EmbeddingGemma, using only fictional evaluation records:

- `ollama-source.jpg`: the persisted INC-17 answer and the matching stored source passage. TXT has no reliable page numbering.
- `ollama-settings.jpg`: an explicitly requested structured-output and real-embedding probe completed; its timestamp describes that fixture check, not continuous availability or full RAG acceptance.
- `ollama-mobile.jpg`: the same real answer at 390 × 844; measured document width 390, no horizontal overflow.

Desktop captures use the browser's ordinary 1280 × 720 viewport. No compositing, retouching, generated images, private documents, passwords or API keys. The full evaluation still has false abstentions and a read-tool timeout: these captures are evidence of the shown journeys, not proof of complete model reliability. See the dated results in `VALIDATION.md`.
