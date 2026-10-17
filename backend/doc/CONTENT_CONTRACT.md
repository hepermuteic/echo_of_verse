# ContentPack 1.2 与 Godot 客户端契约

后端 0.5.0 当前源为 content/shuidiaogetou-3。完整内容使用 ContentPack 1.2、ResourceManifest 1.1；客户端 Poem/SaveSlot/Settings 和 JourneySnapshot 仍为 1.0。继续读取历史 ContentPack 1.0/1.1 与 ResourceManifest 1.0，旧源和既有交接不改写。

## runtime（1.2 新增）

1.2 必须提供非空 runtime 和 clientPresentation；旧版本不能携带非空 runtime。runtime 字段为 engine=godot、engineMajor=4、targetPlatform=windows、engineVersion、renderer、coordinateSystem=godot_right_handed_y_up、metersPerUnit=1、quaternionOrder=xyzw、bindingsConfirmed。

engineVersion 可为 null，确认值必须为准确 4.x 数字版本（不能填写 4.x 占位文本）；renderer 可为 null 或 forward_plus/mobile/gl_compatibility；bindingsConfirmed 为严格布尔值，默认为 false。三项未确认分别产生 GODOT_VERSION_PENDING、GODOT_RENDERER_PENDING、GODOT_BINDINGS_PENDING，草稿警告、正式发布错误。

内容 1.2 只搭配 Godot 资源清单 1.1；内容 1.0/1.1 只搭配旧清单 1.0，混用返回 RESOURCE_PROFILE。资源用途与传递依赖执行相同引擎兼容规则，详见 ASSETS.md。

当前资源目录 shuidiaogetou-assets-2，资源 ID 不变、版本升为 2；路径空缺、位置占位和绑定待确认均如实保留。后端不自动转换实际坐标、不补造场景路径或节点。

## 两类数据的职责

ClientPoem 是前端既有类型，统一用于 HTTP 和 client-poems.json。内部作品身份仍为 su_shi.shuidiaogetou；客户端身份为 shuidiaogetou。客户端字段和样例见 ../../api.md、examples/client-poems.json；其数据由 app/client_content.py 的单一投影函数生成。

完整 ContentPack 负责诗篇、稳定句段、三幕、事件前置、演出、文本、来源、场景绑定、参数和回顾规则。展示用 acts[{n,t}] 不含完整幕推进规则；stanzas 是语义句段的显示分组，不是事件进度。SaveSlot 的行数和幕索引不能作为通关证据。

## clientPresentation（1.1 新增）

| 字段 | 规则 |
| --- | --- |
| sourceCommit | 记录前端类型/文案来源固定提交；当前 e24415f2f5784df287fa20cb56b786e3e3c13e2f |
| id/title/form/dynasty/genre/first/art | 展示元数据，枚举同前端；art 不是引擎资源路径 |
| stanzaSegmentIds | 恰好两组，非空；按顺序覆盖全部 8 个稳定句段一次，不可重复、遗漏或重排 |
| acts | 三个 {actId,n}，必须与完整 acts 的顺序对应；输出 t 来自幕 title |
| imagery | {name,lineTextId,clipTextId,noteTextId,sourceTextId,art}[]；文本解析为前端 imagery 的四个字符串 |
| noteTextId? | 可选补充说明，缺省时不输出 note |

clientPresentation 的非空展示绑定在 schemaVersion=1.1/1.2 必需，不能缺失或 null；1.0 仅允许缺省或 null。精确结构见 content-pack.schema.json。引用文本必须存在且 required=true，参加正式发布审核；不能通过改成可选绕过客户端可见文本审核。

新增的意象说明、体验片段和出处均来自前端固定快照，保留 demo_unreviewed。出处显示与出版版本核验不同；原词、解释和创作类型分开登记。clip 不是玩家真实经历，不参与冻结回顾。

## 完整三幕语义保持

poem 的小序独立，segments 使用稳定 segmentId/唯一 order；contentVersion 与资源目录版本明确区分。对象、区域、出生点和环境均以 ID 绑定。资源清单保留 snake_case，内容字段保留 camelCase，assetId/assetVersion 显式映射 asset_id/asset_version。

三幕出口为 act1.cup.confirmed、act2.return.confirmed、act3.moon.confirmed。高处探索 act2.high.visited 可选；早返不能依赖高处。清影 act3.shadow.responded 必需，最终望月依赖清影。跨幕依赖只引用之前幕的出口。

Presentation 顺序执行，全部 required 步骤完成再确认事件；客户端在幕出口提交检查点。暂停、失焦、加载和结算不累计有效驻足，重置丢弃本幕未提交记录。当前 shadow.distance=1.5 meters 和五组演出仍未确认。

## 冻结快照与本地回顾

JourneySnapshot={schemaVersion,contentVersion,journeyId,completed,committedEvents:[{eventId,sequence}],regionDwell:[{regionId,effectiveSeconds}]}，独立于客户端完整存档和 SaveSlot。

事件必须唯一、sequence 严格递增、前置先确认，退出旧幕后不可补录；completed=true 要包含所有必需事件。区域已登记且不重复，时长非负有限。后端不从 HTTP 时长推算驻足。

Python evaluate_reflection 为参考，节点保留实际确认顺序；规则按 priority 降序、ruleId 升序选择，未匹配使用默认寄语。英文缺失回退中文并带 englishFallback。normal/early-return/no-optional 合成夹具随包交付，不是实际玩家数据。真实驻足寄语未启用，不使用测试阈值作为制作参数。

## 发布与兼容

validate 检查结构、引用、事件图、资源和客户端投影；export 可带真实待办；release 要求必需中文与来源审核、6 项关键英文及相关英文审核、必需资源及传递依赖 ready、演出和参数 confirmed。新增客户端文本也参加这些审核。工具检查声明，不核验人员真实性或设备质量。

2026-10-17 补强用途校验：事件节点/解释（包括可选事件）、演出对话（包括可选步骤）、insights、默认回顾、回顾规则和 clientPresentation 引用的文本均须 required=true。误设为可选时返回 REQUIRED_TEXT，objectId/field 指向消费位置，message 标明文本 ID；草稿与正式发布均拒绝。审核范围仍包含这些实际展示文本，不能靠标记退出中文或已有英文审核。未引用的可选文本不因此强制审核；关键英文仍仅按原 requiresEnglish 规则检查。

必需事件的 interact 触发对象，以及所有 Presentation 的 required 步骤引用的对象，均参加必需对象集合；对应对象 required=false 返回 REQUIRED_OBJECT（同样是草稿/发布语义错误）。必需资源按对象声明与实际必需用途的并集计算，再结合环境、音频和传递依赖检查。误改对象标记不能使资源退出 ASSET_PENDING 检查；独立可选装饰不提升为必需。资源未交付仍为草稿警告、发布错误。

目录按 contentVersion 原子交付，不覆盖；checksums 覆盖每个其他文件。1.2 仍为 17 文件，包含 GODOT_MAPPING.md、CLIENT_MAPPING.md 和客户端 JSON/Schema；1.1 的 17 文件使用 LEGACY_UNITY_RESOURCE_MAPPING.md，1.0 的 11 文件使用 UNITY_MAPPING.md。校验按三种完整集合执行，删文件后重写摘要列表也不通过。

旧 SaveSlot 不自动转成新事件快照；跨内容版本的快照不能混用，shuidiaogetou-2 的事件快照不能直接用于 -3。客户端应保留旧存档并提供显式兼容表。Godot 后端资源契约已声明；准确版本、渲染器、资源和节点绑定仍未确认。godotResourceContract=declared 仅表示所用契约，clientImport/playerAcceptance 继续 unverified；后端结构通过、Godot 导入、设备离线通关分别记录。
