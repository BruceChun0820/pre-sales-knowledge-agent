# Requirements

## 1. Purpose and Priority Model

本文定义 MVP 的功能和非功能需求。优先级采用 MoSCoW：

- **Must**：MVP 退出条件；缺失则不能称为可演示的售前知识 Agent。
- **Should**：高价值能力；应在 MVP 完整路线内完成，但允许在基础质量未达标时后置。
- **Could**：有数据证明价值后再加入；不影响 MVP 核心验收。
- **Won't (now)**：明确不在当前 MVP。

所有需求应能关联到测试、评测样例或可观察日志。

## 2. Functional Requirements

### 2.1 Document ingestion and knowledge-base construction

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-ING-01 | Must | 从受控本地目录批量导入 PDF、DOCX、Markdown、TXT | 每种格式至少一个公开/模拟样例成功进入 processed manifest |
| FR-ING-02 | Must | 为每次导入记录 document ID、版本、checksum、parser 版本和状态 | manifest 可追溯，失败文档有错误原因 |
| FR-ING-03 | Must | 提取文本并保留页码、章节、段落等可用位置 | chunk 可映射回源文档位置 |
| FR-ING-04 | Must | 清理重复页眉页脚、异常空白和明显乱码，同时保留原文证据 | 清洗前后抽检，不改变关键数字/否定词 |
| FR-ING-05 | Must | 使用可配置、可复现实验的 chunk strategy | chunk 参数写入 manifest，重跑结果确定性一致 |
| FR-ING-06 | Must | 将 chunk、embedding 和 metadata 写入 Qdrant | 导入后数量、ID 和 payload 校验通过 |
| FR-ING-07 | Must | 重复导入相同版本时幂等 | 不产生重复 active chunks |
| FR-ING-08 | Should | 支持文档更新和旧版本失效 | 查询默认只返回 active version，可按版本追溯 |
| FR-ING-09 | Could | 对扫描 PDF 按需 OCR | OCR 能力独立开关并记录 OCR 置信/来源 |

### 2.2 Metadata

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-META-01 | Must | 支持 `industry` 与 `document_type` | 可在 ingestion 指定，并在查询中精确过滤 |
| FR-META-02 | Must | 支持 product、source、language、published_at、version | payload schema 校验通过 |
| FR-META-03 | Must | 缺失字段使用显式 `unknown`/null，不由模型猜测 | 导入日志列出缺失项 |
| FR-META-04 | Should | 支持 tags、region、solution_stage、confidentiality | 查询过滤与评测切片可使用 |
| FR-META-05 | Should | 自动元数据建议必须由规则或人工确认 | 未确认建议不能影响默认过滤 |

### 2.3 Search and Q&A

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-RAG-01 | Must | 对自然语言问题执行 dense retrieval | 返回带 score、rank、chunk ID 的候选集 |
| FR-RAG-02 | Must | 支持显式 metadata filters | 筛选后的结果不越过过滤范围 |
| FR-RAG-03 | Must | 基于检索证据生成回答 | answer payload 包含 claims/citations |
| FR-RAG-04 | Must | 返回来源文档、版本、页码/章节、chunk ID 和可读片段 | 引用可定位并通过抽检 |
| FR-RAG-05 | Must | 证据不足时拒答，并说明缺少什么 | unanswerable 测试集不产生无依据企业事实 |
| FR-RAG-06 | Must | 支持历史方案检索 | 返回方案级结果和匹配片段，而非只返回自由文本回答 |
| FR-RAG-07 | Should | 对模糊或过长查询进行受控 rewrite | 同时保留 original query 和 rewritten query |
| FR-RAG-08 | Should | 对候选 chunks 进行 rerank | 可开关；记录 before/after rank 与耗时 |
| FR-RAG-09 | Could | Dense + sparse hybrid retrieval | 只在评测显著改善关键词/型号类问题时启用 |
| FR-RAG-10 | Could | 自动提出澄清问题 | 低置信且用户意图不明确时触发 |

### 2.4 Solution workflows

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-SOL-01 | Should | 比较两个或多个指定方案 | 按固定维度输出 evidence-backed matrix |
| FR-SOL-02 | Should | 总结指定文档集合 | 摘要中的事实有引用，并区分跨文档共识/冲突 |
| FR-SOL-03 | Should | 生成 Proposal Outline | 返回 JSON/Markdown 结构、证据、假设和待确认问题 |
| FR-SOL-04 | Should | 行业方案检索支持 industry/doc_type filters | 过滤条件在 tool trace 中可见 |
| FR-SOL-05 | Could | 对冲突来源给出新旧版本提示 | 不自动裁决冲突，输出冲突项 |
| FR-SOL-06 | Won't | 自动生成最终报价、合同或承诺 | 不提供此能力 |

### 2.5 Agent and tools

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-AG-01 | Must | 提供结构化、只读工具：知识检索、行业方案检索、方案比较、文档总结、Proposal 大纲 | 每个工具有 Pydantic I/O schema 和 contract tests |
| FR-AG-02 | Must | Agent 根据任务选择工具，并可在有限步骤内继续或结束 | 默认最多 4 步，超限返回受控错误 |
| FR-AG-03 | Must | 工具 Observation 保留 trace、sources 和错误类型 | 可重放和调试 |
| FR-AG-04 | Must | 最终输出使用结构化 schema | 无法解析时重试一次或降级为受控错误 |
| FR-AG-05 | Must | 工具不能访问任意 shell、任意 URL 或未授权文件 | allowlist 测试通过 |
| FR-AG-06 | Should | request-scope state 保存原问题、意图、过滤器、工具历史、证据和最终状态 | state transition 测试通过 |
| FR-AG-07 | Could | 在高风险写操作前 Human-in-the-loop | MVP 无写操作，因此不实现 |
| FR-AG-08 | Won't | Multi-Agent 自主协作 | 不在 MVP |

### 2.6 Evaluation and observability

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-EVAL-01 | Must | 维护 30–50 条版本化 evaluation cases | JSONL schema 校验，来源均可访问 |
| FR-EVAL-02 | Must | 计算 Hit Rate@K、Recall@K；适用时计算 MRR | 指标实现有单元测试 |
| FR-EVAL-03 | Must | 计算/标注 groundedness、citation accuracy、answer correctness | 报告包含逐题明细和聚合 |
| FR-EVAL-04 | Must | 计算 tool selection accuracy、task completion rate | Agent 测试包含 expected tools/path |
| FR-EVAL-05 | Must | 记录 latency、token usage 和估算 cost | 每个阶段和总请求均可追踪 |
| FR-EVAL-06 | Must | 比较 Baseline、Metadata、Rewrite、Reranker | 同一数据版本和模型配置下生成配对报告 |
| FR-EVAL-07 | Should | 把失败按 query/document/metadata 类型切片 | 报告包含主要失败模式 |
| FR-EVAL-08 | Should | LLM judge 结果经人工样本校准 | judge model/prompt/version 固定并记录一致率 |

## 3. Non-functional Requirements

### 3.1 Explainability and traceability

| ID | Priority | Requirement |
|---|---|---|
| NFR-EXP-01 | Must | 每个事实性 claim 至少映射一个 citation；无法映射的内容必须标为推断/建议或删除 |
| NFR-EXP-02 | Must | 每次请求可通过 trace ID 找到 query、filters、retrieved chunks、工具调用、模型配置和最终输出 |
| NFR-EXP-03 | Must | 每个实验记录 corpus version、dataset version、embedding/reranker/LLM、参数和代码 revision |
| NFR-EXP-04 | Should | 对 Query Rewrite 同时显示原查询和重写结果，便于诊断语义漂移 |

### 3.2 Performance

初始目标针对 6 vCPU / 15 GiB / CPU-only VM，须由 Phase 1/2 基准校准：

| ID | Priority | Requirement |
|---|---|---|
| NFR-PERF-01 | Must | P95 retrieval（不含生成）初始目标 ≤ 1.5 s，样例语料规模下测量 |
| NFR-PERF-02 | Should | P95 端到端简单问答初始目标 ≤ 12 s，排除供应商故障 |
| NFR-PERF-03 | Must | ingestion 批处理不因单个坏文档终止整个批次 |
| NFR-PERF-04 | Must | 超时、模型不可用和 Qdrant 不可用有明确错误与有限重试，不无限等待 |

### 3.3 Testability and maintainability

| ID | Priority | Requirement |
|---|---|---|
| NFR-TEST-01 | Must | parser、chunker、metadata、citation、metrics 有确定性单元测试 |
| NFR-TEST-02 | Must | Qdrant、LLM adapter、Agent tools 有集成/contract tests，可使用 fake adapter |
| NFR-TEST-03 | Must | 核心业务接口与 LangGraph、Qdrant SDK、具体 LLM SDK 解耦 |
| NFR-TEST-04 | Should | 固定随机种子、温度和配置，允许评测结果在合理容差内重现 |
| NFR-TEST-05 | Must | 错误使用稳定 code 分类：validation、parse、retrieval、provider、timeout、insufficient_evidence |

### 3.4 Extensibility

| ID | Priority | Requirement |
|---|---|---|
| NFR-EXT-01 | Must | Embedding、VectorStore、Reranker、LLM 通过 Protocol/ABC adapter 可替换 |
| NFR-EXT-02 | Must | 工具 schema 与实现分离，未来可映射到 MCP，但 MVP 不依赖 MCP |
| NFR-EXT-03 | Should | 新文档类型可通过 parser registry 加入 |
| NFR-EXT-04 | Could | 多租户/ACL 在 metadata 与 query policy 层保留扩展点，但不提前实现 |

### 3.5 Data isolation and security boundary

| ID | Priority | Requirement |
|---|---|---|
| NFR-SEC-01 | Must | 只使用公开或模拟数据；禁止真实公司/客户私有资产 |
| NFR-SEC-02 | Must | secrets 仅来自环境变量，本地 `.env` 不提交 |
| NFR-SEC-03 | Must | ingestion 路径限定在配置的 data root，拒绝路径穿越和符号链接越界 |
| NFR-SEC-04 | Must | 文档内容视为不可信数据；其中指令不得改变 Agent policy 或触发工具 |
| NFR-SEC-05 | Must | 默认日志不记录完整文档正文、API key 或敏感 prompt payload |
| NFR-SEC-06 | Must | Agent tools 为只读 allowlist，无 shell、代码执行或通用 HTTP fetch |
| NFR-SEC-07 | Should | 为未来 ACL 预留 `tenant_id`/`access_scope` 字段，但单租户 MVP 使用固定值 |

## 4. API-level Output Contracts

关键结果至少包含：

```json
{
  "request_id": "...",
  "status": "answered | insufficient_evidence | failed",
  "answer": "...",
  "claims": [
    {
      "text": "...",
      "citation_ids": ["cit-1"]
    }
  ],
  "citations": [
    {
      "citation_id": "cit-1",
      "document_id": "...",
      "document_version": "...",
      "title": "...",
      "page": 12,
      "section": "...",
      "chunk_id": "...",
      "quote": "..."
    }
  ],
  "used_tools": ["search_knowledge_base"],
  "warnings": [],
  "metrics": {
    "latency_ms": 0,
    "input_tokens": 0,
    "output_tokens": 0
  }
}
```

字段细节可在实现中调整，但 `status`、claim-citation 关系、来源定位和 trace 不可删除。

## 5. Definition of Done for a Requirement

一个需求只有同时满足以下条件才算完成：

1. 实现与设计文档一致，或 ADR 明确记录变更理由；
2. 对应自动化测试通过；
3. 若影响检索/回答质量，评测报告包含新旧对比；
4. 错误路径和日志可观察；
5. README 或相关文档更新；
6. 未引入超出项目边界的数据或工具权限。

