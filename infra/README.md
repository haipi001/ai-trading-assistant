# 部署配置

当前后端部署入口为 `backend/render.yaml`。根目录 React 前端由 GitHub Pages 工作流构建。

`compose.managed.yml` 与 staging/production overlay 为历史托管镜像部署工具，必须提供适配当前前端的镜像和全部环境配置；本轮未执行云部署。旧 Next.js 开发 Compose 已存档至 `docs/legacy-foundation/docker-compose.nextjs.yml`，不作为当前启动入口。
