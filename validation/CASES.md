# mini-dev 真实任务评测用例 v2（20 题）

## 固定基线与判定规则

- 基线提交：`2671d40db5342f230f22f6cad66745639c97f7bc`。20 个任务各从此提交创建**独立、干净**的工作目录；任务之间不继承改动。
- 只复制该提交跟踪的项目文件。不要把 `.env`、本评测文件、评分规则或其他本地凭据放进 Agent 工作目录。
- 每次运行记录模型 ID、接口类型、任务提示、退出状态、工具调用次数、耗时、接口实际用量（若接口提供）、最终文件差异及测试结果。比较不同实现时保持模型与运行参数一致。
- `result.json` 的 `api_usage` 和单独的 `api_usage.json` 只统计 API 响应返回的 `usage`，包含主 Agent、`explore` 子 Agent、压缩摘要请求。若任一响应缺少完整用量，`complete=false`，token 总量为 `null`。`context_estimate` 来自 trace 中的字符数除以 4，仅是观测到的上下文估算；不可当作 API 计费 token。
- 成功由**最终文件状态和下列检查**判定，不能仅凭 Agent 的最终回答。超时、接口故障、评测环境故障记为“无效运行”，与任务失败分开统计。
- 除各任务列出的允许改动文件外，其他跟踪文件必须与基线保持一致。评测产生的临时文件和 trace 单独保存。
- 单题运行器：从项目根目录执行 `.venv\Scripts\python.exe validation\run_case.py --case 1`（`1` 可换为 `1` 至 `20`）。每次只跑一题，默认在系统临时目录的 `mindev-validation` 下新建独立 checkout 与结果目录。此命令会调用配置的模型；只检查隔离准备时加 `--prepare-only`，不会调用模型。`result.json` 中 `execution_status=invalid` 表示接口、超时或环境故障，`task_outcome=failed` 表示有效运行后检查未通过，自动题检查通过记 `passed`，人工题记 `needs_review` 直至人工审阅。手工复核前在原项目根目录执行 `$Python = (Resolve-Path .venv\Scripts\python.exe).Path`，进入 checkout 后可用下文命令。
- 运行器以**当前工作树的 Agent 实现**操作固定基线 checkout；测试与自动判定则加载 checkout 中的候选代码。`result.json` 记录 Agent 源码 SHA-256，便于复核不同实现。评测运行添加 `--no-bash`，并将本题允许改动的文件通过 `--allowed-file` 交给运行中验证；越界改动会回灌给 Agent，最终评分仍独立核对文件差异。文件工具只访问隔离副本，拒绝环境文件、工作区外路径和符号链接。
- 在每题 checkout 内执行 `git diff --stat 2671d40db5342f230f22f6cad66745639c97f7bc -- .` 核对跟踪文件改动，再用 `git ls-files --others --exclude-standard` 找新增的非忽略文件。运行器把这两类文件及完整 diff 写入结果目录；不允许范围外的文件变更。

## 用例 1：新增 `read_lines`

**提示词**：在 `src/mindev/tools/read.py` 里加一个 `read_lines(path, n)` 函数，返回前 `n` 行。

**允许改动**：`src/mindev/tools/read.py`。

**成功条件**：

1. 模块提供可调用的 `read_lines(path, n)`；原有 `ReadTool` 行为不退化。
2. 对内容为 `alpha\nbeta\ngamma\n` 的 UTF-8 文件，`n=2` 的结果按顺序包含 `alpha`、`beta`，且不包含 `gamma`；`n=10` 包含全部三行；`n=0` 不包含文件内容。允许返回字符串、行列表或带行号的文本，因为原提示词未规定表示形式。
3. 对不存在的文件给出可识别的错误，而不是未处理异常。
4. 在本题 checkout 中运行 `& $Python -m pytest tests/test_tools.py -q`；运行器实际调用的是原项目虚拟环境中 Python 的绝对路径，并把 checkout 的 `src` 放入 `PYTHONPATH`。没有其他跟踪文件被修改。

## 用例 2：改进 `estimate_tokens` 注释

**提示词**：把 `src/mindev/context/repomap.py` 里 `estimate_tokens` 的注释改得更准确。

**允许改动**：`src/mindev/context/repomap.py` 中 `estimate_tokens` 紧邻的注释或文档字符串。

**成功条件**：

1. `estimate_tokens` 的实现及其余代码与基线相同，尤其仍为 `return len(text) // 4`。
2. 新注释明确说明这是按字符数除以 4 的粗略估算，不是真实 tokenizer 的计数；误差会受文本和模型的分词方式影响。
3. 人工语义审阅确认没有引入不成立的普遍断言。例如“Unicode 文本相对等长 ASCII 一定被高估”不成立：`len(text) // 4` 对等长字符串给出相同估值。
4. 在本题 checkout 中运行 `& $Python -m pytest tests/test_repomap.py tests/test_repomap_multilang.py -q`（运行器使用原项目虚拟环境中 Python 的绝对路径及 checkout 的 `src`）。没有其他跟踪文件被修改。**此题必须完成人工语义审阅后才能记为成功。**

## 用例 3：调整读取输出上限

**提示词**：把 `src/mindev/tools/read.py` 的 `MAX_OUTPUT_CHARS` 从 20000 改成 10000，其他逻辑保持不变。

**允许改动**：`src/mindev/tools/read.py`。

**成功条件**：

1. 目标文件相对基线的唯一源码变化是 `MAX_OUTPUT_CHARS = 20_000` 改为 `MAX_OUTPUT_CHARS = 10_000`。
2. 超过上限的读取输出按新上限截断；原有读取测试通过。
3. 在本题 checkout 中运行 `& $Python -m pytest tests/test_tools.py -q`（同样使用原项目虚拟环境及 checkout 的 `src`）；没有其他跟踪文件被修改。

## 扩展用例 4–20

**分级与判定方式**：共 20 题，其中 **14 题全自动**（1、3–15），**6 题需人工审阅**（2、16–20）。难度标签是相对本仓库的改动规模：easy 为单点改动，medium 为单模块行为，hard 为跨行为约束或较复杂的语义判断。所有任务使用上面的固定基线和单题隔离运行。

下表“原有测试”均在该题 checkout 中运行，命令为 `& $Python -m pytest <列出的测试文件> -q`。运行器会自动执行；自动判定还会运行 checkout 外的 `validation/checks.py`，它不随任务文件发送给 Agent。

| # | 难度 | 判定 | 允许改动 | 额外成功条件 | 原有测试 |
|---|---|---|---|---|---|
| 4 | easy | 自动 | `tools/edit.py` | 源码唯一变化是 `MAX_EDIT_CHARS = 100_000` → `50_000` | `tests/test_edit.py` |
| 5 | easy | 自动 | `sandbox/local.py` | 源码唯一变化是 `MAX_OUTPUT_CHARS = 20_000` → `10_000` | `tests/test_sandbox.py` |
| 6 | medium | 自动 | `tools/edit.py` | `WriteFileTool` 能创建缺失的多级父目录并写入内容，已有文件仍可覆盖 | `tests/test_edit.py` |
| 7 | medium | 自动 | `tools/edit.py` | 相同新旧文本返回 no-op、内容不变、不创建快照 | `tests/test_edit.py` |
| 8 | medium | 自动 | `tools/snapshot.py` | `has_snapshot(path)` 在快照前/后/恢复后依次为 `False/True/False`，恢复内容正确 | `tests/test_edit.py` |
| 9 | medium | 自动 | `tools/registry.py` | 重复工具名抛 `ValueError`，单工具注册仍正常 | `tests/test_tools.py` |
| 10 | easy | 自动 | `agent/trace.py` | `summarize()` 新增 `compact_events` 计数，原统计保持正确 | `tests/test_trace.py` |
| 11 | medium | 自动 | `agent/trace.py` | `clear()` 清空内存事件，保留 JSONL，之后仍可追加 | `tests/test_trace.py` |
| 12 | medium | 自动 | `agent/session.py` | `delete()` 删除会话文件，对缺失文件幂等 | `tests/test_session.py` |
| 13 | hard | 自动 | `agent/permissions.py` | 未知 risk 一律拒绝，现有 read/write/command 行为不退化 | `tests/test_permissions.py` |
| 14 | hard | 自动 | `context/repomap.py` | `.pyi` 出现在源码列表，顶层类和函数被提取并渲染 | `tests/test_repomap.py tests/test_repomap_multilang.py` |
| 15 | medium | 自动 | `tools/registry.py` | `names()` 返回字母序工具名，`schemas()` 仍按注册顺序 | `tests/test_tools.py` |
| 16 | medium | 人工 | `README.md` | 准确区分内置 eval 与真实任务评测，分别报告自动/人工结果，不编造数字 | `tests/test_cli.py` |
| 17 | hard | 人工 | `DESIGN.md` | 修正编辑和沙箱的事实错误，准确说明默认 local 命令边界；术语与实现一致 | `tests/test_cli.py` |
| 18 | medium | 人工 | `cli.py` | `--trace/--plan/--yes` 帮助文字清楚、无误导，选项行为不变 | `tests/test_cli.py` |
| 19 | hard | 人工 | `agent/loop.py` | 私有方法确实减轻 `run` 的复杂度，权限/trace/observer/退出行为不变 | `tests/test_loop.py tests/test_permissions.py tests/test_trace.py` |
| 20 | hard | 人工 | `llm/openai.py` | API 失败提示可操作且不含密钥，正常响应和工具调用保持不变 | `tests/test_openai.py tests/test_stream.py` |

表中的 `tools/`、`agent/`、`sandbox/`、`context/`、`llm/` 均在 `src/mindev/` 下。每题完整提示词、路径和测试命令以 `validation/run_case.py` 的 `CASES` 表为准。人工题仅凭原有测试通过不能记为成功；审阅 diff、运行结果及本表条件后，用 `.venv\Scripts\python.exe -m validation.review_case <result.json> --verdict passed|failed --notes "具体证据"` 记录结论。

## 汇总口径

在项目根目录执行 `.venv\Scripts\python.exe -m validation.summary` 汇总默认结果目录；若运行时用了 `--output-root`，汇总时也传相同参数。**自动成功率 = 自动题通过数 / 自动题有效运行数**，不包含 6 道人工题或无效运行。人工题单列已审通过、已审失败、原有测试/文件范围等预检查失败、待审及无效运行，不合入自动成功率。重复的有效运行会报错，须选定一条后才能报告。上次手工验证得到的 `2/3` 仅作历史记录，不能替代上述固定基线的新评测。
