# Roadmap

## Roadmap Rules

- 不以日期承诺进度；每个 Phase 由退出条件驱动。
- 未满足当前 Phase 退出条件，不用后续框架掩盖问题。
- Evaluation schema 从 Phase 1 开始，Phase 5 是正式扩展和验收，不是第一次评测。
- 每个 Phase 结束由项目负责人审核关键产物。
- CRM Implementation Agent 永远不是当前 MVP 的前置条件。

## Phase 0 — Documentation & Architecture

### Goal

明确问题、边界、架构、技术选型、RAG/Agent 设计、评测方法和实际开发顺序。

### Deliverables

- README 与 8 份设计文档；
- 模块化单体目录骨架；
- `.gitignore`、`.env.example`、最小 `pyproject.toml`；
- Ubuntu 环境与资源检查；
- 待确认设计决策清单。

### Exit Criteria

- 所有文档通过负责人审核；
- MVP/非目标/CRM boundary 无歧义；
- Python 版本、数据语言、LLM provider policy 等关键决策得到确认；
- 获得明确批准进入 Phase 1。

### Current Status

已完成并作为 Git `main` 的初始稳定基线。未实现业务代码、未安装依赖、未启动服务。

## Phase 1 — Document Ingestion + Vector DB

### Current Status

`ACCEPTED`. AC-P1-01 through AC-P1-17 passed on the QA-tested PR head; PM accepted the implementation and authorized promotion to `main`. Final evidence is recorded in `docs/qa/QA-001.md`.

### Goal

从公开/模拟文档稳定生成可追溯 chunks，并写入可重建的 Qdrant index。

### Deliverables

- Python compatibility spike 与 lockfile；
- parser registry：PDF、DOCX、Markdown、TXT；
- manifest、checksum、version、幂等导入；
- cleaning、structure-aware chunking、metadata validation；
- 两个 embedding candidates 的 CPU benchmark；
- Qdrant Docker Compose 与 collection/index setup；
- ingestion CLI、unit/integration tests；
- 5–10 个 parser golden fixtures 和初始 evaluation cases。

### Exit Criteria

- 样例 corpus 可从零重复构建；
- chunk 可定位到 source page/section；
- 重复导入不产生重复 active data；
- 坏文档不会终止整批；
- embedding model 选择有 quality/latency/memory 对比；
- Qdrant count/payload/filter smoke tests 通过。

## Phase 2 — Basic RAG Q&A + Citation

### Current Status

Planned under `docs/phases/PHASE-02.md`. Phase 1 prerequisites are satisfied, but Phase 2 implementation still requires explicit PM/user activation. At activation, Dev1 and Dev2 task branches are cut from the accepted `main` baseline, then follow the contract-first integration gate before parallel implementation.

### Goal

实现最小、直接、可引用的 Question -> Retrieve -> Generate 流程，不引入 Agent loop。

### Deliverables

- query normalization、dense retriever、context builder；
- OpenAI-compatible LLM adapter 与 fake adapter；
- structured answer/claim/citation schema；
- citation validator 与 insufficient-evidence behavior；
- FastAPI `/query`、`/search`、health endpoints；
- request trace、latency/token logging；
- Q&A integration/acceptance tests。

### Exit Criteria

- 代表性问题返回可定位引用；
- Qdrant/LLM 失败不会触发无依据回答；
- unanswerable cases 能拒答；
- baseline retrieval/answer report 可重复运行；
- 所有 API output 通过 schema validation。
- 所有实现通过远程 PR 提交到 `dev`，并由 QA 对准确的远程 head SHA 验收；
- citation validator 能阻止未知引用、无引用事实声明和无依据 quote 返回 `answered`。

## Phase 3 — Retrieval Optimization + Reranking

### Goal

以评测证据提升检索，不凭感觉添加技术。

### Deliverables

- Metadata Filter Experiment A；
- Query Rewrite Experiment B；
- Cross-Encoder Reranker Experiment C；
- chunk size/overlap/top-K ablations；
- latency/memory/cost 对比；
- optional Hybrid Experiment D（仅有明确失败模式时）；
- 选定默认 retrieval config 与决策记录。

### Exit Criteria

- 每个组件有 adopt/reject 的量化理由；
- holdout 上无不可接受 citation/latency regression；
- 最终 config、模型 revision、index version 可追溯；
- reranker/hybrid 失败有安全降级。

## Phase 4 — Agent Tool Calling + ReAct

### Goal

在稳定 RAG 服务之上实现单 Agent、typed tools、bounded ReAct 和显式 state。

### Deliverables

- 5 个领域工具与 contract tests；
- LangGraph state、nodes、edges 和 step budget；
- structured tool calling、observation validation；
- error/timeout/repeated-call policies；
- agent trace 与 tool selection evaluation；
- prompt-injection/tool safety tests。

### Exit Criteria

- Agent 不提供 shell/任意网络/文件写工具；
- 允许任务在步数限制内完成；
- tool selection/arguments 可评测；
- direct RAG 路径仍可独立调用；
- Agent 不绕过 insufficient-evidence/citation gate。

## Phase 5 — Formal Evaluation

### Goal

完成可执行、可复现的 30–50 case RAG/Agent 评测，并建立回归门禁。

### Deliverables

- 40-case dataset v1（30 dev + 10 holdout）；
- expected sources、reference/forbidden claims、expected tool paths；
- retrieval、answer、citation、agent、system metrics；
- human/LLM-judge calibration；
- overall/slice/per-case report；
- failure taxonomy 与 prioritized improvement backlog；
- deterministic CI regression subset。

### Exit Criteria

- 指标实现有测试，数据来源经人工复核；
- baseline/A/B/C 使用同一冻结数据比较；
- 初始 acceptance targets 被确认或基于证据调整；
- 主要失败模式有明确 owner/next action；
- holdout 结果未被用于反复调参。

## Phase 6 — Proposal / Solution Workflows

### Goal

完成业务可演示的 compare、summary 和 Proposal Outline 工作流。

### Deliverables

- solution-level search results；
- evidence-backed comparison matrix；
- multi-document summary with conflicts；
- Proposal Outline JSON/Markdown；
- assumptions、unknowns、open questions；
- 对应 API、tools、evaluation cases 和 demo script。

### Exit Criteria

- 所有事实性输出有 citations；
- comparison 每个对象和维度有 coverage/unknown 标记；
- Proposal Outline 不产生报价、合同承诺或虚构案例；
- workflows 在 acceptance cases 达到确认门槛；
- README 提供可重复演示步骤。

## Phase 7 — Optional CRM Implementation Agent Extension

### Goal

在不接触任何原公司私有资产的前提下，研究通用配置 Agent 的 tool abstraction、phase gates 和 MCP integration architecture。

### Deliverables

- 通用 `ConfigurationTool` interface；
- 自建 Mock CRM domain 和 synthetic schema；
- dry-run / diff / validation / approval flow；
- Human-in-the-loop pause/resume；
- optional public MCP adapter；
- threat model、audit trail 和 evaluation cases。

### Exit Criteria

- 与 Pre-sales Knowledge MVP 清晰隔离；
- 不包含真实公司接口、数据、MCP schema、Skill 或业务规则；
- 所有变更默认 dry-run，执行前需审批；
- mock tool 行为和 failure modes 有测试；
- 负责人单独批准此扩展。

## Cross-phase Quality Gates

每个 Phase 都需满足：

- 数据与 secrets 边界未被突破；
- 新组件有业务理由和替代方案记录；
- 失败路径已测试；
- 影响质量的改动有评测对比；
- 文档与实际实现一致；
- 没有因方便而加入通用高权限工具。

## Deferred Backlog

以下不进入当前 roadmap 的必选交付：

- 独立前端；
- OCR 与复杂表格解析；
- 多租户 ACL/SSO；
- 增量企业内容连接器；
- Kubernetes/HA/水平扩展；
- long-term memory；
- multi-agent；
- automatic final Proposal/DOCX export；
- CRM production integration。
