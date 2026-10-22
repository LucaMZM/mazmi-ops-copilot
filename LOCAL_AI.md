# Local AI: Ollama profile and verification

The opt-in [Ollama profile](profiles/ollama.env.example) runs generation and embeddings without a paid API key. It preserves the deterministic demo and the optional Gemini/OpenAI adapters. The repository-wide defaults remain Gemini; selecting this profile changes only the backend process you start. The application never downloads models or switches to a paid fallback.

## Reuse an existing installation

Check before changing anything:

```bash
ollama --version
ollama list
ollama ps
curl --fail http://127.0.0.1:11434/api/version
```

Use the existing daemon if it is already listening. Do not start a second server, reinstall Ollama or change another project's service configuration. On the validation machine, the existing installation is Ollama **0.40.7**, with `qwen3:4b` and `embeddinggemma` already installed. Inventory is not proof that a model completes a request; see [the dated evidence](VALIDATION.md).

If a required model is absent, stop the local-model check and review disk/memory requirements before authorizing a download. No model download is part of the setup commands here. Do not silently substitute Qwen3 1.7B or another embedding model.

## Start the isolated local profile

Follow the native dependency/database setup in [README.md](README.md). Keep the real connection string privately in the root `.env`; use a dedicated evaluation database for experiments. Before starting against an existing database, read [database/MIGRATIONS.md](database/MIGRATIONS.md).

```bash
# From the repository root, with the existing virtualenv active:
export MAZMI_ENV_FILE="$PWD/profiles/ollama.env.example"
cd backend
python -m app.migrate
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Separate terminal, from the repository root:
cd frontend
npm run dev
```

The additional profile is read after the root `.env`; exported environment variables take precedence over both. Inspect conflicting exported `GENERATION_PROVIDER`, `EMBEDDING_PROVIDER` or `DEMO_MODE` values before debugging the profile. Keep private overrides out of the tracked example. `APP_ENV=development`, `DEMO_MODE=false`, both providers `ollama`, context **4096**, request timeout **120 seconds** and configured embedding dimensions **768** are explicit in the profile. Restart the backend after configuration changes. No `OPENAI_API_KEY` or `GEMINI_API_KEY` is required for these operations.

Start the frontend with its existing dependencies. Open localhost:3000, register a local account and select a workspace. Settings reports configuration separately from verification. **Check local** explicitly runs fictional structured-output and embedding requests; GET `/api/system` itself performs no provider network requests. A result belongs to that process and configuration, expires after **300 seconds**, and does not prove continuous liveness or that all product journeys passed. Concurrent probes are rejected rather than queued indefinitely. A failed probe is shown honestly and does not disable ordinary text input.

## Bounded capability check

With the profile still exported and the daemon idle:

```bash
# From backend; do not run alongside a build or another inference suite:
python -m app.check_local
```

This command checks installed model metadata, Spanish generation, structured JSON validated by Pydantic, streamed text deltas, a tool proposal with a synthetic read-only result, actual embedding dimensions and a fresh request after closing an early stream. It neither executes a tool nor writes documents/database data. Exit status is nonzero on failure. Its fixture prompts are intentionally public; do not substitute private documents into shared diagnostic output.

A transport close does not establish immediate GPU cancellation. Capability advertising in `/api/show`, accepted HTTP parameters and a successful fixture are different observations. Initial real probes exposed incompatible thinking/sampling settings. With the installed Qwen3 preset, `think=null` (model default), seed 42 and a 1024-token budget produced the exact Spanish greeting in 23.305 seconds. The adapter preserves the model sampling defaults (observed temperature 0.6, top_p 0.95, top_k 20, min_p 0), uses context 4096 and never forwards the separate thinking field as an answer. Hard-coded greedy sampling and unsupported `think=false` were removed.

The later [full smoke report](backend/evals/ollama-smoke-results.json) preserves five successful capabilities and a failed counting-based cancellation fixture. A revised greeting-based early close and subsequent fresh request passed in a [separate selected check](backend/evals/ollama-cancellation-results.json). This cumulatively verifies the capabilities; it is not a single all-green full smoke. The [real RAG report](backend/evals/local-live-results.json) records four indexed policies, document Recall@6/MRR of 1.0, four correct negative abstentions and **two false abstentions out of four answerable questions**. The ticket-read journey separately returned a controlled 503 at the 120-second timeout. Simple function-calling fixtures passing does not establish reliable completion of every agent request. Do not increase context or hide failures to advertise a validated release.

Ollama uses native `/api/chat`, `/api/embed`, `/api/tags` and `/api/show` through httpx, not the OpenAI Responses protocol. The adapter maps JSON Schema, NDJSON streaming, function arguments and tool results to the application's internal contract. Backend schema validation, authorization, extractive evidence selection and confirmation remain authoritative.

## Resources on an 8 GB Mac

The observed MacBook Air M2 has 8 GB unified memory. Installed files are approximately **2.50 GB** for Qwen3 4B (`Q4_K_M`, 2,497,293,931 bytes) and **622 MB** for EmbeddingGemma (`BF16`, 621,875,917 bytes). File size does not equal resident memory. Context/KV cache, model reloads, browser, Next.js and PostgreSQL all compete for the same memory; measure pressure and latency on the target machine.

Serialize tests, builds and inference. A dedicated daemon can use `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_LOADED_MODELS=1`; these are **daemon-start settings**, not application profile variables, and must not silently reconfigure a daemon shared with another project. The adapter requests `keep_alive=0` so models are released between calls, trading memory for reload latency. Do not assume generation and embeddings remain resident together. Close unnecessary applications, keep room for database backups and stop if memory pressure becomes sustained. A larger-memory machine is preferable for repeated evaluation; no minimum latency or hardware throughput is promised.

## Collections, reindexing and migrations

EmbeddingGemma is configured for 768 dimensions. The smoke test must measure the returned length; metadata advertising 768 is not the same measurement. Inputs have distinct document/query prefixes; `truncate=false` rejects overlong inputs rather than silently changing them. EmbeddingGemma's documented input context is 2048 tokens, so long chunks and questions need explicit boundary tests.

Collection identity includes provider, model, dimensions, Ollama digest and prefix revision. Equal dimensions do not make demo, Gemini, OpenAI and Ollama vectors interchangeable. Both vector and FTS retrieval filter workspace, ready document state and the active collection before fusion. A document can remain visible but incompatible until explicitly reindexed in Knowledge. Reindexing preserves stored text/IDs and replaces vectors/metadata transactionally; failure rolls back to the previous collection. It does not retain a second vector version.

Migration **003** adds full-text search; **004** separates embedding collections and changes vector indexing. Existing OpenAI vectors are preserved, not converted to Ollama vectors. There is **no migration 005** for this release. Back up, test restoration, check free space and plan for table/index locks before applying migrations to a database with data. Never fix compatibility by editing metadata or marking a migration applied manually.

## Reproducible product evaluation

Use short fictional purchasing, incident, inventory and approval policies. Sign in, upload and wait for ready status; verify actual vectors, collection identity, hybrid retrieval, cited passages and source inspector. Include answerable, absent, related-but-insufficient, contradictory, multi-passage and injection cases. For DO, inspect the proposal, reject one and approve a separate request, then check the ticket and audit record. Cross-workspace/requester and transaction-failure tests are mandatory regardless of the model.

Three reproducible commands answer different questions:

```bash
# From backend, with the local profile active; run sequentially:
python -m app.evaluate_grounding
# Explicit model assessment of fixed passages, without retrieval/embedding evaluation:
python -m app.evaluate_grounding --live
# Full HTTP-handler/real-database/model pipeline on a NEW EMPTY dedicated DB:
# Set DATABASE_URL privately to a database ending in _local or _eval first.
python -m app.evaluate_local --live \
  --output evals/local-live-results.json \
  --credentials-file /tmp/mazmi-local-browser-credentials.json
```

The full evaluator requires development mode, demo disabled, both providers Ollama and an empty dedicated database. It refuses existing records **before migration**, preserves the resulting fictional database for inspection and never resets it. Re-running needs another new dedicated database. The optional credentials file must be new and outside Git; it is created with mode 0600 for later browser login. Do not publish, screenshot or paste it. The public JSON contains fixture metrics, not the password. A nonzero exit/result must remain visible rather than relabelling a partial run as passing.

The full corpus contains four fictional policies and eight questions, with tool/approval/audit and workspace checks in addition to retrieval. Its per-document Recall@6/MRR, known-source selection, abstentions and stage durations describe only that corpus and model configuration. Review the returned quotations manually: exact citation IDs do not prove applicability. The separate `python -m app.evaluate` SQL evaluator uses synthetic vectors; it is not the same measurement. Historical reports remain in `backend/evals`; [VALIDATION.md](VALIDATION.md) distinguishes offline policy guards, raw real-model smoke and full live pipeline evidence, retaining all known failures.

## Optional local voice

Faster-Whisper/Piper are independent of chat and are not required for this release. When resources allow, explicitly install `backend/requirements-voice.txt` into the existing virtualenv and prepare licensed models outside Git. Configure an absolute local CTranslate2 directory with `STT_MODEL_PATH`, and Piper `.onnx` plus adjacent `.onnx.json` with `PIPER_MODEL_PATH`. STT uses `local_files_only=True`; the application does not download weights by model name. Verify the voice license and optional `PIPER_EXECUTABLE` yourself.

Browser recording requires localhost or HTTPS, permission and a supported format. Limits remain 60 seconds and 10 MB. Denied permission or absent models must leave text chat usable. Real microphone/TTS remains unverified unless the dated report explicitly says otherwise. Compose does not include voice extras or model mounts; Docker Desktop was not started in this session. Never expose Ollama or PostgreSQL directly to the Internet.

References: [Ollama chat](https://docs.ollama.com/api/chat), [embeddings](https://docs.ollama.com/api/embed), [tools](https://docs.ollama.com/capabilities/tool-calling), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [EmbeddingGemma model card](https://huggingface.co/google/embeddinggemma-300m), [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper), [Piper](https://github.com/OHF-Voice/piper1-gpl).
