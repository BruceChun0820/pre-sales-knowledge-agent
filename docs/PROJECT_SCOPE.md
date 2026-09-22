# Project Scope

## 1. Problem Statement

企业售前知识分散在产品资料、行业方案、案例、实施文档和历史 Proposal/RFP 中。传统文件搜索只能解决“文件在哪里”，不能稳定回答：

- 哪些历史方案与当前客户需求最相关；
- 某项产品能力的适用范围、限制和证据是什么；
- 多个行业或方案在能力、约束和交付方式上有何差异；
- 新 Proposal 应引用哪些已验证内容；
- 一个回答能否追溯到具体文档位置。

本项目建设一个可运行、可解释、可评估的知识与方案助手。系统以 RAG 提供证据，以受控 Agent 工具完成多步骤任务，并通过离线评测而不是主观演示判断改进是否有效。

## 2. Target Users

### 2.1 Primary users

- 售前顾问：查产品能力、案例和行业方案，准备客户交流材料。
- 解决方案架构师：比较方案差异，识别约束和待确认项。
- 售前负责人：复用组织知识，降低材料质量对个人经验的依赖。

### 2.2 Secondary users

- 产品经理：了解售前常见问题和资料覆盖缺口。
- 项目面试官或技术评审者：检查 RAG/Agent 设计、实现取舍和评测证据。

### 2.3 Out-of-scope users

- 需要自动修改 CRM、生产系统或客户环境的实施人员；
- 需要法律、合同或合规最终裁决的用户。

## 3. Core Use Cases

| ID | Use case | Expected outcome |
|---|---|---|
| UC-01 | 企业知识问答 | 返回基于知识库的答案、引用和“不足以回答”状态 |
| UC-02 | 历史方案检索 | 按需求、行业、产品和文档类型找到相关方案及关键片段 |
| UC-03 | 行业方案对比 | 以固定比较维度输出相同点、差异、限制和来源 |
| UC-04 | 产品能力查询 | 区分“支持、条件支持、未说明、不支持”，逐项引用 |
| UC-05 | 多文档总结 | 对指定文档集合生成带来源的主题摘要 |
| UC-06 | Proposal 大纲 | 根据客户背景和检索证据生成结构化大纲与待确认问题 |
| UC-07 | 资料缺口识别 | 当知识库缺少关键证据时明确指出缺口，而非补写事实 |

## 4. MVP Scope

MVP 的产品边界是 **Pre-sales Knowledge Agent**。

### 4.1 Data scope

- 公开许可资料和自行构造的模拟售前资料；
- PDF、DOCX、Markdown、TXT；
- 单个逻辑知识库、单租户演示；
- 文档级版本、来源、行业、产品、文档类型和发布日期元数据；
- 数字文本优先，扫描件 OCR 不作为必须能力。

### 4.2 Retrieval and answer scope

- 可重建的 ingestion pipeline；
- Dense retrieval baseline；
- Metadata filter、Query Rewrite、Reranker 实验；
- 以评测结果决定是否加入 Hybrid retrieval；
- 回答、检索结果和生成材料都保留来源；
- 无足够相关证据时拒答或给出澄清问题。

### 4.3 Agent scope

- 5 个只读领域工具；
- 结构化工具输入和输出；
- 显式、有限步数的 ReAct/tool-calling loop；
- request-scope state、错误分类、超时和降级；
- 不允许 shell、任意文件、网络浏览或业务系统写入工具。

### 4.4 Interface scope

- FastAPI API 与自动生成的 Swagger 页面；
- CLI/scripts 用于 ingestion 与 evaluation；
- 无独立 Web 前端要求。

### 4.5 Evaluation scope

- 30–50 条人工审核的 evaluation cases；
- expected sources、reference claims、expected tool/path；
- Retrieval、Answer、Citation、Agent、Latency、Cost 指标；
- Baseline 与 A/B/C 实验可重复比较。

## 5. Phase 2 / Extension Scope

这里的“Phase 2 Scope”指产品扩展阶段，不等同于 Roadmap 中的 Phase 2 编号。

- 更多文件格式、表格理解和 OCR；
- 多租户、身份认证、角色与文档 ACL；
- 增量同步、对象存储、审计与生产可观测性；
- 对话级长期记忆和用户偏好；
- 人工审核后导出 Proposal 文档；
- 更复杂的 Planning、Reflection 或多 Agent 协作（仅在评测证明有价值时）；
- 通用 CRM Implementation Agent 研究：仅使用抽象 Tool Interface、Mock Tool 和公开/自建 Skill。

## 6. CRM Implementation Agent Boundary

| 项目 | MVP | Future Extension |
|---|---:|---:|
| 售前知识检索与引用 | Yes | Yes |
| 方案比较、总结、大纲 | Yes | Yes |
| Tool Calling / ReAct | 只读知识工具 | 可加入 mock 配置工具 |
| CRM 配置写入 | No | 仅 mock 或用户自有公开接口 |
| 公司内部 MCP / API | No | No |
| 公司私有 Skill / Schema | No | No |
| Human-in-the-loop phase gate | 非必须 | 可研究 |

未来扩展的目标是研究“接口抽象、审批和状态机”，不是还原任何公司的 CRM 实现。

## 7. Explicit Non-goals

- 不构建通用企业搜索平台或完整内容管理系统；
- 不训练基础模型，不做大规模 fine-tuning；
- 不保证从扫描件、复杂表格或图片中无损提取信息；
- 不自动发送邮件、修改 CRM、生成报价或执行生产操作；
- 不把互联网搜索结果自动视为内部可信知识；
- 不在 MVP 引入 Kafka、Redis、Kubernetes、服务网格或微服务拆分；
- 不把 Multi-Agent、Reflection、Planning 当作必须关键词；
- 不以 LLM-as-judge 的单一分数替代人工抽检；
- 不使用真实企业私有数据或秘密。

## 8. Success Criteria

以下是 MVP 退出条件。数值阈值是**初始目标**，在第一版评测集完成后校准并由项目负责人确认。

### 8.1 Functional

- 能从零重建样例知识库，重复导入不会生成重复有效文档；
- 10 个代表性任务可通过 API 完整演示；
- 所有事实性回答都含可定位引用；
- 证据不足问题能拒答，不生成“企业事实”；
- 方案比较和大纲返回结构化结果及来源。

### 8.2 Quality

- Hit Rate@5 初始目标 ≥ 0.85；
- Recall@10 初始目标 ≥ 0.80；
- Citation Accuracy 初始目标 ≥ 0.90；
- Faithfulness/Groundedness 初始目标 ≥ 0.85；
- Tool Selection Accuracy 初始目标 ≥ 0.90；
- 每次策略变更有配置、数据集版本和对比报告。

### 8.3 Engineering

- 核心领域接口不依赖 Agent 框架；
- 单元、集成、验收测试可在本地执行；
- 请求日志包含 trace ID、工具调用、检索 chunk ID、耗时和 token/cost；
- API key、原始敏感数据和运行产物不进入 Git；
- 默认可通过 Docker Compose 在单台 Ubuntu VM 上演示。

## 9. Assumptions and Constraints

- 当前 Ubuntu VM：6 vCPU、15 GiB RAM、无 NVIDIA GPU；
- 当前系统 Python 为 3.14.4，Phase 1 需先验证 PyTorch/Transformers 依赖兼容性；
- 数据规模以个人项目演示为主，不按千万级 chunk 设计；
- LLM 通过 OpenAI-compatible API 访问，供应商和模型可配置；
- Embedding 与 reranking 优先本地运行，但必须满足 VM 的延迟和内存约束；
- 评测样例和参考答案需要人工审核，不能完全依赖 LLM 自动生成。

## 10. Open Decisions for Owner Approval

1. 样例知识库以“中英双语”还是“中文为主、英文补充”为目标？这会影响 embedding/reranker 的最终选择。
2. 是否接受 Phase 1 为项目单独管理 Python 3.13，以规避 Python 3.14 的生态兼容风险？
3. OpenAI-compatible LLM API 的具体供应商、模型、预算和数据保留政策是什么？
4. MVP 是否要求完全离线 embedding，还是允许调用外部 embedding API 做对照实验？
5. Citation 的展示粒度是否必须包含页码；对于 DOCX/TXT，是否接受 section + paragraph/chunk 定位？
6. Proposal Outline 是只生成 Markdown/JSON 大纲，还是 MVP 需要导出 DOCX？本设计默认前者。

