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
- A worker may not expand scope, change architecture, weaken tests, merge its own PR, or push directly to `main` or `dev`.

## Isolation and Ownership

- **One feature at a time:** each worker handles only the Task IDs explicitly assigned in its handoff; parallelism comes from separate workers and worktrees, not scope mixing inside one worker.
- One task stream uses one dedicated Git worktree and one task branch based on the coordinator-specified `dev` commit.
- All implementation PRs target `dev`. `main` remains the stable accepted branch.
- Only the coordinator edits `AGENTS.md`, `feature_list.json`, `progress.md`, phase documents, shared contracts, dependency locks, or cross-stream settings unless a handoff explicitly delegates a named file.
- Dev workers write task-specific evidence to `docs/handoffs/<TASK-ID>.md` and the remote PR; they do not edit shared status trackers.
- If another stream owns a file or a public contract must change, stop and send a proposed diff/decision request to the coordinator.

## Verification Commands

- Use `./init.sh` for the standard full check. Add focused tests required by the active Task.
- Do not claim PASS without command output or another reproducible artifact.
- Do not commit secrets, private company/customer data, model weights, caches, generated vector storage, or machine-specific paths.

## Definition of Done

A task is done only when its approved scope is implemented, every assigned acceptance criterion and quality gate passes, verification evidence is recorded, the branch is pushed, a reachable remote PR targets `dev`, and the task worktree remains restartable. Completing one task never authorizes unassigned features.

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
