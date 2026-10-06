# P0 文件硬白名单：写前拒绝

## 改动与边界

`--allowed-file` 现在传入隔离副本的 `WorkspacePathPolicy`。`write_file`、`edit_file`、`delete_file` 先用 `resolve_write()` 校验路径，再读取、创建快照或改动文件；名单外目标直接返回 `access denied`。`read_file` 保持工作区内只读访问。启用该选项仍要求 `--no-bash`，因此模型没有另一条命令写入路径。原有批次后 `FileScopeCheck` 保留，用于发现验证命令等其他途径产生的额外改动。

保证范围是模型通过这三个文件工具发起的写入。`--verify` 是用户配置的 Docker 命令，它的副作用由批次后检查发现，不经过写前白名单；如命令生成额外文件，需调整命令或将该文件列入允许集。路径检查也不防范另一个宿主进程在检查与打开之间替换路径。

## 可复现证据

- 负向测试对已有的非允许文件依次尝试覆盖、精确编辑和删除，并尝试新建非允许文件；四次均被拒绝，底层 `open()` 未被调用，没有快照，原文件内容不变，也没有新文件。
- CLI 集成测试确认隔离副本中非允许文件仍可读取、不可写入。
- 脚本化 Agent 测试先尝试越界编辑，收到工具拒绝错误，再编辑允许文件；越界文件始终保持原样，只有成功的允许编辑触发批次验证。这条机制不依赖模型执行撤回。
- 完整回归：`141 passed`，设置 `MINIDEV_REQUIRE_DOCKER=1` 后两项真实 Docker 用例均执行通过。

本机复现命令（PowerShell，Docker Desktop CLI 安装在 D 盘）：

```powershell
$env:PATH = 'D:\Apps\DockerDesktop\resources\bin;' + $env:PATH
$env:MINIDEV_REQUIRE_DOCKER = '1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider
```

此步未重新运行在线 14 题，历史的 14/14 单次采样和四条“反馈后撤回”trace 仍记录在 [文件范围反馈报告](p0-file-scope-report.md)，不能当作硬白名单版本的通过率。
