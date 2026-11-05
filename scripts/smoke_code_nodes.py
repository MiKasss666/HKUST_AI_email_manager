"""Execute every code node of the generated DSL with dummy inputs.

Dify Code nodes must define ``def main(...)``. This smoke test catches syntax
errors, top-level ``return`` (a real Cloud failure we hit), and undefined-name
mistakes.

    py -3 scripts/smoke_code_nodes.py
"""

from __future__ import annotations

import os
import sys
import traceback

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    os.path.join(ROOT, "workflows", "HKUST_AI_email_manager.yml"),
]


def dummy(name):
    lowered = name.lower()
    if lowered in ("candidates", "candidates_value", "items", "ignored_ids",
                   "controls_commands", "controls_reports"):
        return []
    if any(key in lowered for key in ("json", "text", "html", "subject", "prompt",
                                      "state_json", "ctx_json", "message", "account",
                                      "status", "newest_id", "oldest_id", "letters",
                                      "action")):
        return ""
    if any(key in lowered for key in ("failed", "count", "days", "expires")):
        return 0
    if any(key in lowered for key in ("signed", "transient", "authorized", "paused",
                                      "ok", "has_items")) or lowered.startswith("is_"):
        return False
    return ""


def main() -> int:
    bad = 0
    for path in FILES:
        with open(path, "r", encoding="utf-8") as fh:
            dsl = yaml.safe_load(fh)
        print("==", os.path.basename(path))
        for node in dsl["workflow"]["graph"]["nodes"]:
            data = node["data"]
            if data["type"] != "code":
                continue
            names = [v["variable"] for v in data.get("variables") or []]
            code = data["code"]
            if "def main(" not in code:
                bad += 1
                print("  NO MAIN() in", data.get("title"), node["id"])
                continue
            namespace = {}
            try:
                exec(compile(code, f"<code {node['id']}>", "exec"), namespace)
                result = namespace["main"](*[dummy(name) for name in names])
                declared = set((data.get("outputs") or {}).keys())
                if isinstance(result, dict) and declared:
                    extra = sorted(set(result) - declared)
                    absent = sorted(declared - set(result))
                    if extra:
                        bad += 1
                        print("  UNDECLARED OUTPUTS in", data.get("title"), node["id"],
                              "->", extra)
                    if absent:
                        print("  declared but not returned:", data.get("title"),
                              node["id"], "->", absent)
            except NameError as ex:
                bad += 1
                print("  NAME ERROR in", data.get("title"), node["id"], "->", ex)
            except TypeError as ex:
                print("  type note:", data.get("title"), node["id"], "->", ex)
            except Exception as ex:  # noqa: BLE001
                bad += 1
                print("  RUNTIME ERROR in", data.get("title"), node["id"], "->",
                      type(ex).__name__, ex)
                traceback.print_exc(limit=2)
    print("done, fatal problems:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
