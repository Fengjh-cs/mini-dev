# mini-dev 真实任务评测用例 v1

## 固定基线与判定规则

- 基线提交：`2671d40db5342f230f22f6cad66745639c97f7bc`。三个任务各从此提交创建**独立、干净**的工作目录；任务之间不继承改动。
- 只复制该提交跟踪的项目文件。不要把 `.env`、本评测文件、评分规则或其他本地凭据放进 Agent 工作目录。
- 每次运行记录模型 ID、接口类型、任务提示、退出状态、工具调用次数、耗时、接口实际用量（若接口提供）、最终文件差异及测试结果。比较不同实现时保持模型与运行参数一致。
- 成功由**最终文件状态和下列检查**判定，不能仅凭 Agent 的最终回答。超时、接口故障、评测环境故障记为“无效运行”，与任务失败分开统计。
- 除各任务列出的允许改动文件外，其他跟踪文件必须与基线保持一致。评测产生的临时文件和 trace 单独保存。
- 单题运行器：从项目根目录执行 `.venv\Scripts\python.exe validation\run_case.py --case 1`（将 `1` 换为 `2` 或 `3`）。每次只跑一题，默认在系统临时目录的 `mindev-validation` 下新建独立 checkout 与结果目录。此命令会调用配置的模型；只检查隔离准备时加 `--prepare-only`，不会调用模型。`result.json` 中 `execution_status=invalid` 表示接口、超时或环境故障，`task_outcome=failed` 表示有效运行后检查未通过，`needs_review` 表示还要按本文件做最终检查；不得将它算作成功。手工复核前在原项目根目录执行 `$Python = (Resolve-Path .venv\Scripts\python.exe).Path`，进入 checkout 后可用下文命令。
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

## 汇总口径

分别报告“成功 / 有效运行”和“无效运行 / 总运行”；同时列出每题的失败原因。上次手工验证得到的 `2/3` 仅作为历史记录，不能替代在上述固定基线和统一规则下的重新运行。
