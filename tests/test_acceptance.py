import tempfile
import unittest
from pathlib import Path
from ch_write.decisions import is_explicit_confirmation, record_change, record_decision
from ch_write.modes import classify_request
from ch_write.objects import add_object, add_relation
from ch_write.project import init_project
from ch_write.render import render_graph, render_maps, render_timeline
from ch_write.sources import register_sources
from ch_write.worlddata import append_location_state, append_timeline_entry

ROOT = Path(__file__).resolve().parents[1]


def _register_one(root: Path, name: str) -> dict:
    src = ROOT / "tests" / "fixtures" / name
    report = register_sources(root, [{
        "path": str(src), "order": 1, "priority": 1,
        "merge_strategy": "material"
    }])
    return report["sources"][0]


class TestAcceptance(unittest.TestCase):
    def test_generation_source_can_be_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "Generation", "markdown", "balanced")
            source = _register_one(project, "generation-source.md")
            self.assertEqual(source["status"], "registered")
            self.assertIsNotNone(source["digest"])
            text = (ROOT / "tests" / "fixtures" / "generation-source.md").read_text(encoding="utf-8")
            self.assertIn("商船", text)
            self.assertIn("尸体", text)
            self.assertIn("爆炸", text)

    def test_ambiguous_confirmation_not_accepted(self):
        self.assertFalse(is_explicit_confirmation("都可以", ["DEC-0001"]))
        self.assertFalse(is_explicit_confirmation("你决定", ["DEC-0001"]))

    def test_conflicting_sources_are_both_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "Conflict", "markdown", "balanced")
            a = ROOT / "tests" / "fixtures" / "conflict-a.md"
            b = ROOT / "tests" / "fixtures" / "conflict-b.md"
            report = register_sources(project, [
                {"path": str(a), "order": 1, "priority": 1, "merge_strategy": "canon-source"},
                {"path": str(b), "order": 2, "priority": 2, "merge_strategy": "reference"},
            ])
            self.assertEqual(len(report["sources"]), 2)
            for source in report["sources"]:
                self.assertEqual(source["status"], "registered")
                self.assertIsNotNone(source["digest"])
            self.assertNotEqual(report["sources"][0]["digest"], report["sources"][1]["digest"])

    def test_assist_source_registers_unapplied_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "Assist", "markdown", "balanced")
            source = _register_one(project, "assist-source.md")
            self.assertEqual(source["status"], "registered")
            self.assertIsNotNone(source["digest"])
            text = (ROOT / "tests" / "fixtures" / "assist-source.md").read_text(encoding="utf-8")
            self.assertIn("沈青", text)
            self.assertIn("沈白", text)
            change = record_change(project, {
                "type": "character_relation",
                "location": "第一场",
                "original": "沈青把酒杯推给沈白，沈白没有接。",
                "problem": "人物动机不足",
                "proposal": "补充兄弟多年未见的原因，再写这场对手戏。",
                "expected_effect": "让沈白的拒绝有动机支撑",
                "impact": {"scope": "scene"},
            })
            self.assertEqual(change["confirmation_status"], "pending")
            self.assertEqual(change["execution_status"], "pending")
            self.assertIsNone(change["version"])

    def test_decompose_source_builds_and_renders_stable_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "Decompose", "markdown", "balanced")
            source = _register_one(project, "decompose-source.md")
            self.assertEqual(source["status"], "registered")
            self.assertIsNotNone(source["digest"])
            text = (ROOT / "tests" / "fixtures" / "decompose-source.md").read_text(encoding="utf-8")
            self.assertIn("孟舟", text)
            self.assertIn("青苇渡", text)
            self.assertIn("白鹭洲", text)

            char = add_object(project, "character", "孟舟", {})
            loc = add_object(project, "location", "青苇渡", {})
            event = add_object(project, "event", "夜航", {})
            add_relation(project, char["object_id"], "appears_in", loc["object_id"])
            append_location_state(project, loc["object_id"], {
                "location_id": loc["object_id"],
                "valid_from": "永和七年",
                "valid_to": None,
                "controller": None,
                "status": "active",
                "precision": "exact",
                "roads": [],
                "resources": [],
                "events": [event["object_id"]],
            })
            append_timeline_entry(project, event["object_id"], {
                "event_id": event["object_id"],
                "time_kind": "absolute",
                "precision": "approximate",
                "status": "active",
                "source_refs": [source["source_id"]],
                "known_by": ["decompose"],
            })

            graph_path = render_graph(project, "relationships", "markdown")
            timeline_path = render_timeline(project, "story-order", "markdown")
            map_path = render_maps(project, "topology", "json")

            graph_text = graph_path.read_text(encoding="utf-8")
            self.assertIn(char["object_id"], graph_text)
            self.assertIn(loc["object_id"], graph_text)
            self.assertIn(event["object_id"], timeline_path.read_text(encoding="utf-8"))
            self.assertIn(loc["object_id"], map_path.read_text(encoding="utf-8"))

    def test_request_mode_classification(self):
        self.assertEqual(classify_request("请把这份小说素材生成剧本。"), "generate")
        self.assertEqual(classify_request("帮我改进这段剧本的人物关系。"), "assist")
        self.assertEqual(classify_request("拆解这个剧本，输出人物图谱、时间线和地图。"), "decompose")
        self.assertEqual(classify_request("分析剧本的人物关系图。"), "decompose")
        self.assertEqual(classify_request("请做叙事分析。"), "decompose")
        self.assertEqual(classify_request("分析一下。"), "ambiguous")

    def test_assist_markers_beat_generic_write_marker(self):
        for request in ("改写剧本", "重写剧本", "续写剧本", "扩写剧本", "辅写剧本"):
            with self.subTest(request=request):
                self.assertEqual(classify_request(request), "assist")

    def test_ambiguous_request_requires_mode_selection(self):
        self.assertEqual(classify_request("帮我弄一下这个剧本。"), "ambiguous")
        self.assertEqual(classify_request("都可以，你决定。"), "ambiguous")

    def test_missing_reason_does_not_record_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "MissingReason", "markdown", "balanced")
            with self.assertRaises(ValueError):
                record_decision(project, {
                    "title": "主角背叛",
                    "content": "加一场主角背叛朋友的戏。",
                    "direct_purpose": "把人物推进不可逆选择",
                    "expected_effect": "读者看到关系的破裂",
                    "alternatives": [],
                    "affected_objects": [],
                })
            self.assertFalse((project / "logs" / "decisions.jsonl").exists())
            self.assertFalse((project / "indexes" / "decisions.json").exists())