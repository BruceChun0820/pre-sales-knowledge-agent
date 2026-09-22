# Pre-sales Knowledge Agent

售前知识与方案智能助手：一个面向企业售前团队的、可评估的 RAG + Agent 项目。项目将公开资料与自建模拟售前文档转化为可检索知识库，支持带来源的问答、历史方案检索、跨方案比较、文档总结和 Proposal 大纲辅助生成。

> 当前状态：**Phase 1 — Document Ingestion + Vector DB / PLANNED**。Phase 0 文档与架构基线已完成；Phase 1 的任务定义和 Dev/QA 交接已就绪，等待用户授权开发。尚未安装项目依赖、启动 Qdrant、调用 LLM，或实现业务代码。

## 1. 项目背景

售前人员面对新客户需求时，往往需要在产品手册、行业方案、项目案例、实施指南和历史 Proposal/RFP 材料中反复查找信息。常见问题不是“找不到文件”，而是：

- 不知道应查哪类资料，关键词与文档表述不一致；
- 多份方案内容重叠或冲突，缺少可比较的结构；
- 生成材料时难以逐条追溯事实来源；
- 检索质量依赖个人经验，缺少可量化的改进方法。

本项目以检索质量、引用可靠性和可评估性为首要目标。Agent 负责选择受控工具和组织多步任务，不替代知识证据，也不获得任意系统写权限。

## 2. 要解决的问题

1. 将 PDF、DOCX、Markdown、TXT 等公开或模拟资料统一解析、清洗、切分并建立索引。
2. 根据自然语言问题检索相关证据，并返回可定位到文档、页码或章节的引用。
3. 对多个方案进行有依据的比较、总结和大纲生成。
4. 通过固定评测集比较 Metadata Filter、Query Rewrite、Reranking 等策略，而非凭主观感受调参。
5. 用简单、可观察、可限制步数的 Agent 工作流封装上述能力。

## 3. 核心能力

- 文档导入、解析、清洗、Chunking 与元数据管理
- Dense Retrieval；按评测结果决定是否启用 Hybrid Retrieval
- Metadata Filtering、Query Rewrite、Reranking 实验
- 企业知识问答与历史方案检索
- 多文档总结与行业方案对比
- Proposal Outline 结构化生成
- Claim-to-citation 引用与拒答
- Tool Calling、受限 ReAct、Structured Output、Agent State
- Retrieval、Answer、Agent、Latency 与 Cost Evaluation

## 4. MVP 范围

MVP 是 **Pre-sales Knowledge Agent**，包括：

- 使用公开资料或自建模拟资料构建单租户知识库；
- 支持 PDF、DOCX、Markdown、TXT 的批量导入；
- 提供知识问答、方案检索、受控比较、总结和 Proposal 大纲；
- 每个事实性结论返回来源，证据不足时明确拒答；
- 支持行业、文档类型、产品、发布日期等元数据过滤；
- 具备可重复运行的离线评测集与实验报告；
- 通过 FastAPI 提供可演示、可测试的接口。

MVP 不包含真实 CRM 配置、企业内部 MCP、私有 Skill、生产级权限系统、前端门户、微服务、Kafka、Redis、Kubernetes 或多 Agent 协作。

CRM Implementation Agent 仅作为未来 Phase 7：届时也只通过通用 Tool Interface 与 Mock Tool 研究规划、审批和 MCP 集成架构，不复制、模拟或泄露任何公司的私有实现。

## 5. 架构概览

项目采用模块化单体：

```text
Client / Swagger
       |
    FastAPI
       |
Agent Orchestrator ---- Structured Tools
       |                    |
       +------------ RAG Application Services
                            |
     Query Processing -> Retrieval -> Rerank -> Context -> Answer/Citation
                            |
                         Qdrant

Documents -> Parse -> Clean -> Chunk -> Metadata -> Embed -> Qdrant
```

Basic RAG 阶段使用普通 Python service 显式编排；进入 Tool Calling 阶段后才引入 LangGraph。领域模型、检索接口和评测接口不依赖 LangGraph，以避免框架锁定。

详见 [Architecture](docs/ARCHITECTURE.md)、[RAG Design](docs/RAG_DESIGN.md) 和 [Agent Design](docs/AGENT_DESIGN.md)。

## 6. 推荐技术栈

| 领域 | MVP 推荐 | 说明 |
|---|---|---|
| Language | Python 3.13；先验证现有 3.14 | 当前 Ubuntu 为 3.14.4；Phase 1 先做依赖兼容性门禁 |
| API | FastAPI + Pydantic | OpenAPI、输入输出校验、易于自动测试 |
| Agent | LangGraph（Phase 4 起） | 显式状态图、可限制循环、适合确定性步骤与 LLM 步骤混合 |
| LLM | OpenAI-compatible API，通过自有 adapter | 不把业务层绑定到单一供应商 |
| Parsing | PyMuPDF + python-docx + 标准库 | 先覆盖数字文本；OCR 后置 |
| Embedding | BGE-M3 候选；轻量多语模型作为 CPU baseline | 以中文/英文评测和 VM 延迟决定最终模型 |
| Vector DB | Qdrant | 持久化、payload filter、dense/sparse/hybrid 演进路径 |
| Reranker | BGE Cross-Encoder 候选，按实验启用 | CPU 环境下必须证明质量增益值得延迟成本 |
| Evaluation | 自建 JSONL harness + pytest；Ragas 可选 | 客观指标优先，LLM-as-judge 只作补充 |
| Runtime | Docker Compose | 只承载本地 Qdrant 和应用演示，不做微服务拆分 |

完整比较见 [Tech Stack](docs/TECH_STACK.md)。

## 7. 项目目录规划

```text
pre-sales-knowledge-agent/
├── app/
│   ├── api/             # HTTP routes、request/response schema
│   ├── agent/           # LangGraph state、nodes、policies（Phase 4）
│   ├── core/            # settings、logging、errors、observability
│   ├── domain/          # framework-neutral entities 与 interfaces
│   ├── rag/             # ingestion、chunking、retrieval、reranking、citation
│   └── tools/           # 受控、结构化 Agent tools
├── data/
│   ├── raw/             # 本地公开/模拟原始资料；默认不提交大文件
│   ├── processed/       # 解析与切分产物；可重建
│   └── samples/         # 可提交的小型公开/模拟样例
├── docs/                # 范围、需求、架构与设计决策
├── evaluation/
│   ├── datasets/        # questions、expected sources、reference claims
│   └── reports/         # 实验结果；注明配置和版本
├── infra/               # Docker Compose、Qdrant 本地配置（Phase 1）
├── scripts/             # ingestion、evaluation 等显式入口
├── tests/
│   ├── unit/
│   ├── integration/
│   └── acceptance/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

目录目前为空骨架，业务代码将在 Phase 1 经确认后开始。

## 8. 开发阶段

| Phase | 主题 | 当前状态 |
|---|---|---|
| 0 | Documentation & Architecture | 已完成并建立 Git 基线 |
| 1 | Document Ingestion + Vector DB | PLANNED，Handoff 已就绪，尚未授权开发 |
| 2 | Basic RAG Q&A + Citation | 未开始 |
| 3 | Retrieval Optimization + Reranking | 未开始 |
| 4 | Agent Tool Calling + ReAct | 未开始 |
| 5 | Formal Evaluation | 未开始；评测基础从 Phase 1 建立 |
| 6 | Proposal / Solution Workflows | 未开始 |
| 7 | Optional CRM Extension | 非 MVP，未开始 |

每阶段的目标、交付物和退出条件见 [Roadmap](docs/ROADMAP.md)。

当前 Phase 的可执行范围见 [Phase 01](docs/phases/PHASE-01.md)，流程规范见 [Development Process](docs/DEVELOPMENT_PROCESS.md)。开发与 QA 分别使用 [Dev Handoff](docs/pr/PHASE-01-DEV-HANDOFF.md) 和 [QA Handoff](docs/qa/PHASE-01-QA-HANDOFF.md)。

## 9. 数据与安全原则

- 仅使用公开资料或自行构造的模拟企业资料。
- 不导入真实公司文档、客户数据、MCP Schema、接口定义或私有 Skill。
- `.env`、原始大文件、模型缓存、向量数据库存储和运行日志默认不提交 Git。
- 引用指向稳定的 `document_id + version + page/section + chunk_id`，避免只返回文件名。
- 任何“生成”都不能把模型常识伪装成企业知识；证据不足时拒答或明确标注推测。

## 10. Project Management Status

- [x] 项目范围、需求和非目标已定义
- [x] 模块化单体架构与数据流已设计
- [x] RAG、Agent 和 Evaluation 方案已形成
- [x] 技术选型包含替代方案与取舍
- [x] 分阶段 Roadmap 已定义
- [x] Git `main` / `dev` 工作流已定义
- [x] Phase 1 Objective、Scope、Tasks、Acceptance Criteria 与 Quality Gates 已定义
- [x] Phase 1 Dev/QA Handoff 已准备
- [ ] Dev 尚未开始 Phase 1 实现
- [ ] QA 尚未开始 Phase 1 验收
