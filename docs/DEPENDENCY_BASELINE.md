# Dependency Baseline

## Status

Phase 1 `TASK-01` is partially complete:

- Base project and development dependencies are configured and installed in `.venv`.
- Python 3.14.4 is usable for the current Phase 1 base dependency set.
- Embedding dependencies are explicitly isolated as an optional CPU path.
- Sentence-Transformers/PyTorch CPU installation is not yet complete because the PyTorch CPU wheel download was interrupted by a network stall.
- No CUDA or NVIDIA package was installed.

This is a dependency/environment document, not a business implementation.

## Runtime Environment

| Item | Value |
|---|---|
| Host | Ubuntu VM `bruce-Virtual-Lab` |
| CPU | 6 vCPU |
| Memory | 15 GiB |
| GPU | None detected |
| Python | 3.14.4 |
| Project environment | `.venv` |
| Qdrant | Client configured; server not started in this task |

## Configured Dependency Groups

### Base/runtime group

- `pydantic` — typed domain/config models
- `pydantic-settings` — environment-backed settings
- `PyMuPDF` — PDF parsing and source location
- `python-docx` — DOCX parsing
- `qdrant-client` — vector store adapter in Phase 1

### Development group

- `pytest` — unit/integration/acceptance tests
- `pytest-cov` — coverage reporting
- `ruff` — lint and format checks

### Optional embedding group

- `sentence-transformers` — Embedding benchmark candidates and later reranking experiments

The embedding group is optional because its normal dependency resolution may select a CUDA-enabled PyTorch build on Linux. This VM is CPU-only, so the CPU PyTorch wheel must be installed first.

## Installed Base Versions

The exact transitive environment is frozen in `requirements-phase1.lock`.

| Package | Installed version |
|---|---:|
| pydantic | 2.13.5 |
| pydantic-settings | 2.15.0 |
| PyMuPDF | 1.28.2 |
| python-docx | 1.2.0 |
| qdrant-client | 1.19.1 |
| pytest | 8.4.2 |
| pytest-cov | 6.3.0 |
| ruff | 0.16.8 |

Verification imports for the installed base group passed. `torch` and `sentence-transformers` are currently not installed.

## Reproduction Commands

Run from the project root on Ubuntu:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-phase1.lock
```

The lock file is for the Phase 1 base + development environment. Do not install into system Python.

## CPU Embedding Installation

Only run this after the base environment is healthy:

```bash
.venv/bin/python -m pip install -r requirements-embedding-cpu.txt
.venv/bin/python -m pip install -e ".[embedding]"
```

Verify before using a model:

```bash
.venv/bin/python -c "import torch; import sentence_transformers; print(torch.__version__); print(torch.cuda.is_available())"
```

Expected result: import succeeds and `torch.cuda.is_available()` is `False`.

Do **not** run plain `pip install sentence-transformers` first. On this VM it may pull CUDA/NVIDIA packages. If the CPU wheel cannot be downloaded, stop TASK-05 and report the exact network error; do not silently fall back to a CUDA build.

## Dependency Policy

- Direct dependency ranges live in `pyproject.toml`.
- Exact resolved base versions live in `requirements-phase1.lock`.
- Optional heavyweight model/runtime dependencies must be isolated and documented.
- New dependencies require a Task/Phase reason and an update to the lock file.
- No dependency may introduce Java, Kafka, Redis, Kubernetes, microservices, LLM calls, or Agent behavior in Phase 1.
- No model weights, pip cache, `.venv`, Qdrant storage, or secrets are committed.

## Decision Record

### Problem

The VM has no GPU, but the default Linux resolution of Sentence-Transformers selected a CUDA-enabled PyTorch dependency path.

### Options

1. Install Sentence-Transformers normally and accept CUDA packages.
2. Install CPU-only PyTorch first, then install the optional embedding group.
3. Replace the embedding experiment with a different runtime without measuring it.

### Decision

Use option 2. Keep Sentence-Transformers optional, use `requirements-embedding-cpu.txt` to force the CPU wheel, and keep the base Phase 1 environment free of model-runtime dependencies until that CPU path is verified.

### Reason

It respects the VM hardware constraint, prevents unnecessary CUDA downloads, and preserves the intended BGE/Sentence-Transformers evaluation path.

### Trade-off

Embedding benchmark setup has one additional installation step and is currently blocked by the PyTorch wheel download. The base parsing/Qdrant/test work can proceed independently without hiding that blocker.

