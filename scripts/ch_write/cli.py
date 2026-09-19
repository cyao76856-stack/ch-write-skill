import argparse
from pathlib import Path
import json
import sys

from .constants import INTERACTION_PROFILES, LIST_LEVELS
from .render import (
    GRAPH_FORMATS,
    GRAPH_TYPES,
    MAP_FORMATS,
    MAP_TYPES,
    TIMELINE_FORMATS,
    TIMELINE_TYPES,
    render_graph,
    render_lists,
    render_maps,
    render_timeline,
)
from .decisions import (
    confirm_decision,
    record_change,
    record_decision,
    set_interaction_profile,
)
from .io import read_json
from .objects import add_object, add_relation
from .lists import LIST_CATEGORIES, upsert_list_item
from .worlddata import append_location_state, append_timeline_entry
from .project import SCRIPT_MASTERS, init_project
from .sources import get_source_status, register_sources
from .validation import impact, validate_project
from .versions import (
    archive_version,
    confirm_batch,
    get_status,
    mark_tampered,
    restore_version,
    snapshot_working,
)

COMMANDS = ("init", "status", "profile", "source", "object", "decision",
            "change", "list", "timeline", "location", "snapshot", "confirm",
            "impact", "validate", "render", "archive", "restore")


def build_parser():
    parser = argparse.ArgumentParser(prog="story_project")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        command_parser = sub.add_parser(name)
        if name == "init":
            command_parser.add_argument("--root", type=Path, required=True)
            command_parser.add_argument("--name", required=True)
            command_parser.add_argument(
                "--script-master",
                choices=SCRIPT_MASTERS,
                required=True,
            )
            command_parser.add_argument(
                "--interaction-profile",
                choices=INTERACTION_PROFILES,
                required=True,
            )
        elif name == "status":
            command_parser.add_argument("--root", type=Path, required=True)
        elif name == "profile":
            command_parser.add_argument("--root", type=Path, required=True)
            command_parser.add_argument(
                "--profile",
                choices=INTERACTION_PROFILES,
                required=True,
            )
            command_parser.add_argument("--author-statement", required=True)
        elif name == "impact":
            command_parser.add_argument("--root", type=Path, required=True)
            command_parser.add_argument("--id", required=True)
        elif name == "validate":
            command_parser.add_argument("--root", type=Path, required=True)
            command_parser.add_argument("--json", action="store_true")
        elif name == "source":
            source_sub = command_parser.add_subparsers(
                dest="source_command",
                required=True,
            )
            source_add = source_sub.add_parser("add")
            source_add.add_argument("--root", type=Path, required=True)
            source_add.add_argument("--file", type=Path, required=True)
            source_add.add_argument("--order", type=int, required=True)
            source_add.add_argument("--priority", type=int, required=True)
            source_add.add_argument("--merge-strategy", required=True)
            source_add.add_argument("--replace", action="store_true")
            source_status = source_sub.add_parser("status")
            source_status.add_argument("--root", type=Path, required=True)
        elif name == "object":
            object_sub = command_parser.add_subparsers(
                dest="object_command",
                required=True,
            )
            object_add = object_sub.add_parser("add")
            object_add.add_argument("--root", type=Path, required=True)
            object_add.add_argument("--type", required=True)
            object_add.add_argument("--name", required=True)
            object_add.add_argument(
                "--attribute",
                action="append",
                default=[],
                metavar="KEY=VALUE",
            )
            object_relation = object_sub.add_parser("relation")
            object_relation.add_argument("--root", type=Path, required=True)
            object_relation.add_argument("--source", required=True)
            object_relation.add_argument("--relation", required=True)
            object_relation.add_argument("--target", required=True)
            object_relation.add_argument("--evidence", default=None)
        elif name == "decision":
            decision_sub = command_parser.add_subparsers(
                dest="decision_command",
                required=True,
            )
            decision_add = decision_sub.add_parser("add")
            decision_add.add_argument("--root", type=Path, required=True)
            decision_add.add_argument("--payload", required=True)
        elif name == "change":
            change_sub = command_parser.add_subparsers(
                dest="change_command",
                required=True,
            )
            change_add = change_sub.add_parser("add")
            change_add.add_argument("--root", type=Path, required=True)
            change_add.add_argument("--payload", required=True)
        elif name == "list":
            list_sub = command_parser.add_subparsers(
                dest="list_command",
                required=True,
            )
            list_upsert = list_sub.add_parser("upsert")
            list_upsert.add_argument("--root", type=Path, required=True)
            list_upsert.add_argument(
                "--category",
                choices=LIST_CATEGORIES,
                required=True,
            )
            list_upsert.add_argument(
                "--level",
                choices=LIST_LEVELS,
                required=True,
            )
            list_upsert.add_argument("--json", type=Path, required=True)
        elif name == "timeline":
            timeline_sub = command_parser.add_subparsers(
                dest="timeline_command",
                required=True,
            )
            timeline_add = timeline_sub.add_parser("add")
            timeline_add.add_argument("--root", type=Path, required=True)
            timeline_add.add_argument("--event-id", required=True)
            timeline_add.add_argument("--json", type=Path, required=True)
        elif name == "location":
            location_sub = command_parser.add_subparsers(
                dest="location_command",
                required=True,
            )
            location_state = location_sub.add_parser("state")
            location_state.add_argument("--root", type=Path, required=True)
            location_state.add_argument("--location-id", required=True)
            location_state.add_argument("--json", type=Path, required=True)
        elif name == "snapshot":
            command_parser.add_argument("--root", type=Path, required=True)
            command_parser.add_argument("--label", required=True)
        elif name == "confirm":
            command_parser.add_argument("--root", type=Path, required=True)
            command_parser.add_argument("--id", default=None)
            command_parser.add_argument("--author-statement", default=None)
            command_parser.add_argument("--batch-id", default=None)
            command_parser.add_argument(
                "--ids",
                action="append",
                default=None,
                metavar="ID_OR_JSON_LIST",
            )
            command_parser.add_argument(
                "--object-revisions",
                default=None,
                metavar="JSON_OBJECT",
            )
        elif name == "render":
            render_sub = command_parser.add_subparsers(
                dest="render_command",
                required=True,
            )
            render_lists_parser = render_sub.add_parser("lists")
            render_lists_parser.add_argument("--root", type=Path, required=True)
            render_lists_parser.add_argument("--category", choices=LIST_CATEGORIES, required=True)
            render_lists_parser.add_argument("--level", choices=LIST_LEVELS, required=True)
            render_graph_parser = render_sub.add_parser("graph")
            render_graph_parser.add_argument("--root", type=Path, required=True)
            render_graph_parser.add_argument("--graph-type", choices=GRAPH_TYPES, required=True)
            render_graph_parser.add_argument("--output-format", choices=GRAPH_FORMATS, required=True)
            render_timeline_parser = render_sub.add_parser("timeline")
            render_timeline_parser.add_argument("--root", type=Path, required=True)
            render_timeline_parser.add_argument("--timeline-type", choices=TIMELINE_TYPES, required=True)
            render_timeline_parser.add_argument("--output-format", choices=TIMELINE_FORMATS, required=True)
            render_maps_parser = render_sub.add_parser("maps")
            render_maps_parser.add_argument("--root", type=Path, required=True)
            render_maps_parser.add_argument("--map-type", choices=MAP_TYPES, required=True)
            render_maps_parser.add_argument("--output-format", choices=MAP_FORMATS, required=True)
        elif name == "archive":
            command_parser.add_argument("--root", type=Path, required=True)
            command_parser.add_argument("--version", required=True)
        elif name == "restore":
            command_parser.add_argument("--root", type=Path, required=True)
            command_parser.add_argument("--version", required=True)
            command_parser.add_argument("--target", type=Path, default=None)
    return parser


def _source_path_is_registered(root: Path, source_path: Path) -> bool:
    index_path = Path(root) / "indexes" / "sources.json"
    if not index_path.exists():
        return False

    data = read_json(index_path)
    sources = data.get("sources")
    if not isinstance(sources, list) or not all(
        isinstance(source, dict) for source in sources
    ):
        raise ValueError("invalid sources index")

    normalized = str(Path(source_path).expanduser().resolve(strict=False))
    for source in sources:
        path = source.get("path")
        if isinstance(path, str) and (
            str(Path(path).expanduser().resolve(strict=False)) == normalized
        ):
            return True
    return False


def _parse_attributes(values: list[str]) -> dict:
    attributes = {}
    for value in values:
        key, separator, raw_value = value.partition("=")
        if not separator or not key:
            raise ValueError(f"invalid attribute: {value}; expected KEY=VALUE")
        attributes[key] = raw_value
    return attributes


def _parse_ids(values: list[str] | None) -> list[str]:
    if not values:
        return []
    if len(values) == 1:
        try:
            parsed = json.loads(values[0])
        except json.JSONDecodeError:
            parsed = values
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return list(values)


def _parse_object_revisions(value: str | None) -> dict:
    if value is None:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("--object-revisions must be a JSON object")
    return {str(key): str(item) for key, item in parsed.items()}


def _configure_utf8_output():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main(argv=None):
    _configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            init_project(
                args.root,
                args.name,
                args.script_master,
                args.interaction_profile,
            )
        elif args.command == "status":
            result = get_status(args.root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "profile":
            result = set_interaction_profile(
                args.root,
                args.profile,
                args.author_statement,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "source":
            if args.source_command == "add":
                if not args.replace and _source_path_is_registered(args.root, args.file):
                    raise ValueError(
                        f"source is already registered: {args.file}; use --replace"
                    )
                result = register_sources(
                    args.root,
                    [{
                        "path": str(args.file),
                        "order": args.order,
                        "priority": args.priority,
                        "merge_strategy": args.merge_strategy,
                    }],
                    replace=args.replace,
                )
            else:
                result = get_source_status(args.root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "object":
            if args.object_command == "add":
                result = add_object(
                    args.root,
                    args.type,
                    args.name,
                    _parse_attributes(args.attribute),
                )
            else:
                evidence = None
                if args.evidence is not None:
                    evidence = json.loads(args.evidence)
                result = add_relation(
                    args.root,
                    args.source,
                    args.relation,
                    args.target,
                    evidence,
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "decision":
            if args.decision_command == "add":
                payload = json.loads(args.payload)
                result = record_decision(args.root, payload)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "change":
            if args.change_command == "add":
                payload = json.loads(args.payload)
                result = record_change(args.root, payload)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "list":
            if args.list_command == "upsert":
                payload = read_json(args.json)
                result = upsert_list_item(
                    args.root,
                    args.category,
                    payload,
                    args.level,
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "timeline":
            if args.timeline_command == "add":
                payload = read_json(args.json)
                result = append_timeline_entry(
                    args.root,
                    args.event_id,
                    payload,
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "location":
            if args.location_command == "state":
                payload = read_json(args.json)
                result = append_location_state(
                    args.root,
                    args.location_id,
                    payload,
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "snapshot":
            result = snapshot_working(args.root, args.label)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "confirm":
            batch_ids = _parse_ids(args.ids)
            if batch_ids:
                if not args.batch_id:
                    raise ValueError("--batch-id is required for batch confirm")
                result = confirm_batch(
                    args.root,
                    args.batch_id,
                    batch_ids,
                    _parse_object_revisions(args.object_revisions),
                )
            else:
                if not args.id or not args.author_statement:
                    raise ValueError(
                        "--id and --author-statement are required for single confirm"
                    )
                result = confirm_decision(
                    args.root,
                    args.id,
                    args.author_statement,
                    args.batch_id,
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "impact":
            result = impact(args.root, args.id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "validate":
            result = validate_project(args.root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "render":
            if args.render_command == "lists":
                result = render_lists(args.root, args.category, args.level)
            elif args.render_command == "graph":
                result = render_graph(args.root, args.graph_type, args.output_format)
            elif args.render_command == "timeline":
                result = render_timeline(args.root, args.timeline_type, args.output_format)
            else:
                result = render_maps(args.root, args.map_type, args.output_format)
            print(json.dumps({"path": str(result)}, ensure_ascii=False, indent=2))
        elif args.command == "archive":
            result = archive_version(args.root, args.version)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "restore":
            result = restore_version(args.root, args.version, args.target)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
