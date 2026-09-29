---
name: superpower
description: "superpowers 开发方法论套件调度器:按工作流阶段路由到 15 个子 skill。触发场景:任何创造性/功能开发工作开始前(brainstorming);有规格需拆解多步实现计划时(writing-plans);执行实现计划(executing-plans 或 subagent-driven-development);实现任何功能或修 bug 前(test-driven-development);遇到 bug、测试失败或异常行为(systematic-debugging);需要隔离工作区(using-git-worktrees);有 2+ 个无依赖的独立任务可并行(dispatching-parallel-agents);完成任务或大功能后需要代码评审(requesting-code-review / receiving-code-review);即将宣称工作完成前(verification-before-completion);实现完成需决定如何集成分支(finishing-a-development-branch);创建/编辑/验证 skill(writing-skills);superpowers 会话出错需要复盘(diagnosing-superpowers)。匹配任一子场景时使用本 skill 进行路由。"
---

# superpower 调度器

本目录是 obra/superpowers 方法论套件的聚合入口,包含 15 个子 skill。每个子 skill 的完整指令位于本目录下对应子文件夹的 `SKILL.md` 中。

## 核心原则

只要某个子 skill 可能适用于当前任务(哪怕只有 1% 的可能),就必须先读取其 SKILL.md 并遵循执行;不允许绕过流程直接写代码。

## 路由规则

先根据当前所处的工作流阶段判断命中的子 skill,然后**必须读取对应子文件夹中的 SKILL.md 并严格按其流程执行**。

| 阶段 / 触发条件 | 子 skill | 指令文件 |
|---|---|---|
| 会话开始,建立 skill 查找与使用规范 | using-superpowers | [using-superpowers/SKILL.md](./using-superpowers/SKILL.md) |
| 任何创造性工作(新功能、新组件、行为修改)开始前,探索意图与设计 | brainstorming | [brainstorming/SKILL.md](./brainstorming/SKILL.md) |
| 有规格/需求,需要产出多步实现计划(写代码之前) | writing-plans | [writing-plans/SKILL.md](./writing-plans/SKILL.md) |
| 执行实现计划:功能开发需要隔离工作区时 | using-git-worktrees | [using-git-worktrees/SKILL.md](./using-git-worktrees/SKILL.md) |
| 执行实现计划:本人作为实现者在本会话内联执行 | executing-plans | [executing-plans/SKILL.md](./executing-plans/SKILL.md) |
| 执行实现计划:每个任务派发子代理并在任务间做评审 | subagent-driven-development | [subagent-driven-development/SKILL.md](./subagent-driven-development/SKILL.md) |
| 有 2+ 个无共享状态、无顺序依赖的独立任务 | dispatching-parallel-agents | [dispatching-parallel-agents/SKILL.md](./dispatching-parallel-agents/SKILL.md) |
| 实现任何功能或修 bug,写实现代码之前 | test-driven-development | [test-driven-development/SKILL.md](./test-driven-development/SKILL.md) |
| 遇到任何 bug、测试失败或非预期行为,提出修复方案之前 | systematic-debugging | [systematic-debugging/SKILL.md](./systematic-debugging/SKILL.md) |
| 完成任务/大功能或合并前,请求代码评审 | requesting-code-review | [requesting-code-review/SKILL.md](./requesting-code-review/SKILL.md) |
| 收到代码评审反馈,落实建议之前(不盲从、先验证) | receiving-code-review | [receiving-code-review/SKILL.md](./receiving-code-review/SKILL.md) |
| 即将宣称工作完成/已修复/通过之前,先跑验证命令拿证据 | verification-before-completion | [verification-before-completion/SKILL.md](./verification-before-completion/SKILL.md) |
| 实现完成、测试全过,决定如何集成分支 | finishing-a-development-branch | [finishing-a-development-branch/SKILL.md](./finishing-a-development-branch/SKILL.md) |
| 创建新 skill、编辑现有 skill 或部署前验证 | writing-skills | [writing-skills/SKILL.md](./writing-skills/SKILL.md) |
| superpowers 会话出了问题(返工、计划被忽略、结果差、耗时过长等)需要归因或写 bug 报告 | diagnosing-superpowers | [diagnosing-superpowers/SKILL.md](./diagnosing-superpowers/SKILL.md) |

## 典型工作流串联

brainstorming → writing-plans → using-git-worktrees → subagent-driven-development(内含 test-driven-development、requesting-code-review)→ verification-before-completion → finishing-a-development-branch

调试场景:systematic-debugging →(修复后)verification-before-completion

## 边界

- 多个子 skill 同时命中时,按工作流阶段顺序依次进入,不要跳过未完成的前置阶段。
- 用户明确说"跳过计划/直接改"时,仍建议先读取 verification-before-completion 与 test-driven-development 的 SKILL.md,再决定是否让步并说明风险。
