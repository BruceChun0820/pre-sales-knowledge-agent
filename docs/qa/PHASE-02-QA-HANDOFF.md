# Phase 02 QA Handoff

## Purpose

Independently verify that Phase 2 provides a deterministic direct RAG API with bounded evidence, valid citations, explicit refusal, safe failure behavior, and no Agent or Phase 3 scope. QA uses `docs/phases/PHASE-02.md` as authoritative and does not redefine requirements.

## Entry Conditions

Return `NOT READY FOR QA` unless Dev provides:

- reachable remote PR URL(s) targeting `dev` and exact tested head SHA(s);
- completed Task IDs and task handoff files;
- accepted Phase 1 index/corpus identity and Phase 2 base SHA;
- all quality-gate commands reported PASS;
- retrieval and answer/citation baseline reports with reproduction commands;
- AC-P2-01 through AC-P2-17 evidence mapping;
- documented environment, dependencies, Qdrant collection isolation, and known limitations.

QA must test the remote PR head, not a local-only commit.

## Test Environment

- Dedicated QA worktree based on the integration PR head.
- Isolated project Python environment and an isolated Qdrant test collection.
- Approved public/synthetic corpus and frozen evaluation dataset.
- Deterministic fake LLM for required tests; no real API key or network required.
- Record commit, Python/lock versions, embedding model/revision, collection/index identity, corpus/config identity, and test time.

## Acceptance Matrix

| QA ID | AC | Procedure | PASS condition |
|---|---|---|---|
| QA-P2-01 | AC-P2-01 | Inspect contract PR and import domain contracts with FastAPI/Qdrant/LLM SDK unavailable. | PR targets `dev`; imports pass; no framework SDK type leaks. |
| QA-P2-02 | AC-P2-02 | Submit empty query, invalid K, malformed enum, and unauthorized filter/scope overrides. | Every request fails with the documented stable error; no retrieval/generation occurs. |
| QA-P2-03 | AC-P2-03 | Search positive/negative filter cases and reconcile payloads. | Rank/score/provenance fields exist and filter violations equal 0. |
| QA-P2-04 | AC-P2-04 | Repeat identical query/search/context runs. | Normalized query, hit order within score tolerance, context order, and source IDs are deterministic. |
| QA-P2-05 | AC-P2-05 | Supply duplicate/adjacent/oversized hits. | Deduplication/budget behavior matches policy; overflow is typed and never silently exceeds budget. |
| QA-P2-06 | AC-P2-06 | Run empty and below-threshold evidence with an invocation-counting fake. | Status is `insufficient_evidence` and LLM invocation count is 0. |
| QA-P2-07 | AC-P2-07 | Run answerable fake cases and reconcile claims/citations to supplied evidence. | Every factual claim has at least one valid supplied citation. |
| QA-P2-08 | AC-P2-08 | Inject unknown source ID, unsupported quote, and uncited factual claim. | None can return `answered`; stable validation reasons are present. |
| QA-P2-09 | AC-P2-09 | Run fake-provider success/malformed/timeout/failure tests twice offline. | Results are deterministic; no credential/network is required. |
| QA-P2-10 | AC-P2-10 | Inspect config and capture logs/errors using sentinel secret/source text. | Credentials are environment-only; sentinel secret/body is absent from logs/errors. |
| QA-P2-11 | AC-P2-11 | Exercise health/search/query success and invalid-input paths; validate schemas. | All endpoints, statuses, fields, and error mappings match published contracts. |
| QA-P2-12 | AC-P2-12 | Stop/unavailable Qdrant and inject LLM failures. | Response is failed/documented non-2xx and contains no factual answer. |
| QA-P2-13 | AC-P2-13 | Inspect responses/traces for success/refusal/failure. | Request ID and latency always exist; supplied provider usage is preserved. |
| QA-P2-14 | AC-P2-14 | Re-run both baseline commands from clean recorded inputs. | Reports reproduce within documented tolerance and record all required identities. |
| QA-P2-15 | AC-P2-15 | Run `./init.sh` and documented focused/acceptance checks. | Every command exits 0; failures/errors equal 0. |
| QA-P2-16 | AC-P2-16 | Inspect dependency tree, imports, routes, changed files, and runtime services. | No Agent/LangGraph/rewrite/reranker/hybrid/UI/CRM/private data or unrelated service exists. |
| QA-P2-17 | AC-P2-17 | Compare PR metadata, handoffs, checkout, and tested commits. | PRs are reachable, target `dev`, head SHAs match tested commits, and Dev did not self-merge. |

## Required Negative Tests

- Whitespace-only and over-limit query.
- Filter with no matches and attempted mandatory-scope override.
- Embedding dimension/model mismatch and Qdrant unavailable.
- Duplicate hits, insufficient context, oversized indivisible evidence.
- LLM malformed JSON/schema, timeout, authentication/rate-limit/unavailable errors.
- Unknown citation ID, valid ID with invalid quote, claim with no citation.
- Log redaction with sentinel API key and sentinel source paragraph.
- Health endpoint when process is live but dependency is not ready.

## QA Rules

- Do not change production code, expected behavior, thresholds, or ACs.
- Do not use implementation output as the expected answer without independent evidence labels.
- Do not use real employer/customer documents or production credentials.
- Do not delete unrelated Qdrant collections/data or install unapproved services.
- Do not merge PRs or accept a local-only commit.
- If an AC is contradictory or untestable, report `REQUIREMENT ISSUE` to PM.

## Evidence and Result

For every QA ID record PASS/FAIL/BLOCKED, command/procedure, output/count/hash, defect ID, and re-test commit. Final recommendation is:

- `QA PASSED` only when QA-P2-01 through QA-P2-17 all PASS;
- `QA FAILED` when any criterion fails;
- `BLOCKED` only for an evidenced external condition;
- `REQUIREMENT ISSUE` when PM must repair the requirement.

QA approval does not promote `dev` to `main`; PM performs final scope/architecture review and phase acceptance.
