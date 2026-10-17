# 《水调歌头》后端 0.5.0

提供单作品只读查询、AI/RAG 内容制作 CLI、Godot 内容契约及离线交接工具。客户端负责三幕玩法、完整存档、检查点和本地回顾。

当前内容为未审核草稿。Godot 准确版本、渲染器、资源文件、使用权和节点绑定仍待确认；后端契约不代表 Godot 工程已导入或可玩。

## 开始使用

需要 Python 3.12 或以上版本及 uv。在本后端目录执行：

```powershell
uv sync --frozen
if (-not (Test-Path config/credentials.env)) {
    Copy-Item config/credentials.env.example config/credentials.env
}
# 编辑本机 credentials.env 后先做离线配置检查。
uv run --env-file config/credentials.env python -m app.check_config
uv run --env-file config/credentials.env uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

API 地址、DeepSeek 密钥、数据库连接串等统一填写在本机 `config/credentials.env`，字段说明见 [凭据模板](config/credentials.env.example)。真实文件不提交仓库、不打包进镜像。使用 `--env-file` 显式加载，已有进程环境变量优先；数据库连接串为空且无环境变量覆盖时使用本地 SQLite。

高级参数继续使用 TOML；完整填写规则见 [配置说明](doc/CONFIGURATION.md)。

## 只读 API

- `GET /health`：数据库健康检查。
- `GET /api/v1/poems`：单作品目录。
- `GET /api/v1/poems/lookup`：按标题及可选作者查询。

运行后可查看 `/docs` 和 `/openapi.json`。接口字段见 [API 说明](../api.md)，机器契约与示例见 [OpenAPI](examples/openapi.json) 和 [HTTP 样例](examples/client-http-examples.json)。没有服务端存档、设置保存、行为上报或在线生成接口。

## 离线内容与 Godot 对接

```powershell
uv run python -m app.demo_content validate --source content/shuidiaogetou-3
uv run python -m app.demo_content export --source content/shuidiaogetou-3 --output ../content-drafts
```

默认源为 `content/shuidiaogetou-3`，使用 ContentPack 1.2 / ResourceManifest 1.1；JourneySnapshot 和客户端字段契约仍为 1.0。旧内容源按原格式保留，禁止覆盖历史交接。

导出包含完整内容、资源清单、Schema、客户端投影、Godot 映射说明及校验和。客户端应以真实交互确认事件，不能从 UI 行数推导通关。规则见 [内容契约](doc/CONTENT_CONTRACT.md) 和 [Godot 资源说明](doc/ASSETS.md)。

正式发布需通过文学审核、关键英文、资源交付、演出参数和 Godot 运行声明等门槛；当前草稿不满足发布条件。满足条件后使用新版本或新输出目录执行：

```powershell
uv run python -m app.demo_content release --source content/shuidiaogetou-3 --output ../content-releases
```

## AI 内容制作

先填写凭据，并根据 [AI 使用说明](doc/AI_AUTHORING.md) 确认调用授权和请求预算。离线配置检查不会调用模型：

```powershell
uv run --env-file config/credentials.env python -m app.check_config --config config/ai-authoring.example.toml
```

制作 CLI 支持解析、BM25 检索校验、Scene Schema、Godot 草稿编译和基于 JourneySnapshot 的诗意反馈。模型调用必须显式传 `--allow-model-calls`；账本不可重置或自动轮换，输出不会自动替换当前内容源或升级审核状态。

## 数据维护

启动不会清库。内部身份为 `su_shi.shuidiaogetou`，客户端身份为 `shuidiaogetou`，不修改数据库主键。退役清理必须显式执行预览、备份、恢复核验和事务定向删除；业务库维护另行授权。

仓库不包含私有配置、数据库、备份、测试运行结果或历史生产维护脚本。测试源码位于 `tests/`，使用隔离环境运行。
