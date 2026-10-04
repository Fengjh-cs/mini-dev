# mini-dev

一个极简 CLI coding agent（简历项目）。核心思路：**自己实现 agent 循环 / 文件编辑 / 上下文管理**，其余（CLI 界面、沙箱、diff、语法解析）复用成熟开源组件。

## 状态

- [x] Phase 0 — 项目脚手架
- [x] Phase 1 — 最小 agent loop（读文件 + 跑命令）
- [x] Phase 2 — 结构化编辑（write_file / edit_file + 快照回滚）+ 沙箱执行
- [x] Phase 3 — RepoMap 仓库上下文压缩（tree-sitter）
- [x] Phase 4 — Plan/Act 双模式 + 权限审批
- [ ] Phase 5 — 打磨（MCP / demo / 评测）★ 当前

## 快速开始

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # macOS/Linux 用 .venv/bin/python
cp .env.example .env                              # 填入 OPENAI_API_KEY
.venv/Scripts/python -m pytest -q                 # 运行测试
```

## 使用

```bash
mindev run "读一下 README.md，用一句话总结它讲了什么"
mindev run "列出当前目录的文件"
```

> 默认模型 `gpt-5-mini`（可用 `MINIDEV_MODEL` 环境变量覆盖；`gpt-5` 系列里带 `-codex` 的模型需更高权限，普通账号无访问权限）。
> 支持任意 OpenAI 兼容后端：设 `OPENAI_BASE_URL` 即可切换 DeepSeek（`https://api.deepseek.com`）、OpenRouter（`https://openrouter.ai/api/v1`）等。
> 命令默认在宿主机执行（`--sandbox local`）；加 `--sandbox docker` 可在 Docker 容器里跑（进程/网络隔离，需本机已装 Docker）。
> 每次运行会自动用 tree-sitter 生成 RepoMap（文件树 + 顶层函数/类 + 行号）注入系统提示词，加 `--no-repomap` 可关闭。
> 加 `--plan` 进入只读规划模式（不改文件、不跑命令，只产出方案）；默认对写文件/跑命令做交互确认，加 `--yes` 跳过确认。

## 架构

详见 [DESIGN.md](DESIGN.md)。
