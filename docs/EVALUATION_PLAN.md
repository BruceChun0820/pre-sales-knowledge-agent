# Evaluation Plan

## 1. Purpose

Evaluation 是产品设计的一部分，不是开发完成后的展示。它回答三个问题：

1. 检索是否找到正确证据？
2. 回答是否忠于证据并正确引用？
3. Agent 是否选择正确工具并完成任务？

优化顺序：**Parsing/Corpus -> Retrieval -> Context -> Answer -> Agent**。上游未达标时，不用更复杂 Agent 掩盖问题。

## 2. Evaluation Layers

| Layer | Unit under test | Main metrics |
|---|---|---|
| Parsing | document -> parsed blocks | extraction completeness, location accuracy, critical token preservation |
| Retrieval | query -> ranked chunks/docs | Hit Rate@K, Recall@K, MRR, filter accuracy |
| Answer | evidence -> response | groundedness, citation accuracy, answer correctness, refusal accuracy |
| Agent | task -> tool trace/result | tool selection accuracy, task completion, step efficiency |
| System | end-to-end | latency, token usage, cost, failure rate |

## 3. Evaluation Corpus

### 3.1 Source policy

- 公开许可的产品说明、行业白皮书或开源项目文档；
- 自行构造的虚构公司产品手册、案例、方案和 RFP；
- 不使用真实公司内部文档、客户名称、MCP schema、API 或 Skill；
- 每份文档保留 source/license/provenance；
- synthetic 文档显式标记，不混称为真实案例。

### 3.2 Suggested starter corpus

目标 12–20 份文档，覆盖：

- 3 个虚构产品能力手册；
- 3–4 个行业方案（如零售、制造、金融，内容自行构造）；
- 3 个案例；
- 2 个实施/集成指南；
- 2 个 Proposal/RFP 样例；
- 2 个含相似术语、版本差异或冲突陈述的文档；
- 1 个含 prompt-injection 文本的安全测试文档。

语料不能过度重复，否则 retrieval 指标会虚高。

## 4. Evaluation Dataset: 40 Cases

建议先构造 40 条人工审核 case，并在语料稳定后冻结 v1。

| Slice | Count | Purpose |
|---|---:|---|
| 单文档事实/产品能力 | 12 | 基础 retrieval、数字/限制词、citation |
| 跨文档比较 | 8 | 多来源覆盖、冲突与维度完整性 |
| Metadata-scoped query | 6 | industry/document type/product filtering |
| 模糊/口语/缩写 query | 5 | Query Rewrite 收益与语义漂移 |
| 多文档总结 | 4 | coverage、faithfulness、source diversity |
| Proposal Outline | 3 | tool path、结构、assumption/open questions |
| Unanswerable / adversarial | 2 | refusal、prompt injection；后续可增加 |
| **Total** | **40** | |

为了更可靠评估拒答，v2 建议把 unanswerable/adversarial 扩展到总集的 15–20%。

### 4.1 Dataset split

- Development set：30 条，用于 chunk/top-k/rewrite/reranker 调整；
- Holdout set：10 条，在方案冻结前不用于调参；
- 另建 parser golden fixtures，不混入问答统计。

小数据集不宣称统计泛化；报告同时给总分、逐题结果和切片结果。

### 4.2 Case schema

```json
{
  "case_id": "capability-001",
  "split": "dev",
  "task_type": "qa",
  "question": "虚构产品 A 是否支持离线部署？有哪些限制？",
  "explicit_filters": {"products": ["product-a"]},
  "expected_document_ids": ["product-a-guide-v2"],
  "expected_source_locations": [
    {"document_id": "product-a-guide-v2", "page": 8, "section": "部署模式"}
  ],
  "reference_claims": [
    {"claim": "支持离线部署", "required": true},
    {"claim": "离线模式不包含自动云升级", "required": true}
  ],
  "forbidden_claims": ["离线模式支持自动云升级"],
  "expected_tools": ["search_knowledge_base"],
  "allowed_tool_paths": [["search_knowledge_base"]],
  "expected_status": "answered",
  "notes": "Tests condition and limitation."
}
```

Comparison、summary、outline case 可增加 `required_dimensions`、`required_documents`、`required_sections` 和 `expected_unknowns`。

### 4.3 How to construct expected sources and answers

1. 先选择来源段落，再编写问题，避免问题无 ground truth；
2. 标注所有相关文档/位置，不只标一个“最明显”来源；
3. Reference answer 拆成 atomic claims；
4. 为数字、条件、否定和版本建立 forbidden/wrong claims；
5. 对多跳问题标出每个 claim 所需来源；
6. 另一轮人工复核问题是否自然、答案是否唯一或可接受；
7. 记录 ambiguity，不强制开放问题只有一个措辞；
8. LLM 可辅助提出候选问题，但不能单独决定 ground truth。

## 5. Retrieval Metrics

### 5.1 Hit Rate@K

每个 query 的 top-K 中是否至少包含一个 expected relevant source：

```text
Hit@K(q) = 1 if topK(q) intersects relevant(q), else 0
Hit Rate@K = mean(Hit@K(q))
```

适合基础问答“至少找到一个关键证据”。同时报告 chunk-level 和 document-level，避免多个相邻 chunks 夸大表现。

### 5.2 Recall@K

```text
Recall@K(q) = |topK(q) ∩ relevant(q)| / |relevant(q)|
```

适合 compare、summary、多跳任务，因为需要覆盖多个来源。Relevant set 应以文档/位置标注，处理邻接 chunks 时采用 relevance groups，避免 chunk strategy 改变使分母失真。

### 5.3 MRR

```text
RR(q) = 1 / rank(first relevant result)
MRR = mean(RR(q))
```

适合存在明确首要答案来源的 fact/search cases。对于需要多个来源的 compare/summary，MRR 不能代表 coverage，因此只在对应 slice 报告。

### 5.4 Additional diagnostics

- nDCG@K（当 relevance 有等级时，v2）；
- filter exactness/violation count；
- zero-result rate；
- source diversity；
- duplicate chunk rate；
- relevant document rank distribution；
- context precision proxy：最终 context 中 relevant chunks 比例。

## 6. Answer Metrics

### 6.1 Groundedness / Faithfulness

把回答拆为 atomic claims，判断每个 claim 是否由 provided evidence 支持：

```text
Groundedness = supported factual claims / all factual claims
```

优先使用人工标注的 deterministic support rules/抽检；可用固定 LLM judge 批量辅助，但记录 judge model、prompt、temperature 和版本。

### 6.2 Citation Accuracy

拆成三个指标，避免单一分数掩盖问题：

- **Citation validity**：引用 ID/文档/位置真实存在；
- **Citation entailment**：引用内容支持对应 claim；
- **Citation completeness**：事实性 claims 中有支持引用的比例。

可汇总：

```text
Citation Precision = supported cited claims / all cited claims
Citation Coverage = cited factual claims / all factual claims
```

### 6.3 Answer Correctness

将 predicted claims 与 `reference_claims` 比较：

- required claim coverage；
- forbidden claim occurrence；
- 数字/实体 exact match；
- 对开放总结使用 rubric：correct / partially correct / incorrect，并保留理由。

语义相似度只能辅助，不能把措辞相似当作事实正确。

### 6.4 Refusal Accuracy

```text
Refusal precision = correct refusals / all refusals
Refusal recall = correct refusals / all expected-unanswerable cases
```

同时统计 answerable 问题被错误拒答的比例。

## 7. Agent Metrics

### 7.1 Tool Selection Accuracy

两种粒度：

- first-tool accuracy：首个工具是否正确；
- path accuracy/F1：实际工具集合/顺序是否属于允许路径。

参数也要验证，例如 compare 必须包含正确 document IDs，metadata filter 不能被遗漏。

### 7.2 Task Completion Rate

只有同时满足以下条件才算 complete：

- final status 与 expected status 一致；
- required output fields/sections 存在；
- required claims/dimensions 达标；
- citations valid；
- 无 forbidden action/claim；
- 未超过 step budget。

### 7.3 Efficiency and reliability

- mean/P95 tool steps；
- repeated-call rate；
- tool error recovery rate；
- structured output validity rate；
- agent step-limit rate。

## 8. System Metrics

按 stage 记录：

- parse time per page/document；
- embedding throughput chunks/s；
- retrieval P50/P95；
- rerank P50/P95；
- time to first/complete answer；
- end-to-end P50/P95；
- input/output tokens；
- provider-reported 或价格表估算 cost；
- Qdrant/LLM/tool failure rate；
- peak RSS（embedding/reranker benchmark）。

Cost 报告必须记录价格版本和日期；无可靠价格时只报 tokens，不伪造金额。

## 9. Baseline and Experiments

### 9.1 Baseline B0: Dense Vector Search

- 单一 embedding candidate；
- 无 metadata filter（除 tenant/active）；
- 无 rewrite；
- 无 reranker；
- 固定 candidate/context K；
- 固定 answer prompt/model。

目的：建立最小系统质量和延迟。

### 9.2 Experiment A: Metadata Filter

保持其他配置与 B0 相同，仅对有显式/正确可推断范围的 cases 应用 filter。比较 Hit/Recall、filter violations、zero-results、latency。对于没有范围的 query 不强行过滤。

### 9.3 Experiment B: Query Rewrite

以 A 的最佳配置为基础，对 rewrite slice 启用单次 structured rewrite；原查询可作为并行/回退候选。比较 retrieval delta、semantic drift、extra tokens/cost、latency、错误 filter 引入率。

### 9.4 Experiment C: Reranker

以 B 的最佳配置为基础，对 top-N candidates rerank。比较 MRR、Recall/context precision、answer/citation metrics、CPU P95、peak memory。

### 9.5 Optional Experiment D: Hybrid Retrieval

仅当 keyword-heavy slice 暴露 dense failure 时加入 dense+sparse + rank fusion。不能与首次 reranker 实验同时引入，保证因果可解释。

## 10. Experiment Protocol

每次 run：

1. 冻结 corpus、evaluation dataset、代码 revision 和 provider model；
2. 只改变一个主要变量；
3. 保存完整 config 和逐题结果；
4. 报告 overall + slice metrics；
5. 对 dev set 调参，对 holdout 只做最终比较；
6. LLM generation 使用固定 seed/temperature；若 provider 不保证确定性，对关键设置重复 3 次并报范围；
7. 使用 paired per-case delta，不只比较平均分；
8. 人工复查所有 regression 和所有 unanswerable cases；
9. 不因单一综合分上涨而忽略 citation 或 latency 回退。

## 11. Initial Acceptance Targets

这些是需在 v1 数据集后校准的起始门槛：

| Metric | Initial target | Notes |
|---|---:|---|
| Hit Rate@5 | ≥ 0.85 | fact/search cases |
| Recall@10 | ≥ 0.80 | multi-source cases |
| Citation validity | 1.00 | 确定性检查不应失败 |
| Citation precision | ≥ 0.90 | 人工/校准 judge |
| Citation coverage | ≥ 0.90 | factual claims |
| Groundedness | ≥ 0.85 | 不允许以 correctness 换 hallucination |
| Tool selection accuracy | ≥ 0.90 | first-tool + args checks |
| Task completion rate | ≥ 0.80 | Agent workflow cases |
| Answerable false refusal | ≤ 0.10 | 同时报告 unanswerable recall |

Latency 不用一个跨供应商的虚假硬阈值。先记录 baseline，再规定 reranker/rewrite 的最大可接受增量；需求文档中的 P95 目标由实际 benchmark 校准。

## 12. LLM-as-Judge Policy

- 不用于 Hit@K、Recall、MRR、ID/quote validity 等可确定计算；
- 只用于 groundedness、开放回答 correctness 等语义判断；
- judge 不看到系统配置名称，避免偏好某方案；
- 对至少 10 条、覆盖 pass/fail/borderline 的样本做人工校准；
- 报告 judge-human agreement，不一致案例人工裁决；
- judge model/prompt/version 固定，变更后重跑 baseline；
- 任何单条高风险结论不能仅由 judge 自动通过。

## 13. Reports and Regression Gates

每份实验报告包括：

```text
experiment_id / hypothesis
dataset + corpus versions
full configuration
aggregate and slice metrics
per-case results
latency/token/cost
regressions and failure taxonomy
decision: adopt / reject / investigate
```

CI 的小型 deterministic subset 可检查 parser golden、retrieval IDs、citation validity、tool schema。完整含 LLM 的评测由显式命令运行，避免每次测试产生不可控成本。

## 14. Failure Taxonomy

- parse order/layout error；
- source location missing；
- chunk too small/large；
- relevant document not retrieved；
- correct document retrieved but wrong passage；
- metadata filter missing/wrong/too narrow；
- query rewrite drift；
- reranker regression；
- context truncation/duplication；
- unsupported answer claim；
- wrong/missing citation；
- incorrect refusal；
- wrong tool/arguments/path；
- provider/timeout/schema failure；
- prompt injection/tool policy violation。

每次改进应针对主要失败类别，而不是无目的增加组件。

