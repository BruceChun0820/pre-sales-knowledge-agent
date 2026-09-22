# Dev Prompt — Phase 01

下面内容可直接发送给 Dev：

```text
你现在负责 Pre-sales Knowledge Agent 的 Phase 01：Document Ingestion + Vector DB。

请先阅读并以这些文档为准：

1. README.md
2. docs/PROJECT_SCOPE.md
3. docs/REQUIREMENTS.md
4. docs/ARCHITECTURE.md
5. docs/TECH_STACK.md
6. docs/RAG_DESIGN.md
7. docs/DEVELOPMENT_PROCESS.md
8. docs/phases/PHASE-01.md
9. docs/pr/PHASE-01-DEV-HANDOFF.md
10. docs/pr/PR_TEMPLATE.md
11. docs/qa/PHASE-01-QA-HANDOFF.md
12. docs/DEPENDENCY_BASELINE.md

当前状态：

- 当前分支为 dev；不要在 main 上开发。
- Phase 01 的任务定义、Acceptance Criteria 和 Quality Gates 已批准。
- 项目 `.venv` 已建立。
- Phase 1 base dependencies 已安装并锁定在 `requirements-phase1.lock`。
- 已配置的基础依赖包括 Pydantic、Pydantic Settings、PyMuPDF、python-docx、qdrant-client、pytest、pytest-cov、ruff。
- Embedding 依赖是 optional CPU 路径，目前尚未完成安装。
- 不要直接执行 `pip install sentence-transformers`，因为可能拉取 CUDA/NVIDIA 依赖。
- 如果需要继续 TASK-05，先执行 `requirements-embedding-cpu.txt` 中的 CPU PyTorch 安装；CPU wheel 下载失败时立即停止并向 PM 报告完整错误，不要切换到 CUDA 版本。
- 当前项目没有配置 origin 时，不能假设远程 PR 可用；先检查 `git remote -v`。如果 origin 缺失或指向错误仓库，停止并反馈 PM。

执行顺序：

1. 验证 `.venv`、`requirements-phase1.lock`、pyproject.toml 和 base imports。
2. 完成 TASK-01 的剩余兼容性/依赖证据；不要修改系统 Python。
3. 按依赖顺序实现 TASK-02 至 TASK-08。
4. 先实现领域模型和 adapter contracts，再实现 parser、cleaning、chunking、embedding benchmark、Qdrant adapter 和 ingestion orchestration。
5. 每个 Task 都必须补充对应 unit/integration/golden/acceptance tests。
6. 不要实现 Phase 2+ 功能。

本 Phase 允许的范围：

- PDF、DOCX、Markdown、TXT 解析；
- manifest、checksum、document version、source location；
- conservative cleaning、structure-aware deterministic chunking；
- metadata validation、deterministic chunk IDs；
- 两个 embedding candidate 的 CPU benchmark；
- Qdrant persistent collection、payload filters、idempotent upsert、safe version activation；
- ingestion CLI/script 和结构化运行摘要；
- pytest、ruff、format、integration 和 parser golden tests。

明确禁止：

- LLM、OpenAI API、FastAPI、LangGraph、Agent、Tool Calling、ReAct、Memory；
- Query Rewrite、Reranker、Hybrid Retrieval、Sparse Vector、OCR；
- Java、Kafka、Redis、Kubernetes、Microservices、Multi-Agent；
- CRM API、MCP、私有 Skill、真实公司/客户资料；
- shell/任意网络/任意文件写入 Agent tool；
- 直接 push 或 commit 到 main；
- 创建新远程仓库或改变远程仓库可见性。

停止并反馈 PM 的情况：

- Python 3.14 与批准依赖不兼容；
- CPU embedding wheel 下载失败或需要 CUDA；
- Qdrant metadata/schema 需要破坏性变更；
- Acceptance Criteria 无法客观测试；
- 需要引入 Out of Scope 组件；
- 测试资料来源或授权不清楚；
- origin 缺失、错误，或无法创建 target=dev 的远程 PR。

完成后不要自行合并。请：

1. 从最新 dev 创建 task branch，例如 `feature/phase-01-task-03-document-parsers`。
2. 按 docs/pr/PR_TEMPLATE.md 填写变更、测试、AC 和 Quality Gate 证据。
3. 将 task branch push 到已批准的 origin。
4. 创建 target=`dev` 的远程 PR。
5. 把远程 PR URL、repository、source branch、target branch、head SHA、测试结果和已知限制反馈给 PM。
6. QA 只验收已 push 的 PR head；Dev 不要自行 merge。
```

