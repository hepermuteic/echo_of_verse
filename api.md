# 前后端 API 与字段传输审查

本文件是本仓库的对接入口，依据 `frontend/` 当前源码、`backend/` 0.5.0 及其 OpenAPI/Schema 整理。前端源自 fork 的 `e24415f2f5784df287fa20cb56b786e3e3c13e2f`；本轮按要求只审查、整理目录与文档，**没有增加前端 HTTP 接入代码**。

## 1. 当前状态与边界

| 项目 | 当前实现 | 对接结论 |
|---|---|---|
| 客户端技术 | Vue 3 + Vite + TypeScript | 此仓库不是 Godot 工程，没有 project.godot、场景或 GDScript |
| 诗篇数据 | frontend/src/data/poems.ts 内的静态 POEMS，12 首 | 页面未请求后端；后端仅支持《水调歌头》 |
| Poem 展示字段 | 前端 Poem 与后端 ClientPoem | 字段形状兼容；实际网络消费未接入 |
| HTTP 查询 | 后端提供三个只读 GET | 前端没有 fetch/axios 调用、API base URL 配置或 Vite 代理 |
| 存档 | 前端 localStorage、3 槽 SaveSlot | 不上传后端，不是完整旅程或通关证明 |
| 设置 | 设置页内存状态；音乐音量与静音另行持久化 | 后端提供默认值/字段契约，没有设置保存 API |
| 诗意反馈 | 前端结尾页按行数显示，后端另有离线 JourneySnapshot 工具 | 两者尚未联动，不能从行数合成玩家事件 |

“字段形状兼容”“后端 HTTP 可用”“页面已接通”“Godot 导入通过”“设备可玩”是不同结论。本文不将前两项当作后三项。

## 2. 地址、认证与传输规则

- 本机后端默认地址为 `http://127.0.0.1:8000`。在 backend 目录启动，命令见 [readme.md](readme.md)。
- Swagger：`/docs`；运行时机器契约：`/openapi.json`；仓库快照：[backend/examples/openapi.json](backend/examples/openapi.json)。
- 三个路由均为 GET，没有请求体，也没有必需的 API token / Authorization 头；不提供登录注册。
- DeepSeek、数据库等凭据仅供后端本机使用，不传给浏览器、Poem、URL 查询参数或 localStorage。
- HTTP 为 UTF-8 JSON；查询参数使用 URLSearchParams 等方式编码中文，不能手工拼接未编码的标题或作者。
- 浏览器直连跨端口后端时需要明确配置 CORS 来源，或以后配置 Vite 同源代理。当前 vite.config.ts 未配置代理，本文不代表代理已实现。
- EOV_API_BASE_URL 只用于后端探测，不是前端配置，也不控制 uvicorn 监听端口。现有前端没有 VITE_API_BASE_URL 消费代码。

## 3. GET /health

无参数。成功 200：

```json
{"status":"ok","mode":"offline_content","deployment":"local_single_process"}
```

只证明数据库检查成功，不保证内容、审核、资源或客户端体验就绪。数据库不可用返回 503。

## 4. GET /api/v1/poems

| 查询参数 | 类型 | 默认值 | 约束 |
|---|---|---|---|
| limit | 整数 | 20 | 1–100 |
| offset | 整数 | 0 | 非负 |

拒绝未知参数。前端现有朝代、题材筛选是对本地静态数组的筛选，不能直接作为 dynasty / genre 参数传给此接口。

响应形状（类型表示，完整 JSON 见 [HTTP 示例](backend/examples/client-http-examples.json)）：

```ts
type ContentState = {
  contentVersion: string | null
  contentStatus: 'missing' | 'draft' | 'released' | 'invalid'
}
type PoemListItem = Poem & ContentState & {
  content_review_status: 'demo_unreviewed' | 'reviewed'
}
type PoemListResponse = {
  items: PoemListItem[]
  total: number
  limit: number
  offset: number
}
```

关键点：作品字段直接平铺在 `items[i]`，没有 `items[i].poem`。当前 total 为 0 或 1，offset>0 返回空 items，但 total 仍为作品总数。初始化没有收录成功时目录可以为空；不能自动改用静态 12 首掩盖接口失败或空目录。

## 5. GET /api/v1/poems/lookup

| 查询参数 | 类型 | 约束 |
|---|---|---|
| title | string，必填 | trim 后长度 1–128，不能为空 |
| author | string，可省略 | 一旦提供，trim 后长度 1–128，不能传空字符串 |

匹配按 NFKC、空白归一化和大小写处理后精确比较；标题允许书名号，不是模糊搜索。支持当前作品标题别名“水调歌头”。

请求示例：`GET /api/v1/poems/lookup?title=%E6%B0%B4%E8%B0%83%E6%AD%8C%E5%A4%B4&author=%E8%8B%8F%E8%BD%BC`。

```ts
type LookupMatch = ContentState & {
  poem: Poem
  content_review_status: 'demo_unreviewed' | 'reviewed'
}
type LookupResponse = ContentState & {
  poem_exists: boolean
  status: 'not_found' | 'poem_only' | 'content_available'
  message: string
  matches: LookupMatch[]
}
```

关键点：查询作品位于 `matches[i].poem`；版本和审核状态位于匹配项外层。不能把整个 LookupResponse 直接当 Poem，也不能照目录的平铺结构解包查询结果。

正常命中使用 `status=content_available`。`poem_only` 为保留的 Schema 枚举，不是当前新版成功投影的承诺。未收录返回 200：

```json
{"poem_exists":false,"contentVersion":null,"contentStatus":"missing","status":"not_found","message":"当前 Demo 未收录该作品","matches":[]}
```

这表示“未收录”，不等于网络错误，也不会触发任意诗词在线生成。

## 6. Poem / ClientPoem 字段

前端定义见 [frontend/src/data/poems.ts](frontend/src/data/poems.ts)；后端定义见 [backend/app/client_contracts.py](backend/app/client_contracts.py)，Schema 见 [client-poem.schema.json](backend/examples/client-poem.schema.json)，完整作品见 [client-poems.json](backend/examples/client-poems.json)。

| 字段 | 传输类型 | 当前约束 / 含义 |
|---|---|---|
| id | string | 后端只返回 shuidiaogetou；内部数据库 ID 为 su_shi.shuidiaogetou，不改主键 |
| title、author、first | string | 标题、作者、首句；当前“水调歌头”“苏轼”“明月几时有” |
| form | ci / qu / shi | 当前 ci |
| dynasty | 唐 / 宋 / 元 / 明 / 清 | 当前宋 |
| genre | 送别 / 边塞 / 思乡 / 山水 / 田园 / 咏月 / 怀古 / 羁旅 / 咏物 / 感怀 | 当前咏月 |
| preface? | string | 小序独立，不并入正文行数 |
| stanzas | [string[], string[]] | 恰好两组非空字符串数组；当前上下阕各四句 |
| acts? | {n:string,t:string}[] | 展示幕编号与标题；不是事件推进配置 |
| imagery? | Imagery[] | 见下表；当前明月、酒杯、清影 |
| note? | string | 可选补充说明 |
| art | ArtKey | 本地展示映射键；不是图片 URL、Godot 路径或模型资源 |

后端对缺省的可选字段省略键，不输出 null。前端已有 `p.acts ?? DEFAULT_ACTS` 和 `p.imagery ?? []` 降级逻辑可以使用；不要凭缺失字段合成玩家事件。

后端展示文本要求长度 1–8192，数字/布尔值不能代替字符串；每组 stanza 至少一行。前端 TypeScript 只约束静态类型，没有对应的网络运行时长度或类型校验。三个幕标题属于展示字段，不承载完整事件前置条件。

Imagery 为 `{name,line,clip,note,src,art}`，前五项均为字符串、art 为 ArtKey。`clip` 是创作展示文案，`src` 是出处说明，不是玩家行为或网络地址。

ArtKey 的 17 个值：`home`、`scene`、`moon`、`cup`、`shadow`、`mist`、`weicheng`、`jingting`、`denggao`、`fengqiao`、`momei`、`cunju`、`tianjingsha`、`linjiangxian`、`jihaizashi`、`rumengling`、`liangzhou`。键值存在不代表后端支持对应诗篇。

HTTP 和离线使用相同作品投影，但离线 `client-poems.json` 是 Poem 数组，没有 HTTP 外壳；离线审核/版本状态另读完整内容包和 validation-report。

## 7. SaveSlot：字段兼容与当前差异

前端定义及实现见 [frontend/src/store/save.ts](frontend/src/store/save.ts)，后端 Schema 见 [client-save-slot.schema.json](backend/examples/client-save-slot.schema.json)。

| 字段 | 契约 | 当前前端读取行为 |
|---|---|---|
| poemId | 当前仅 shuidiaogetou | 允许任一本地静态诗库 ID |
| lineIndex | 整数 0–8 | Number 转换并仅限制下界，可能接受小数或超过 8 的值 |
| act | 整数 0–2 | Number 转换后 clamp；没有严格整数校验 |
| savedAt | 非负整数 Unix 毫秒 | Number 转换；无效/零值可能替换为 Date.now() |

契约示例：`{"poemId":"shuidiaogetou","lineIndex":0,"act":0,"savedAt":0}`。布尔值、字符串或小数不能作为后端严格契约中的整数。

当前 localStorage key 为 `eov:saves:v1`，有 3 个槽。存档写入失败被忽略、只保留内存状态；未提供完整可恢复失败提示。本轮不修改该逻辑，也不上传/删除用户存档。未来接入单作品目录时须显式处理旧作品槽，不能将旧行数存档迁移成虚构的 JourneySnapshot。

## 8. Settings：只定义字段，没有保存接口

设置页见 [SettingsPage.vue](frontend/src/pages/SettingsPage.vue)，默认值和 Schema 见 [client-default-settings.json](backend/examples/client-default-settings.json) / [client-settings.schema.json](backend/examples/client-settings.schema.json)。

| 字段 | 类型 / 范围 | 默认值 |
|---|---|---|
| master / music / ambient / voice / mouse | 整数 0–100 | 80 / 20 / 70 / 90 / 50 |
| size / sub / quality | 整数 0–2 | 1 / 0 / 1 |
| brush / reduce / subOn | boolean | true / false / true |

前端初始字段与默认值一致，但 music 初值来自已保存的 BGM 音量。当前只持久化音乐音量和静音，分别使用 `eov:bgm:v1`、`eov:bgm:mute:v1`；其余字段主要保留在页面内存中。页面显示“设置已保存”不能证明所有字段落盘或生效；“恢复默认”按钮也尚未绑定实现。没有 POST /settings 或服务器设置读取接口。

## 9. 错误、状态和未来接入要求

错误外壳为 `{error:{code,message,fields?},request_id}`，响应头含同一 `X-Request-ID`。前端以后应按 HTTP 状态及 error.code 分流，不能只读取 message 或把所有错误当“未收录”。

| HTTP / code | 处理含义 |
|---|---|
| 404 / HTTP_ERROR | 路径不存在；旧任务、会话、报告 API 已退役 |
| 405 / HTTP_ERROR | 方法错误，响应保留 Allow |
| 422 / VALIDATION_ERROR | 修正参数；fields 含 location、message、type |
| 500 / LOCAL_DATA_INVALID | SQL 当前作品资料损坏 |
| 500 / INTERNAL_ERROR | 通用内部错误，使用请求 ID 排障 |
| 503 / DATABASE_UNAVAILABLE | 数据库暂不可用 |
| 503 / CONTENT_UNAVAILABLE | 当前内容缺失、损坏、引用无效或无法投影 |

未来实际接入至少应实现：加载/空目录/错误状态、超时与取消、明确重试、正确解包两种响应外壳、运行时字段检查、审核状态展示、旧存档兼容。当前没有这些 HTTP 处理逻辑；本轮不宣称已实现。

## 10. JourneySnapshot 与 Godot 边界

当前 EndingPage.vue 的 onMounted 会把 lineIndex 写到全诗长度，并按行数比例点亮“登临”等节点。直接进入结尾页也可能得到满行数，所以它不能证明真实通关、登高或诗意反馈正确。

JourneySnapshot 独立于 SaveSlot：

```ts
type JourneySnapshot = {
  schemaVersion: '1.0'
  contentVersion: string
  journeyId: string
  completed: boolean
  committedEvents: {eventId:string,sequence:number}[]
  regionDwell: {regionId:string,effectiveSeconds:number}[]
}
```

仅允许同版本内容、唯一且按顺序确认的真实事件。三个幕出口为 `act1.cup.confirmed`、`act2.return.confirmed`、`act3.moon.confirmed`；高处探索可选，清影响应必需。未登高不得写入登高事件或生成登高经历；暂停、失焦、加载、结算不累计有效驻足。详细规则见 [内容契约](backend/doc/CONTENT_CONTRACT.md)。

Godot 资源契约使用 ContentPack 1.2 / ResourceManifest 1.1；准确版本、渲染器、res:// 资源路径和实际节点绑定仍待交付。art 展示键不能转换成虚构资源路径。资源、Godot 导入、Windows 导出与设备断网通关分别验收，参见 [资源说明](backend/doc/ASSETS.md)。

## 11. AI 与凭据

AI 制作在后端 CLI 中显式执行，支持解析、BM25 文化检索校验、Scene Schema、草稿编译及 JourneySnapshot 反馈，不新增 HTTP API。需要模型调用授权及现有请求预算；普通 API 启动不会调用模型。用法见 [AI 说明](backend/doc/AI_AUTHORING.md)。

真实凭据仅填写 `backend/config/credentials.env`，仓库只提供 [空值模板](backend/config/credentials.env.example)。配置和转义见 [配置说明](backend/doc/CONFIGURATION.md)。数据库账户和 AI 密钥不得放进 Vite 的 VITE_* 变量，因为这些值会进入客户端构建。
