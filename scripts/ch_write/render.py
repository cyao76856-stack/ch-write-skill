from __future__ import annotations

import html
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from .constants import LIST_LEVELS
from .io import read_json, read_jsonl
from .lists import LIST_CATEGORIES, _SIMPLE_REQUIRED
from .objects import effective_relations

GRAPH_TYPES = ("relationships",)
GRAPH_FORMATS = ("mermaid", "svg", "markdown")
TIMELINE_TYPES = ("story-order",)
TIMELINE_FORMATS = ("mermaid", "markdown")
MAP_TYPES = ("topology",)
MAP_FORMATS = ("json", "svg", "html")

_CATEGORY_LABELS = {
    "structure": "结构",
    "stages": "阶段",
    "genre": "类型",
    "deconstruction": "解构",
}

def _require_initialized_project(root: Path) -> None:
    if not (Path(root) / "project.json").is_file():
        raise FileNotFoundError(f"project is not initialized: {Path(root) / 'project.json'}")


def _load_project(root: Path) -> dict:
    _require_initialized_project(root)
    return read_json(Path(root) / "project.json")


def _output_detail(root: Path) -> str:
    profile = _load_project(root).get("interaction_profile", {})
    detail = profile.get("output_detail") if isinstance(profile, dict) else None
    return detail if detail in ("brief", "standard", "detailed") else "standard"


def _write_text(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _escape_xml(value) -> str:
    return _xml_escape(str(value))


def _display(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _load_entities(root: Path) -> dict:
    path = Path(root) / "indexes" / "entities.json"
    if not path.exists():
        return {}
    data = read_json(path)
    entities = data.get("objects", {})
    if not isinstance(entities, dict):
        raise ValueError("invalid entities index")
    return entities


def _is_active_entry(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("tombstoned"):
        return False
    if entry.get("merged_into") is not None:
        return False
    status = entry.get("status", "active")
    return status not in ("tombstoned", "merged")


def _load_active_relations(root: Path) -> list[dict]:
    path = Path(root) / "indexes" / "relations.json"
    if path.exists():
        data = read_json(path)
        relations = data.get("relations", [])
        if not isinstance(relations, list):
            raise ValueError("invalid relations index")
    else:
        relations = effective_relations(root)
    return [
        relation for relation in relations
        if isinstance(relation, dict) and relation.get("status") == "active"
    ]


def _mermaid_text(value) -> str:
    text = str(value)
    text = text.replace("\\", " ")
    text = text.replace('"', "")
    text = text.replace("'", "")
    text = text.replace("[", "(").replace("]", ")")
    text = text.replace("{", "(").replace("}", ")")
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "/")
    return text.strip()


def _markdown_cell(value) -> str:
    return _display(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _markdown_inline(value) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")



def _mermaid_node_id(value) -> str:
    node_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")
    if not node_id:
        node_id = "NODE"
    if node_id[0].isdigit():
        node_id = f"N{node_id}"
    return node_id


def _fields_for_level(category: str, level: str, item: dict) -> list[str]:
    if level == "full":
        return [field for field in item]
    simple_fields = tuple(_SIMPLE_REQUIRED[category])
    standard_fields = {
        "structure": ("id", "name", "layer", "narrative_function", "mainline", "connections"),
        "stages": ("id", "name", "object_type", "stage_index", "initial_state", "goal", "end_state", "next_stage"),
        "genre": ("id", "name", "main_genre", "subgenre", "tone", "narrative_form", "novel_weight"),
        "deconstruction": ("id", "name", "object_type", "one_line_definition", "core_attributes", "function", "current_state"),
    }[category]
    fields = simple_fields if level == "simple" else standard_fields
    return [field for field in fields if field in item]


def _one_line_for_item(category: str, item: dict) -> str:
    field = {
        "structure": "narrative_function",
        "stages": "initial_state",
        "genre": "subgenre",
        "deconstruction": "one_line_definition",
    }[category]
    return _display(item.get(field))


def render_lists(root: Path, category: str, level: str) -> Path:
    """Render one list master file as a Markdown view."""
    root = Path(root)
    _require_initialized_project(root)
    if category not in LIST_CATEGORIES:
        raise ValueError(f"category must be one of {LIST_CATEGORIES}")
    if level not in LIST_LEVELS:
        raise ValueError(f"level must be one of {LIST_LEVELS}")

    list_path = root / "store" / "lists" / f"{category}.json"
    if list_path.exists():
        data = read_json(list_path)
        items = data.get("items", [])
        if not isinstance(items, list):
            raise ValueError(f"invalid list master data: {list_path}")
    else:
        items = []

    detail = _output_detail(root)
    lines = [f"# {_CATEGORY_LABELS.get(category, category)} · {level}", ""]
    if not items:
        lines.append("（暂无条目）")
    else:
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = _markdown_inline(item.get("id", ""))
            name = _markdown_inline(item.get("name", ""))
            one_line = _markdown_cell(_one_line_for_item(category, item))
            fields = _fields_for_level(category, level, item)
            lines.append(f"## {name} · `{item_id}`")
            lines.append("")
            if detail == "brief":
                lines.append(f"- `{item_id}` {name} — {one_line}")
                for field in fields:
                    lines.append(f"  - **{_markdown_cell(field)}**: {_markdown_cell(item.get(field))}")
                lines.append("")
                continue
            lines.append("| 字段 | 值 |")
            lines.append("| --- | --- |")
            for field in fields:
                lines.append(f"| {_markdown_cell(field)} | {_markdown_cell(item.get(field))} |")
            lines.append("")

    return _write_text(
        root / "views" / "lists" / f"{category}.{level}.md",
        "\n".join(lines) + "\n",
    )


def _graph_mermaid(nodes: dict, relations: list[dict]) -> str:
    lines = ["graph TD"]
    for object_id, entry in nodes.items():
        label = _mermaid_text(
            f"{entry.get('name', object_id)} ({entry.get('type', 'unknown')})"
        )
        node_id = _mermaid_node_id(object_id)
        lines.append(f'  {node_id}["{label}"]')
    for relation in relations:
        source_id = relation.get("source_id")
        target_id = relation.get("target_id")
        if source_id not in nodes or target_id not in nodes:
            continue
        label = _mermaid_text(relation.get("relation", ""))
        lines.append(
            f"  {_mermaid_node_id(source_id)} -->|{label}| "
            f"{_mermaid_node_id(target_id)}"
        )
    return "\n".join(lines) + "\n"


def _graph_svg(nodes: dict, relations: list[dict]) -> str:
    node_ids = list(nodes)
    columns = max(1, min(4, len(node_ids)))
    rows = (len(node_ids) + columns - 1) // columns
    node_width = 220
    node_height = 64
    gap_x = 40
    gap_y = 60
    width = columns * node_width + (columns + 1) * gap_x
    height = rows * node_height + (rows + 1) * gap_y

    positions = {}
    for index, object_id in enumerate(node_ids):
        column = index % columns
        row = index // columns
        positions[object_id] = (
            gap_x + column * (node_width + gap_x),
            gap_y + row * (node_height + gap_y),
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
        f'<title>relationships graph</title>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>',
        '.node rect { fill:#eef3ff; stroke:#345; stroke-width:1.5; }',
        '.node text { font-family: sans-serif; }',
        '.edge { stroke:#666; stroke-width:1; fill:none; }',
        '</style>',
    ]

    for relation in relations:
        source_id = relation.get("source_id")
        target_id = relation.get("target_id")
        if source_id not in positions or target_id not in positions:
            continue
        x1, y1 = positions[source_id]
        x2, y2 = positions[target_id]
        label = _escape_xml(relation.get("relation", ""))
        parts.append(
            f'<line class="edge" x1="{x1 + node_width}" y1="{y1 + node_height // 2}" '
            f'x2="{x2}" y2="{y2 + node_height // 2}" marker-end="url(#arrow)"/>'
        )
        parts.append(
            f'<text x="{(x1 + x2 + node_width) // 2}" '
            f'y="{(y1 + y2 + node_height) // 2}" font-size="11">{label}</text>'
        )
    parts.append(
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" '
        'refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" '
        'fill="#666"/></marker></defs>'
    )

    for object_id, (x, y) in positions.items():
        entry = nodes[object_id]
        name = _escape_xml(entry.get("name", object_id))
        object_type = _escape_xml(entry.get("type", "unknown"))
        parts.append(f'<g class="node">')
        parts.append(
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="8"/>'
        )
        parts.append(
            f'<text x="{x + 12}" y="{y + 20}" font-size="12" font-weight="bold">'
            f'{_escape_xml(object_id)}</text>'
        )
        parts.append(
            f'<text x="{x + 12}" y="{y + 38}" font-size="13">{name}</text>'
        )
        parts.append(
            f'<text x="{x + 12}" y="{y + 52}" font-size="11" fill="#555">{object_type}</text>'
        )
        parts.append('</g>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _graph_markdown(nodes: dict, relations: list[dict]) -> str:
    lines = ["# relationships", "", "| 对象 | 类型 | 名称 |", "| --- | --- | --- |"]
    for object_id, entry in nodes.items():
        lines.append(
            f"| {_markdown_cell(object_id)} | {_markdown_cell(entry.get('type'))} | "
            f"{_markdown_cell(entry.get('name'))} |"
        )
    lines.append("")
    lines.append("| 源 | 关系 | 目标 |")
    lines.append("| --- | --- | --- |")
    for relation in relations:
        if relation.get("source_id") not in nodes or relation.get("target_id") not in nodes:
            continue
        lines.append(
            f"| {_markdown_cell(relation.get('source_id'))} | "
            f"{_markdown_cell(relation.get('relation'))} | "
            f"{_markdown_cell(relation.get('target_id'))} |"
        )
    return "\n".join(lines) + "\n"


def render_graph(root: Path, graph_type: str, output_format: str) -> Path:
    """Render the current object/relation graph as Mermaid, SVG, or Markdown."""
    root = Path(root)
    _require_initialized_project(root)
    if graph_type not in GRAPH_TYPES:
        raise ValueError(f"graph_type must be one of {GRAPH_TYPES}")
    if output_format not in GRAPH_FORMATS:
        raise ValueError(f"output_format must be one of {GRAPH_FORMATS}")

    entities = _load_entities(root)
    relations = _load_active_relations(root)
    nodes = {
        object_id: entry for object_id, entry in entities.items()
        if _is_active_entry(entry)
    }
    for relation in relations:
        for endpoint in ("source_id", "target_id"):
            object_id = relation.get(endpoint)
            entry = entities.get(object_id)
            if object_id and object_id not in nodes and _is_active_entry(entry):
                nodes[object_id] = entry
    nodes = dict(sorted(nodes.items(), key=lambda pair: pair[0]))

    if output_format == "mermaid":
        content = _graph_mermaid(nodes, relations)
        suffix = ".mmd"
    elif output_format == "svg":
        content = _graph_svg(nodes, relations)
        suffix = ".svg"
    else:
        content = _graph_markdown(nodes, relations)
        suffix = ".md"

    return _write_text(
        root / "exports" / "graphs" / f"{graph_type}{suffix}",
        content,
    )


def _timeline_is_placed(record: dict) -> bool:
    if record.get("status") == "unplaced":
        return False
    if not record.get("time_kind"):
        return False
    precision = record.get("precision")
    if not precision or precision == "unknown":
        return False
    return True


def _collapse_timeline(records: list[dict]) -> list[tuple[str, dict, int]]:
    latest: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        event_id = record.get("event_id")
        if not event_id:
            continue
        latest[event_id] = record
        counts[event_id] = counts.get(event_id, 0) + 1
    return [
        (event_id, latest[event_id], counts[event_id])
        for event_id in latest
    ]


def _timeline_mermaid(records: list[dict]) -> str:
    collapsed = _collapse_timeline(records)
    lines = ["flowchart LR"]
    if not collapsed:
        lines.append('  EMPTY["（暂无时间线事件）"]')
    else:
        for event_id, record, _history_count in collapsed:
            event_id = str(event_id)
            node_id = _mermaid_node_id(event_id)
            if _timeline_is_placed(record):
                time_kind = _mermaid_text(record.get("time_kind", ""))
                precision = _mermaid_text(record.get("precision", ""))
                label = f"{event_id} ({time_kind}, {precision})"
            else:
                label = f"{event_id} (unplaced)"
            lines.append(f'  {node_id}["{_mermaid_text(label)}"]')
    return "\n".join(lines) + "\n"


def _timeline_markdown(records: list[dict]) -> str:
    collapsed = _collapse_timeline(records)
    lines = ["# story-order", ""]
    if not collapsed:
        lines.append("（暂无时间线事件）")
        return "\n".join(lines) + "\n"
    lines.append("| 事件 | 时间类型 | 精度 | 状态 | 记录数 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for event_id, record, history_count in collapsed:
        placement = "" if _timeline_is_placed(record) else " (unplaced)"
        lines.append(
            f"| {_markdown_cell(event_id)}{placement} | "
            f"{_markdown_cell(record.get('time_kind'))} | "
            f"{_markdown_cell(record.get('precision'))} | "
            f"{_markdown_cell(record.get('status'))} | "
            f"{history_count} |"
        )
    return "\n".join(lines) + "\n"


def render_timeline(root: Path, timeline_type: str, output_format: str) -> Path:
    """Render the append-only timeline log as Mermaid or Markdown."""
    root = Path(root)
    _require_initialized_project(root)
    if timeline_type not in TIMELINE_TYPES:
        raise ValueError(f"timeline_type must be one of {TIMELINE_TYPES}")
    if output_format not in TIMELINE_FORMATS:
        raise ValueError(f"output_format must be one of {TIMELINE_FORMATS}")

    records = read_jsonl(root / "store" / "timeline.jsonl")
    if output_format == "mermaid":
        content = _timeline_mermaid(records)
        suffix = ".mmd"
    else:
        content = _timeline_markdown(records)
        suffix = ".md"

    return _write_text(
        root / "exports" / "timelines" / f"{timeline_type}{suffix}",
        content,
    )


def _assets_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets"


def _map_locations(root: Path) -> list[dict]:
    entities = _load_entities(root)
    records = read_jsonl(root / "store" / "location_states.jsonl")
    latest: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        location_id = record.get("location_id")
        if not location_id:
            continue
        latest[location_id] = record

    locations = []
    for location_id, record in latest.items():
        entry = entities.get(location_id)
        name = entry.get("name") if isinstance(entry, dict) else None
        locations.append({
            "location_id": location_id,
            "name": name or location_id,
            "valid_from": record.get("valid_from"),
            "valid_to": record.get("valid_to"),
            "controller": record.get("controller"),
            "status": record.get("status"),
            "precision": record.get("precision"),
            "roads": record.get("roads", []),
            "resources": record.get("resources", []),
            "events": record.get("events", []),
        })

    for object_id, entry in entities.items():
        if object_id in latest:
            continue
        if not _is_active_entry(entry) or entry.get("type") != "location":
            continue
        locations.append({
            "location_id": object_id,
            "name": entry.get("name", object_id),
            "valid_from": None,
            "valid_to": None,
            "controller": None,
            "status": entry.get("status"),
            "precision": None,
            "roads": [],
            "resources": [],
            "events": [],
        })
    return locations


def _map_svg_inner(locations: list[dict]) -> str:
    width = 960
    parts = [
        '<style>',
        '.location rect { fill:#fff; stroke:#345; stroke-width:1.5; }',
        '.location text { font-family: sans-serif; }',
        '</style>',
    ]
    if not locations:
        parts.append(
            f'<text x="30" y="40" font-size="16">（暂无地点数据）</text>'
        )
    for index, location in enumerate(locations):
        x = 40
        y = 40 + index * 110
        location_id = _escape_xml(location.get("location_id", ""))
        name = _escape_xml(location.get("name", location.get("location_id", "")))
        status = _escape_xml(location.get("status") or "")
        controller = _escape_xml(location.get("controller") or "")
        parts.append(f'<g class="location">')
        parts.append(
            f'<rect x="{x}" y="{y}" width="{width - 80}" height="92" rx="8"/>'
        )
        parts.append(
            f'<text x="{x + 14}" y="{y + 24}" font-size="13" font-weight="bold">{location_id}</text>'
        )
        parts.append(f'<text x="{x + 14}" y="{y + 44}" font-size="15">{name}</text>')
        parts.append(
            f'<text x="{x + 14}" y="{y + 64}" font-size="11">status: {status}</text>'
        )
        parts.append(
            f'<text x="{x + 14}" y="{y + 80}" font-size="11">controller: {controller}</text>'
        )
        parts.append('</g>')
    return "\n".join(parts) + "\n"


def _map_svg(root: Path, locations: list[dict]) -> str:
    template_path = _assets_dir() / "templates" / "svg" / "map.svg"
    inner = _map_svg_inner(locations)
    width = 960
    height = max(240, len(locations) * 110 + 40)
    if not template_path.exists():
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} {height}" role="img">'
            '<title>topology map</title>'
            '<rect width="100%" height="100%" fill="#f7f5ef"/>'
            f'{inner}</svg>'
        )
    template = template_path.read_text(encoding="utf-8")
    return (
        template
        .replace("{{width}}", str(width))
        .replace("{{height}}", str(height))
        .replace("{{title}}", "topology map")
        .replace("{{content}}", inner)
    )


def _map_table(locations: list[dict]) -> str:
    lines = [
        "| 地点 | 名称 | 状态 | 控制者 | 起始 | 结束 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for location in locations:
        lines.append(
            f"| {_markdown_cell(location.get('location_id'))} | "
            f"{_markdown_cell(location.get('name'))} | "
            f"{_markdown_cell(location.get('status'))} | "
            f"{_markdown_cell(location.get('controller'))} | "
            f"{_markdown_cell(location.get('valid_from'))} | "
            f"{_markdown_cell(location.get('valid_to'))} |"
        )
    return "\n".join(lines) + "\n"


def _html_table(locations: list[dict]) -> str:
    lines = [
        "<table><thead><tr><th>地点</th><th>名称</th><th>状态</th>"
        "<th>控制者</th><th>起始</th><th>结束</th></tr></thead><tbody>"
    ]
    for location in locations:
        cells = [
            location.get("location_id"),
            location.get("name"),
            location.get("status"),
            location.get("controller"),
            location.get("valid_from"),
            location.get("valid_to"),
        ]
        rendered = "".join(
            f"<td>{html.escape(_display(value))}</td>" for value in cells
        )
        lines.append(f"<tr>{rendered}</tr>")
    lines.append("</tbody></table>")
    return "".join(lines) + "\n"


def _map_html(root: Path, locations: list[dict]) -> str:
    template_path = _assets_dir() / "templates" / "html" / "atlas.html"
    if not template_path.exists():
        return (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>atlas</title></head><body>"
            f"{_html_table(locations)}</body></html>"
        )
    template = template_path.read_text(encoding="utf-8")
    svg = _map_svg(root, locations)
    return (
        template
        .replace("{{title}}", "topology map")
        .replace("{{map_svg}}", svg)
        .replace("{{table}}", _html_table(locations))
        .replace("{{json}}", html.escape(_map_json_content(locations)))
    )


def _map_json_content(locations: list[dict]) -> str:
    return json.dumps(
        {"map_type": "topology", "locations": locations},
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def _write_map_fallback(root: Path, map_type: str, locations: list[dict]) -> Path:
    json_path = root / "exports" / "maps" / f"{map_type}.json"
    table_path = root / "exports" / "maps" / f"{map_type}.md"
    _write_text(json_path, _map_json_content(locations))
    _write_text(table_path, _map_table(locations))
    return json_path


def render_maps(root: Path, map_type: str, output_format: str) -> Path:
    """Render location master data as JSON, SVG, or HTML."""
    root = Path(root)
    _require_initialized_project(root)
    if map_type not in MAP_TYPES:
        raise ValueError(f"map_type must be one of {MAP_TYPES}")
    if output_format not in MAP_FORMATS:
        raise ValueError(f"output_format must be one of {MAP_FORMATS}")

    locations = _map_locations(root)
    if output_format == "json":
        return _write_text(
            root / "exports" / "maps" / f"{map_type}.json",
            _map_json_content(locations),
        )
    if output_format == "svg":
        try:
            content = _map_svg(root, locations)
        except Exception:
            return _write_map_fallback(root, map_type, locations)
        return _write_text(
            root / "exports" / "maps" / f"{map_type}.svg",
            content,
        )
    content = _map_html(root, locations)
    return _write_text(
        root / "exports" / "maps" / f"{map_type}.html",
        content,
    )
