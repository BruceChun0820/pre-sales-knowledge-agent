# RAG Design

## 1. Objectives

RAG 子系统的首要目标不是“给 LLM 填充更多文本”，而是稳定提供：

1. 与问题相关且范围正确的证据；
2. 可定位、可验证的来源；
3. 可测量的候选排名与失败原因；
4. 在证据不足时可拒答的边界。

端到端流程：

```text
Document
  -> Parsing
  -> Cleaning
  -> Chunking
  -> Metadata
  -> Embedding
  -> Vector Store
  -> Query Processing
  -> Retrieval
  -> Reranking (optional)
  -> Context Construction
  -> Answer
  -> Citation Validation
```

## 2. Document and Parsing

### 2.1 Supported inputs

- PDF：PyMuPDF，提取 page、block、bbox（可用时）和文本；
- DOCX：python-docx，提取 heading、paragraph、table 与顺序；
- Markdown：保留 heading hierarchy、list 和 code/table boundary；
- TXT：按段落和行号定位。

### 2.2 Parse output

Parser 不直接输出最终 chunks，而输出统一 `ParsedBlock`：

```text
document_id
document_version
block_id
block_type: heading | paragraph | table | list | caption
text
page / section_path / paragraph_index
order
parser_name + parser_version
```

这使 cleaning 和 chunking 不依赖原始格式。

### 2.3 Parsing quality gates

- 空文本比例、乱码比例、异常短页；
- 页码/章节定位完整度；
- 数字、百分比、型号、否定词抽样比对；
- 表格转文本后列关系是否保留；
- 重复页眉页脚识别是否误删正文。

如果数字文本提取不足，标记 `needs_ocr`，MVP 默认不自动 OCR。

## 3. Cleaning

允许的清洗：

- Unicode normalization；
- 合并 PDF 断行与被拆开的单词（使用保守规则）；
- 压缩多余空白；
- 删除跨多页重复且位置稳定的页眉页脚；
- 保留列表、标题和表格边界标记。

禁止的“清洗”：

- 用 LLM 改写原文作为索引正文；
- 自动补全缺失句子；
- 删除“不支持、除外、仅限”等限制词；
- 把多个来源合成无法追溯的新文档。

保存 `cleaner_version` 和内容 checksum。必要时保留 cleaned text artifact 供调试，但它必须可由 raw 重建。

## 4. Chunk Strategy

### 4.1 Recommended strategy: structure-aware, token-bounded

优先按 heading/paragraph/list/table 分组，再应用 token 上限：

1. 每个 chunk 带上短的 section path；
2. 尽量不跨越顶层章节；
3. 短的相邻段落可合并；
4. 超长 block 以句子边界递归切分；
5. 表格按“表头 + 行组”切分，表头在每个 table chunk 重复；
6. overlap 仅用于被窗口切开的长段落，不在完整章节间机械重复。

### 4.2 Experiment ranges, not best parameters

不预设唯一最佳值。第一轮候选：

| Config | Target tokens | Overlap | Purpose |
|---|---:|---:|---|
| C1 | 256 | 32 | 高定位精度、较多 chunks |
| C2 | 512 | 64 | 默认候选，平衡语义完整性与定位 |
| C3 | 768 | 96 | 适合长政策/方案段落，观察噪声和成本 |
| C4 | structure-only with max 512 | conditional | 测试结构优先是否优于固定窗口 |

实际 token 使用 embedding model tokenizer 计算。Overlap 应以句子/段落边界实现，不能截断在半句话。

### 4.3 How to select

在固定 evaluation dataset 上比较：

- Hit Rate@5、Recall@10、MRR；
- citation 定位是否过宽；
- context token 数和重复率；
- ingestion chunk 数、index size；
- answer groundedness/correctness；
- 各文档类型切片表现。

若 config 对某类文档明显不同，可支持按 `document_type` 的少量策略，不为每个文档手调。

## 5. Metadata Schema

### 5.1 Required document-level fields

| Field | Type | Source | Notes |
|---|---|---|---|
| `tenant_id` | string | system | MVP 固定 `demo`；查询强制注入 |
| `document_id` | string | manifest | 稳定 ID，不使用可变文件名 |
| `document_version` | string | manifest | checksum/显式版本派生 |
| `title` | string | explicit/parser | 可人工修正 |
| `source_uri` | string | loader | 项目内相对路径或公开 URL |
| `document_type` | enum | explicit | product_guide, solution, case_study, proposal, rfp, implementation_guide, other |
| `industry` | list[string] | explicit | 受控词表，未知为空 |
| `products` | list[string] | explicit | 受控/规范化名称 |
| `language` | string | detector/explicit | zh, en, mixed |
| `published_at` | date/null | explicit | 不从模糊文本猜测 |
| `active` | bool | ingestion | 默认只检索 active |
| `confidentiality` | enum | explicit | public, synthetic；MVP 不允许 internal |

### 5.2 Required chunk-level fields

```text
chunk_id, chunk_index, text_checksum,
page_start, page_end, section_path, paragraph_start,
parser_version, cleaner_version, chunker_version,
embedding_model, embedding_dimension
```

### 5.3 Filter rules

- `tenant_id`、`active` 由系统强制；
- industry/document_type/product 可由用户或 tool schema 指定；
- 模型推断出的 filter 必须通过 enum normalization；
- 过窄 filter 导致零结果时，不静默取消；返回 zero-result，并可建议用户确认放宽范围；
- 对 filterable fields 建 Qdrant payload index。

## 6. Embedding and Vector Store

### 6.1 Embedding records

每个 index/collection 必须保证一个 embedding space，不混合模型或维度。记录：

- model ID + revision；
- tokenizer/max length；
- query/document instruction；
- normalization；
- vector dimension；
- batch size、device、dtype；
- corpus and pipeline version。

模型变更通过新 collection alias 或 versioned collection 重建，不原地混写。

### 6.2 Qdrant layout

Phase 1 使用一个 versioned collection 存 chunks。Point ID 需确定性生成。Payload 保存 metadata 和定位；是否保存完整 chunk text由安全/调试需要决定，MVP 可保存模拟数据正文。

推荐 collection naming：

```text
pre_sales_chunks_<embedding_key>_<pipeline_version>
```

应用通过 logical alias 访问 active collection，切换前验证 count、payload 和 smoke queries。

## 7. Query Processing

### 7.1 Deterministic normalization

- trim、Unicode normalization；
- 保留产品型号、数字、版本号和 quoted phrases；
- 解析用户显式 industry/document_type/product filters；
- 识别任务类型：fact, search, compare, summarize, outline；
- 不删除否定词和限制条件。

### 7.2 Query Rewrite

Rewrite 属于实验 B，不是默认：

- 输入 original query、受控 glossary、任务类型；
- 输出一个 `semantic_query`，可选 `keyword_queries` 与 normalized filters；
- 不添加用户未表达的产品事实；
- 不覆盖 original query；
- 限制为一次 rewrite，不递归扩写；
- 评测语义漂移和 zero-result recovery。

适合：口语化问题、缩写、上下文依赖、过长复合问题。不适合精确型号/原文短语，可保留原查询并行检索。

## 8. Retrieval

### 8.1 Dense baseline

Baseline 只使用 query embedding + cosine/dot product（按模型推荐）检索。每个 hit 返回：

```text
chunk_id, rank, raw_score, document metadata, source location, text
```

保留 raw ranking，以便后续策略可配对比较。

### 8.2 Top-K as experiment variables

区分：

- `candidate_k`：初检候选数量；
- `rerank_k`：送入 cross-encoder 的数量；
- `context_k`：最终进入 LLM 的 chunks；
- `max_context_tokens`：最终硬预算。

初始实验范围而非承诺值：

- no reranker：candidate_k/context selection 在 5、8、12 比较；
- reranker：candidate_k 20/40，rerank 后 context_k 5/8；
- 每个文档最多 chunks 和 source diversity 也应纳入实验。

不要仅增加 K 追求 recall，因为会提高上下文噪声、token 成本和错误引用风险。

### 8.3 Metadata filtering

Experiment A：在相同 dense model 下比较无 filter 与正确 filter。评估：

- scoped queries 的 Hit@K/Recall@K；
- 错误/过窄 filter 的 zero-result rate；
- filter inference accuracy；
- latency。

### 8.4 Is hybrid search needed?

初始不启用。以下失败模式达到可观测比例后再加入：

- 产品型号、版本号、缩写和精确术语被 dense search 漏掉；
- 关键专有名词的 lexical match 明显有价值；
- evaluation dataset 的 keyword-heavy slice 显著落后。

若启用：

- Qdrant dense + sparse named vectors；
- 使用 RRF/DBSF 等 rank-level fusion，避免未归一化 raw score 线性相加；
- 作为独立 Experiment D，不与 Query Rewrite/Reranker 同时变更多个因素。

## 9. Reranking

Reranker 接收 original/rewritten query 与 top candidates，输出 pair score 和新 rank。

规则：

- 不改变 metadata filter 范围；
- 不生成新文本或新来源；
- 保留 dense rank 与 rerank rank；
- CPU batching、max pair length 和 timeout 可配置；
- 失败时可降级，但 response/report 必须标记；
- 只在 quality-latency trade-off 优于 baseline 时默认开启。

## 10. Context Construction

Context Builder 是确定性组件：

1. 去除相同/高度重叠 chunk；
2. 必要时合并同一文档相邻 chunks；
3. 保持 source diversity，避免一个文档占满上下文；
4. 分配稳定 citation IDs，如 `[S1]`；
5. 放入 title、version、page/section 和正文；
6. 在 token budget 内按 rank/coverage 选择；
7. 对 compare 任务按方案分组，确保每个被比较对象有证据；
8. 保存 selected/not-selected reasons 供评测。

模型不可看到未选中的 source metadata，也不能引用不存在的 citation ID。

## 11. Answer and Citation Strategy

### 11.1 Structured generation

生成输出包含：

- `status`；
- `answer`；
- `claims[]`：每个 claim 绑定 citation IDs；
- `assumptions[]`；
- `unknowns[]`；
- `citations_used[]`。

对 comparison/proposal 使用专门 schema，不强迫所有任务返回同一自由文本格式。

### 11.2 Citation identity

Citation 最终映射：

```text
citation_id
document_id + document_version
title + source_uri
page range or section_path
chunk_id
supporting quote/snippet
```

引用片段从 source chunk 截取，不让 LLM自行生成 quote。

### 11.3 Citation validation

至少执行确定性检查：

- citation ID 存在于提供上下文；
- document/version/chunk 仍有效；
- quote 是 chunk 的规范化子串；
- 每个事实性 claim 有引用；
- comparison 的每个对象有对应来源。

语义 support 可由人工标签或 LLM judge 辅助，但不能替代上述 checks。

## 12. Refusal and Insufficient Knowledge

以下情况返回 `insufficient_evidence`：

- 没有候选通过校准后的 relevance/sufficiency gate；
- 用户要求的 filter 范围内没有资料；
- 多跳问题的关键子问题缺少来源；
- 来源冲突且无法从版本/权威性规则确定；
- citation validation 无法支持核心 claims；
- retrieval service 不可用（错误类型不同，但不能 fallback 到模型常识）。

拒答格式应包含：

- 当前无法确认的具体事项；
- 已检索范围和 filters；
- 可选澄清问题或建议补充的资料类型；
- 不输出猜测性的企业事实。

## 13. Versioning and Reproducibility

每个 evaluation result 必须记录：

```text
corpus_version
manifest_checksum
parser/cleaner/chunker config
embedding model + revision
Qdrant collection/alias
query processor config
candidate_k/rerank_k/context_k
reranker model + revision
LLM model + parameters
prompt/schema version
evaluation dataset version
code revision
```

任何影响 chunk IDs 或 embedding space 的改变触发重建；不允许把不同配置结果混入同一报告而不标记。

## 14. Initial Experiment Matrix

| ID | Retrieval | Filter | Rewrite | Rerank | Question answered |
|---|---|---|---|---|---|
| B0 | Dense | No | No | No | 最简 baseline 能到什么水平？ |
| A1 | Dense | Yes | No | No | 明确范围能否提高 scoped query？ |
| B1 | Dense | Conditional | Yes | No | rewrite 是否提升模糊问题且不漂移？ |
| C1 | Dense | Conditional | Best of B | Yes | reranker 的质量增益是否值得 CPU 延迟？ |
| D1 optional | Dense + sparse | Conditional | Best | Optional | 精确词问题是否仍需要 hybrid？ |

一次实验只改变一个主要因素。首先优化 retrieval，再评估 answer generation，防止 LLM 掩盖检索缺陷。

