# Agent Operating Guide

This repository uses a coordinator-and-workers harness. Requirements and architecture are maintained by PM; Dev implements approved tasks; QA verifies the published acceptance criteria.

## Startup Workflow

Before writing code:

1. Confirm the repository, worktree, branch, and clean/dirty state with `pwd`, `git status`, `git branch --show-current`, and `git log --oneline -5`.
2. Read this file, `feature_list.json`, `progress.md`, the active `docs/phases/PHASE-XX.md`, and your Dev/QA handoff.
3. Run `./init.sh`. If the baseline fails for reasons unrelated to your task, stop and report the exact failure.
4. Confirm your Task ID, owned paths, dependencies, acceptance criteria, forbidden changes, and PR target.

## Roles and Authority

- **PM/coordinator:** owns scope, architecture, public contracts, task assignment, shared trackers, integration order, and phase acceptance.
- **Dev worker:** implements only assigned Task IDs. A worker must not create or delegate to another worker.
- **QA worker:** verifies requirements independently and must not change production code or redefine acceptance criteria.
- A worker may not expand scope, change architecture, weaken tests, merge its own PR, or push directly to `main`.

## Isolation and Ownership

- **One feature at a time:** each worker handles only the Task IDs explicitly assigned in its handoff; parallelism comes from separate workers and worktrees, not scope mixing inside one worker.
- One task stream uses one dedicated Git worktree and one task branch. Every task branch starts from the coordinator-specified `main` commit; after an integration gate, the coordinator may require workers to sync an exact newer `main` commit before writes begin.
- `main` is the only permanent branch. All implementation PRs target `main`; direct pushes remain forbidden.
- Only the coordinator edits `AGENTS.md`, `feature_list.json`, `progress.md`, phase documents, shared contracts, dependency locks, or cross-stream settings unless a handoff explicitly delegates a named file.
- Dev workers write task-specific evidence to `docs/handoffs/<TASK-ID>.md` and the remote PR; they do not edit shared status trackers.
- If another stream owns a file or a public contract must change, stop and send a proposed diff/decision request to the coordinator.

## Phase 2 Worker Dispatch

- PM starts Phase 2 by recording the promoted Phase 1 `main` SHA and explicitly dispatching the Dev1 and Dev2 handoffs.
- Dev1 and Dev2 use separate named worktrees and task branches; neither worker works in the Phase 1 checkout or the other worker's worktree.
- Dev1 completes the contract gate first. Dev2 may perform read-only preparation after dispatch but must not edit code until PM supplies the merged contract SHA.
- Dev1 and Dev2 branches are initially created from the same accepted `main` SHA. After the contract gate merges to `main`, both workers sync the coordinator-specified contract commit before production edits and then execute concurrently within owned paths.
- Each worker pushes only its task branch and opens a remote PR to `main`; approved PRs are integrated by the coordinator in the documented order.

## Verification Commands

- Use `./init.sh` for the standard full check. Add focused tests required by the active Task.
- Do not claim PASS without command output or another reproducible artifact.
- Do not commit secrets, private company/customer data, model weights, caches, generated vector storage, or machine-specific paths.

## Definition of Done

A task is done only when its approved scope is implemented, every assigned acceptance criterion and quality gate passes, verification evidence is recorded, the branch is pushed, a reachable remote PR targets `main`, and the task worktree remains restartable. Completing one task never authorizes unassigned features.

## End of Session

Before ending a session, record in `docs/handoffs/<TASK-ID>.md`:

- branch, commit, PR URL and target;
- completed and remaining acceptance criteria;
- commands and results;
- files/public contracts changed;
- blockers, risks, and exact next action.

Leave the task worktree reproducible. Do not mark shared feature status complete; the coordinator updates it after reviewing evidence.

## Escalation

Stop and report the Task/AC, evidence, options, and recommendation when requirements conflict, an owned-path boundary must be crossed, a new dependency/service is needed, a public schema must break, or a requested behavior is out of scope.
