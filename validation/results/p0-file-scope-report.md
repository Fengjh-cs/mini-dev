# P0 文件范围反馈验证（2026-10-06）

## 口径

这是针对 [4.2 历史基线](phase42-report.md) 中 `map-off-compact-off` 自动题的单次复测。固定 checkout 为 `2671d40db5342f230f22f6cad66745639c97f7bc`，模型为 `deepseek-chat`，接口主机为 `api.deepseek.com`，关闭 RepoMap 和压缩，禁用 bash。14 道自动题与历史基线相同；6 道人工题没有纳入本次复测。当前 Agent 源码 SHA-256 为 `9145c97132b10f3d1dfca77f848349926c12a0f20ec904e9d5d0feca1d30b46f`。

运行器现在把每题的允许文件以 `--allowed-file` 传给 Agent。每批成功的文件编辑后，验证器比较隔离工作副本与任务开始时的文件快照；越界文件名随验证失败回灌给 Agent。新增的 `delete_file` 工具可清理临时文件。最终评分仍由运行器独立检查跟踪文件、非忽略的新文件、原有测试和自动判定。

在项目根目录复现本组实验的 PowerShell 命令如下。它会从本地 `.env` 读取接口配置，并把每题结果写到新的临时目录：

```powershell
$root = Join-Path $env:TEMP ('mindev-scope-p0-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
foreach ($caseId in @(1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)) {
    .venv\Scripts\python.exe -m validation.run_case --case $caseId --model deepseek-chat --output-root $root --no-repomap --compact-threshold 0
}
```

## 结果

| 指标 | 历史基线 | 本次复测 |
|---|---:|---:|
| 自动题正式通过 | 9/14 | 14/14 |
| 自动题无效运行 | 0 | 0 |
| 自动题独立检查通过 | 14/14 | 14/14 |

原来失败的 7、8、9、12、14 题这次均正式通过。全部 14 题的原有测试退出码为 0，独立检查通过，最终没有允许范围外的跟踪改动或非忽略新文件。

运行中共有 4 次文件范围验证失败，Agent 随后用 `edit_file` 撤回，下一次验证通过：

| 题号 | 越界文件 | 证据 |
|---|---|---|
| 1 | `src/mindev/cli.py` | `20261006T152213Z-case1-fcd5cd77/trace.jsonl` |
| 7 | `tests/test_edit.py` | `20261006T151138Z-case7-ccc65c3c/trace.jsonl` |
| 11 | `tests/test_trace.py` | `20261006T152355Z-case11-d057bf29/trace.jsonl` |
| 14 | `tests/test_repomap.py` | `20261006T151330Z-case14-18174720/trace.jsonl` |

原始 `result.json`、`changes.diff`、trace 和 Agent 日志保存在 `C:\Users\fjh697\AppData\Local\Temp\mindev-scope-p0-20261006-231138` 的各题目录中。旧数据保存在 `C:\Users\fjh697\AppData\Local\Temp\mindev-phase42-20261006-175707-official\map-off-compact-off`。两个目录都应保留，以便复核。

本地回归运行 `$env:MINIDEV_REQUIRE_DOCKER='1'; .venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider`，结果为 **133 passed**；真实 Docker 隔离和验证测试均执行。

## 解释与限制

本次 14/14 是单模型、单次采样。第 1、7、11、14 题的 trace 直接展示了“越界编辑 → 范围失败反馈 → 撤回 → 通过”的闭环；第 8、9、12 题这次直接只改目标文件，不能把它们的通过单独归因于失败反馈。Agent 同时增加了删除工具和通用验证提示，模型输出也有随机性，因此本次结果不能证明稳定通过率为 100%。

文件范围验证是**批次结束后的检测和反馈**，不会在工具调用前阻止瞬时越界写入；该模式要求 `--no-bash`。需要硬性阻止写入时，应另做文件工具 access 层白名单。历史 9/14 保留为改动前结果，不与本次 14/14 混算为单一成功率。
