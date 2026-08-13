# 文档入口（teach-guard-ai）

业务愿景与好课标准在上游私有文档仓。本仓只保留工程所需摘要与契约，避免与上游长期双源漂移。

## 1. 产品（做什么、怎么验收）

请先阅读 [01-product/README.md](./01-product/README.md)。

MVP 与分期范围以 [001 PRD](./01-product/001_prd_教学守护助手产品说明.md) 为唯一产品源。

## 2. 架构与技术（怎么做、为什么）

请阅读 [02-architecture/README.md](./02-architecture/README.md)。

评价尺子从哪里来，见 [上游标准引用](./02-architecture/001_upstream-standards_上游标准引用.md)。

## 3. 交付（Issue、DevOps）

请阅读 [03-delivery/README.md](./03-delivery/README.md)。

当前只做什么见 [开发看板](./03-delivery/001_dev-board_开发看板.md)；分支与合入见 [分支与合入](./03-delivery/002_devops-workflow_分支与合入.md)。

## 4. 新会话推荐阅读顺序

1. [开发看板](./03-delivery/001_dev-board_开发看板.md)：当前只做什么。
2. [001 PRD](./01-product/001_prd_教学守护助手产品说明.md)：确认做什么、不做什么。
3. [上游标准引用](./02-architecture/001_upstream-standards_上游标准引用.md)：确认评价尺子从哪里来。
4. [分支与合入](./03-delivery/002_devops-workflow_分支与合入.md)：GitHub Flow、一 Issue 一 PR。
5. 根目录 [README.md](../README.md)：如何安装工具链与运行 `teach-guard check`。
6. 本仓 Cursor Rule：[`.cursor/rules/teach-guard-ai.mdc`](../.cursor/rules/teach-guard-ai.mdc)。新会话 Skill：`.cursor/skills/teach-guard-new-session/`。
