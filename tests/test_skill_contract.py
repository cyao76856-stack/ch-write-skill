import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REFS = [
    "00-core-loop.md", "10-project-model.md",
    "20-socratic-questioning.md", "21-confirmation-and-canon.md",
    "30-generate.md", "31-assist.md", "32-decompose.md",
    "40-outputs-and-rendering.md", "50-quality-and-conflicts.md",
    "60-errors-security-and-fallbacks.md",
]

ALLOWED_CONTROL_CHARS = {"\t", "\n", "\r"}

# Routing-doc contract: a request that clearly matches exactly one mode is
# auto-routed into that mode without a separate mode confirmation.
AUTO_MODE_RULE = "自动选择该模式并直接进入该模式的必要问题；不额外要求模式确认"
AMBIGUOUS_ONLY_RULE = "仅当请求真正模糊、多模式且无明确顺序，或与当前项目冲突时，才要求作者选择模式"
FIRST_QUESTION_MARKERS = (
    "首个必要叙事权重问题",
    "辅写目标与范围问题",
    "输出格式问题",
    "单个理由问题",
)


def _forbidden_control_chars(path):
    text = path.read_text("utf-8")
    return [
        (index, hex(ord(char)))
        for index, char in enumerate(text)
        if ord(char) < 32 and char not in ALLOWED_CONTROL_CHARS
    ]


class TestSkillContract(unittest.TestCase):
    def test_frontmatter_and_references(self):
        text = (ROOT / "SKILL.md").read_text("utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: ch-write-skill", text.splitlines())
        self.assertIn("description:", text)

        for name in REFS:
            self.assertTrue((ROOT / "references" / name).is_file(), name)
            self.assertIn(f"references/{name}", text, name)

    def test_agents_metadata(self):
        yaml = (ROOT / "agents" / "openai.yaml").read_text("utf-8")
        self.assertIn('display_name: "CH-Write-skill"', yaml)
        default_prompt_lines = [
            line for line in yaml.splitlines()
            if line.strip().startswith("default_prompt:")
        ]
        self.assertEqual(len(default_prompt_lines), 1)
        self.assertIn("ch-write-skill", default_prompt_lines[0])

    def test_no_control_characters(self):
        paths = [ROOT / "SKILL.md", ROOT / "agents" / "openai.yaml", *sorted((ROOT / "references").glob("*.md"))]
        for path in paths:
            self.assertEqual(_forbidden_control_chars(path), [], path)

    def test_generate_mapping_commands_are_intact(self):
        text = (ROOT / "references" / "30-generate.md").read_text("utf-8")
        for command in ("impact", "validate", "render", "archive", "restore"):
            self.assertIn(f"`{command}`", text, command)

    def test_no_unfinished_placeholders(self):
        paths = [
            ROOT / "SKILL.md",
            ROOT / "agents" / "openai.yaml",
            *sorted((ROOT / "references").glob("*.md")),
        ]
        for path in paths:
            text = path.read_text("utf-8")
            self.assertNotIn("TODO", text)
            self.assertNotIn("TBD", text)

    def test_clear_mode_auto_selection_rules(self):
        for path in (ROOT / "SKILL.md", ROOT / "references" / "00-core-loop.md"):
            text = path.read_text("utf-8")
            self.assertIn(AUTO_MODE_RULE, text, path)
            self.assertIn(AMBIGUOUS_ONLY_RULE, text, path)
            for marker in FIRST_QUESTION_MARKERS:
                self.assertIn(marker, text, path)

if __name__ == "__main__":
    unittest.main()
