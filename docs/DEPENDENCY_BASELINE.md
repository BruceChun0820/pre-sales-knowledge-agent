# Dependency Baseline

## Status

Phase 1 `TASK-01` base environment verification is complete:

- Base project and development dependencies are configured and installed in `.venv`.
- Python 3.14.4 is usable for the current Phase 1 base dependency set.
- The committed base, CPU, and embedding lock files together match the installed project environment.
- Direct dependency imports, PyMuPDF parsing, and the in-memory Qdrant client smoke test pass.
- Embedding dependencies remain isolated as an optional CPU path with an exact lock.
- CPU-only PyTorch 2.14.0 and Sentence-Transformers 5.7.0 are installed and verified.
- Both pinned TASK-05 candidates completed on the same synthetic bilingual evaluation set.
- No CUDA or NVIDIA package was installed; `torch.cuda.is_available()` is `False`.

This is a dependency/environment document, not a business implementation.

## Runtime Environment

| Item | Value |
|---|---|
| Host | Ubuntu VM `bruce-Virtual-Lab` |
| CPU | 6 vCPU |
| Memory | 15 GiB |
| GPU | None detected |
| Python | 3.14.4 |
| PyTorch | 2.14.0+cpu |
| Sentence-Transformers | 5.7.0 |
| Project environment | `.venv` |
| Qdrant | Client configured; server not started in this task |
| Docker Engine | 29.8.1 |
| Docker Compose | v5.5.1 |
| Qdrant image | Not selected or pulled; pinned image is a TASK-06 deliverable |

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

`requirements-phase1.lock` contains project dependencies only; virtual-environment tooling such as `pip` is intentionally not part of the project dependency graph.

## Compatibility Verification

All checks below ran from the project root with `.venv/bin/python` on the Ubuntu VM:

| Check | Result |
|---|---|
| Clean temporary environment installed from `requirements-phase1.lock` | PASS |
| `pip freeze` compared with `requirements-phase1.lock` | PASS |
| Pydantic and pydantic-settings imports | PASS |
| PyMuPDF import and in-memory PDF text extraction | PASS |
| python-docx import | PASS |
| Qdrant client import and in-memory collection listing | PASS |
| Python 3.14.4 | PASS for the installed base dependency set |
| Docker daemon | AVAILABLE |
| Ruff lint | PASS |
| Ruff format check | PASS |
| Pytest | 42 passed |
| CPU embedding runtime | PASS; both pinned candidates completed with CUDA disabled |

The Qdrant server image is intentionally not selected in TASK-01. TASK-06 must define and pin the image in Docker Compose before server integration begins.

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
.venv/bin/python -m pip install -r requirements-embedding.lock
.venv/bin/python -m pip install -e . --no-deps
```

Verify before using a model:

```bash
.venv/bin/python -c "import torch; import sentence_transformers; print(torch.__version__); print(torch.cuda.is_available())"
```

Expected result: import succeeds and `torch.cuda.is_available()` is `False`.

`requirements-embedding.lock` pins the optional model-runtime packages. Model weights remain in the user cache and must never be committed. If Hugging Face access requires a local proxy, ensure the shell inherits the configured proxy before running the benchmark.

Do **not** run plain `pip install sentence-transformers` first. On this VM it may pull CUDA/NVIDIA packages. If the CPU wheel cannot be downloaded, report the exact error; do not silently fall back to a CUDA build.

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

Use option 2. Keep Sentence-Transformers optional, install the CPU wheel first, and reproduce the exact optional runtime from `requirements-embedding.lock`.

### Reason

It respects the VM hardware constraint, prevents unnecessary CUDA downloads, and preserves the measured MiniLM/BGE-M3 evaluation path.

### Trade-off

Embedding setup has an additional installation step and downloads large model artifacts into the user cache. The base dependency set remains lightweight and independently reproducible.

