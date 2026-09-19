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
- 运行测试需要 pytest

## 安装

```powershell
git clone https://github.com/cyao76856-stack/ch-write-skill.git "$env:USERPROFILE\.codex\skills\ch-write-skill"
```

安装后重新打开或刷新 Codex，使 Skill 被重新加载。

## 使用

在 Codex 中调用：

```text
$ch-write-skill
```

## 项目初始化

```powershell
python -B scripts/story_project.py init --root "<project>" --name "<name>" --script-master markdown --interaction-profile balanced
```

## 测试

```powershell
python -m pytest -q
```

## License

MIT
