# mini-dev 设计文档

> 本文档沉淀需求分析结论，是后续各阶段开发的唯一事实来源。随项目推进持续更新。

## 1. 目标与约束

- **目标**：做一个能写进简历的 CLI coding agent，体现「自己懂 agent 工程」，而非简单包一层现成 SDK。
- **技术栈**：Python 3.11+ 为主语言；LLM 走 OpenAI（底层做 provider 抽象）。
- **硬约束**：
  1. 不一开始就追求完整 agent，按 Phase 递进。
  2. 每一步完成后必须验证（单测 + 手动 smoke 场景）。
  3. 每一步完成后提交并上传 GitHub。

## 2. 核心模块

| # | 模块 | 作用 | 自研/复用 |
|---|------|------|-----------|
| 1 | Agent Loop | 组 prompt→调模型→解析 tool_use→执行工具→回灌，循环到不再调用工具 | **自研** |
| 2 | 工具系统 | 工具定义/校验/执行（name/schema/run/validate） | 半复用 |
| 3 | 上下文管理 | 决定每轮给模型看什么 + 压缩（compact） | **自研** |
| 4 | 文件编辑 | 把模型改动可靠落到文件（patch/diff）+ 回滚 | **自研** |
| 5 | 沙箱执行 | 隔离跑模型生成的命令/测试 | 复用 |
| 6 | 权限安全 | 哪些操作自动放行、哪些需审批 | 半复用 |
| 7 | 交互界面 | CLI/TUI、流式输出 | 复用 |

**自研重点 = 1、3、4**，这是「你懂 agent」的证明。

## 3. 参考架构（Claude Code vs Codex）

### Claude Code（Anthropic）
- 定位：harness + model 分离；循环 `gather context → take action → verify → repeat`，直到输出不含 tool_use。
- 工具：`Read/Edit/Write/NotebookEdit`、`Glob/Grep`、`Bash`、`WebFetch/WebSearch`、`Agent/Skill`、`TodoWrite`、`Task`、`Plan` 等。
- 扩展：subagents（`.claude/agents/*.md`，最多 3 层）、skills、hooks、commands、plugins、MCP。
- 上下文压缩：先清旧 tool output，再摘要；`/compact`。
- 沙箱：可选、OS 级、仅 shell；文件工具/MCP/hooks 在沙箱外。
- 文件编辑：`Edit`（字符串替换）+ `Write`（覆盖），编辑前快照支持 `/rewind`。

### OpenAI Codex
- 定位：harness + environment（沙箱/本机/Docker）分离；"keep going until resolved" + `update_plan` 追踪。
- 工具：内建 runtime 工具 `shell / apply_patch / update_plan / web_search / view_image`。
- 扩展：subagents（TOML 定义）、skills、hooks、plugins、MCP。
- 上下文压缩：`model_auto_compact_token_limit` + 90% clamp（不可完全关闭）。
- 沙箱：核心强制、覆盖所有动作，`read-only / workspace-write / danger-full-access`。
- 文件编辑：**`apply_patch`（V4A 自定义 diff）为核心**。
- CLI 已 Apache-2.0 开源（Rust），可直接读 harness 源码。

### 借鉴点
- Codex 的「文件编辑收敛成一个 apply_patch 工具」——本项目编辑工具照此设计。
- Claude Code 的「checkpoint / 回滚」——编辑前快照。
- 两者都用「subagent 独立 context、返回摘要」控制上下文污染。

## 4. 参考项目（可复用/可精读）

| 项目 | 语言 | License | 复用价值 |
|------|------|---------|----------|
| Aider | Python | Apache-2.0 | **RepoMap + edit-format 抽象，个人最值得精读** |
| smolagents | Python | Apache-2.0 | CodeAgent 极简 loop，起步骨架 |
| Pi | TS | MIT | <1000 token 提示词 + 4 工具，从零复刻范本 |
| OpenHands | Python | MIT | 事件流 + Action/Observation + Docker 沙箱，学架构 |
| Cline | TS | Apache-2.0 | 上下文管理（去重+截断+摘要）+ Plan/Act |
| Gemini CLI | TS | Apache-2.0 | core/cli 分层 + tool scheduler |
| OpenCode | TS | MIT | client/server + SSE + 插件系统（体量大） |
| Codex CLI | Rust | Apache-2.0 | 官方工业级 harness，读源码 |

## 5. 可复用组件

| 类别 | 选型 | 用途 |
|------|------|------|
| LLM 接入 | `openai` SDK（后续可加 `anthropic`，做 provider 抽象） | 模型调用 + tool calling |
| CLI | `rich` + `prompt_toolkit` | 输出渲染 + REPL 输入 |
| 沙箱 | `Docker`（默认）/ `microsandbox`（Windows 强隔离） | 隔离执行 |
| 语法结构 | `tree-sitter` / `py-tree-sitter` | RepoMap、大纲、语法校验 |
| 语义 | LSP：`pyright` + `multilspy`（可选） | 定义/引用/诊断 |
| Diff | `unidiff` / `patch-ng` | 解析/应用补丁 |
| 缓存 | Anthropic/OpenAI prompt caching 前缀断点 | 省钱 |

## 6. 需自研的核心差异功能

1. **Agent Loop**（Phase 1）—— while 循环 + 解析 tool_use + 结果回灌。
2. **apply_patch 结构化编辑**（Phase 2）—— 模型输出 patch，解析/应用/回滚。
3. **RepoMap 仓库上下文压缩**（Phase 3）—— tree-sitter 把仓库压进 token 预算内的结构图。
4. **Plan/Act 双模式 + 权限**（Phase 4）—— 只读/执行分离，降低误操作面。

## 7. 目录结构

```
mini-dev/
├── README.md
├── DESIGN.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── src/mindev/
│   ├── cli.py              # 入口
│   ├── agent/              # loop.py / history.py / compact.py
│   ├── tools/              # base.py / read.py / edit.py / write.py / bash.py / search.py / registry.py
│   ├── context/            # repomap.py / prompter.py
│   ├── llm/                # base.py / openai.py / anthropic.py
│   ├── sandbox/            # base.py / docker.py
│   └── ui/                 # console.py
└── tests/
```

## 8. 分阶段计划与验收标准

| Phase | 目标 | 验收标准 | 提交点 |
|-------|------|----------|--------|
| 0 | 仓库 + 设计文档 + 空包 | `pip install -e .` 成功；`mindev --help` 打印；`pytest` 过 | `init: project skeleton` |
| 1 | 最小 loop（读文件 + 跑命令，无沙箱） | 让它读 README、跑 `ls` 并总结；`test_loop` 用 mock LLM 断言循环退出 | `feat: minimal agent loop` |
| 2 | apply_patch 编辑 + 沙箱 | 「改名某函数」diff 正确应用；`test_edit` 测解析/回滚 | `feat: apply_patch editing + sandbox` |
| 3 | RepoMap 上下文 | 大仓库 token 显著下降、能答「XX 函数在哪」 | `feat: repomap context` |
| 4 | 权限 / Plan-Act | 危险命令需确认；Plan 模式只读 | `feat: permission + plan/act` |
| 5 | 打磨 | MCP + demo + 评测 + README 截图 | `docs: demo + polish` |

## 9. 验证记录

- **Phase 0**：`pip install -e ".[dev]"` 成功；`pytest` 1 passed；`mindev --help` 正常打印帮助。
- **Phase 1**：`pytest` 9 passed（loop / tools 用 mock LLM 测试）；`mindev run` 无 key 时正确报错、退出码 1。
- **base_url 支持**：`pytest` 14 passed（新增 5 个 provider 测试：base_url 参数/环境变量、tool call 解析、最终文本、tool 结果回灌）。
- **Phase 2**：`pytest` 29 passed（编辑 9 + 沙箱 6，共 15 个新测试）；`mindev run --help` 显示 `--sandbox {local,docker}`。
- **Phase 3**：`pytest` 35 passed（新增 6 个 RepoMap 测试）；真实仓库 RepoMap 正确列出文件树 + 顶层符号/行号。
- **Phase 4**：`pytest` 42 passed（新增 7 个权限测试：read 放行、只读拒绝 write/command、approver 允许/拒绝、拒绝后文件不变）；CLI 显示 `--plan` / `--yes`。
- **Phase 5**：`pytest` 47 passed（MCP 3 + eval 2）；`python demo.py` 无 key 跑通 RepoMap + 脚本化 agent；新增 CI workflow + MIT LICENSE。
- **面试增强（上下文压缩 / 工具校验 / LLM-Judge / 会话持久化 / 观测追踪 / 流式 / subagent / git 检查点 / 多语言 RepoMap）**：`pytest` 79 passed（新增 32 个测试）。

## 当前隔离边界（阶段 3）

`mindev run` 每次先把当前工作树复制到独立目录；`.env` 类文件、Git 元数据、虚拟环境、常见缓存和文件系统链接不进入副本。RepoMap、主 Agent 和探索子 Agent 的文件工具都以该副本为根。命令工具只通过 Docker 运行，容器只挂载副本、禁用网络，并使用只读根文件系统；无 Docker 时可用 `--no-bash` 运行文件任务。本地 shell、宿主机 MCP 和原仓库 Git checkpoint 不参与隔离运行。副本会保留供人工审阅，不会自动合并到源仓库。

这是进程与挂载层面的隔离，依赖 Docker 的隔离能力；文件路径检查及复制过程仍有并发替换路径的竞态风险。开发机未安装 Docker 时，容器内越界写入负向测试会跳过；CI 有独立 Docker job 拉取镜像并强制执行该测试。

## 编辑后验证（阶段 4.1）

用户可重复传入 `--verify COMMAND`。一轮工具批次中有成功的文件编辑时，AgentLoop 在整批工具执行完后自动运行指定测试，并把 PASS/FAIL、退出码与截断后的输出附在最后一次成功编辑的工具响应中。每个模型工具调用仍只收到对应 ID 的一条结果。失败后模型可继续编辑、重新验证；如果最后一轮仍失败，最终答复会明确标记未通过。测试在与 bash 相同的 Docker 工作副本内执行，需预先构建带依赖的镜像。
