# 4.2 固定模型功能对比

同一 Agent 版本、同一模型、同一接口、同一 20 题基线，分别测试 RepoMap 开/关与压缩开/关。先固定一个支持工具调用的模型 ID，并确认 `.env` 配置；以下命令会对外发送任务与 Agent 读取的仓库内容，合计最多 80 次任务运行，每次可能有多次 API 请求。

在项目根目录的 PowerShell 中执行；`$fixedModel` 填实际模型 ID，不要放密钥：

批量运行器支持断点续跑，默认同时跑 3 题；某批次出现无效运行时停止，避免把接口或环境故障扩散到其余任务。输出目录应是本次评测专用的空目录，也可包含本次已完成的有效结果。
检查无效运行的 `result.json` 与日志后，若选择保留该次无效结果并继续其余题目，可对同一目录重跑命令并加 `--resume-with-invalid`；汇总会继续把它列为无效，整组实际 token 总量保持未知。

```powershell
$fixedModel = "<same-chat-model-id>"
$root = Join-Path $env:TEMP ("mindev-compare-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
.venv\Scripts\python.exe -m validation.run_matrix --model $fixedModel --output-root $root --workers 3
```

也可以逐题串行执行同样的四组设置：

```powershell
$fixedModel = "<same-chat-model-id>"
$root = Join-Path $env:TEMP ("mindev-compare-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$variants = @(
  @{ name = "map-off-compact-off"; map = $false; threshold = 0 },
  @{ name = "map-on-compact-off"; map = $true; threshold = 0 },
  @{ name = "map-off-compact-on"; map = $false; threshold = 2000 },
  @{ name = "map-on-compact-on"; map = $true; threshold = 2000 }
)
foreach ($variant in $variants) {
  foreach ($caseId in 1..20) {
    $caseArgs = @("validation\run_case.py", "--case", "$caseId", "--model", $fixedModel,
                  "--compact-threshold", "$($variant.threshold)",
                  "--output-root", (Join-Path $root $variant.name))
    if (-not $variant.map) { $caseArgs += "--no-repomap" }
    & .venv\Scripts\python.exe @caseArgs
  }
}
& .venv\Scripts\python.exe -m validation.compare `
  --variant map-off-compact-off (Join-Path $root "map-off-compact-off") `
  --variant map-on-compact-off (Join-Path $root "map-on-compact-off") `
  --variant map-off-compact-on (Join-Path $root "map-off-compact-on") `
  --variant map-on-compact-on (Join-Path $root "map-on-compact-on")
```

每题结果目录保留 `result.json`、`api_usage.json`、trace、测试日志和改动 diff。对比程序检查题号、提示词、模型、接口主机、固定基线与 Agent 源码指纹一致；任一条件不符就拒绝比较。每组单列 14 道自动题的有效运行通过率、无效运行数，以及 6 道人工题的待审/已审结果。配对改进/退步只统计两边都有效的自动题。

`actual_api_usage` 是 API 响应的 prompt/completion/total token；只要一题无效或缺失完整响应统计，整组 token 总量就为 `null`，并显示覆盖题数。`paired_actual_api_usage` 只用各组共同有效且 `usage` 完整的相同题号计算实际 token 变化，并单列全部题和自动题。`estimated_context` 是 trace 中“字符数 ÷ 4”的观测峰值平均数及压缩触发事件数，不能与 API 用量相加，也不能作为计费量。真正发出的摘要请求数看 `compaction_summary_requests`。人工题经过 diff 审阅后，使用 `validation.review_case` 记录带证据的 verdict，再重跑比较。

对比报告中的功能变化和 token 用量均需引用真实运行结果；仅运行本地单元测试不能填入通过率或节省比例。比较 token 变化时使用 `actual_api_usage.total_tokens`；估算上下文下降只称为“上下文估算值变化”。
