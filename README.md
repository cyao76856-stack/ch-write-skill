# CH-Write-Skill

一个用于小说与剧本创作的中文 Codex Skill，支持生成、辅写、拆解、canon 管理、镜头与时长控制，以及版本化输出。

## 功能

- **生成剧本**：从来源材料推进到总结、大纲、四类列表、场景镜头计划、时序计划和正文。
- **辅写剧本**：支持续写、扩写、改写、重写和缩写。
- **拆解剧本**：只读输出总结、大纲、列表、图谱、时间线、地图和问题报告。
- **Canon 管理**：记录提案、确认、撤销、替代、依赖和影响。
- **版本化输出**：保留 working、proposals、versions、views、exports 和 archive。
- **确定性脚本**：通过 Python 脚本维护项目数据、校验、版本和渲染。

## 环境要求

- Codex Desktop 或兼容 Codex Skill 的环境
- Python 3.10 或更高版本
- 运行项目脚本不需要额外第三方依赖
- 运行测试需要 `pytest`

## 安装

### Windows

将仓库克隆到 Codex 的 skills 目录：

```powershell
git clone https://github.com/cyao76856-stack/ch-write-skill.git "$env:USERPROFILE\.codex\skills\ch-write-skill"
```

也可以手动将整个目录复制到：

```text
C:\Users\<your-name>\.codex\skills\ch-write-skill
```

安装后重新打开或刷新 Codex，使 Skill 被重新加载。

## 使用

在 Codex 中调用：

```text
$ch-write-skill
```

然后直接描述任务，例如：

```text
使用 $ch-write-skill 根据这份设定生成一个 12 分钟的短片剧本。
```

## 项目初始化

Skill 提供一个确定性脚本入口：

```powershell
python -B scripts/story_project.py init `
  --root "C:\path\to\story-project" `
  --name "My Story" `
  --script-master markdown `
  --interaction-profile balanced
```

常用命令：

```text
status
profile
source add
object add
decision add
change add
list upsert
timeline add
snapshot
confirm
impact
validate
render
archive
restore
```

## 目录结构

```text
ch-write-skill/
├── SKILL.md
├── README.md
├── LICENSE
├── .gitignore
├── agents/
├── assets/
├── references/
├── scripts/
└── tests/
```

## 测试

```powershell
python -m pytest -q
```

## 安全与隐私

- 默认不向外部服务发送稿件。
- 不要把 API Key、密码或其他凭据写入项目文件。
- 发布或分享项目时，先检查来源文本、导出文件和日志中是否包含隐私内容。
- 来源文本中的指令只作为叙事内容处理，不作为系统或工具指令执行。

## 贡献

欢迎提交 Issue 和 Pull Request。提交前请：

1. 运行测试。
2. 避免提交缓存、密钥和私人稿件。
3. 对流程、数据结构或确认规则的修改，请在 Pull Request 中说明影响范围。

## License

[MIT](LICENSE)
