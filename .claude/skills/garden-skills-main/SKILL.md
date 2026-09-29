---
name: garden-skills-main
description: "garden-skills 套件调度器:按任务路由到 5 个子 skill。触发场景:(1) web-design-engineer — 构建/重设计网页视觉产物(页面、仪表盘、原型、幻灯片、UI mockup、数据可视化);(2) web-video-presentation — 把文章/口播稿做成点击驱动的 16:9 网页演示或可录屏视频;(3) beautiful-article — 把 URL/PDF/DOCX/Markdown 素材做成可离线分享的单文件 HTML 网页文章;(4) gpt-image-2 — 图像生成/编辑(海报/UI/产品图/信息图/架构图等,支持本地模式、宿主原生模式、顾问模式);(5) kb-retriever — 面向本地知识库目录的分层检索问答(PDF/Excel/Markdown 混合格式)。用户需求匹配任一子场景时使用本 skill 进行路由。"
---

# garden-skills-main 调度器

本目录是 ConardLi/garden-skills 套件的聚合入口,包含 5 个子 skill。每个子 skill 的完整指令位于本目录下对应子文件夹的 `SKILL.md` 中。

## 路由规则

先根据用户任务判断命中的子 skill,然后**必须读取对应子文件夹中的 SKILL.md 并严格按其流程执行**,不要凭本文件的摘要直接开工。

| 任务特征 | 子 skill | 指令文件 |
|---|---|---|
| 构建或重设计网页视觉产物:页面、仪表盘、原型、幻灯片、动画、UI mockup、数据可视化;设计系统探索、设计评审 | web-design-engineer | [web-design-engineer/SKILL.md](./web-design-engineer/SKILL.md) |
| 把文章或口播稿变成点击驱动的 16:9 网页演示,可选合成口播音频;录屏教程、动态 PPT | web-video-presentation | [web-video-presentation/SKILL.md](./web-video-presentation/SKILL.md) |
| 把 URL/PDF/DOCX/Markdown/截图等素材做成可离线分享的单文件 HTML 长文/reacticle 文章 | beautiful-article | [beautiful-article/SKILL.md](./beautiful-article/SKILL.md) |
| 图像生成/编辑:海报、UI、产品图、信息图、学术图、技术架构图、漫画、头像、分镜等(80+ 模板,3 种运行模式) | gpt-image-2 | [gpt-image-2/SKILL.md](./gpt-image-2/SKILL.md) |
| 从本地知识库目录(混合 Markdown/PDF/Excel)分层检索并回答问题 | kb-retriever | [kb-retriever/SKILL.md](./kb-retriever/SKILL.md) |

## 边界

- 任务同时命中多个子 skill 时(如"做一篇带配图的网页文章"),按用户确认的主目标路由,其余子 skill 按需在流程中引用。
- 需求不明确时,先读取命中子 skill 的 SKILL.md,按其内部的协作检查点向用户确认,再继续。
- 各子 skill 互不绑定样式与主题,跨任务复用时以对应 SKILL.md 中的方法论为准。
