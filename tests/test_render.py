import tempfile
import unittest
from pathlib import Path

from ch_write.project import init_project
from ch_write.objects import add_object, add_relation
from ch_write.render import render_graph, render_lists, render_maps, render_timeline
from ch_write.lists import upsert_list_item
from ch_write.worlddata import append_location_state, append_timeline_entry


class TestRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "story"
        init_project(self.root, "Story", "markdown", "balanced")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_graph_timeline_and_map_render_from_master_data(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "character", "B", {})
        add_relation(self.root, a["object_id"], "affects", b["object_id"])
        upsert_list_item(self.root, "structure", {
            "id": "STR-0001", "name": "开场", "layer": "act",
            "narrative_function": "建立冲突"
        }, "simple")
        list_path = render_lists(self.root, "structure", "simple")
        graph_path = render_graph(self.root, "relationships", "mermaid")
        timeline_path = render_timeline(self.root, "story-order", "mermaid")
        map_path = render_maps(self.root, "topology", "svg")
        for path in (list_path, graph_path, timeline_path, map_path):
            self.assertTrue(path.is_file(), path)
        self.assertIn(a["object_id"], graph_path.read_text("utf-8"))
        placeholder = "TODO"
        self.assertNotIn(placeholder, list_path.read_text("utf-8"))


    def test_timeline_marks_unplaced_events(self):
        append_timeline_entry(self.root, "EVT-0001", {
            "event_id": "EVT-0001",
            "time_kind": None,
            "relation": "before",
            "anchor": "EVT-0002",
            "precision": None,
            "status": "unplaced",
            "source_refs": [],
            "known_by": [],
        })
        mermaid_path = render_timeline(self.root, "story-order", "mermaid")
        markdown_path = render_timeline(self.root, "story-order", "markdown")
        self.assertIn("EVT-0001", mermaid_path.read_text("utf-8"))
        self.assertIn("unplaced", mermaid_path.read_text("utf-8"))
        self.assertIn("EVT-0001", markdown_path.read_text("utf-8"))
        self.assertIn("unplaced", markdown_path.read_text("utf-8"))

    def test_map_svg_uses_location_id_from_master_data(self):
        location = add_object(self.root, "location", "王都", {})
        append_location_state(self.root, location["object_id"], {
            "location_id": location["object_id"],
            "valid_from": "760-01-01",
            "valid_to": None,
            "controller": "FCT-0001",
            "status": "正常",
            "precision": "approximate",
            "roads": [],
            "resources": [],
            "events": [],
        })
        svg_path = render_maps(self.root, "topology", "svg")
        text = svg_path.read_text("utf-8")
        self.assertIn(location["object_id"], text)
        self.assertIn("王都", text)
        self.assertNotIn("TODO", text)

    def test_svg_escapes_character_name_script_tag(self):
        add_object(self.root, "character", "<script>alert(1)</script>", {})
        svg_path = render_graph(self.root, "relationships", "svg")
        text = svg_path.read_text("utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertNotIn("<script>alert(1)</script>", text)

    def test_html_escapes_location_name_script_tag(self):
        location = add_object(self.root, "location", "<script>alert(1)</script>", {})
        append_location_state(self.root, location["object_id"], {
            "location_id": location["object_id"],
            "valid_from": "760-01-01",
            "valid_to": None,
            "controller": "FCT-0001",
            "status": "正常",
            "precision": "approximate",
            "roads": [],
            "resources": [],
            "events": [],
        })
        html_path = render_maps(self.root, "topology", "html")
        text = html_path.read_text("utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertNotIn("<script>alert(1)</script>", text)

    def test_simple_and_full_list_views_differ(self):
        item = {
            "id": "STR-0001", "name": "开场", "layer": "act",
            "narrative_function": "建立冲突", "mainline": "A",
            "connections": ["STR-0002"], "source_refs": ["SRC-0001"],
            "status": "draft", "related_items": ["STR-0002"],
            "impact": ["影响"], "conflicts": ["冲突"],
            "open_questions": ["问题"],
        }
        upsert_list_item(self.root, "structure", item, "full")
        simple_text = render_lists(self.root, "structure", "simple").read_text("utf-8")
        full_text = render_lists(self.root, "structure", "full").read_text("utf-8")
        self.assertNotEqual(simple_text, full_text)
        self.assertNotIn("open_questions", simple_text)
        self.assertIn("open_questions", full_text)

    def test_repeated_timeline_observations_collapse_to_latest(self):
        append_timeline_entry(self.root, "EVT-0001", {
            "event_id": "EVT-0001", "time_kind": None, "relation": "before",
            "anchor": "EVT-0002", "precision": None, "status": "unplaced",
            "source_refs": [], "known_by": [],
        })
        append_timeline_entry(self.root, "EVT-0001", {
            "event_id": "EVT-0001", "time_kind": "absolute", "relation": "before",
            "anchor": "EVT-0002", "precision": "exact", "status": "confirmed",
            "source_refs": [], "known_by": [],
        })
        text = render_timeline(self.root, "story-order", "mermaid").read_text("utf-8")
        self.assertIn("absolute", text)
        self.assertNotIn("unplaced", text)
        self.assertEqual(text.count('EVT-0001["'), 1)

    def test_repeated_location_states_collapse_to_latest(self):
        location = add_object(self.root, "location", "王都", {})
        append_location_state(self.root, location["object_id"], {
            "location_id": location["object_id"], "valid_from": "760-01-01",
            "valid_to": "760-01-02", "controller": None, "status": "旧状态",
            "precision": "approximate", "roads": [], "resources": [], "events": [],
        })
        append_location_state(self.root, location["object_id"], {
            "location_id": location["object_id"], "valid_from": "760-01-03",
            "valid_to": None, "controller": "FCT-0001", "status": "正常",
            "precision": "exact", "roads": [], "resources": [], "events": [],
        })
        text = render_maps(self.root, "topology", "svg").read_text("utf-8")
        self.assertIn("正常", text)
        self.assertNotIn("旧状态", text)
        self.assertEqual(text.count(f">{location['object_id']}<"), 1)

    def test_mermaid_labels_sanitize_special_characters(self):
        add_object(self.root, "character", "A|B]C\"D\nE", {})
        text = render_graph(self.root, "relationships", "mermaid").read_text("utf-8")
        self.assertNotIn("A|B]C\"D\nE", text)
        self.assertNotIn("A|B", text)
        self.assertNotIn("B]C", text)
        self.assertNotIn("C\"D", text)

    def test_html_atlas_keeps_pipe_in_location_name(self):
        location = add_object(self.root, "location", "A|B", {})
        append_location_state(self.root, location["object_id"], {
            "location_id": location["object_id"],
            "valid_from": "760-01-01",
            "valid_to": None,
            "controller": "FCT-0001",
            "status": "正常",
            "precision": "approximate",
            "roads": [],
            "resources": [],
            "events": [],
        })
        text = render_maps(self.root, "topology", "html").read_text("utf-8")
        self.assertIn("A|B", text)
        self.assertNotIn("A\\|B", text)

    def test_markdown_tables_escape_pipes_and_newlines(self):
        upsert_list_item(self.root, "structure", {
            "id": "STR-0001", "name": "A|B\nC", "layer": "act",
            "narrative_function": "建立冲突",
        }, "simple")
        text = render_lists(self.root, "structure", "simple").read_text("utf-8")
        self.assertIn("A\\|B C", text)
        self.assertNotIn("A|B\nC", text)


if __name__ == "__main__":
    unittest.main()
