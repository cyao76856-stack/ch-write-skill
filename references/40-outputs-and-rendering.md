# 40 Outputs and Rendering

本参考定义四类列表、三档字段、权重优先级、master format、渲染与导出。

## 1. 四类列表

- `structure`：结构列表。
- `stages`：阶段列表。
- `genre`：类型列表（仅整部作品类型，不表示人物或地点分类）。
- `deconstruction`：解构列表。

## 2. 三档字段

- `simple`：编号、名称、类别、一句话定义或功能。
- `standard`：简版字段 + 核心属性、主要关系、当前阶段、剧情功能。
- `full`：标准版字段 + 来源、状态、关联项、影响、矛盾、未决问题和历史版本。

各列表的 `simple` 必填字段：
- `structure`：`id`、`name`、`layer`、`narrative_function`。
- `stages`：`id`、`name`、`object_type`、`stage_index`、`initial_state`。
- `genre`：`id`、`name`、`main_genre`、`subgenre`。
- `deconstruction`：`id`、`name`、`object_type`、`one_line_definition`。

`standard` 和 `full` 增加：
- `structure`：`mainline`、`connections`。
- `stages`：`goal`、`end_state`、`next_stage`。
- `genre`：`tone`、`narrative_form`、`novel_weight`。
- `deconstruction`：`core_attributes`、`function`、`current_state`。

`full` 再增加：`source_refs`、`status`、`related_items`、`impact`、`conflicts`、`open_questions`。

## 3. 权重与优先级

叙事权重固定维度：
- 人物、情节、世界、主题、情感、信息或悬疑、动作或冲突、社会或政治。
- 允许自定义维度。
- 权重表达：高、中、低、无，可进一步使用百分比或优先级排序。

列表版本优先级：
> 作者选择的列表版本 > 叙事权重 > skill 的默认建议。

叙事权重只能影响提问顺序、输出顺序、检查强度和默认建议，不能擅自升降列表版本。

## 4. Master format

- 列表 JSON/JSONL 是 master format；Markdown 是渲染视图。
- 手改 view 必须回填主数据后才能进入 canon。
- 剧本正文每个项目选择唯一 master format：Markdown 或 Fountain。
- DOCX 和 PDF 作为导出格式，不反向成为 canon。
- 导出文件标记来源版本、状态和导出时间。

## 5. 渲染链

```text
列表 JSON -> Markdown
人物图谱 JSON -> Mermaid/SVG；大型图谱使用 Graphviz
时间线 JSON -> Markdown/Mermaid
地点数据 -> SVG -> HTML 图册 -> PNG
剧本 master -> Markdown/Fountain -> DOCX -> PDF
```

当前脚本支持：
- `render lists --category structure|stages|genre|deconstruction --level simple|standard|full`。
- `render graph --graph-type relationships --output-format mermaid|svg|markdown`。
- `render timeline --timeline-type story-order --output-format mermaid|markdown`。
- `render maps --map-type topology --output-format json|svg|html`。

## 6. 能力分级

必需能力：
- 读写 txt、md、JSON、JSONL。
- 创建项目、working、proposals 和 versions。
- 维护 manifest、canon、decision 和 stale。
- 输出表格、清单和 Mermaid 文本。
- 安全跳过无法执行的内容。

目标支持能力：
- 读取 DOCX。
- 输出 Fountain。
- 生成 SVG 和 HTML。
- 导出 DOCX。

可选增强能力：
- Mermaid 转 SVG、Graphviz、PNG、PDF、OCR、外部资料检索、生成式图片。

能力不可用时必须明确降级，不能伪造成功结果。
