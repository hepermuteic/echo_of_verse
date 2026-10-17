# 统一配置与检查

## API 与数据库凭据集中填写（2026-10-17）

普通填写入口为后端 `config/credentials.env`；可提交模板为 `config/credentials.env.example`。这是一份本机服务凭据文件，不是用户登录系统，也不提供新的 HTTP 认证接口。文件初始不含真实密钥；现有业务凭据和历史测试密钥未读取或复制。

在 `backend` 目录操作：

```powershell
# 首次克隆后创建；不要覆盖已经填写的私有文件。
if (-not (Test-Path config/credentials.env)) {
    Copy-Item config/credentials.env.example config/credentials.env
}
# 编辑文件后先做离线检查，不探测网络、不开数据库、不调用模型。
uv run --env-file config/credentials.env python -m app.check_config
# 需要 AI 制作时单独检查对应 profile；密钥留空会报告 incomplete。
uv run --env-file config/credentials.env python -m app.check_config --config config/ai-authoring.example.toml
# 启动本机只读 API；监听地址与端口由命令控制。
uv run --env-file config/credentials.env uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

| 文件内字段 | 填写条件与用途 |
|---|---|
| EOV_API_BASE_URL、EOV_DEPLOYMENT_NAME | 健康探测地址及部署标签；base URL 不控制 uvicorn 的监听端口 |
| LLM_API_BASE_URL、LLM_MODEL、DEEPSEEK_API_KEY | DeepSeek 制作 CLI 的地址、模型与密钥；HTTP 服务不会因填写而调用模型 |
| DATABASE_URL | 本机需要 PostgreSQL 时填写完整连接串，含用户名、密码、主机、端口和库名；空值保留 SQLite |
| REDIS_URL | 本机可选 Redis，当前只读查询不依赖它 |
| POSTGRES_PASSWORD、REDIS_PASSWORD、HTTP_PORT | 现有 Docker Compose 的可选填写项；数据库用户与库名固定为 echoes |
| EMBEDDING_*、EOV_STORAGE_* | 预留字段，未接入，不要求填写；填写不会启用服务 |

凭据通过 `uv run --env-file` 注入子进程环境，程序仍只从环境变量取密钥，不新增配置加载代码或依赖。**已有进程环境变量优先于文件值**，包括已存在的空值；多份 `--env-file` 中后指定的文件覆盖先指定的文件。意外沿用旧值时，先清理当前终端中对应变量，再重新运行。文件路径相对当前工作目录；应用内的 TOML 相对路径规则保持不变。文件不存在时 uv 会停止执行；但本机实测未闭合引号等语法错误可能只产生警告并继续，警告可能带原始出错行。出现该警告应先修正文件，再确认离线检查的服务状态符合预期；不要将警告原文保存到报告、仓库或聊天。离线检查通过不保证凭据文件每一行都已成功解析，也不代表服务已连通。

模板使用单引号，保留空格、`#`、`$` 和反斜杠；值自身带单引号时使用 dotenv 支持的引号/转义语法，不要把文件当成 PowerShell 脚本执行。PostgreSQL 的格式为 `postgresql+psycopg://用户名:编码后的密码@主机:端口/库名`；用户名、密码中的特殊字符须单独做 URL 编码，例如 `@`→`%40`、`#`→`%23`、`%`→`%25`，不要编码整条 URL。Redis 连接串同样处理账号密码。空的 DATABASE_URL 只有在没有更高优先级环境变量时才保留 SQLite；执行 API 启动会照常进行数据库初始化，**离线配置检查不会**。

高级非敏感参数继续沿用下文 TOML。AI CLI 默认使用 `config/ai-authoring.example.toml`，其 `--config` 与 HTTP 的 `EOV_CONFIG_FILE` 选择规则不同；统一凭据文件内的地址、模型覆盖和密钥可供二者使用。付费调用仍须 `--allow-model-calls` 和已授权的剩余预算，填写密钥不会重置既有账本。

### 容器使用边界

后端目录提供独立的 compose.yaml 与 Dockerfile，按其定义使用本地 SQLite 卷；它不会自动读取凭据文件。若要注入运行凭据，应在明确的部署配置中按需指定环境变量。模板中的 POSTGRES_PASSWORD、REDIS_PASSWORD 和 HTTP_PORT 为原项目部署预留项，本次仓库不附带原多服务 Compose，也不承诺这些预留项会被独立 Compose 使用。不要把凭据复制进镜像。

## 现有 TOML 高级配置

2026-10-17：新增显式 AI 内容制作 CLI 配置 `config/ai-authoring.example.toml`，复用本文 TOML 加载器和环境变量覆盖。默认 DeepSeek / deepseek-flash / DEEPSEEK_API_KEY；解析、校验、场景生成及离线反馈只有传 `--allow-model-calls` 才调用模型，每个已授权轮次跨命令共享20次预算；不会自动轮换或清空账本。服务模板、普通检查及 HTTP 启动仍不调用模型；Embedding 仍未接入。下文“LLM预留”描述适用于原 HTTP 服务；CLI 用法见 [AI_AUTHORING.md](AI_AUTHORING.md)。

日期：2026-10-09。统一入口为 `config/services.example.toml`，首次使用可复制为 `config/services.toml`。运行配置已加入忽略列表，且不进入 Docker 构建上下文。模板不含真实密钥。

集中管理配置符合常见工程管理实践：配置与代码分离、模板可版本管理、实际部署值可覆盖、秘密不写入仓库、配置错误在接入前校验。这里采用本地 TOML + 环境变量的实用组合；不是声称它严格等同于所有部署参数均使用环境变量的 Twelve-Factor 规范。生产环境仍应由部署系统/秘密管理服务注入密钥。[Twelve-Factor 配置原则](https://www.12factor.net/config)

## 配置位置与优先级

1. `EOV_CONFIG_FILE` 指定文件，优先级最高；指定不存在的文件会失败，不静默回退。
2. 未指定时读取后端 `config/services.toml`；不存在则使用安全默认模板 `config/services.example.toml`。
3. 支持的环境变量覆盖文件字段。相对配置路径、sqlite_path 和本地素材路径均以后端目录为基准。

空的旧 LLM/Embedding 环境变量不覆盖 TOML 值；`EOV_CORS_ORIGINS` 显式设为空则关闭跨域。配置在启动前填写，修改后重启进程，不承诺热更新。

仅需要高级非敏感参数时再创建本机 TOML：

```powershell
if (-not (Test-Path config/services.toml)) {
    Copy-Item config/services.example.toml config/services.toml
}
# 编辑 services.toml 的服务商、开关、超时等高级参数。
# 如需另选文件：
$env:EOV_CONFIG_FILE = 'config/services.toml'
# 密钥统一填写 config/credentials.env，使用 --env-file 加载。
```

不使用 TOML 中的 api_key/access_key 明文字段；配置只保存诸如 api_key_env="LLM_API_KEY" 的环境变量名称。未知配置字段会拒绝。应用没有自动加载本地 `.env`。

## 配置分组

| 分组 | 要配置的内容 | 当前使用情况 |
|---|---|---|
| app | 部署标签、明确的 CORS 来源 | API 启动时使用 |
| api | 后端 base_url、健康探测超时 | 用于显式 API 探测，不控制 uvicorn 监听地址 |
| database | SQLite 路径、数据库 URL 环境变量名 | API/维护脚本读取；PostgreSQL URL 默认从 DATABASE_URL 注入 |
| redis | URL 环境变量名、连接/操作超时 | 仅清理退役目录缓存；新查询直接读取 SQL，不依赖 Redis |
| llm | enabled、provider、API 地址、model、密钥变量名、超时、重试次数 | HTTP 不调用模型；AI 制作 CLI 的 DeepSeek 适配已实现，使用独立 profile |
| embedding | 同 LLM，独立模型与凭据 | 预留；没有向量生成或向量检索，当前 RAG 使用本地 BM25 |
| storage | enabled、local/minio/oss、endpoint、region、bucket、密钥变量名、本地路径、超时、签名有效期 | 预留；当前没有对象存储 SDK 或资源交付端点 |

provider 是待选择的服务商标识，未绑定具体厂商或模型。LLM/Embedding 地址必须为 HTTP(S)，不含口令、Query 或 fragment；具体调用路径由未来服务适配器决定，不通过任意测试路径调用未知服务。

预留服务的 enabled 只表示“纳入配置完整性检查”；填好配置或将 enabled=true 不会启动真实模型调用、上传资源，也不会改变未收录诗词的行为。

enabled=true 的模型配置必须填写 provider/API 地址/model；requires_api_key=true 时指定的密钥变量必须有值。对象存储必须填写 endpoint/bucket 和访问密钥，OSS 另需 region；未来可按部署需求增加托管身份适配，目前没有实现。

## 环境变量兼容与部署

| 环境变量 | 作用 |
|---|---|
| EOV_CONFIG_FILE | 指定统一 TOML 文件 |
| EOV_DB_PATH、EOV_DEPLOYMENT_NAME、EOV_CORS_ORIGINS | 覆盖当前应用设置 |
| DATABASE_URL、REDIS_URL | 默认的秘密连接串变量；文件可指定别的变量名称 |
| EOV_API_BASE_URL | 覆盖健康探测的后端地址 |
| EOV_CONTENT_SOURCE | 内容源/正式交接目录，当前默认 content/shuidiaogetou-3；相对路径以后端目录为基准；新版客户端 HTTP 要求完整 clientPresentation |
| LLM_API_BASE_URL、LLM_MODEL、EMBEDDING_API_BASE_URL、EMBEDDING_MODEL | 保留已有部署覆盖方式 |
| DEEPSEEK_API_KEY | AI 制作 CLI 默认密钥变量，仅显式允许时调用模型 |
| LLM_API_KEY、EMBEDDING_API_KEY | 原服务 profile / Embedding 预留密钥变量 |
| EOV_STORAGE_ENDPOINT、EOV_STORAGE_BUCKET、EOV_STORAGE_REGION | 覆盖预留存储设置 |
| EOV_STORAGE_ACCESS_KEY_ID、EOV_STORAGE_SECRET_ACCESS_KEY、EOV_STORAGE_SESSION_TOKEN | 默认对象存储凭据变量 |

当前交付只包含后端独立 Compose；原项目多服务部署配置不在此交付内。现有 endpoint/model 环境变量覆盖仍兼容。

当前源码为 0.5.0，镜像构建携带 content 和非敏感配置模板；源码提交不代表服务已经部署。

## 统一检查命令

在后端目录执行：

```powershell
# 默认：离线检查配置，不访问网络、不开库、不调用模型。
uv run --env-file config/credentials.env python -m app.check_config
# 配置和资源清单一并检查。
uv run --env-file config/credentials.env python -m app.check_config --manifest examples/resource-manifest.json
# 显式执行只读连通性检查。
uv run --env-file config/credentials.env python -m app.check_config --probe api --probe database --probe redis
# API 运行于 Nginx 8080 时，探测目标可覆盖。
$env:EOV_API_BASE_URL = 'http://127.0.0.1:8080'
uv run --env-file config/credentials.env python -m app.check_config --probe api
# 自动化回归测试。
uv run pytest -q
```

输出 JSON，不打印密钥、带凭据的连接串或驱动异常文本。配置非法、启用服务缺配置、探测失败或 require-ready 未满足时退出码 1；正常退出码 0。参数用法错误退出码 2。

| 状态 | 能证明什么 |
|---|---|
| valid | 结构/约束通过 |
| configured_only | 配置完整，不证明适配器或服务可用 |
| local_sqlite | 未注入数据库 URL，采用本地 SQLite |
| disabled | 可选配置未纳入要求或未设置 Redis |
| reachable | 显式探测成功；不等于完整业务可用 |
| skipped | 未配置可选服务或没有可只读探测的 SQLite 文件路径 |
| incomplete/invalid/failed | 配置不完整、非法或探测失败 |

API 探测只 GET /health；数据库只 SELECT 1，不建表/迁移/写种子；SQLite 使用只读连接，不创建缺失文件；Redis 只 PING。普通配置探测不进行 LLM/Embedding 计费请求或存储写读测试；DeepSeek真实调用仅由上述显式CLI及独立测试驱动执行。

自动化测试使用安全模板和隔离临时 SQLite，清除继承的 DATABASE_URL/REDIS_URL，防止误用开发者运行库。测试包含环境覆盖、路径稳定性、秘密输出保护、启用服务缺项、元数据依赖/类型和资源未交付判定。
