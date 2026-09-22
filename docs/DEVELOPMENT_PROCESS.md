# Development Process

## 1. Purpose

本文定义 Pre-sales Knowledge Agent 的 Phase、Task、Git、Dev、QA 和验收流程。所有开发活动必须能映射到已批准的 Phase 文档和 Task ID。

## 2. Roles and Decision Rights

| Role | Responsibilities | Must not do |
|---|---|---|
| Product Manager / System Architect / Project Manager | 维护 Scope、需求、架构、Phase、Task、Acceptance Criteria；处理变更；接受或拒绝 Phase | 不绕过 QA 接受实现，不在未评估影响时扩大 Scope |
| Developer | 按 Dev Handoff 实现指定 Task，补充测试和证据，报告阻塞或架构偏差 | 不自行增加功能、改变公共架构或直接在 `main` 开发 |
| QA | 按 PM 定义的 Acceptance Criteria 验证并记录 PASS/FAIL | 不重新定义需求，不用主观“看起来可以”替代证据，不直接修改 production code |

同一人员可以在个人项目中承担多个角色，但每次交接仍需留下独立、可审计的文档和结果。

## 3. Phase Lifecycle

```text
PM defines Phase and handoffs
        -> Dev implements approved Tasks
        -> Dev pushes task branch to approved remote
        -> Dev opens remote PR/evidence
        -> PM scope/architecture review
        -> QA executes acceptance plan
        -> Dev fixes failed criteria on same scope
        -> QA re-tests
        -> PM accepts Phase
        -> dev is merged to main
```

### 3.1 Phase entry requirements

开发开始前必须存在：

- `docs/phases/PHASE-XX.md`；
- 可独立验收的 Task IDs；
- PASS/FAIL Acceptance Criteria；
- Quality Gates；
- Dev Handoff；
- QA Handoff；
- 所有已知关键决策或 open decision。

缺少任一项时，Phase 状态为 `NOT READY`。

### 3.2 Phase statuses

- `PLANNED`：范围已写但未批准开发；
- `READY FOR DEV`：输入、Task、验收标准完整；
- `IN DEVELOPMENT`：Dev 正在实现；
- `READY FOR QA`：Dev 自检与质量门禁通过；
- `QA FAILED`：至少一个 Must acceptance criterion 失败；
- `QA PASSED`：QA 证据完整且所有 Must criteria 通过；
- `ACCEPTED`：PM 确认范围、架构与 QA 结果后接受；
- `BLOCKED`：外部依赖或待决策问题阻止推进。

## 4. Git Branching Policy

### 4.1 Permanent branches

- `main`：稳定、已验收的基线。禁止直接开发和未经 QA 的合并。
- `dev`：当前开发集成分支。所有 feature/task 分支以它为基线并合回它。

### 4.2 Task branches

命名：

```text
feature/phase-01-task-03-document-parsers
fix/phase-01-task-03-corrupt-pdf-handling
docs/phase-01-clarify-metadata-contract
```

每个分支应覆盖一个可独立评审的 Task 或紧密相关的小批 Tasks。禁止在一个 PR 中混入无关重构。

### 4.3 Merge flow

1. 从最新 `dev` 创建 task branch；
2. 实现指定 Task，提交测试和文档；
3. 确认 `origin` 指向用户批准的远程私有仓库；缺失或错误时停止并反馈 PM；
4. 将 task branch 推送到 `origin`，设置 upstream；
5. 创建远程 PR，source 为 task branch，target 必须为 `dev`；
6. Dev 自检 Quality Gates，并在 PR 描述中提交证据；
7. PM 检查 scope/architecture 和 PR metadata；
8. QA 通过远程 PR 对应 commit 按 handoff 验收；
9. 未通过则在同一 task branch 修复并 push，QA 对新 commit re-test；
10. Phase 全部 QA PASSED 后，由 PM 批准 `dev -> main` 的独立 PR；
11. 不允许绕过 QA、直接 push feature commit 到 `main`、或由 Dev 自行 merge。

远程仓库必须是已批准的 repository。Dev 不得在 Task 流程中创建新仓库、改变仓库可见性或公开代码。

## 5. Commit and PR Requirements

### 5.1 Commit

提交信息建议：

```text
type(scope): concise outcome
```

例如：`feat(ingestion): add deterministic document manifest`。

Commit 应：

- 原子化且可解释；
- 不包含 secret、模型缓存、向量存储或大数据文件；
- 不使用“temp/final/fix stuff”等无法追踪的描述；
- 不改写已共享历史，除非负责人明确批准。

### 5.2 PR evidence

每个 Dev PR 必须说明：

- 远程 PR URL；
- remote repository full name；
- source branch、target branch（必须为 `dev`）；
- PR head commit SHA；
- Phase 与 Task IDs；
- 实际变更文件；
- Acceptance Criteria 对照；
- 执行的测试与原始结果摘要；
- lint/format/type checks；
- 远程 CI/check 状态与链接（如仓库已配置）；
- 数据、配置或架构影响；
- 已知限制与未完成项；
- 是否存在 Scope/Architecture deviation；
- 回滚方式。

模板见 `docs/pr/PR_TEMPLATE.md`。

### 5.3 Remote PR rules

- PR 必须从远程可访问的 task branch 创建，不能只提供本地 commit hash。
- PR target 必须是 `dev`；误指向 `main` 的 PR 不进入 QA。
- PR 必须锁定/显示被 QA 验收的 head commit；Dev push 新 commit 后必须通知 QA 重新确认。
- PR 描述必须保留 Task、AC、测试命令和已知限制；不能用“已测试”替代结果。
- GitHub Actions 或其他远程检查失败时，PR 状态为 `NOT READY FOR QA`，除非 PM 明确记录豁免。
- QA 只验收 PR 当前 head，不验收开发者本地未 push 的改动。
- PM 只在 QA PASSED 后批准合并；Dev 不得自批准、自合并或删除审计证据。
- Phase 完成后，`dev -> main` 使用独立 PR，必须引用 Phase QA 结果和 PM 接受决定。

## 6. Scope and Change Control

Dev 或 QA 发现以下情况时必须停止相关 Task 并反馈 PM：

- Acceptance Criteria 无法客观测试或互相冲突；
- 需要改变公共 interface、metadata schema、collection layout 或模块边界；
- 需要新增外部服务、付费 API 或高权限工具；
- 需要使用真实公司/客户数据；
- 实现会超出 Phase Out of Scope；
- 当前 Python/依赖环境无法满足约束；
- 需要降低 citation、安全或可追踪性要求。

PM 处理方式：澄清原需求、修改 Phase/Task、记录技术决策，或将内容移入后续 Phase。禁止用“顺便做了”绕过变更控制。

## 7. Technical Decision Format

重要决策必须记录：

1. **Problem**：要解决的具体问题；
2. **Options**：至少两个可行方案；
3. **Decision**：选择什么；
4. **Reason**：与当前业务和约束的关系；
5. **Trade-off**：得到和放弃什么，后续何时重新评估。

触发条件包括：新增基础设施、改变持久化模型、替换核心框架、修改安全边界、改变兼容版本或引入外部数据服务。

## 8. Definition of Ready for Development

Task 只有满足以下条件才可进入开发：

- Goal、Input、Expected Output 明确；
- Technical Constraints 与 Dependencies 已列出；
- Acceptance Criteria 可执行且可判 PASS/FAIL；
- Required Files/Modules 或允许的模块范围明确；
- Forbidden Changes 明确；
- 测试数据可获得且符合数据边界；
- 影响架构的 open decision 已关闭，或 Task 明确是 decision spike。

## 9. Definition of Ready for QA

Dev 在交给 QA 前必须提供：

- 远程 PR URL、repository、source/target branch 和当前 head SHA；
- Task IDs 与变更摘要；
- 所有 required automated checks 已通过；
- 测试命令和结果；
- Acceptance Criteria 自检表；
- 环境启动/重置步骤；
- 已知限制；
- 无 secret、大文件、私有数据的检查结果。

任何 Must check 失败时不得标记 `READY FOR QA`。

## 10. Definition of Done

Task 完成需要：

- 实现只覆盖批准 Scope；
- 自动化测试与适用的 integration test 通过；
- Acceptance Criteria 有可审计证据；
- Quality Gates 全部通过；
- 文档、配置样例和公共接口说明更新；
- QA 对 Must criteria 给出 PASS；
- PM 确认无未批准架构偏差。

Phase 完成还需要全部 Tasks Done、跨 Task 集成验收通过，并由 PM 接受后合入 `main`。

## 11. QA Finding and Re-test Policy

QA finding 至少包含：

- finding ID；
- 对应 AC/Task；
- 环境与前置条件；
- 可重复步骤；
- expected vs actual；
- 日志/截图/输出；
- severity：Blocker / Major / Minor；
- re-test status。

如果 QA 认为 Acceptance Criteria 本身错误或缺失，不直接修改标准；将状态标记为 `REQUIREMENT ISSUE` 并反馈 PM。PM 更新文档后，QA 按新版本重新执行。

## 12. Security and Data Rules

- 只使用公开或自建模拟数据；
- `.env`、API key、token、密码不得提交；
- 不提交模型文件、Qdrant storage、原始大文件和生成缓存；
- 文档内容按不可信输入处理；
- 无 PM 批准不得增加 shell、任意 HTTP、CRM、文件写入等 Agent tools；
- 不得创建新远程 repository、改变可见性或对外发布；只能使用已批准的远程仓库。
