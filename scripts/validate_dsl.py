"""Structural validator for the generated Dify workflow DSL files.

    py -3 scripts/validate_dsl.py

Checks that are cheap and catch most generation mistakes:
  - node ids unique, edges reference existing nodes;
  - if-else edges use a declared case id or "false", other nodes use "source";
  - every node is reachable from an entry node;
  - at least one end node, no duplicate end variables;
  - tool nodes carry provider identity fields.
It does not replace importing the DSL into Dify.
"""

from __future__ import annotations

import glob
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    os.path.join(ROOT, "workflows", "HKUST_AI_email_manager.yml"),
]
ENTRY_TYPES = {"start", "trigger-schedule", "trigger-webhook", "trigger-plugin"}
# Dify environment variables only support these three value types. A boolean
# value_type is accepted by import but makes GET /workflows/draft fail with 400.
ALLOWED_ENV_TYPES = {"string", "number", "secret"}
KNOWN_NODE_TYPES = {
    "start", "end", "answer", "llm", "code", "template-transform", "if-else",
    "question-classifier", "tool", "http-request", "variable-aggregator",
    "assigner", "iteration", "loop", "human-input", "trigger-schedule",
    "trigger-webhook", "trigger-plugin", "knowledge-retrieval", "agent",
    "parameter-extractor", "list-operator", "document-extractor",
}


WITH_TOOL_REQUIRED = {}
_TOOLS_DIR = os.path.join(ROOT, "tools")
for _path in glob.glob(os.path.join(_TOOLS_DIR, "*.yaml")):
    with open(_path, "r", encoding="utf-8") as _fh:
        _doc = yaml.safe_load(_fh)
    WITH_TOOL_REQUIRED[_doc["identity"]["name"]] = {
        item["name"] for item in (_doc.get("parameters") or []) if item.get("required")
    }


def validate(path: str) -> list:
    problems = []
    with open(path, "r", encoding="utf-8") as fh:
        dsl = yaml.safe_load(fh)
    for env in (dsl.get("workflow") or {}).get("environment_variables") or []:
        value_type = env.get("value_type")
        if value_type not in ALLOWED_ENV_TYPES:
            problems.append(
                "env %r has invalid value_type %r (allowed: %s)"
                % (env.get("name"), value_type, ", ".join(sorted(ALLOWED_ENV_TYPES)))
            )
    graph = dsl["workflow"]["graph"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        problems.append("duplicate node ids")
    node_by_id = {n["id"]: n for n in nodes}

    for e in edges:
        if e["source"] not in node_by_id:
            problems.append("edge source missing: " + e["id"])
        if e["target"] not in node_by_id:
            problems.append("edge target missing: " + e["id"])
    for n in nodes:
        data = n["data"]
        ntype = data["type"]
        if ntype not in KNOWN_NODE_TYPES:
            problems.append(f"node {n['id']} unknown type {ntype!r}")
        if ntype == "code":
            # Dify Code nodes execute the snippet as a module and require a
            # ``def main(...)`` entry. A top-level ``return`` raises
            # "'return' outside function" on Dify Cloud.
            code = data.get("code") or ""
            if "def main(" not in code:
                problems.append(f"code node {n['id']} does not define def main(...)")
            try:
                compile(code, f"<code {n['id']}>", "exec")
            except SyntaxError as ex:
                problems.append(f"code node {n['id']} syntax error: {ex}")
            declared = set((data.get("outputs") or {}).keys())
            for variable in data.get("variables") or []:
                if not variable.get("value_selector"):
                    problems.append(f"code node {n['id']} input {variable.get('variable')} has no selector")
            if not declared:
                problems.append(f"code node {n['id']} declares no outputs")
        if ntype == "tool":
            for key in ("provider_id", "provider_name", "tool_name", "plugin_id"):
                if not data.get(key):
                    problems.append(f"{n['id']} tool node missing {key}")
            required = WITH_TOOL_REQUIRED.get(data.get("tool_name") or "")
            if required is None:
                problems.append(f"{n['id']} unknown tool {data.get('tool_name')!r}")
            else:
                provided = set((data.get("tool_parameters") or {}).keys())
                missing = sorted(required - provided)
                if missing:
                    problems.append(
                        f"{n['id']} tool {data.get('tool_name')} missing required params {missing}")
        if ntype == "llm":
            for item in data.get("prompt_template") or []:
                if not isinstance(item.get("text"), str):
                    problems.append(
                        f"{n['id']} llm node prompt text must be a string template, got {type(item.get('text')).__name__}")
        if ntype == "if-else":
            case_ids = {c["case_id"] for c in data.get("cases", [])}
            handles = {e["sourceHandle"] for e in edges if e["source"] == n["id"]}
            if not handles:
                problems.append(f"if-else {n['id']} has no outgoing edges")
            for handle in handles:
                if handle not in case_ids and handle != "false":
                    problems.append(f"if-else {n['id']} unknown handle {handle!r}")
        elif ntype == "human-input":
            # Handles are the configured action ids plus the timeout branch.
            allowed = {action.get("id") for action in data.get("user_actions") or []}
            allowed |= {"__timeout", "__timeout__"}
            handles = {e["sourceHandle"] for e in edges if e["source"] == n["id"]}
            if not handles:
                problems.append(f"human-input {n['id']} has no outgoing edges")
            for handle in handles:
                if handle not in allowed:
                    problems.append(f"human-input {n['id']} unknown handle {handle!r}")
            if not data.get("delivery_methods"):
                problems.append(f"human-input {n['id']} has no delivery method")
        elif ntype not in ("end",):
            for e in edges:
                if e["source"] == n["id"] and e["sourceHandle"] != "source":
                    problems.append(f"node {n['id']} ({ntype}) uses handle {e['sourceHandle']!r}")

    entries = [n for n in nodes if n["data"]["type"] in ENTRY_TYPES]
    if not entries:
        problems.append("no entry node")
    reachable = set()
    frontier = [n["id"] for n in entries]
    while frontier:
        current = frontier.pop()
        if current in reachable:
            continue
        reachable.add(current)
        for e in edges:
            if e["source"] == current and e["target"] not in reachable:
                frontier.append(e["target"])
    unreachable = [i for i in ids if i not in reachable]
    if unreachable:
        problems.append("unreachable nodes: " + ", ".join(unreachable))

    ends = [n for n in nodes if n["data"]["type"] == "end"]
    if not ends:
        problems.append("no end node")
    return problems


def main() -> int:
    failed = False
    for path in FILES:
        problems = validate(path)
        print(os.path.basename(path), "OK" if not problems else "PROBLEMS")
        for problem in problems:
            print("  -", problem)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
