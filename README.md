# teach-guard-ai · 教学守护 AI 助手

- **定位**：把授课视频变成可核对的检查报告（单视频精查 + 目录批量扫描）的工程仓
- **形态**：本地 CLI；无账号、无门户
- **标准与方法上游**：私有业务文档仓（口径以那边为准；本仓只保留工程所需摘要）
- **关系**：本仓是课评流水线的**替代产品**；全新实现，不复制前身仓代码

> 本仓负责**可运行流水线**。好课标准、带教路径与言行底线在上游文档仓，不在这里另起一套。本仓为 public 仓库，文档不写维护者真名、所在机构或对外品牌名。

---

## 1. 目标（分期）

1. **单视频核心**：抽音轨 → 转写 → 标点与结构 → 识别六课型 → 概念与示例检查 → 讲解结构 → 提升建议（分数评定后置）。
2. **单视频升级**：可导入 XMind 的结构 Markdown、讲义 Markdown、基于讲义的全屏类 PPT 幻灯片。
3. **目录批量**：时长、课型、言行底线扫描、时长与结构完整性，并生成全天扫描报告。

当前里程碑是 **M1（单视频 `inspect`）**。产品范围以 [产品 PRD](./docs/01-product/001_prd_教学守护助手产品说明.md) 为准。

当前**不做**：全员自查门户、绩效考核联动、自动判断视频是否同属一天、云端 ASR、本阶段打课研百分制分数。

---

## 2. 新会话请先读

1. [产品 PRD](./docs/01-product/001_prd_教学守护助手产品说明.md)（范围、用户、验收）
2. [上游标准引用](./docs/02-architecture/001_upstream-standards_上游标准引用.md)
3. 文档总入口：[docs/README.md](./docs/README.md)
4. [开发看板](./docs/03-delivery/001_dev-board_开发看板.md) 与 [分支与合入](./docs/03-delivery/002_devops-workflow_分支与合入.md)
5. 本仓 Cursor Rule：[`.cursor/rules/teach-guard-ai.mdc`](./.cursor/rules/teach-guard-ai.mdc)

CLI 产品命令：`teach-guard inspect <文件>` 精查单个视频（当前做到抽轨）；`teach-guard scan <目录>` 扫描授课日目录（尚未实现）。

**默认技术栈**：Python 3.12 CLI（uv）· 本地 mlx-whisper · DeepSeek API · Markdown 工具链（Prettier + prettier-plugin-zh + markdownlint）

---

## 3. Markdown 工具链

编辑器安装推荐扩展后，保存 Markdown 会自动格式化（含中英文空格）。

```bash
npm install
npm run format      # 格式化
npm run lint:md     # Markdownlint 检查
```

提交前请确保 `npm run format:check` 与 `npm run lint:md` 均通过。CI 工作流：`.github/workflows/docs-lint.yml`。

---

## 4. Python CLI

```bash
uv sync
uv run teach-guard --help
uv run teach-guard check
uv run teach-guard inspect --help
uv run teach-guard inspect <视频或音频文件>
```

课例默认放在 `data/input/`（相对路径会先看当前目录，再看这里）。`inspect` 会在 `data/output/` 下按输入的相对路径建运行目录（例如 `data/input/01_课/day01/大纲.avi` → `data/output/01_课/day01/大纲/`），写入 `manifest.json` 和同名 `mp3`。这两个目录都不入库。转写与建议报告按开发看板后续 Issue 补上。`scan` 尚未实现。

---

## 5. 隐私

- 真实学员脸、工号、未脱敏对话默认不进 Git。
- API Key、模型密钥只放本地环境变量或私钥文件（已进 `.gitignore`）。
- 对外演示用脱敏或自制样例音视频。
- public 仓库中不写维护者真名、所在机构或对外品牌名。
