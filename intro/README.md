# AI 交易助手 · 独立产品介绍站

静态 HTML / CSS / JavaScript。沿用现有 Sites 项目与原生静态技术栈。

## 本地预览

在仓库根目录执行 `python3 -m http.server 4178 --directory intro`，访问 http://localhost:4178/ 。

## 内容与素材

- 视觉参考：https://landonorris.com/ ，采用大字、明暗叙事、荧光绿、轮廓纹理与画面叠放；未使用对方商标、人物照片、字体或源代码。
- `assets/*.png`：2026-11-13 从线上产品浏览器截图，未填充用户数据或重新绘制界面。
- 产品：https://haipi001.github.io/ai-trading-assistant/?lay=1#HELP
- 截图是实际 UI，但包含 LOCAL SIM 模拟行情、演示资讯和模拟账户。非实时市场或收益证明。
- 内容结合线上 HELP、实际页面与产品 README；描述入口时保留配置/预览/模拟及后端依赖边界。

## 交互

截图标签支持鼠标与方向键，原图支持对话框放大和 Esc 关闭，移动导航支持展开与收起。动效尊重减少动态效果设置。

## 发布与目录约定

线上产品介绍网站：https://ai-trading-assistant-intro.lizekai136.chatgpt.site/ 。

本目录是介绍网站源码，独立于交易工作台。HTML、CSS、JavaScript 直接维护，无需 npm 构建。`assets/` 为站点素材；请勿提交凭据或个人账户数据。根目录 GitHub Pages 流程只发布工作台，不会自动更新独立 Sites 介绍站；修改本目录后需另行同步并发布 Sites。
