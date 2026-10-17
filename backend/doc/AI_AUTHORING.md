# 水调歌头 AI 解析与 RAG 内容制作

2026-10-17 新增授权：真实 AI/RAG 的后端 CLI。HTTP 仍为 0.5.0 的只读目录服务，现有 Docker 不更新；客户端、三幕事件和正式发布条件不改变。

## 快速使用

工作目录：仓库内 `backend`，先用 `uv sync --locked` 安装锁定依赖。

统一填写文件为后端 `config/credentials.env`；首次克隆且文件不存在时，从 `config/credentials.env.example` 复制。填入 `DEEPSEEK_API_KEY`，需要更换 API 地址或模型时修改同文件的 `LLM_API_BASE_URL` / `LLM_MODEL`。真实文件不提交仓库，模板可以提交；不要复制历史测试密钥。已有进程环境变量优先于凭据文件，应用自身不会自动加载该文件。详细填写及转义规则见 [配置说明](CONFIGURATION.md)。

```powershell
uv run --env-file config/credentials.env python -m app.ai_authoring build-index --run-id my-index
# 检查 AI 配置是否完整，不调用模型、不连接数据库。
uv run --env-file config/credentials.env python -m app.check_config --config config/ai-authoring.example.toml
# 以下两条会调用模型；执行前必须有有效凭据和独立确认的剩余授权预算。
uv run --env-file config/credentials.env python -m app.ai_authoring run --with-scene --allow-model-calls --run-id my-realm
uv run --env-file config/credentials.env python -m app.ai_authoring validate --claims examples/ai-validation-claims.json --allow-model-calls --run-id my-fact-check
```

凭据文件本身不授予计费请求预算。示例模型命令必须在获得本轮调用授权后使用；已有账本不可清空或绕过。续测须单独授权并显式指定对应账本。

默认配置为 `config/ai-authoring.example.toml`，通过已有 `load_config` 读取；`--config` 可指定自己的 TOML。CLI 默认 profile 为 DeepSeek、`https://api.deepseek.com`、`deepseek-flash`、`DEEPSEEK_API_KEY`；该配置不启用 HTTP 或健康检查中的模型调用。原服务模板和 Embedding 预留设置不变。API 地址必须是不带口令、query、fragment 的 HTTP(S) base URL。环境变量覆盖继续生效。

`build-index` 完全本地；`analyze` 解析小序和八句；`validate` 默认提取并检查现有文化说明；`run` 检查生成解析和现有文化说明，`run --with-scene` 继续生成Scene Schema、检查新场景并编译独立Godot草稿。除 `build-index` 外须显式传 `--allow-model-calls`。所有命令都不连接业务数据库。普通 API 启动和 `check_config` 不计费调用模型。

## 命令输入与退出码

- `--source`：内容源目录，默认现有 `content/shuidiaogetou-3`；仅允许内部身份 `su_shi.shuidiaogetou` 及原八个稳定句段。
- `--corpus`、`--dictionary`：本地知识库 JSON 和 UTF-8 专名词典；默认 `knowledge/shuidiaogetou` 下的文件。
- `--index`：可选已生成的 `index.json`；使用前重算并检查指纹、来源及词项，过期或篡改则失败。
- `validate --analysis <analysis.json>`：核对输入报告的内容、知识库和逐句检索证据后检查其主张；不额外检查现有文化说明。与 `--claims` 互斥。
- `validate --claims <claims.json>`：输入 `Claim[]`，字段为 claimId、targetId、text、kind，可选 sourceQuote。targetId 必须是当前句段、小序或文本 ID；kind 为 original/historical/interpretation/game_creation。显式输入的 kind 是调用者声明，game_creation 单独列出，不作为事实已核验。
- `generate-scene --analysis <analysis.json> --validation <validation.json>`：复用已经验证的阶段产物生成三幕场景；检查内容/知识库摘要和证据一致性。只接受现有Godot 1.2/1.1内容档，不把旧Unity源迁移为新格式。
- `feedback --journey <snapshot.json>`：离线读取JourneySnapshot；也接受明确的 `{synthetic:true,input:<snapshot>}` 参考夹具。拒绝SaveSlot和不符合事件/前置/顺序/内容版本的快照，不写回存档。用户提供的快照始终未核验设备真实性，情绪标为文学推断。
- `--output`：草稿父目录；`--run-id`：便携名称，仅字母、数字、点、下划线、短横线，首字符必须是字母或数字。相对 CLI 文件路径基于当前工作目录；配置文件相对路径延续现有配置加载规则，基于后端根目录。
- 退出码：0 执行完成；1 模型、额度或授权条件失败；2 输入、文件或输出目录失败。0 不代表所有主张都被证据支持，更不代表人工审核通过。

## 知识与解析约定

首批知识库保存教育局原词/注释、彭文良期刊论文、王莉茹文化随笔的必要资料。古代原词去除教学注码，现代说明为编者摘要，均记录 locator、representation、作者/发布机构、采集日期和人工未审核状态。摘要引用只能称为“知识库摘要”，不能伪称源文逐字引文。网络 PDF 不能代替纸质版本核验。没有下载或宣称校验原始 PDF 字节。

BM25 使用 jieba 搜索模式（HMM=false）、项目专名词典、k1=1.5、b=0.75、NFKC/casefold。自然段保持来源边界，超过600字符则无丢失切分；每次最多六个正分结果。指纹涵盖完整知识库、专名词典、jieba 版本、其基础词典摘要及算法版本。不做向量检索；无须 Embedding、pgvector 或 Redis。

解析按 preface、sdt.segment.01 至 .08 输出，每段有释义、情绪变化及 time/location/people/imagery/actions/sounds/events/emotions 八维列表。每个非空值必须提供原文原句或本次检索证据，并注明 explicit/inferred/imagined/unknown；未知值为“未知”，没有证据的维度为空列表。events 是诗义语义，不是玩家事件记录。

文化说明先提取带源文片段的原子主张，并保留整段覆盖检查，降低漏提取导致的绕过。模型给出 supported/contradicted/insufficient/conflicting，分别对应证据支持/证据反驳/证据不足/来源冲突。当前提示版本sdt-ai-2使用每条主张自己的0起始证据索引；程序从本条真实段落构造引用，不让模型编写chunkId或引文。越界/重复索引拒绝，冲突至少引用两个不同来源。sourceQuote必须是目标原文中的真实片段，并参与短释义检索。公开ValidationReport仍保留逐字引文和来源。语义判断仍由模型提供，不构成事实正确性证明。game_creation单列，模型不得修改humanReview；旧sdt-ai-1报告仍可读取。

## Scene Schema与离线反馈

场景生成消费有效解析及RAG报告，仅把supported主张作为文化事实约束，其余保留不足/冲突状态。LLM生成三幕的时间、天气、地点、情绪、对象米制位置、视觉提示、声音方向、事件旁白和交互说明。场景中的新增细节是game_creation；原词未明示天气必须说明，不把月宫想象当成实际登月。

对象、事件和资源仅引用当前来源中的稳定身份；全部对象、事件和句段必须覆盖。编译保留现有事件前置、触发器及必需/可选属性，把模型的位置和旁白写入新版本ContentPack，并保留视觉/声音/场景设定为未审核创作文本。通过新场景文化检查后才编译。资源状态、路径、使用权不会被模型升级；bindingsConfirmed=false，正式发布仍阻断。

离线反馈调用现有快照验证器后生成按已提交事件排序的逐节点诗句解释，不增加未出现的登高事件，不从UI行数推导通关。真实联调仅使用明确标记的参考夹具，不宣称实际玩家或设备已验收。

## 请求额度与故障

首轮默认账本为 仓库内 `work/ai-rag-261017/deepseek-budget.json`，跨命令共享20次上限。每次网络请求前锁定账本并原子持久化，崩溃留下的reserved请求也占额度。账本损坏或锁冲突时停止，不自动清空或重置。仅在用户明确授权新一轮测试时，通过`--budget-ledger <新路径>`选择独立账本；每本仍最多20次，不得用切换账本绕过同一首轮授权。每次计费测试还须遵守操作者另行确认的费用预算。

请求采用非流式 JSON Output、禁用思考、最多8192输出 token；输入消息序列化后最多24000字符。超长批次按完整对象拆分；单个对象仍过长则明确失败，不裁掉证据。429、500/502/503/504及网络临时错误最多重试两次，1/2秒退避；400/401/402/403等立即停止。空内容、截断、JSON/字段/引用错误最多重新生成一次。以上全部重试都计入20次。用量记录实际返回模型与 token 数，缺失用量保持 null，不伪造费用。

## 交付边界

输出包含解析、引用、场景、反馈和相应校验和；同名目录不覆盖。生成结果始终为未审核草稿，必须另行完成文学审核、资源交付、Godot 导入和设备验收。参考旅程不等于真实玩家记录。

参考：[DeepSeek 接入](https://api-docs.deepseek.com/zh-cn/)、[JSON Output](https://api-docs.deepseek.com/zh-cn/guides/json_mode/)、[思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)、[jieba](https://github.com/fxsjy/jieba)。
