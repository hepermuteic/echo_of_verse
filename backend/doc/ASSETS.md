# 资源交接：Godot 4.x 契约与旧版兼容

后端 0.5.0 默认使用 ContentPack 1.2 / ResourceManifest 1.1，目标为 Godot 4.x、Windows 桌面。当前交付后端声明与校验契约，准确版本、渲染器、实际文件和场景绑定未确认，没有创建或导入 Godot 工程。

资源身份为 (asset_id,asset_version)，catalog_version 标识清单快照。任意合法资源 ID 可登记；ID 开放不等于格式、用途和依赖校验取消。

## Godot 资源清单 1.1

schema_version=1.1、engine=godot，全部资源使用 delivery=godot_resource。资源稳定 ID 保持不变；迁移记录的 asset_version 升为 2，catalog_version 为 shuidiaogetou-assets-2。

| 用途 asset_type | format | 路径扩展名 |
| --- | --- | --- |
| scene / vfx | tscn | .tscn |
| model | glb | .glb |
| material | tres | .tres |
| texture | png | .png |
| audio | wav / ogg / mp3 | 对应音频扩展名 |

resource_path 只接受规范化 res:// 项目路径，保留大小写；拒绝空段、点段、父级段、反斜杠、磁盘绝对路径、远程地址、编码路径、查询串、片段和控制字符。路径扩展名须与 format 一致。地址、Unity 版本/渲染管线、旧坐标元数据及远程位置不能混入 Godot 资源记录。

declared 可暂缺 resource_path，不据资源 ID 猜测文件位置。ready 要求路径、正整数 size_bytes、SHA-256 和明确使用权；这些是交付声明，不代表后端读取了文件或验证了场景。当前八项全部 declared，路径为空、license=pending，没有冒充资源已交付。

对象使用 scene/model/vfx，音频步骤使用 audio；平台只允许 windows/any。直接引用及传递依赖复用同一引擎/平台规则。资源不得 retired；身份版本精确、依赖存在且无环；ready 不得依赖 declared。必需资源集合继续按声明与实际用途的并集计算，不允许通过对象可选标记绕过交付。

## 运行约定与发布门槛

ContentPack 1.2 的 runtime 声明 engine=godot、engineMajor=4、targetPlatform=windows。engineVersion 和 renderer 可为空，renderer 为 forward_plus/mobile/gl_compatibility；bindingsConfirmed 默认为 false。三项未确认时草稿给出警告，正式发布失败。

coordinateSystem=godot_right_handed_y_up，metersPerUnit=1，quaternionOrder=xyzw；旋转须归一化，位置/缩放有限且缩放为正。当前位置和出生点仍为占位，不进行 Unity→Godot 自动坐标转换，也不将这些值当作真实场景绑定。

Godot 客户端按稳定 objectId/regionId/spawnId/environmentId 注册实际节点。后端不虚构 NodePath。res:// 用于随包资源，客户端存档/设置应写 user://；实际导入、目标平台导出和设备通关分别验收。

格式和坐标依据：[Godot 文件系统](https://docs.godotengine.org/en/stable/tutorials/scripting/filesystem.html)、[3D 坐标](https://docs.godotengine.org/en/stable/tutorials/3d/introduction_to_3d.html)、[音频格式](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_audio_samples.html)。

## 旧版资源清单 1.0

旧 ContentPack 1.0/1.1 继续使用 ResourceManifest 1.0；保留 builtin、Windows/any、URP/未指定渲染元数据约束。builtin 需要 address 与匹配 Unity 对象格式，对象引用 prefab/model/vfx。1.0 不允许混入 Godot 资源；1.1 资源清单不允许混入旧记录。

旧 placement 仍按 Unity 左手系、Y 向上、米解释，rotation 为归一化 xyzw 四元数。旧源和历史交接不改写，新内容不能将旧坐标直接标为已确认 Godot 绑定。

ResourceManifest 的 snake_case 与内容 AssetRef 的 camelCase 显式映射。客户端 art 是前端展示键，不是清单资源身份或本地引擎地址。模型详见 app/resources.py 和 examples/resource-manifest.schema.json。

当前仍有 7 项必需引用/依赖未交付。旧 file/addressables 仅为预留元数据，不作为新 Godot 交付类型；不新增下载端点或 OSS 接入。

离线核对命令：
`uv run python -m app.check_config --manifest content/shuidiaogetou-3/resource-manifest.json`。
--require-ready 当前预期失败。正式内容发布继续检查类型、版本、用途、依赖和使用权。

Godot 准确版本、渲染器、实际资源及绑定由客户端和资源提供方补齐后，再以新版本确认交付并实际导入验收。结构校验不会提高工程验收状态。
