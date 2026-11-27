# Repository agent rules

Keep this table limited to recurring mistake classes and the check that enforces each one. Drop a rule once its mistake can no longer happen.

| Rule | Enforced by |
|---|---|
| `backend/docs/sat_graph.surql.gz` must stay compacted (no superseded versions, no nested `INSERT`, no >600 KB line, <=12 MB gz / <=40 MB raw, exact `EXPECTED_ROWS`). Run `python backend/scripts/bootstrap_sat_corpus.py --compact` after corpus exports. | `tests/backend/unit/test_repo_invariants.py::test_sat_snapshot_is_compact_valid_and_free_of_superseded_bloat` |
| Every `SurrealSATGraphStore.chat_*_snapshot` method must return `"chat_revision": revision` so `SATChatRetriever` uses zero-copy `SATRetriever(..., copy_snapshot=False, revision=...)`. | `tests/backend/unit/test_repo_invariants.py::test_surreal_chat_snapshots_always_tag_chat_revision` and `tests/backend/unit/test_sat_chat.py::test_sat_chat_retriever_uses_zero_copy_only_when_chat_revision_present` |
| SurrealDB Cloud HTTP `/import` and `/export` must authenticate with JWT `Bearer` (`_http_auth_header`) and keep `/import` parts well under Cloudflare's 100 MB cap (`DEFAULT_HTTP_IMPORT_MAX_BYTES = 512 KiB`). | `tests/backend/unit/test_bootstrap_sat_corpus.py::test_http_import_surql_chunks_payload_and_checks_errors` |
| Never pass `thinking={"type": "disabled"}` directly to Cohere callers; use `services.cohere_chat.default_thinking_option()`. | `tests/backend/unit/test_repo_invariants.py::test_no_raw_cohere_thinking_disabled_outside_cohere_chat` and `tests/backend/unit/test_cohere_chat.py` |
| `SATRetriever.search` must support non-`SearchPlan` plans (such as `DocumentaryPlan`) via `getattr(plan, "language", "es")`. | `tests/backend/unit/test_documentary.py` |
| Run offline verification (`pnpm test` or focused `pytest`) before committing. | `.github/workflows/ci.yml` |
