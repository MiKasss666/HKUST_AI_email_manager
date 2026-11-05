"""Functional smoke test for the code nodes of the main workflow.

Runs the real snippets extracted from workflows/HKUST_AI_email_manager.yml against a
small fake mailbox and fake model output:

  plan -> validate (happy path + count mismatch) -> report HTML

    py -3 scripts/smoke_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DSL = os.path.join(ROOT, "workflows", "HKUST_AI_email_manager.yml")

NODES = {
    "plan": "1700000034",
    "validate": "1700000051",
    "report": "1700000042",
}


def load_code(path):
    with open(path, "r", encoding="utf-8") as fh:
        dsl = yaml.safe_load(fh)
    by_id = {n["id"]: n["data"] for n in dsl["workflow"]["graph"]["nodes"]}
    return {name: by_id[node_id]["code"] for name, node_id in NODES.items()}


def run_code(code, **inputs):
    namespace = {}
    exec(compile(code, "<code>", "exec"), namespace)
    return namespace["main"](**inputs)


CANDIDATES = [
    {"entryid": "mail-1", "subject": "COMP 1021 assignment 3 due Friday",
     "sender_name": "Teaching Team", "sender": "comp1021@ust.hk",
     "body_head": "submit by 2026-03-06", "categories": [],
     "web_link": "https://outlook/1"},
    {"entryid": "mail-2", "subject": "Campus newsletter",
     "sender_name": "HKUST", "sender": "news@ust.hk",
     "body_head": "events this week", "categories": ["MyLabel"],
     "web_link": "https://outlook/2"},
]

ENV = dict(name="Alice", student_id="12345678", school_domains="ust.hk",
           faculty="School of Science", courses="COMP 1021", urgent_days=14,
           language="zh", newest_id="mail-1", catchup_date="",
           dry_run_value="false")


def main():
    code = load_code(DSL)
    planned = run_code(code["plan"], candidates=CANDIDATES, controls_commands=[],
                       controls_reports=[], **ENV)
    assert planned["candidate_count"] == 2
    assert planned["has_candidates"] is True
    assert planned["dry_run"] is False
    assert "mail-1" in planned["ids_json"]
    assert planned["prompt"]

    model_items = [
        {"ref": 1, "级别": "S", "截止日期": "2026-03-06", "学校": True},
        {"ref": 2, "级别": "C", "截止日期": None, "学校": True},
    ]
    model_text = json.dumps({"items": model_items}, ensure_ascii=False)
    validated = run_code(code["validate"], text=model_text,
                         candidates_value=CANDIDATES, ids_json=planned["ids_json"],
                         school_domains_value=ENV["school_domains"],
                         faculty_value=ENV["faculty"], courses_value=ENV["courses"],
                         urgent_days_value=ENV["urgent_days"])
    verdicts = json.loads(validated["verdicts_json"])
    assert validated["failed"] == 0, validated
    assert [v["entryid"] for v in verdicts] == ["mail-1", "mail-2"]
    assert verdicts[0]["level"] == "S"

    # count mismatch -> whole batch rejected, nothing is written
    short = json.dumps({"items": model_items[:1]}, ensure_ascii=False)
    rejected = run_code(code["validate"], text=short, candidates_value=CANDIDATES,
                        ids_json=planned["ids_json"],
                        school_domains_value=ENV["school_domains"],
                        faculty_value=ENV["faculty"], courses_value=ENV["courses"],
                        urgent_days_value=ENV["urgent_days"])
    assert rejected["failed"] == 2
    assert json.loads(rejected["verdicts_json"]) == []

    html = run_code(code["report"], text=json.dumps({"points": ["交作业", "活动通知"]}),
                    items=CANDIDATES, language="zh", letters_value="sabc", days=7)
    assert "<html>" in html["html"]
    assert "邮件总结" in html["subject"]
    assert html["points_count"] == 2

    print("pipeline smoke OK",
          {"plan_chars": len(planned["prompt"]), "subject": html["subject"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
