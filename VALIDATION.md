# mini-dev 真实验证清单（P0）

> 目标：让 mini-dev 用真实模型跑起来，拿到能写进简历的真实数据。
> 前置：已充值额度（推荐 DeepSeek，几块钱即可跑很多次）。
> 完成后把「记录汇总」里的真实数字填回 README 和简历。

## 0. 配 DeepSeek

1. 注册并充值：https://platform.deepseek.com
2. 拿到 API Key
3. 在项目根目录建 `.env`（参考 `.env.example`）：

```bash
OPENAI_API_KEY=sk-你的deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com
MINIDEV_MODEL=deepseek-chat
```

> **模型选择原则**：选「chat / 通用类（支持 function calling）」的模型，**不要**选「reasoner / 推理类」——后者（R1、V3.2-Speciale 等）在思考模式下不支持工具调用，mini-dev 靠工具调用工作，用它必失败。
>
> **模型 ID 以 [DeepSeek 官方文档](https://api-docs.deepseek.com) 为准**：ID 可能更新（`deepseek-chat` 在新版可能换成 `deepseek-v4-flash` 等），填之前先确认当前可用的 chat 模型名。

## 1. 冒烟测试（确认链路通）

```bash
.venv/Scripts/mindev run --yes "读一下 README.md，用一句话总结它讲了什么"
```

- 预期：看到 `-> read_file(...)` 工具调用，然后输出总结。
- 记录：✅ / ❌，失败则贴报错。

## 2. 跑内置评测（拿到真实通过率）

```bash
.venv/Scripts/mindev eval --judge
```

- 记录：`X/3 passed`、`avg score`。
- 简历第一个硬数字：**eval 通过率 X/3**。

## 3. 跑真实任务（记录成功/失败 + bad case）

用项目自身代码当靶子，从易到难各跑一个（下面只是示例，可换成任何你想测的任务）：

| # | 任务 | 命令 |
|---|------|------|
| 1 | 加一个函数 | `mindev run --yes "在 src/mindev/tools/read.py 里加一个 read_lines(path, n) 函数，返回前 n 行"` |
| 2 | 改注释 | `mindev run --yes "把 src/mindev/context/repomap.py 里 estimate_tokens 的注释改得更准确"` |
| 3 | 改逻辑 | `mindev run --yes "把 src/mindev/tools/read.py 的 MAX_OUTPUT_CHARS 从 20000 改成 10000"` |

每个任务记录：

| 任务 | 成功? | 工具调用次数 | 失败原因 |
|------|-------|-------------|----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

> ⚠️ 在**临时分支**上跑：`git checkout -b validation`，跑完 `git diff` 看它改得对不对，再 `git reset --hard && git checkout main` 丢弃，别污染 main。

## 4. 测上下文压缩收益（token 数据）

```bash
# 开压缩（故意把阈值调小到 2000，便于观察压缩行为）
.venv/Scripts/mindev run --yes --compact-threshold 2000 --trace trace_on.jsonl "逐行解释 src/mindev/agent/loop.py 的 run 方法"

# 关压缩
.venv/Scripts/mindev run --yes --compact-threshold 0 --trace trace_off.jsonl "逐行解释 src/mindev/agent/loop.py 的 run 方法"
```

- 对比 `trace_on.jsonl` 和 `trace_off.jsonl` 里每轮记录的 `tokens` 字段。
- 简历第二个硬数字：**上下文压缩使 token 下降 X%**。

## 5. 收集 bad case（面试必问）

把第 3 步里失败的任务记下来，回答两个问题：
- 失败原因？（参数填错 / old_string 不唯一 / 工具没找到 / 模型没完成任务）
- 我怎么改的让它通过？（或：如果没解决，计划怎么改）

> 面试官问「哪里失败过」时，能讲出一个**真实失败 + 你的处理**，是「真做过」的最强证据，比任何漂亮指标都管用。

## 6. 写回 README / DESIGN

把第 2-5 步的真实数字填进 README 的「验证记录」和简历里的量化占位符。

---

## 记录汇总（跑完填这里）

- 成本：共跑了 __ 次，花费约 __ 元
- eval 通过率：__ / 3
- 上下文压缩：token 下降 __ %
- 真实任务成功率：__ / 3
- bad case：__ 个，解决 __ 个
