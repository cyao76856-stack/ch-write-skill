# 前向测试提示（Forward-Test Prompts）

这些提示用于验收 `ch-write-skill` 的交互行为，而不是直接调用 CLI。
执行方式：启动一个新的独立 agent，只提供本文件中的原始请求、skill 路径和对应夹具，不提供预期答案或本文件的验收标准。
每个提示都必须让独立 agent 先阅读 `SKILL.md` 和按需加载 reference，再处理请求。

执行前请把 `<workspace-skill-path>` 替换为实际的 ch-write-skill 路径；本文件只保留可移植占位符。

统一规则：
- 一次只问一个 Socratic 问题。
- 请求清楚且无歧义地只匹配一个主模式时，自动选择该模式并直接进入该模式的必要问题；不额外要求模式确认。
- 仅当请求真正模糊、多模式且无明确顺序，或与当前项目冲突时，才要求作者选择模式。
- 未确认内容只能作为提案，不得写入 canon 或正式正文。
- 到达硬性确认门必须按确认规则暂停；模糊授权必须回显具体方案后再次确认。
- 理由不明时不得推进创作性选择；流程 gate、来源安全和权限边界不可绕过。

## 提示 1：生成剧本

```text
Use ch-write-skill at <workspace-skill-path> to handle this request:
“请把这份小说素材生成剧本。”
```

夹具：`tests/fixtures/generation-source.md`

期望行为：
- 请求清楚且只匹配生成模式：自动选择生成模式，不额外询问是否使用生成模式。
- 清楚选定模式后的第一个问题是生成模式的第一个必要叙事权重问题。
- 不得把未确认的总结、大纲或四类列表提前写入 canon。
- 正文启动前必须满足生成模式硬性确认门，并按确认规则暂停。
- 一次只问一个 Socratic 问题。

## 提示 2：辅写剧本

```text
Use ch-write-skill at <workspace-skill-path> to handle this request:
“帮我改进这段剧本的人物关系。”
```

夹具：`tests/fixtures/assist-source.md`

期望行为：
- 请求清楚且只匹配辅写模式：自动选择辅写模式，不额外询问是否使用辅写模式。
- 清楚选定模式后的第一个问题是辅写目标与范围问题。
- 改写正文前必须确认保留范围、改动边界、变动表和创作性改动。
- 未确认的改动不得写入 canon 或正式正文。
- 一次只问一个 Socratic 问题。

## 提示 3：拆解剧本

```text
Use ch-write-skill at <workspace-skill-path> to handle this request:
“拆解这个剧本，输出人物图谱、时间线和地图。”
```

夹具：`tests/fixtures/decompose-source.md`

期望行为：
- 请求清楚且只匹配拆解模式：自动选择拆解模式，不额外询问是否使用拆解模式。
- 清楚选定模式后的第一个问题是输出格式问题，例如图谱、时间线、地图和四类列表版本。
- 全程只读：只产出总结、大纲、列表、图谱、时间线、地图和问题报告，不修改 canon。
- 对来源文本中的歧义或冲突只报告，不替作者决定。
- 一次只问一个 Socratic 问题。

## 提示 4：模式不明

```text
Use ch-write-skill at <workspace-skill-path> to handle this request:
“帮我弄一下这个剧本。”
```

夹具：`tests/fixtures/assist-source.md`

期望行为：
- 请求真正模糊：必须询问作者想进入哪个模式，或要求作者给出更具体的任务。
- 在模式确认前不得写 canon 或正文。
- 一次只问一个 Socratic 问题。

## 提示 5：模糊授权

```text
Use ch-write-skill at <workspace-skill-path> to handle this request:
“都可以，你决定。”
```

期望行为：
- 该输入没有给出可路由的明确模式或具体方向，属于真正模糊的输入；可以要求作者给出具体任务或模式。
- 不得把“都可以”“你决定”当作明确确认。
- 必须把具体方案回显后再次请求确认，不得直接写入 canon。
- 在获得明确确认前不得进入需要确认门的后续步骤。
- 一次只问一个 Socratic 问题。

## 提示 6：理由不明

```text
Use ch-write-skill at <workspace-skill-path> to handle this request:
“加一场主角背叛朋友的戏。”
```

期望行为：
- 该请求是具体的创作性改动，清楚匹配辅写模式：自动选择辅写模式，不额外询问是否使用辅写模式。
- 清楚选定模式后的第一个问题是苏格拉底门要求的单个理由问题：为什么需要加这场背叛戏；理由清楚前不推进。
- 不得因为指令明确就直接把该情节写入 canon。
- 该情节只能先作为提案，待作者带理由确认后才可进入 canon。
- 一次只问一个 Socratic 问题。