# Task Handoff Records

This directory contains one durable handoff per implemented Task ID.

Workers may create or update only their assigned `docs/handoffs/<TASK-ID>.md`. Shared state in `feature_list.json` and `progress.md` is coordinator-owned.

Each handoff must record:

- Task ID, owner, branch, base SHA, head SHA, remote PR URL, and target branch;
- completed and remaining acceptance criteria;
- exact verification commands and results;
- changed files and public-contract impact;
- blockers, known limitations, and next action.

The remote PR is the primary review artifact; a local-only handoff is incomplete.
