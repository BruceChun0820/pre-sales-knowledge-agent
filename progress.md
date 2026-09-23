# Project Progress

## Current State

- Last Updated: 2026-09-23
- Current Objective: preserve the accepted Phase 1 baseline on `main`, then wait for explicit Phase 2 activation.
- Accepted phase: Phase 1 — Document Ingestion + Vector DB
- Next planned phase: Phase 2 — Basic RAG Q&A + Citation
- Phase 1 QA: `docs/qa/QA-001.md`, AC-P1-01 through AC-P1-17 PASS

## Completed

- Phase 0 documentation and architecture baseline.
- Phase 1 TASK-01 through TASK-08, including persistent Qdrant, safe version activation, ingestion CLI, and CPU embedding selection.
- Metadata-only update defect fixed and independently re-tested against live Qdrant.
- Phase 1 implementation PR #2 merged to `dev`; final QA evidence PR #3 merged to `dev`.
- Phase 2 plan, ownership, prompts, worktree boundaries, QA matrix, and Harness artifacts completed.

## Phase 2 Gate

Phase 1 prerequisites are satisfied. Phase 2 is `READY FOR EXPLICIT ACTIVATION`, not automatically active. PM/user must explicitly start it and provide the accepted `main` SHA.

At activation:

1. Create Dev1 and Dev2 task branches/worktrees from the same accepted `main` commit.
2. Dev1 performs the contract gate; Dev2 remains read-only.
3. After the contract PR merges to `dev`, both workers sync the exact gate commit before production edits.
4. Each worker submits a separate remote PR to `dev`; final Phase promotion remains `dev -> main` after QA and PM acceptance.

## Decisions

- Use a coordinator pattern; workers do not spawn workers.
- The start-of-Phase source of truth is the last accepted `main` commit.
- `dev` is the within-Phase integration target.
- Dev1 owns retrieval/evidence; Dev2 owns generation/API; QA remains independent.
- Direct RAG precedes Agent/LangGraph, and dense retrieval precedes rewrite/rerank/hybrid experiments.

## Blockers

- No technical blocker is open.
- Phase 2 work is intentionally paused until explicit activation.

## Files and Evidence

- Phase 1 final QA: `docs/qa/QA-001.md`.
- Phase 2 specification: `docs/phases/PHASE-02.md`.
- Dev handoffs/prompts: `docs/pr/PHASE-02-DEV1-HANDOFF.md`, `docs/pr/PHASE-02-DEV2-HANDOFF.md`, and matching prompt files.
- QA plan: `docs/qa/PHASE-02-QA-HANDOFF.md`.

## Next Session

Confirm `main` is the accepted Phase 1 promotion commit. Do not create or dispatch Phase 2 worktrees until PM/user explicitly starts Phase 2.

## Recommended Next Step

Wait for Phase 2 activation. At activation, record the exact `main` SHA, create isolated Dev1/Dev2 worktrees, and execute the contract-first dispatch protocol.
