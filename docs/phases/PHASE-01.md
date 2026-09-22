# Phase 01 — Document Ingestion + Vector DB

## Status

`PLANNED`. Dev/QA handoffs are prepared; business implementation requires explicit user authorization and has not started.

## Objective

Build a deterministic, traceable ingestion foundation that converts approved public or synthetic PDF, DOCX, Markdown, and TXT documents into validated chunks with source metadata and persists their embeddings in Qdrant.

This phase answers one question: **Can the project reliably build and rebuild a searchable evidence index without losing source provenance?**

It does not answer user questions or implement an Agent.

## Scope

- Confirm an isolated, reproducible Python development environment.
- Establish the Phase 1 application/domain module skeleton and typed contracts.
- Discover allowed files and maintain document manifest/checksum/version/status.
- Parse PDF, DOCX, Markdown, and TXT into a common block representation.
- Apply conservative cleaning and structure-aware, token-bounded chunking.
- Validate document/chunk metadata and produce deterministic identifiers.
- Benchmark two embedding candidates on the CPU-only Ubuntu VM.
- Run Qdrant locally with persistent storage through Docker Compose.
- Upsert, validate, filter, and idempotently rebuild a versioned collection.
- Provide an ingestion CLI/script with structured summary and per-document errors.
- Add unit, integration, parser golden, and small retrieval smoke tests.
- Produce a Phase 1 benchmark/decision report.

## Out of Scope

- LLM calls, answer generation, prompts, citations in generated answers.
- FastAPI endpoints or an interactive UI.
- LangGraph, Tool Calling, ReAct, Planning, Reflection, memory, or Multi-Agent.
- Query Rewrite, cross-encoder reranking, hybrid retrieval, or sparse vectors.
- OCR and guaranteed extraction of scanned PDFs.
- Production authentication, multi-tenancy, SSO, ACL, or cloud deployment.
- Real company/customer documents, private MCP, CRM APIs, or private Skills.
- Java, Kafka, Redis, Kubernetes, microservices, or remote Git hosting.
- Automatic metadata invention by an LLM.

Any request requiring these items must be returned to PM as a scope change.

## Architecture Impact

Phase 1 creates the lowest-level evidence pipeline inside the existing modular monolith:

```text
Approved local files
  -> Manifest / Loader
  -> Parser Registry
  -> ParsedBlock
  -> Cleaner
  -> ChunkingStrategy
  -> Metadata validation
  -> EmbeddingProvider
  -> VectorStore (Qdrant)
```

New boundaries:

- `app/domain`: framework-neutral entities and Protocol/ABC interfaces.
- `app/rag/ingestion`: file discovery, manifest, orchestration.
- `app/rag/parsing`: format-specific adapters.
- `app/rag/chunking`: cleaning and chunking strategies.
- `app/rag/embedding`: model adapters and benchmark support.
- `app/rag/vector_store`: Qdrant adapter and collection lifecycle.
- `app/core`: configuration, errors, logging.
- `scripts`: explicit ingestion and benchmark entry points.

Qdrant is the only service added. It stores derived chunks/vectors and metadata; original documents remain in the approved data directory. No module may expose Qdrant SDK objects as public domain contracts.

## Technical Decisions

### TD-01 — Python runtime compatibility

1. **Problem:** Ubuntu provides Python 3.14.4, while ML dependencies may not all publish compatible native wheels.
2. **Options:** use system 3.14 directly; manage project Python 3.13; use Conda/container-only development.
3. **Decision:** first run an isolated Python 3.14 compatibility spike. If all approved core dependencies install and smoke tests pass, keep 3.14. Otherwise stop and request PM approval to use a project-managed Python 3.13. Never modify system Python packages.
4. **Reason:** reuse the existing environment when safe while protecting reproducibility and system integrity.
5. **Trade-off:** the spike adds one task and may delay implementation, but avoids discovering binary incompatibility after code is coupled to the environment.

### TD-02 — Qdrant as vector store

1. **Problem:** Phase 1 needs persistent vectors, payload filtering, deterministic rebuilds, and a future hybrid path.
2. **Options:** Qdrant; Chroma; FAISS plus custom metadata/persistence.
3. **Decision:** use Qdrant in Docker Compose with a named local volume and pinned image version.
4. **Reason:** payload filters and persistent service boundaries match the MVP requirements without building custom storage.
5. **Trade-off:** one container must be managed and integration-tested; it is heavier than an in-process FAISS index.

### TD-03 — Parser stack

1. **Problem:** supported formats require traceable source locations with minimal dependencies.
2. **Options:** PyMuPDF + python-docx + small text parsers; `unstructured`; one LLM/document API.
3. **Decision:** use PyMuPDF for PDF, python-docx for DOCX, and explicit Markdown/TXT parsers.
4. **Reason:** behavior is inspectable, source location can be preserved, and the dependency surface is limited.
5. **Trade-off:** complex layouts, tables, and scanned documents require explicit handling or later extensions.

### TD-04 — Embedding selection by experiment

1. **Problem:** the corpus is expected to contain Chinese and English text, while the VM has no GPU.
2. **Options:** lightweight multilingual SentenceTransformer; BGE-M3 dense mode; hosted embedding API.
3. **Decision:** benchmark one lightweight multilingual CPU baseline and BGE-M3 dense mode on the same mini dataset. Select only after quality, latency, throughput, memory, and index-size evidence. Hosted embedding is excluded unless PM later approves data transfer.
4. **Reason:** no single model is an honest default before corpus-language and CPU measurements exist.
5. **Trade-off:** two local models require download/storage during Dev; BGE-M3 may be rejected for latency even if quality is higher.

### TD-05 — No Agent or LLM in Phase 1

1. **Problem:** orchestration frameworks could obscure ingestion defects and expand scope.
2. **Options:** build ingestion through LangChain/LangGraph; implement explicit typed services first.
3. **Decision:** use plain Python services and adapters; no LangGraph, agent loop, or LLM call.
4. **Reason:** parsing, chunking, provenance, and persistence must be independently testable.
5. **Trade-off:** some integration wrappers may be added later, but the domain contracts remain reusable.

## Tasks

### TASK-01 — Environment and Dependency Baseline

**Goal**

Prove a reproducible isolated Python environment before feature implementation.

**Input**

- Ubuntu Python 3.14.4 and Docker/Compose already installed.
- Phase 1 approved dependency categories from `TECH_STACK.md`.

**Expected Output**

- Updated `pyproject.toml` with only Phase 1 dependencies and separated dev dependencies.
- Lockfile produced by the approved dependency manager.
- Environment setup instructions.
- Compatibility report containing install/import and minimal smoke-test results.

**Technical Constraints**

- Do not install packages into `/usr/bin/python3` or the system site-packages.
- Do not add FastAPI, LangGraph, LLM SDK, Ragas, reranker, or unrelated dependencies.
- Pin direct dependencies; commit lockfile; do not pin secrets or machine-specific paths.
- If Python 3.14 compatibility fails, stop and report exact errors before installing another interpreter.

**Dependencies**

- None.

**Acceptance Criteria**

- `python -c` imports each approved Phase 1 direct dependency in the isolated environment with exit code 0.
- A lockfile is present and a clean environment can reproduce the same dependency graph.
- The system Python package directory is unchanged by the project setup.
- Compatibility report names Python, package, Docker, and Qdrant image versions.

### TASK-02 — Domain Contracts and Configuration

**Goal**

Define framework-neutral data contracts before implementing adapters.

**Input**

- Metadata schema and architecture documents.
- Output of TASK-01.

**Expected Output**

- Typed models for `DocumentRecord`, `ParsedBlock`, `SourceLocation`, `Chunk`, `EmbeddingBatch`, and ingestion result/error.
- Protocol/ABC boundaries for parser, chunker, embedding provider, and vector store.
- Environment-based settings with validated defaults.
- Unit tests for required fields, enums, invalid values, and serialization.

**Technical Constraints**

- Domain models must not import Qdrant, PyMuPDF, python-docx, LangChain, or LangGraph types.
- `tenant_id` and `active` must be system-controlled fields.
- Unknown metadata remains null/explicit unknown; it is not guessed.
- Public interfaces require type annotations and docstrings explaining invariants.

**Dependencies**

- TASK-01.

**Acceptance Criteria**

- Invalid `document_type`, empty `document_id`, invalid version, or missing source identity raises a typed validation error.
- Every `Chunk` requires a stable source location and pipeline version fields.
- Tests prove domain modules can import without Qdrant or parser SDK imports.
- Settings load from environment variables and do not require a real secret for unit tests.

### TASK-03 — Manifest, File Discovery, and Parsers

**Goal**

Safely discover approved files and parse each supported format into ordered blocks with provenance.

**Input**

- At least one public/synthetic PDF, DOCX, Markdown, and TXT fixture.
- Corrupt and unsupported-file fixtures.
- Domain contracts from TASK-02.

**Expected Output**

- Allowed-root file discovery and extension/size/path validation.
- Manifest with checksum, version, status, parser name/version, timestamps, and error details.
- PDF/DOCX/Markdown/TXT parser adapters.
- Golden parser fixtures and tests.

**Technical Constraints**

- Reject path traversal and symlink escape from configured data root.
- Preserve page for PDF; heading/paragraph/table order for DOCX; heading/line location for Markdown/TXT.
- One corrupt document must not terminate the batch.
- Do not OCR; mark image-only/insufficient-text documents as `needs_ocr` or typed unsupported state.

**Dependencies**

- TASK-01, TASK-02.

**Acceptance Criteria**

- Each supported fixture produces at least one ordered `ParsedBlock` and the expected source locator.
- A known PDF sentence maps to its expected page number.
- A known DOCX heading and following paragraph remain in order.
- Unsupported and corrupt files produce typed per-document failures while valid files in the same batch still parse.
- Re-reading an unchanged file produces the same checksum and document version.
- Files outside the allowed root are rejected.

### TASK-04 — Cleaning and Chunking

**Goal**

Produce deterministic, semantically bounded chunks without losing critical source information.

**Input**

- Parsed blocks from TASK-03.
- Chunk experiment configurations from `RAG_DESIGN.md`.

**Expected Output**

- Conservative text cleaner with explicit version.
- Structure-aware, token-bounded chunking strategy.
- Deterministic chunk IDs/checksums and source-range propagation.
- Tests for headings, long paragraphs, repeated headers, tables/lists, Chinese/English text, and overlap.

**Technical Constraints**

- Do not use an LLM to clean or rewrite source text.
- Preserve numbers, model names, percentages, negation, and limitation terms.
- Do not cross top-level sections unless configuration explicitly permits it.
- Overlap applies only where a long block is split and must use sentence/paragraph boundaries when possible.

**Dependencies**

- TASK-02, TASK-03.

**Acceptance Criteria**

- Two runs with identical input/config produce identical ordered chunk IDs and text checksums.
- Every chunk retains `document_id`, version, source locator, section path, chunk index, cleaner/chunker version.
- Configured maximum token size is not exceeded except for an explicitly reported indivisible token case.
- Golden tests prove critical numbers and negation terms survive cleaning.
- No chunk has empty text after normalization.

### TASK-05 — Embedding Candidate Benchmark

**Goal**

Select a Phase 1 embedding model using measured bilingual retrieval quality and CPU resource cost.

**Input**

- Stable chunks from TASK-04.
- A reviewed mini evaluation set with at least 10 queries and expected document/chunk relevance.
- Two candidates: one lightweight multilingual model and BGE-M3 dense mode.

**Expected Output**

- Embedding provider adapter with model/revision/dimension/normalization metadata.
- Reproducible benchmark script/config.
- Report with Hit Rate@5, Recall@10, indexing throughput, query P50/P95, peak RSS, vector dimension, and estimated index size.
- Technical decision: selected model or explicit request for PM decision if trade-off is unresolved.

**Technical Constraints**

- CPU only; no hosted embedding API.
- Same corpus, queries, chunking, and relevance labels for both candidates.
- Record model revision and tokenizer/max-length behavior.
- Do not select solely by one quality metric or solely by speed.

**Dependencies**

- TASK-01, TASK-04.

**Acceptance Criteria**

- Both candidates process the same non-empty chunk set or the report contains a reproducible failure.
- Metrics and resource measurements are saved with configuration and model revisions.
- Re-running the selected configuration preserves vector dimensions and produces retrieval metrics within documented deterministic tolerance.
- Selected model has a written Problem/Options/Decision/Reason/Trade-off record.

### TASK-06 — Qdrant Persistence and Vector Store Adapter

**Goal**

Persist versioned chunk embeddings and metadata behind a domain vector-store interface.

**Input**

- Chunk and embedding contracts.
- Selected/candidate embedding output.
- Qdrant Docker image with an explicit version.

**Expected Output**

- `infra/docker-compose.yml` with Qdrant persistent named volume and health check.
- Qdrant adapter for collection creation, batch upsert, search, filter, count, and version activation.
- Payload indexes for fields used by Phase 1 filters.
- Integration tests for persistence, filters, ID stability, and model/dimension mismatch.

**Technical Constraints**

- No unpinned `latest` image.
- No credentials committed; local unauthenticated access must bind only as appropriate for the development environment.
- A collection cannot mix embedding dimensions/models.
- Application interfaces return domain objects, not Qdrant SDK objects.

**Dependencies**

- TASK-02, TASK-05.

**Acceptance Criteria**

- Qdrant health check reaches healthy state through Docker Compose.
- Inserted points remain available after container restart using the configured volume.
- Filters on `tenant_id`, `active`, `industry`, `document_type`, and `products` return no out-of-scope points.
- Re-upserting an identical chunk ID does not increase the point count.
- A vector with the wrong dimension is rejected with a typed error.
- Integration tests can create and remove only their isolated test collection without deleting unrelated data.

### TASK-07 — End-to-End Ingestion Orchestration

**Goal**

Provide one explicit command that processes an approved corpus and safely activates a verified index version.

**Input**

- TASK-03 through TASK-06 components.
- Sample corpus and metadata manifest.

**Expected Output**

- Ingestion application service and CLI/script.
- Structured run summary with discovered/parsed/chunked/embedded/upserted/skipped/failed counts.
- Idempotent rerun and changed-document version behavior.
- Staged write, verification, and active-version switch behavior.
- End-to-end integration tests.

**Technical Constraints**

- Do not activate a partially written or failed document version.
- Do not delete the prior active version before the new version verifies successfully.
- Batch failures are isolated per document and reflected in exit status/summary.
- No LLM, API server, Agent, or background queue.

**Dependencies**

- TASK-03, TASK-04, TASK-05, TASK-06.

**Acceptance Criteria**

- The approved sample corpus imports through one documented command.
- Summary counts equal manifest, chunk, and Qdrant counts for successful documents.
- A second unchanged run creates zero duplicate active chunks and reports documents as skipped/unchanged.
- Changing one fixture creates a new document version while the failed-new-version test leaves the previous version active.
- One corrupt fixture is reported as failed and valid fixtures complete in the same run.
- All active Qdrant points map to an existing manifest document/version and source locator.

### TASK-08 — Phase 1 Quality, Evaluation, and Handoff Evidence

**Goal**

Make the Phase independently reproducible and ready for QA.

**Input**

- All Phase 1 implementation and tests.
- Phase acceptance criteria and QA handoff.

**Expected Output**

- Unit, integration, and acceptance test suites.
- Updated setup/ingestion documentation and architecture notes.
- Benchmark and retrieval smoke-test report.
- PR evidence mapped to every Phase AC.
- No-secret/private-data scan evidence.

**Technical Constraints**

- Tests cannot require an external LLM or hosted service.
- Test data must be public or synthetic and small enough for the repository policy.
- Quality commands must return non-zero on failure.
- Do not weaken criteria to make the Phase pass.

**Dependencies**

- TASK-01 through TASK-07.

**Acceptance Criteria**

- All Quality Gates below pass in a clean checkout/isolated environment.
- QA can reproduce environment setup, Qdrant startup, ingestion, restart, and idempotency tests from documentation.
- Every Phase AC has a test ID, command, or recorded manual evidence.
- No unresolved Blocker/Major defect remains when status changes to `READY FOR QA`.

## Phase Acceptance Criteria

| ID | PASS condition |
|---|---|
| AC-P1-01 | A clean, isolated environment installs from committed project metadata/lock and all Phase 1 imports exit 0. |
| AC-P1-02 | One approved fixture for each PDF, DOCX, Markdown, and TXT parses into ordered blocks with expected provenance. |
| AC-P1-03 | Corrupt/unsupported/path-escape fixtures produce typed failures and do not stop valid documents in the same run. |
| AC-P1-04 | Every chunk has non-empty text, deterministic ID/checksum, document/version, source locator, chunk index, and pipeline versions. |
| AC-P1-05 | Golden tests confirm configured numbers, product/model names, and negation/limitation terms are preserved. |
| AC-P1-06 | Two identical ingestion runs produce no duplicate active chunks and the same active point count. |
| AC-P1-07 | A document change creates a new version; a failed replacement does not deactivate the last verified version. |
| AC-P1-08 | Embedding report compares two candidates on the same ≥10 reviewed queries and includes required quality/resource metrics. |
| AC-P1-09 | One embedding model is selected through a documented decision, or Phase is marked BLOCKED pending PM decision. |
| AC-P1-10 | Qdrant data survives a container restart and remains queryable. |
| AC-P1-11 | Mandatory payload filters return zero tenant/active/industry/document-type/product violations in integration tests. |
| AC-P1-12 | A wrong vector dimension/model configuration fails explicitly and cannot silently enter the active collection. |
| AC-P1-13 | End-to-end ingestion summary counts reconcile with manifest and Qdrant counts for successful documents. |
| AC-P1-14 | `pytest` completes with zero failed/error tests; lint and format checks exit 0. |
| AC-P1-15 | Repository scan finds no API keys, passwords, real company/customer data, model binaries, or Qdrant runtime storage. |
| AC-P1-16 | No LLM call, FastAPI endpoint, LangGraph/Agent code, OCR, hybrid retrieval, reranker, or out-of-scope infrastructure is introduced. |
| AC-P1-17 | Dev submits a reachable remote PR in the approved repository with source task branch, target `dev`, matching tested head SHA, Task/AC evidence, and no self-merge. |

Any failed criterion means the Phase is not QA PASSED. AC-P1-09 may intentionally produce `BLOCKED`, not a silent fallback.

## Quality Gates

Before `READY FOR QA`, Dev must provide commands and passing evidence for:

- format check passes for all Python files;
- lint passes with no ignored new violations;
- all unit tests pass;
- all Qdrant integration tests pass from an isolated test collection;
- parser golden tests pass;
- end-to-end ingestion/idempotency tests pass;
- public interfaces are typed and critical invariants have docstrings;
- no circular dependency from domain modules to framework/SDK adapters;
- no obvious duplicated parser/chunking orchestration logic;
- no committed `.env`, key, password, private data, model weights, cache, or Qdrant storage;
- direct dependencies are justified and locked;
- Docker image is pinned and persistence is tested;
- README/setup/decision/benchmark documentation matches implementation;
- PR contains an AC-by-AC evidence table;
- remote PR URL is reachable, targets `dev`, and its head SHA matches the tested commit;
- remote CI/check results are included when the repository provides them;
- no Blocker/Major finding remains open.

## Required Evidence Package

Dev hands QA:

- commit/PR reference and Task IDs;
- clean setup commands;
- dependency compatibility report;
- parser fixture provenance;
- automated check output summaries;
- Qdrant restart/persistence evidence;
- first-run and second-run ingestion summaries;
- embedding comparison report;
- secret/private-data scan result;
- known limitations and any PM-approved deviations.

## Exit Decision

Only PM may mark Phase 1 `ACCEPTED`, after QA marks every Must criterion PASS. Only then may the tested `dev` state be merged to `main`.
