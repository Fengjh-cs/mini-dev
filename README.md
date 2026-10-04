# mini-dev

一个极简 CLI coding agent（简历项目）。核心思路：**自己实现 agent 循环 / 文件编辑 / 上下文管理**，其余（CLI 界面、沙箱、diff、语法解析）复用成熟开源组件。

## 状态

- [x] Phase 0 — 项目脚手架（本提交）
- [ ] Phase 1 — 最小 agent loop（读文件 + 跑命令）
- [ ] Phase 2 — apply_patch 结构化编辑 + 沙箱执行
- [ ] Phase 3 — RepoMap 仓库上下文压缩
- [ ] Phase 4 — Plan/Act 双模式 + 权限审批
- [ ] Phase 5 — 打磨（MCP / demo / 评测）

## 快速开始

```bash
python -m venv .venv
# Windows: .venv/Scripts/python -m pip install -e ".[dev]"
# macOS/Linux: .venv/bin/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest -q   # 运行测试
mindev --help                       # 查看帮助
```

## 架构

详见 [DESIGN.md](DESIGN.md)。
