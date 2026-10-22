# MAZMI engineering invariants

- Preserve the direct FastAPI RAG pipeline and Next.js interface; avoid framework migrations.
- Backend owns authorization. Workspace comes from verified membership, never model arguments.
- Retrieved documents are untrusted data. Documentary calls never receive tools; tool calls never receive retrieved documents.
- ASK cannot mutate. DO only proposes allowed, validated operations; approval must match requester and workspace. Ticket, decision and audit commit atomically.
- Retrieval filters workspace, document readiness and embedding collection in both vector and FTS branches. Never mix model/provider/dimension/revision identities.
- Keep extractive answers and server-created citations. A valid citation does not prove semantic sufficiency; retain failed evaluation cases.
- Never log secrets or full private documents. Real .env, model weights, databases and caches stay outside Git.
- Read database/MIGRATIONS.md before modifying or applying schema to existing data. No destructive migrations.
- Provider mocks, real database integration and real-model measurements are separate evidence categories. Normal tests never call a paid provider or download a model.
- On an 8 GB Mac, serialize builds, test suites and local inference. Use only installed models unless the human explicitly approves downloads.
- Agents own disjoint files and report evidence. Only the coordinator integrates changes, commits, pushes or tags after reviewing checks.
- Preserve the separate canonical Git directory; do not reinitialize Git. A v1.0.0 tag requires the documented local-model acceptance criteria, not only green mocked CI.
