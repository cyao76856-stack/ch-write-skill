# 10 Project Model

本参考定义主数据、索引、对象、关系、四维状态、稳定编号、存储和版本策略。

## 1. 主原则

- 主数据只存一次；列表 JSON/JSONL 和剧本 master 是 canon 的唯一来源。
- 附件按内容哈希去重；版本使用 manifest 与差异；提案使用索引与补丁。
- 展示内容按需渲染；旧版本压缩归档；上下文按需加载。
- working 可修改但不是 canon；proposals 是不可修改的提案归档；vNNN 是不可修改的确认版本。
- views 和 exports 可重新生成，不反向成为 canon。

## 2. 项目结构

```text
<项目名>/
├── project.json
├── indexes/
│   ├── entities.json
│   ├── relations.json
│   ├── sources.json
│   └── versions.json
├── store/
│   ├── objects/
│   │   ├── characters.jsonl
│   │   ├── locations.jsonl
│   │   ├── factions.jsonl
│   │   ├── events.jsonl
│   │   ├── rules.jsonl
│   │   └── items.jsonl
│   ├── relations.jsonl
│   ├── lists/
│   │   ├── structure.json
│   │   ├── stages.json
│   │   ├── genre.json
│   │   └── deconstruction.json
│   ├── timeline.jsonl
│   ├── location_states.jsonl
│   └── blobs/
├── logs/
│   ├── decisions.jsonl
│   ├── changes.jsonl
│   └── open-questions.jsonl
├── versions/
│   ├── v001/manifest.json
│   ├── v002/manifest.json
│   └── v003/manifest.json
├── working/
├── proposals/
│   ├── index.jsonl
│   └── patches/
├── views/
├── exports/
└── archive/
```

## 3. 索引

- `indexes/entities.json`：当前对象快照，`objects` 为 `object_id -> entry` 的映射。
- `indexes/relations.json`：当前有效关系链；可由 `store/relations.jsonl` 重建。
- `indexes/sources.json`：来源登记、路径、顺序、优先级、合并策略、摘要、状态。
- `indexes/versions.json`：版本清单和版本间链接。
- 索引是派生状态；主日志为 append-only，修改后应重建对应索引。

## 4. 对象与关系

### 对象类型与稳定编号
- CHR：人物。
- LOC：地点。
- FCT：势力或组织。
- EVT：事件。
- OBJ：物品或资源。
- RUL：规则。
- REL：关系。
- THM：主题或母题。
- SCN：场景。
- STG：阶段。
- STR：结构项。
- DEC：决定。
- CHG：变动。
- SRC：来源。

### 编号规则
- 格式为 `TYPE-0001` 或更多位。
- 编号一旦分配永不复用；名称变化不改变编号。
- 删除对象标记 tombstoned；合并保留旧编号并建立映射；拆分创建新编号并记录来源。
- 同名不等于同实体；跨来源合并必须由作者确认。
- 所有图谱、时间线、列表和 canon 引用稳定编号，不依赖显示名称。

### 关系类型
`depends_on`、`causes`、`blocks`、`enables`、`contains`、`appears_in`、`knows`、`owns`、`affects`、`contradicts`、`supersedes`、`same_as`、`derived_from`。

## 5. 四维状态

### 来源类型
`source-derived`、`inferred`、`proposed`、`imported`、`unknown`。

### 决定状态
`pending`、`confirmed`、`rejected`、`withdrawn`、`superseded`、`stale`、`waived`。

### 文件状态
`draft`、`reviewed`、`confirmed`、`immutable`、`tampered`。

### Canon 归属
`active`、`stale`、`excluded`。

任何主数据记录都至少包含来源类型；决定记录使用决定状态；working 文件使用文件状态；canon 条目使用 canon 归属。

## 6. 主数据存储

- 对象日志为 `store/objects/<type>.jsonl`，每条记录包含 `object_id`、`type`、`name`、`aliases`、`attributes`、`status`、`revision`、`created_at`、`updated_at`。
- 关系日志为 `store/relations.jsonl`，每次变更追加新关系记录，旧关系被 `supersedes` 替代。
- 时间线与地点状态为 append-only：`store/timeline.jsonl` 和 `store/location_states.jsonl`，每次观测追加，不覆盖历史。
- 四类列表主数据为 `store/lists/<category>.json`；每项保留 `revision`、`history`、`created_at`、`updated_at`。
- `logs/decisions.jsonl` 是系统主决策记录；Markdown 只作为读取视图。
- `logs/changes.jsonl` 保存变动表；`logs/open-questions.jsonl` 保存未决项。

## 7. 版本模型

- `working/` 可修改，未确认。
- `snapshot` 将 working 状态固化到 `proposals/` 或待确认批次。
- `confirm` 完成后创建新版本 manifest 到 `versions/vNNN/`。
- 每个 manifest 记录父版本、确认批次、对象 revision、新增、移除、stale、来源版本、导出记录。
- 未变化对象继续引用旧 revision，不复制完整内容。
- `archive` 压缩旧版本，`restore` 可恢复；两者都不得覆盖已存在目标。
- 版本损坏时标记不完整，不自动重建并冒充原版本。

## 8. 禁止事项

- 不在作者确认前写 canon；不覆盖旧版本；不删除提案和决定历史。
- 不让 view 或 export 反向修改 master data。
- 不自动级联修改 canon；所有影响先列出并等待作者逐项决定。
