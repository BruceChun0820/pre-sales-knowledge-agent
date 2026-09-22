# Phase 01 QA Handoff

## Purpose

Verify that Phase 01 builds a deterministic, traceable, persistent document index and does not introduce Phase 2+ capabilities. QA uses `docs/phases/PHASE-01.md` as the authoritative requirement source and must not redefine it.

## Entry Conditions

QA begins only when Dev provides:

- PR/commit reference targeting `dev`;
- reachable remote PR URL in the approved repository;
- source task branch, target branch `dev`, and current PR head SHA;
- remote CI/check status, if configured;
- implemented Task IDs;
- clean environment/setup instructions;
- all automated Quality Gates reported PASS;
- fixture provenance and corpus manifest;
- embedding benchmark report;
- first/second ingestion summaries;
- AC-P1-01 through AC-P1-16 evidence table;
- known limitations and PM-approved deviations.

If an entry item is missing, return status `NOT READY FOR QA`.

## Test Environment

- Remote Ubuntu project checkout on the Dev PR/branch.
- Isolated project Python environment.
- Docker and Docker Compose available.
- Qdrant test collection/volume that does not contain unrelated data.
- Only committed public/synthetic fixtures.
- No LLM/API credentials required.

QA must record Python, dependency lock, Docker, Qdrant image, commit, corpus version, and test time.

## Acceptance Test Matrix

| QA ID | AC | Procedure | PASS condition |
|---|---|---|---|
| QA-P1-01 | AC-P1-01 | Create a clean isolated environment from project metadata/lock and run import smoke tests. | Install and imports exit 0 with documented versions; system site-packages are not used for project installs. |
| QA-P1-02 | AC-P1-02 | Parse one approved PDF, DOCX, Markdown, and TXT golden fixture. | All formats produce ordered non-empty blocks and match expected page/section/line locators. |
| QA-P1-03 | AC-P1-03 | Run a batch containing valid, corrupt, unsupported, traversal, and symlink-escape inputs. | Invalid inputs have typed failures; no outside file is read; valid inputs still complete. |
| QA-P1-04 | AC-P1-04 | Chunk the same parsed corpus twice with identical config. | Ordered chunk IDs, checksums, text, and required metadata are identical. |
| QA-P1-05 | AC-P1-05 | Compare golden source and cleaned/chunked output for marked numbers, model names, negation, and limitations. | Every marked critical token/phrase is preserved; no semantic reversal occurs. |
| QA-P1-06 | AC-P1-06 | Run ingestion twice without modifying inputs and compare Qdrant counts/IDs. | Second run adds zero duplicate active points and active counts/IDs remain stable. |
| QA-P1-07 | AC-P1-07 | Change one fixture, ingest successfully, then simulate a failed replacement. | Successful change creates/activates a new version; failed replacement leaves last verified version active. |
| QA-P1-08 | AC-P1-08 | Inspect and rerun the embedding benchmark on the reviewed ≥10-query set. | Both candidates use identical data; required quality/resource metrics and model revisions are present. |
| QA-P1-09 | AC-P1-09 | Inspect technical decision and selected config. | A single model is selected with Problem/Options/Decision/Reason/Trade-off, or Phase is explicitly BLOCKED. |
| QA-P1-10 | AC-P1-10 | Ingest data, record IDs/count, restart Qdrant container, query again. | Same active points remain available after restart. |
| QA-P1-11 | AC-P1-11 | Execute filters for tenant, active, industry, document type, and product, including negative controls. | Every returned point satisfies every applied filter; violation count is 0. |
| QA-P1-12 | AC-P1-12 | Attempt an upsert/query with wrong vector dimension/model config. | Operation fails with the documented typed error and active collection remains unchanged. |
| QA-P1-13 | AC-P1-13 | Reconcile CLI summary with manifest records, generated chunks, and Qdrant point counts. | All successful/skipped/failed counts reconcile exactly; mismatches are 0. |
| QA-P1-14 | AC-P1-14 | Run documented format, lint, unit, integration, golden, and acceptance commands. | Every command exits 0 and test failures/errors equal 0. |
| QA-P1-15 | AC-P1-15 | Scan tracked files for secrets/private data and prohibited artifacts. | No key/password/private data/model binary/cache/Qdrant storage is tracked. |
| QA-P1-16 | AC-P1-16 | Inspect dependency tree and changed files for out-of-scope components. | No LLM/FastAPI/LangGraph/Agent/OCR/hybrid/reranker/unapproved infrastructure is introduced. |
| QA-P1-17 | AC-P1-17 | Open the remote PR and compare its source/target/head metadata with the Dev handoff and checkout. | PR is reachable, targets `dev`, source branch is the task branch, head SHA matches the tested commit, and Dev has not merged it. |

## Additional Negative Tests

- Empty document and whitespace-only document.
- Duplicate filenames in different allowed subdirectories.
- Same content with different filename and metadata.
- Missing required metadata and invalid enum.
- Mixed Chinese/English paragraph and long unbroken token.
- Document larger than configured limit.
- Qdrant unavailable during upsert.
- Embedding provider returns wrong batch length or non-finite vector.
- Interrupted/staged ingestion before activation.

These tests must produce defined errors and must not corrupt the last active index.

## Quality Gate Verification

QA verifies, rather than assumes, the Dev evidence:

- reproduce format/lint/test commands;
- inspect test isolation and ensure integration tests do not delete unrelated collections;
- verify domain modules do not import Qdrant/parser/framework SDKs;
- inspect public types/docstrings and error codes;
- confirm lockfile and pinned Qdrant image;
- confirm documentation matches actual commands;
- verify `.gitignore` and tracked-file list;
- confirm `main` was not used for feature development.
- confirm QA is testing the remote PR head, not an unpushed local commit.

## Evidence Required From QA

For each QA ID record:

- PASS / FAIL / BLOCKED;
- command or procedure;
- relevant output/count/hash;
- defect ID when failed;
- re-test result and commit when fixed.

The final result must include totals and an explicit recommendation:

- `QA PASSED` only if QA-P1-01 through QA-P1-16 all PASS;
- `QA FAILED` if any criterion FAILS;
- `BLOCKED` only for an external condition with evidence;
- `REQUIREMENT ISSUE` when the criterion itself is contradictory or untestable.

## Defect Handling

QA does not change production code or Acceptance Criteria. A finding must identify the Task and AC, reproduce the issue, and show expected vs actual behavior.

If the requirement is defective, QA reports it to PM. PM updates the authoritative Phase document and increments/reviews the test expectation before QA re-runs it.

## Forbidden QA Actions

- Do not redefine expected behavior based on the implementation.
- Do not mark a missing test as PASS based on manual impression.
- Do not use real company/customer documents or credentials.
- Do not install unapproved services to make tests pass.
- Do not merge the PR or bypass PM acceptance.
- Do not accept a local-only commit or a PR targeting `main` as a Phase 1 Dev handoff.
- Do not test against or delete unrelated Qdrant data.

## Phase Exit Recommendation

After QA-P1-01 through QA-P1-17 pass, QA submits the evidence report to PM. QA approval does not merge `dev` to `main`; PM performs the final scope/architecture review and accepts the Phase.
