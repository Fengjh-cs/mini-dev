# 5.1 人工题审阅包（2026-10-07）

## 运行口径

当前硬白名单 Agent（源码 SHA-256：`2fbf979efd4fa121cba8386236a527e43783ff710d6d7bb9090a2c9f95cae29d`）使用 `deepseek-chat`（`api.deepseek.com`）对 6 道人工题各运行一次。与自动题复测保持同一固定靶仓库基线 `2671d40db5342f230f22f6cad66745639c97f7bc`、关闭 RepoMap 和压缩、禁用 bash，并把每题允许文件传入 `--allowed-file`。这里的**Agent 是当前版本，供它修改的靶仓库是历史基线**；尤其不能把第 17 题改出的旧版 `DESIGN.md` 当成当前产品文档。

六次均为 `valid/needs_review`，Agent 和指定测试退出码均为 0；最终改动都只在各题允许文件内，没有未跟踪文件或 `.env`。API usage 六次均完整。**这不产生人工题成功率，也没有写入任何 `human_review`。**

原始证据根目录：

`C:\Users\fjh697\AppData\Local\Temp\mindev-manual-review-1791309069673`

每题子目录包含 `result.json`、`changes.diff`、`trace.jsonl`、`agent.stdout.log`、`tests.stdout.log` 和隔离 checkout。下面的“初审倾向”仅帮助人工聚焦，不能作为最终 verdict。

从项目根目录重新采样的 PowerShell 命令（会调用模型，结果因采样而异）：

```powershell
$root = Join-Path $env:TEMP ('mindev-manual-review-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
foreach ($caseId in @(2, 16, 17, 18, 19, 20)) {
    .\.venv\Scripts\python.exe -m validation.run_case --case $caseId --model deepseek-chat --output-root $root --no-repomap --compact-threshold 0
}
```

| 题号 | 子目录 | 指定测试 | 白名单拒绝 | 初审倾向 |
|---|---|---:|---:|---|
| 2 | `20261006T175143Z-case2-0fe9be73` | 10 passed | 0 | 可考虑通过，有一处措辞需核对 |
| 16 | `20261006T175217Z-case16-6740c6db` | 1 passed | 0 | 倾向不通过 |
| 17 | `20261006T175248Z-case17-51563909` | 1 passed | 0 | 基线口径下可考虑通过 |
| 18 | `20261006T175421Z-case18-2cc75ea2` | 1 passed | 0 | 倾向不通过 |
| 19 | `20261006T175440Z-case19-51f1cc92` | 13 passed | 0 | 存疑，取决于“结果回灌提取”的严格程度 |
| 20 | `20261006T175511Z-case20-af2fa65c` | 7 passed | 4 | 倾向不通过，有合成凭据复现 |

## 逐题审阅卡

### 2：`estimate_tokens` 注释

- **要求：**注释更准确，说明估算边界，不改函数行为。
- **diff：**只把一行 docstring 扩为说明；明确写出 `len(text) // 4`、整数截断和不应当成真实 tokenizer。源码返回语句未改。
- **人工核点：**“under-estimate”若被读成“相对真实 tokenizer 永远低估”就过强；真实 token 数会因文本与 tokenizer 变化。其余描述与基线实现相符。可决定这处措辞是否足以判失败。

### 16：README 评测口径

- **要求：**区分内置 3 题 eval 与真实仓库任务；真实任务中的自动题、人工题成功率分别报告；不编造未测数字。
- **diff：**新增评测说明，但把“自动判定题”直接等同于内置 3 题，把“真实仓库任务”整体描述为人工审阅，并写“这类任务无法自动判定”。基线题库其实有 **14 道自动题＋6 道人工题**。
- **人工核点：**是否完成了“真实任务的自动/人工结果分报”？初审认为没有；`tests/test_cli.py` 通过不能覆盖文档口径错误。

### 17：DESIGN 与基线实现对齐

- **要求：**修正文件编辑与沙箱事实，说明固定靶仓库默认 `local` 命令的真实边界。
- **diff：**把 `apply_patch` 描述改为 `write_file`／`edit_file` 精确替换；写明基线默认 `LocalSandbox` 直接在宿主机执行、Docker 只隔离命令进程与网络而读写挂载工作目录；同时改了目录树等多处文字。这些核心事实与固定基线的 `cli.py`、`sandbox/docker.py` 相符。
- **人工核点：**额外改写是否引入新的不准确说法或降低可读性。尤其这份生成的文档描述的是历史靶仓库，不能直接复制到当前隔离运行版本。

### 18：CLI 帮助文字

- **要求：**`--trace`、`--plan`、`--yes` 文案清楚且无误导，选项行为不变。
- **diff：**只改帮助字符串；但 `--plan` 新文案说“nothing on disk is changed”。基线 `_cmd_run` 即使在 plan 模式仍可 `session_store.save(provider)`，传 `--trace` 时也能追加 JSONL trace。帮助文字的绝对保证因此不成立。
- **人工核点：**该误导是否违反“让新用户清楚副作用”。初审倾向不通过，尽管指定测试通过。

### 19：Agent loop 重构

- **要求：**把 `run` 中的工具执行**与结果回灌**提取为易读私有方法，保持权限、trace、observer、退出行为。
- **diff：**新增 `_execute_tool_call()` 和 `_compact_context_if_needed()`，原有权限、observer、工具执行、trace 顺序看上去保持；但 `for call ...` 和 `self._provider.add_tool_result(call.id, output)` 仍在 `run()` 中。
- **人工核点：**若“结果回灌逻辑提取”要求回灌也进入私有方法，本题没有完全满足；若只要求简化主循环，可考虑通过。13 个原有测试通过只是行为证据，不替代可读性与需求完整性判断。

### 20：Provider 失败提示与凭据边界

- **要求：**Chat Completions 失败时给可操作提示，不泄露 API key；正常响应和工具调用行为不变。
- **diff：**增加错误分类与 `_redact()`，正常调用改经 `_completions_create()`；但捕获上游异常后使用 `raise OpenAIRequestError(...) from exc`，原始异常作为 `__cause__` 保留。`_base_url` 也会未经脱敏直接拼入错误文本。
- **本地合成验证：**用仅存在于测试脚本中的 `sk-synthetic-local-test-only`，让假上游异常回显它；包装异常的 `str(exc)` 不含合成 key，但 `traceback.format_exc()` **含有合成 key**。没有调用网络或读取真实 `.env`。这证明包装消息脱敏不等于完整 traceback 脱敏。
- **trace：**Agent 试写 `tests/test_openai_errors.py`、`verify_openai_errors.py`、`src/mindev/llm/_verify_errors.py`，并试删 `tests/test_openai.py`；四次都被硬白名单拒绝，最终 diff 只含允许的 `openai.py`。
- **人工核点：**在 CLI 打印未捕获异常 traceback 的场景中，这一缺陷是否违反“不泄露 API key”。初审倾向不通过；7 个原有测试未覆盖这个负向场景。

## 人工记录方式

请先对每题核对 `changes.diff` 与对应要求，再给出 `passed` 或 `failed`，附一句具体依据。我只在收到你的裁定后用 `validation.review_case` 写入 `human_review`；到那时再计算人工题结果，预检状态和人工语义 verdict 仍分别保留。
