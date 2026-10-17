# Echoes of Verse · 诗画入境

前后端源码与接口审查文档。当前前端是 Vue 静态展示原型，后端提供《水调歌头》的只读查询和离线内容工具；页面尚未接入 HTTP。仓库不包含 Godot 工程。

```text
backend/     后端源码、Schema、内容草稿、测试源码和配置模板
frontend/    从 fork 重新克隆的 Vue 前端，保留现有页面与静态诗库
api.md       前后端接口、字段传输约定和当前差异
readme.md    项目入口与启动说明
```

## 启动后端

需要 Python 3.12+ 和 uv。在 backend 目录执行：

```powershell
uv sync --frozen
if (-not (Test-Path config/credentials.env)) {
    Copy-Item config/credentials.env.example config/credentials.env
}
# 按需填写本机 credentials.env；默认 SQLite 不需要数据库账号。
uv run --env-file config/credentials.env python -m app.check_config
uv run --env-file config/credentials.env uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

本机默认地址：`http://127.0.0.1:8000`，接口查看 `/docs`。真实凭据不提交仓库。

## 启动前端

需要 Node.js 20.19+ 或 22.12+ 及 npm。在 frontend 目录执行：

```powershell
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

页面默认地址：`http://127.0.0.1:5173`。当前使用本地静态数据，启动后端不会自动让页面接入 API；本轮按要求仅审查并记录差异。

## 对接文档

主文档为 [api.md](api.md)，包含 Poem、查询参数、两种响应外壳、错误体、SaveSlot、Settings 及未接入项。补充资料保留在后端目录内：[配置](backend/doc/CONFIGURATION.md)、[内容契约](backend/doc/CONTENT_CONTRACT.md)、[资源](backend/doc/ASSETS.md)、[AI CLI](backend/doc/AI_AUTHORING.md)。

当前内容仍为草稿，真实资源、文学审核、Godot 绑定和设备体验须分别确认。Vue 行数进度不能作为真实通关或玩家事件证据。
