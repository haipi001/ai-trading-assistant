# 3002 唯一前端记录

- 唯一有效 UI：`/Users/lizekai/Documents/交易系统/ai-trading-assistant`
- 固定访问地址：`http://localhost:3002/`
- 当前版本：`ai-trading-assistant-full-2026.10.30-r127`
- 确认日期：2026-11-01
- 状态：当前交易系统目录中唯一保留的可运行前端方案。

## 启动

```bash
cd '/Users/lizekai/Documents/交易系统/ai-trading-assistant'
npm run dev -- --host 0.0.0.0 --port 3002
```

## 维护规则

- 后续用户提到“3002 UI”、“当前 UI”、“完整复刻版”或“最新 UI”，均默认指本目录。
- 不再从历史 Next.js `frontend`、`terminal` 或旧备份目录启动 UI。
- 新版本必须在本目录内递增，并同步更新 `VERSION.md`。

## AiCoin 补齐方式

用户于 2026-10-27 确认保留现有界面，补齐功能。r15 包含可读源码恢复、路由纠正、首批面板参数兼容及对比/价差计算工作区；未完成全部功能集成。详见 docs/AICOIN_INTEGRATION_2026_10_27.md。

后端统一维护在本目录 `backend/`；旧独立后端目录保留作历史副本。
