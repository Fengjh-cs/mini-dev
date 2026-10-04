# mini-dev

一个极简 CLI coding agent（简历项目）。核心思路：**自己实现 agent 循环 / 文件编辑 / 上下文管理**，其余（CLI 界面、沙箱、diff、语法解析）复用成熟开源组件。

## 状态

- [x] Phase 0 — 项目脚手架
- [x] Phase 1 — 最小 agent loop（读文件 + 跑命令）★ 当前
- [ ] Phase 2 — apply_patch 结构化编辑 + 沙箱执行
- [ ] Phase 3 — RepoMap 仓库上下文压缩
- [ ] Phase 4 — Plan/Act 双模式 + 权限审批
- [ ] Phase 5 — 打磨（MCP / demo / 评测）

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

> 默认模型 `gpt-5-codex`（可用 `MINIDEV_MODEL` 环境变量覆盖）。
> ⚠️ Phase 1 的命令工具**直接在宿主机上执行、无沙箱**，仅用于你自己信任的本地代码。

## 架构

详见 [DESIGN.md](DESIGN.md)。
