# MAZMI Ops Copilot

**Enterprise AI for document knowledge, evidence-backed answers and human-supervised actions.**

[![Next.js 16.4.2](https://img.shields.io/badge/Next.js-16.4.2-24483B?style=flat&logo=nextdotjs&logoColor=white)](frontend/package-lock.json) [![React 19.3.1](https://img.shields.io/badge/React-19.3.1-24483B?style=flat&logo=react&logoColor=white)](frontend/package-lock.json) [![TypeScript 6.0.3](https://img.shields.io/badge/TypeScript-6.0.3-24483B?style=flat&logo=typescript&logoColor=white)](frontend/package-lock.json) [![Python 3.13](https://img.shields.io/badge/Python-3.13-24483B?style=flat&logo=python&logoColor=white)](backend/Dockerfile) [![FastAPI 0.143.3](https://img.shields.io/badge/FastAPI-0.143.3-24483B?style=flat&logo=fastapi&logoColor=white)](backend/requirements.lock)
[![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-24483B?style=flat&logo=postgresql&logoColor=white)](docker-compose.yml) [![pgvector image 0.8.2](https://img.shields.io/badge/pgvector%20image-0.8.2-24483B?style=flat&logo=postgresql&logoColor=white)](docker-compose.yml) [![Gemini SDK 2.31.0](https://img.shields.io/badge/Gemini%20SDK-2.31.0-24483B?style=flat&logo=googlegemini&logoColor=white)](GEMINI.md) [![Ollama optional API](https://img.shields.io/badge/Ollama-optional%20API-24483B?style=flat&logo=ollama&logoColor=white)](LOCAL_AI.md) [![OpenAI SDK 3.33.0](https://img.shields.io/badge/OpenAI%20SDK-3.33.0-24483B?style=flat&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBkPSJNOCAydjVtOC01djVNNSA3aDE0djRhNyA3IDAgMCAxLTE0IDBWN3ptNyAxMXY0Ii8%2BPC9zdmc%2B&logoColor=white)](backend/requirements.lock)
[![Docker Python 3.13 / Node 22](https://img.shields.io/badge/Docker-Python%203.13%20%2F%20Node%2022-24483B?style=flat&logo=docker&logoColor=white)](docker-compose.yml) [![GitHub Actions Ubuntu](https://img.shields.io/badge/GitHub%20Actions-Ubuntu-24483B?style=flat&logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![CI](https://img.shields.io/github/actions/workflow/status/LucaMZM/mazmi-ops-copilot/ci.yml?branch=main&style=flat&logo=githubactions&label=CI&cacheSeconds=60)](https://github.com/LucaMZM/mazmi-ops-copilot/actions/workflows/ci.yml) [![All Rights Reserved](https://img.shields.io/badge/License-All_Rights_Reserved-344966)](LICENSE)


MAZMI answers questions from a team's own documents with **verifiable, literal citations**, abstains when the evidence is not enough, and prepares operational actions that **only run after a person approves them**. Everything is scoped to a workspace and recorded in an audit trail.

Built as a portfolio project with a direct Python RAG pipeline (no LangChain or agent framework), real PostgreSQL persistence and a deliberately small tool surface.

> **Status (9 Nov 2026, version 2.0 on branch `feat/ops-copilot-v2`):** 306 backend and 47 frontend tests pass against real PostgreSQL/pgvector. Retrieval and local-model results are measured and published with their failures in [VALIDATION.md](VALIDATION.md). The local Qwen3 4B model still does not meet the acceptance criteria, so there is no `v1.0.0` tag. Gemini, OpenAI and voice are implemented but not verified live. This is not a production deployment.

## Screenshots

Real captures of the production build running the clearly labelled deterministic demo ([provenance](docs/screenshots/README.md)).

![Copilot: multi-document answer with literal citations](docs/screenshots/v2-copilot.png)

| Workspace | Evidence inspector |
|---|---|
| ![Workspace overview](docs/screenshots/v2-workspace.png) | ![Stored passage behind a citation](docs/screenshots/v2-source-inspector.png) |

| Human approval | Dark theme |
|---|---|
| ![Approval with visible consequences](docs/screenshots/v2-approvals.png) | ![Copilot in dark theme](docs/screenshots/v2-copilot-dark.png) |

[Knowledge](docs/screenshots/v2-knowledge.png) · [Activity](docs/screenshots/v2-activity.png) · [Settings](docs/screenshots/v2-settings.png) · [Mobile](docs/screenshots/v2-copilot-mobile.png)

## What 2.0 changed

| Area | Change | Evidence |
|---|---|---|
| Reliability | Exact ticket reads no longer require a model provider on the streaming endpoint; validation errors keep real HTTP codes | 6 HTTP regressions (3 failed before) |
| Transactions | No connection, lock or open transaction during embeddings or inference; one atomic final write that re-checks scope and cited chunks | Lock/`idle in transaction` tests that failed before |
| Idempotency | `client_request_id` replays a committed turn instead of creating a second proposal; safe retries from the UI | Sequential and concurrent tests |
| Streaming | asyncio SSE bridge, heartbeats, deadline, always one terminal event; robust browser parser | Unit tests (disconnect, timeout, split frames) |
| RAG | Structure-aware chunking, any-term Spanish FTS, per-document diversity, focused literal quotes with document and section | Retrieval ablation with real EmbeddingGemma |
| Frontend | Modular hooks and components; streaming draft isolated from history; conversations rename/archive | 47 tests, typecheck, lint, build |
| Design | Liquid Glass design system, light/dark, phone tab bar, reduced motion/transparency | Real browser checks |

## Architecture

```mermaid
flowchart LR
    Browser[Next.js 16 / React 19] -->|same-origin proxy, SSE| API[FastAPI: session, origin check, workspace]
    API --> Pool[(Bounded psycopg pool)]
    Pool --> DB[(PostgreSQL 17 + pgvector + Spanish FTS)]
    API --> Ingest[Extract → structured chunks → embed]
    API --> Retrieve[Vector + FTS → RRF → diversity]
    Retrieve --> Assess[Guards + model sufficiency check]
    Assess --> Quote[Literal quotes + server citations]
    API --> Tools[ASK read / DO proposal]
    Tools --> Approval[Human approval]
    Approval --> Tx[Ticket + decision + audit in one transaction]
    API <--> Providers[Gemini / Ollama / OpenAI / demo]
```

A chat turn runs in five phases: **preflight** (tool gate, limits, provider requirements) → **short read** (conversation scope, history) → **query embedding without a connection, then SQL retrieval** → **provider work with no connection held** → **one atomic write** that re-checks the conversation, the cited chunks and the idempotency key before storing messages, proposal and audit. A disconnect or deadline rolls back the turn. In-flight provider calls are not interrupted; their results are discarded.

## RAG: how an answer is built

1. **Ingest.** PDF, DOCX, TXT or Markdown up to 20 MB. Text is split by structure: headings (Markdown, numbered, DOCX styles), paragraphs, list items and table rows stay whole; tables repeat their header; each chunk stores its section path. Page numbers come only from PDFs.
2. **Retrieve.** Exact cosine search and Spanish full-text search, both filtered by workspace, document state and embedding collection, fused with Reciprocal Rank Fusion, deduplicated, at most three chunks per document in the first pass.
3. **Assess.** Deterministic guards check scope, missing facts, relations, conditional premises and literal contradictions. A model then decides `sufficient / insufficient / conflicting` and selects passage ids through a strict JSON schema; it never writes the answer.
4. **Answer.** The server renders literal sentences from the selected passages with their origin, for example `Según manual.md (2.2 Solicitud de vacaciones): «…» [1]`, and creates the citation ids. The inspector shows the full stored passage. Otherwise it abstains and says why.

Documents are untrusted data: documentary calls never receive tools and tool calls never receive documents or history. Vectors are isolated by provider, model, dimension and revision; switching models requires explicit reindexing.

## Security controls

Opaque HttpOnly `SameSite=Strict` session cookies (hashed in the database), scrypt passwords, persistent login throttling, origin checks on every mutation, server-side workspace membership on every query, strict Pydantic models, sanitized provider errors, CSP and security headers, bounded uploads and DOCX decompression. ASK cannot mutate. DO only creates a proposal; only the requester in the same workspace can decide it, exactly once, and execution, decision and audit commit together.

## Run it locally

Prerequisites: Python 3.13, Node.js 22+, PostgreSQL 17 with pgvector. Keep virtualenvs, `node_modules` and database clusters outside synchronized folders (iCloud/Dropbox).

```bash
git clone https://github.com/LucaMZM/mazmi-ops-copilot.git
cd mazmi-ops-copilot
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.lock
test -e .env || cp .env.example .env
(cd frontend && npm ci)
```

For the **no-key demo** follow [DEMO.md](DEMO.md): it creates a dedicated `*_demo` database, seeds fictional documents and prints a one-time password locally. For the local-model profile see [LOCAL_AI.md](LOCAL_AI.md); for Gemini see [GEMINI.md](GEMINI.md). Before using an existing database read [database/MIGRATIONS.md](database/MIGRATIONS.md) (migration 005 is additive).

```bash
# Terminal 1
cd backend && python -m app.migrate && uvicorn app.main:app --host 127.0.0.1 --port 8000
# Terminal 2
cd frontend && npm run dev
```

## Tests and evaluations

```bash
cd backend
ruff check .
TEST_DATABASE_URL=postgresql://… pytest -q          # integration tests use isolated schemas
python -m app.evaluate_grounding                    # offline evidence-policy corpus
DATABASE_URL=postgresql://…/x_eval python -m app.evaluate_retrieval --embeddings synthetic --output /tmp/r.json
cd ../frontend
npm test && npm run typecheck && npm run lint && npm run build
```

Without `TEST_DATABASE_URL` the integration tests are skipped, never reported as passed. Normal tests never call a paid provider or download a model. Real-model evaluations (`app.evaluate_local --live`, `app.evaluate_retrieval --embeddings ollama`) are explicit and refuse non-dedicated databases.

## Measured results (summary)

- Retrieval, real EmbeddingGemma, 22 answerable questions: Recall@3 0.955 → **1.0**, full evidence@6 0.955 → **1.0**, MRR 0.977 → 0.977, with chunks about a third of the previous size.
- Qwen3 4B on 8 fixed cases: 2/4 positives, **4/4 correct abstentions**, 1 timeout and 1 incomplete assessment. A faster no-reasoning mode answered 4/4 positives in 176 s instead of 777 s but **accepted insufficient evidence twice**, so it stays opt-in.
- All 13 security journeys (isolation, requester checks, exactly-once approval, rejection without execution, audit) passed with the real model.

Full tables, categories and limits: [VALIDATION.md](VALIDATION.md).

## Limitations

Small synthetic evaluation corpora; no large-corpus or ANN benchmark. The local 4B model is slow and imperfect at sufficiency judgements on 8 GB. Live Gemini/OpenAI, voice and Docker Compose runtime are unverified. Indexing is synchronous (interrupted jobs are marked failed on restart). No email recovery, invitations or RBAC. Prompt-injection controls reduce specific risks; they are not a guarantee.

## License

**Proprietary — All Rights Reserved.** The original code is visible for portfolio evaluation only. Copying, modifying, redistributing, and commercial reuse require prior written permission. See [LICENSE](LICENSE). Third-party components retain their own licenses.
