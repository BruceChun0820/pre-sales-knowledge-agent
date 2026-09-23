# Pull Request Template

## Phase and Tasks

- Phase:
- Task IDs:
- Remote repository:
- PR URL:
- Source branch:
- Target branch: `main`
- Head commit SHA:
- PR status: Draft / Open

## Scope Implemented

列出本 PR 完成的已批准内容。

## Files / Modules Changed

列出主要文件、公共接口和配置变化。

## Acceptance Criteria Evidence

| AC ID | PASS / FAIL | Evidence |
|---|---|---|
| | | |

## Quality Gates

| Gate | PASS / FAIL | Command / Evidence |
|---|---|---|
| Format check | | |
| Lint | | |
| Unit tests | | |
| Integration tests | | |
| Secret/private-data check | | |
| Remote CI/checks | | |

## Remote PR Checklist

- [ ] `origin` 指向已批准的远程私有仓库
- [ ] source task branch 已 push 并设置 upstream
- [ ] PR target 是 `main`
- [ ] PR URL 可由 PM/QA 访问
- [ ] 当前 head SHA 与本地提交一致
- [ ] PR 描述包含 Task IDs、AC 对照、测试结果和已知限制
- [ ] Dev 没有自行 merge PR

## Architecture / Data Impact

- Public interfaces changed:
- Metadata/schema changed:
- Storage/index changed:
- New dependency/service:
- Migration/rebuild required:

## Deviations and Open Issues

写明任何未实现、阻塞、已知限制或需要 PM 决策的事项。没有则写 `None`。

## Reproduction and Rollback

- How to run/verify:
- How to reset test data:
- How to roll back:

## Dev Declaration

- [ ] 只实现了批准的 Task Scope
- [ ] 未提交 secret、私有数据、模型或运行时存储
- [ ] 未绕过失败测试或降低 Acceptance Criteria
- [ ] 文档与实现一致
- [ ] 已将 PR 提交到远程批准仓库，未仅保留本地提交
