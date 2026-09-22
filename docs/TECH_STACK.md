# Technology Stack

## 1. Selection Principles

技术选型按以下顺序判断：

1. 是否直接支持 MVP 的业务问题；
2. 是否可在 6 vCPU / 15 GiB RAM / CPU-only Ubuntu VM 上运行；
3. 是否便于测试、替换和解释；
4. 是否能产出可追溯、可重复的评测结果；
5. 框架带来的复杂度是否小于其解决的问题。

版本号不在 Phase 0 锁死。Phase 1 将通过 dependency lock 与 smoke tests 固定版本。

## 2. Final Recommendation Summary

| Area | Recommendation | Adoption phase |
|---|---|---|
| Python | 3.13 优先；先对现有 3.14.4 做兼容性门禁 | Phase 1 |
| Dependency management | `uv` + `pyproject.toml` + lockfile（需负责人批准安装） | Phase 1 |
| API | FastAPI + Pydantic | Phase 2 |
| Agent orchestration | LangGraph，直接使用低层 graph API | Phase 4 |
| LangChain | 不作为业务核心；仅按需使用独立 provider integration | As needed |
| LLM | OpenAI-compatible client behind adapter | Phase 2 |
| Parsing | PyMuPDF、python-docx、stdlib/Markdown parser | Phase 1 |
| Embedding | BGE-M3 为质量候选；轻量 multilingual model 为 CPU baseline | Phase 1 experiment |
| Vector store | Qdrant in Docker Compose | Phase 1 |
| Reranker | BGE cross-encoder candidate；默认关闭直到实验通过 | Phase 3 |
| Evaluation | Custom deterministic harness + pytest；Ragas optional | Phase 1 onward |
| Testing | pytest + fakes/contract tests | Phase 1 onward |
| Deployment | Modular monolith + Docker Compose | Phase 1 onward |

## 3. Python Version and Environment

### Recommendation

项目目标版本优先使用 Python 3.13，并保留 `>=3.13,<3.15` 的 Phase 0 声明。当前 Ubuntu 系统 Python 是 3.14.4，不能直接假设所有 PyTorch/Transformers/embedding 依赖都有稳定 wheel。

Phase 1 的第一道门禁：

1. 在隔离虚拟环境解析候选依赖；
2. 执行 import、单次 embedding、PyMuPDF 解析和 Qdrant client smoke test；
3. 若 3.14 全部通过，则可保留 3.14；否则使用项目独立 Python 3.13，不改动系统 Python。

### Why not immediately use system Python 3.14

- ML 生态包含 native wheels，支持通常晚于 CPython 发布；
- 在系统 Python 上直接安装会污染 Ubuntu 自带环境；
- 项目需要可重现的解释器和 lockfile。

### Alternatives

- `venv + pip-tools`：成熟，但解释器管理和 lock workflow 分散。
- Poetry：功能完整，但本项目不需要额外 packaging abstraction。
- Conda：适合复杂 CUDA/native 环境；当前 CPU-only MVP 不需要其重量。

推荐 `uv` 是因为它同时处理 Python、虚拟环境、依赖解析和 lock；Phase 0 不安装它。

## 4. FastAPI: Is It Necessary?

### Decision: Yes, but not for Phase 1 ingestion

FastAPI 为 MVP 提供稳定的 demo/test boundary：

- Pydantic 强制请求、工具与响应 schema；
- OpenAPI/Swagger 可直接演示，无需先做前端；
- API 级 acceptance tests 更接近真实使用；
- 支持同步/异步 provider 调用和清晰错误映射。

### Alternatives

| Alternative | Advantages | Why not selected as primary |
|---|---|---|
| Pure CLI | 最简单，适合 ingestion/evaluation | 不适合作为交互式演示和集成边界 |
| Streamlit/Gradio | 快速得到 UI | UI 状态容易混入业务层，API contract 和自动化测试较弱 |
| Flask | 轻量、成熟 | Pydantic/OpenAPI 需要额外组合；本项目结构化输出是核心 |

结论：保留 CLI 用于离线任务；Phase 2 加 FastAPI；独立前端不属于 MVP。

## 5. LangGraph vs Hand-written Agent Loop

### Decision: staged adoption

- Phase 2 Basic RAG：使用普通 Python functions/services，不用 Agent。
- Phase 4 Agent：使用 LangGraph 表达显式 state、tool node、条件边和结束条件。

### Why LangGraph

- 能把确定性 validation/citation step 与 LLM tool selection 放在同一显式图中；
- 状态和 transition 易于测试、追踪；
- 支持未来 persistence 与 human-in-the-loop，但 MVP 不必启用；
- 比隐藏在高层 agent executor 内的循环更容易设置最大步数和错误路径。

### Why not only a hand-written loop

手写 loop 对 1–2 个工具最透明，也应先写一个最小 spike 验证工具 contract。但当 compare/summarize/proposal 引入多个状态和降级路径后，手写分支容易把 orchestration、prompt 和业务服务混在一起。

### Why not use a high-level prebuilt agent immediately

- 默认行为、prompt 和重试可能不够显式；
- 难以区分检索失败与 agent 决策失败；
- 本项目的重要产出之一是解释 graph state 与 tool contracts。

## 6. Does the Project Need LangChain?

### Decision: minimal and optional

LangGraph 本身可单独使用。领域实体、retriever、citation、evaluation 不使用 LangChain `Document` 或 chain abstraction 作为公共 contract。

允许按需采用：

- 单独的模型/provider integration；
- 已验证能减少样板代码的 text splitter 或 Qdrant adapter；
- 仅在 adapter 内使用，避免扩散到 domain/application layer。

不选择“大量 LangChain chain 组合”作为核心，因为：

- 框架对象可能掩盖 rank、score、metadata 和 trace；
- 组件版本变化会扩大维护面；
- 自定义 evaluation 与 citation 需要精确控制中间产物。

## 7. Qdrant vs Chroma vs FAISS

| Criterion | Qdrant | Chroma | FAISS |
|---|---|---|---|
| Nature | 独立/嵌入式向量数据库 | 开发友好的向量数据库 | 向量索引库 |
| Persistence | Yes | Yes | 需自行管理 |
| Metadata filter | 强，payload/filter/index | 支持，适合原型 | 需外部 metadata store 和过滤逻辑 |
| Dense + sparse/hybrid path | 原生演进路径 | 可做，但本项目控制与成熟度需验证 | 需自行组合 |
| Operational realism | 高，Docker 本地接近部署形态 | 高速原型友好 | 最轻但数据库能力缺失 |
| Debuggability | REST/client、payload 可查 | 简单 | 需要自建映射与检查工具 |

### Decision: Qdrant

业务理由是 metadata filtering、可追溯 payload 和未来 hybrid/multi-stage retrieval，而不是“更像生产”。

### Why not Chroma

Chroma 对快速 notebook 原型很好，但本项目明确要实验 filter、hybrid、rerank 和索引配置；Qdrant 提供更直接的演进路径和更清晰的 service boundary。

### Why not FAISS

FAISS 适合纯向量算法 baseline，但不负责文档 payload、持久化版本、filter 和 API。自行补齐这些能力会制造一套小型数据库。若需要验证 ANN 算法性能，可在 isolated experiment 使用，不作为主存储。

## 8. Embedding Model Selection

### Requirements

- 中文和英文售前资料；
- 产品名、缩写、版本号与自然语言概念共存；
- CPU-only 运行；
- 支持批量离线 ingestion 与低频在线 query；
- 模型、维度、normalize 和 instruction 配置可记录。

### Candidates

| Candidate | Strength | Cost/Risk | Intended role |
|---|---|---|---|
| `BAAI/bge-m3` | 多语言；支持 dense/sparse/multi-vector；长上下文；未来 hybrid 路径一致 | 模型较大，CPU latency 与内存需实测；1024-d vectors 更占空间 | 质量候选 / primary candidate |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 小、快、多语言、384-d，CPU 友好 | 主要是通用语义/相似度模型，领域检索质量可能较低 | 性能 baseline / fallback |
| BGE zh v1.5 small/base | 中文检索强、比 M3 轻 | 英文和跨语言目标较弱；上下文较短 | 中文为主时的候选 |
| Hosted embedding API | 延迟稳定、免本地模型管理，可能质量高 | 数据出境、成本、供应商依赖、可重复性 | 仅在允许时做对照实验 |

### Recommendation

不在文档阶段宣布单一“最佳模型”。Phase 1 用同一小型检索集对比：

- CPU baseline：轻量 multilingual SentenceTransformer；
- quality candidate：BGE-M3 dense mode；
- 若语料确认中文占绝大多数，再加入 BGE-zh small/base。

最终选择看 Hit@K/Recall@K、索引大小、batch throughput、query P95 和内存。BGE-M3 的 sparse/multi-vector 能力不会在 Phase 1 同时开启。

## 9. Reranker Selection

### Decision: experiment, not default

使用 Cross-Encoder 对 top-N candidates 做 query-document joint scoring，通常比 bi-encoder 排序精细，但不能预计算 pair score，CPU 成本明显更高。

候选：

- `BAAI/bge-reranker-base`：中英候选，资源相对可控；
- `BAAI/bge-reranker-v2-m3`：多语言质量候选，但 CPU 上更重；
- hosted rerank API：只有数据政策允许时对照。

进入默认路径的条件：

- 在固定 holdout 上显著提升 MRR/Recall 或 answer/citation 指标；
- P95 延迟仍在可接受范围；
- 改善不是只发生在少数重复样例；
- 失败时可降级到 baseline rank。

## 10. Document Parser

| Format | Choice | Reason |
|---|---|---|
| PDF | PyMuPDF | 快、可提取 blocks/coordinates/page，适合 citation location |
| DOCX | python-docx | 直接访问 paragraph/table/heading style；依赖小 |
| Markdown/TXT | Python stdlib + small parser | 保留 heading/line，避免重框架 |
| Scanned PDF | OCR extension later | OCR 需要额外系统依赖和质量评测，不属于 Must |

### Why not `unstructured` as default

它覆盖格式广，但依赖和 partition behavior 更复杂。MVP 文件类型有限，先用明确 parser 更便于定位 extraction error 与 source location。未来复杂版式评测证明需要时再加入。

### Parsing caveat

PDF 的文本顺序、表格和页眉页脚不天然可靠。Parser 输出必须保留 page/block 信息，且对样例做 golden extraction tests，不能把“库返回了文本”等同于“解析正确”。

## 11. Evaluation Framework

### Decision: custom harness first, Ragas optional

Custom harness 负责：

- JSONL dataset schema；
- Hit Rate、Recall、MRR、citation match、latency/cost 等确定性指标；
- 逐题 artifact 与配置快照；
- baseline/A/B/C 配对比较；
- pytest regression gates。

Ragas 可补充 faithfulness、answer correctness、agent/tool metrics，但不能成为唯一评测系统。LLM-based metrics 具有模型和 prompt 依赖，应记录 judge 配置并与人工标签校准。

### Alternatives

| Alternative | Why not primary |
|---|---|
| LangSmith | tracing/evaluation 能力强，但引入外部平台、账号和数据边界；MVP 保持本地可运行 |
| DeepEval | 适合测试式 LLM metrics；仍需自定义 retrieval/citation ground truth |
| TruLens | observability 丰富；对当前小型项目偏重 |
| Only manual review | 不可重复，无法稳定比较 retrieval experiments |

## 12. Testing and Quality Tools

- `pytest`：unit/integration/acceptance；
- `ruff`：lint + import formatting；
- optional `mypy` 或 `pyright`：接口稳定后加入；
- fake LLM/embedding/vector adapters：单元测试不依赖外部 API；
- golden files：parser/chunker/citation regression；
- Docker Compose：Qdrant integration tests 与本地演示。

Phase 0 不安装这些依赖。

## 13. References

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [FastAPI features](https://fastapi.tiangolo.com/features/)
- [Qdrant filtering](https://qdrant.tech/documentation/search/filtering/)
- [Qdrant hybrid and multi-stage queries](https://qdrant.tech/documentation/search/hybrid-queries/)
- [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3)
- [Sentence Transformers retrieve and rerank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)
- [PyMuPDF text extraction](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)
- [python-docx documentation](https://python-docx.readthedocs.io/en/latest/)
- [Ragas metrics overview](https://docs.ragas.io/en/stable/concepts/metrics/overview/)

