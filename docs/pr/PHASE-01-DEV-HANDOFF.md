# Phase 01 Dev Handoff

## Handoff Status

`READY FOR DEV` after PM authorizes implementation. This document authorizes only the tasks listed below.

## Phase

Phase 01 — Document Ingestion + Vector DB

## Task IDs

- TASK-01 — Environment and Dependency Baseline
- TASK-02 — Domain Contracts and Configuration
- TASK-03 — Manifest, File Discovery, and Parsers
- TASK-04 — Cleaning and Chunking
- TASK-05 — Embedding Candidate Benchmark
- TASK-06 — Qdrant Persistence and Vector Store Adapter
- TASK-07 — End-to-End Ingestion Orchestration
- TASK-08 — Phase 1 Quality, Evaluation, and Handoff Evidence

The authoritative task definitions and acceptance criteria are in `docs/phases/PHASE-01.md`.

## Required Implementation Areas

The exact filenames may be refined without changing module ownership. Expected areas:

```text
app/
├── core/                  # settings, typed errors, structured logging
├── domain/                # entities and Protocol/ABC contracts
└── rag/
    ├── ingestion/         # discovery, manifest, orchestration
    ├── parsing/           # PDF, DOCX, Markdown, TXT adapters
    ├── chunking/          # cleaning and chunk strategies
    ├── embedding/         # local embedding adapters/benchmarks
    └── vector_store/      # Qdrant adapter and collection lifecycle
scripts/                   # ingestion and benchmark commands
infra/                     # pinned Qdrant Docker Compose
data/samples/              # approved public/synthetic small fixtures
evaluation/datasets/       # Phase 1 reviewed mini retrieval set
evaluation/reports/        # benchmark report or reproducible generated output policy
tests/
├── unit/
├── integration/
└── acceptance/
```

Do not create API, Agent, prompt, tool-calling, CRM, frontend, or unrelated infrastructure modules in this Phase.

## Functional Requirements

1. Discover only supported files inside the configured data root.
2. Record manifest identity, checksum, version, parser/pipeline versions, status, and per-document errors.
3. Parse PDF, DOCX, Markdown, and TXT while preserving ordered source location.
4. Clean conservatively and produce deterministic structure-aware chunks.
5. Validate required metadata and deterministic IDs.
6. Compare two local multilingual embedding candidates on the same reviewed dataset.
7. Persist vectors and payload in Qdrant with mandatory filters and version isolation.
8. Support idempotent rerun and safe replacement of changed documents.
9. Provide a single documented ingestion command and structured run summary.
10. Provide unit, integration, golden, and acceptance tests without external LLM services.

## Technical Constraints

- Work on a task/feature branch created from `dev`; target `dev`, never `main`.
- Use an isolated environment; do not install into system Python.
- TASK-01 is a stop gate: report Python 3.14 incompatibility before installing another interpreter.
- Domain contracts cannot import Qdrant, parser, LangChain, or LangGraph SDK types.
- Qdrant image must be pinned; data persistence must use an explicit volume.
- Supported source data must be public or synthetic.
- No LLM, hosted embedding API, Agent, FastAPI, OCR, hybrid search, reranker, or arbitrary network fetch.
- No silent metadata inference, silent fallback, or partial-version activation.
- Every error path must return/record a stable typed error.
- Keep batch behavior deterministic for identical inputs and configuration.

## Dependencies and Recommended Order

```text
TASK-01
  -> TASK-02
      -> TASK-03 -> TASK-04 -> TASK-05
      -> TASK-06 (after TASK-05 contract/model decision)
          -> TASK-07
              -> TASK-08
```

TASK-03 and the non-model parts of TASK-06 may be developed in parallel after TASK-02, but shared interfaces must not diverge.

## Acceptance Criteria

Dev must map evidence to AC-P1-01 through AC-P1-16 in `PHASE-01.md`. Minimum handoff evidence includes:

- clean isolated setup succeeds;
- all four file types parse with expected source metadata;
- corrupt/path-escape tests fail safely;
- chunks are deterministic and preserve critical text;
- repeated ingestion creates no duplicates;
- changed/failed versions follow safe activation rules;
- both embedding candidates have comparable metrics/resource results;
- Qdrant survives restart and filters correctly;
- full automated checks pass;
- repository contains no secret/private data or out-of-scope implementation.

Missing evidence is a FAIL, not “not tested”.

## Quality Gates

- format check exit code 0;
- lint exit code 0;
- unit tests: zero failures/errors;
- integration tests: zero failures/errors;
- parser golden tests: zero failures/errors;
- end-to-end ingestion and idempotency tests pass;
- no committed secrets, private data, model weights, caches, or Qdrant storage;
- public interfaces typed; critical invariants documented;
- direct dependencies justified and locked;
- setup, benchmark, and run instructions reproduce from a clean environment;
- PR uses `docs/pr/PR_TEMPLATE.md` and contains AC-by-AC evidence.

## Forbidden Changes

Dev must not:

- add or call an LLM;
- implement question answering, citation generation, API endpoints, UI, Agent, tools, ReAct, memory, or CRM features;
- add Java, Kafka, Redis, Kubernetes, microservices, multi-agent, or unrelated services;
- enable OCR, hybrid search, sparse vectors, or reranking;
- create or publish a remote Git repository;
- push/commit directly to `main`;
- modify Scope, architecture, metadata contracts, or Acceptance Criteria without PM review;
- use real employer/customer material or reproduce private schemas/Skills;
- hard-code credentials or machine-specific absolute paths;
- delete prior active data before replacement verification;
- weaken or skip a failing test to claim completion.

## Stop and Escalate Conditions

Stop the affected Task and report to PM when:

- Python 3.14 cannot support an approved dependency;
- the two embedding candidates cannot run within VM memory;
- PDF/DOCX source location cannot satisfy the defined contract;
- Qdrant schema requires a breaking metadata change;
- a requested behavior requires an Out-of-Scope component;
- an Acceptance Criterion is ambiguous, contradictory, or untestable;
- test data licensing/provenance is unclear.

The report must include exact error/evidence, affected Task/AC, options, and recommended decision. Do not select a scope-expanding workaround independently.

## Definition of Dev Complete

Dev work is complete only when TASK-01–08 outputs exist, all Quality Gates pass, the PR evidence package is complete, and status can legitimately move to `READY FOR QA`. Dev completion is not Phase acceptance.

