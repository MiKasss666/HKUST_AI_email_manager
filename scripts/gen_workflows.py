"""Generate the two Dify workflow DSL files for Email Manager v1.

    py -3 scripts/gen_workflows.py

Outputs (YAML, DSL version 0.5.0):
    workflows/email-manager-login.yml   device-code sign-in helper (User Input app)
    workflows/email-manager-main.yml    the single main workflow (Schedule + Webhook triggers)

The DSL is a *best-effort draft*: plugin tool nodes reference provider ids that
must match the installed plugin, and the LLM nodes must be pointed at the model
the user configured in Dify. The README explains the two-minute fix-up.
"""

from __future__ import annotations

import os
import shutil
import textwrap

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "workflows")

AUTHOR = "mikasss666"
PLUGIN = "email_manager"
PLUGIN_ID = f"{AUTHOR}/{PLUGIN}"
PROVIDER = f"{AUTHOR}/{PLUGIN}/{PLUGIN}"
MODEL = {"provider": "openai", "name": "gpt-5.6-luna", "mode": "chat",
         "completion_params": {"temperature": 0, "max_tokens": 4096}}


def nid(number: int) -> str:
    return "17%08d" % number


def node(node_id, data, x, y, height=98, width=244):
    data.setdefault("desc", "")
    data.setdefault("selected", False)
    return {
        "data": data,
        "height": height,
        "id": node_id,
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "selected": False,
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": width,
    }


def edge(source, target, source_type, target_type, handle="source"):
    return {
        "data": {
            "sourceType": source_type,
            "targetType": target_type,
            "isInIteration": False,
            "isInLoop": False,
        },
        "id": f"{source}-{target}-{handle}-target",
        "source": source,
        "sourceHandle": handle,
        "target": target,
        "targetHandle": "target",
        "type": "custom",
        "zIndex": 0,
    }


def wrap_main(code: str, variables) -> str:
    """Dify Code nodes expect ``def main(...)``; a top-level ``return`` is a
    SyntaxError on Dify Cloud ("'return' outside function")."""
    names = [item["variable"] for item in variables]
    body = "\n".join("    " + line if line.strip() else ""
                     for line in textwrap.dedent(code).strip("\n").splitlines())
    return "def main(%s):\n%s\n" % (", ".join(names), body)


def code_node(node_id, title, variables, code, outputs, x, y, height=200):
    return node(node_id, {
        "type": "code",
        "title": title,
        "variables": variables,
        "code_language": "python3",
        "code": wrap_main(code, variables),
        "outputs": outputs,
    }, x, y, height=height)


def tool_node(node_id, title, tool, params, x, y, desc=""):
    return node(node_id, {
        "type": "tool",
        "title": title,
        "desc": desc,
        "provider_id": PROVIDER,
        "provider_name": PROVIDER,
        "provider_type": "builtin",
        "plugin_id": PLUGIN_ID,
        "tool_name": tool,
        "tool_label": title,
        "tool_description": "",
        "tool_node_version": "2",
        "tool_configurations": {},
        "tool_parameters": params or {},
        "is_team_authorization": True,
    }, x, y, height=110)


def if_else(node_id, title, cases, x, y):
    return node(node_id, {
        "type": "if-else",
        "title": title,
        "cases": cases,
        "logical_operator": "and",
    }, x, y, height=140)


def human_input_node(node_id, title, x, y, form_content, email_subject, email_body,
                     actions, timeout=1, timeout_unit="hour"):
    """Human Input node: the only interactive login path inside a trigger workflow.

    Trigger-started workflows cannot use the WebApp delivery channel, so the
    device code + form link are delivered by e-mail (the form itself is still a
    Dify-hosted page). ``{{#url#}}`` in the body is replaced with the form link.
    """
    return node(node_id, {
        "type": "human-input",
        "title": title,
        "form_content": form_content,
        "inputs": [],
        "user_actions": actions,
        "timeout": timeout,
        "timeout_unit": timeout_unit,
        "delivery_methods": [{
            "type": "email",
            "enabled": True,
            "config": {
                # ``whole_workspace`` is the legacy field name that older Dify
                # versions (1.13.x) expect; newer versions map it onto
                # ``include_bound_group`` via an alias, so this works on both.
                "recipients": {"whole_workspace": True, "items": []},
                "subject": email_subject,
                "body": email_body,
                "debug_mode": False,
            },
        }],
    }, x, y, height=160, width=320)


def case(case_id, selector, operator, value, logical="and"):
    return {
        "case_id": case_id,
        "logical_operator": logical,
        "conditions": [{
            "variable_selector": list(selector),
            "comparison_operator": operator,
            "value": value,
        }],
    }


def aggregator(node_id, title, selectors, out_type="string", x=0, y=0):
    return node(node_id, {
        "type": "variable-aggregator",
        "title": title,
        "output_type": out_type,
        "variables": [list(s) for s in selectors],
        "advanced_settings": None,
    }, x, y)


def end_node(node_id, outputs, x, y):
    return node(node_id, {"type": "end", "title": "End", "outputs": outputs}, x, y, height=90)


def out(var, vtype, selector):
    return {"variable": var, "value_type": vtype, "value_selector": list(selector)}


def env_var(name, vtype, value):
    return {"id": f"env-{name.lower()}", "name": name, "value_type": vtype,
            "value": value, "description": ""}


def ev(name):
    return ["env", name]


def llm_node(node_id, title, prompt_selector, x, y):
    return node(node_id, {
        "type": "llm",
        "title": title,
        "model": MODEL,
        "prompt_template": [
            {"role": "system", "text": "You are a careful email classification assistant. Follow the output format exactly."},
            {"role": "user", "text": prompt_selector},
        ],
        "prompt_config": {"jinja2_variables": []},
        "memory": None,
        "context": {"enabled": False, "variable_selector": None},
        "vision": {"enabled": False},
        "structured_output": None,
        "structured_output_enabled": False,
        "reasoning_format": "separated",
        "error_strategy": "default-value",
        "default_value": [{"key": "text", "type": "string", "value": ""}],
        "retry_config": {"max_retries": 2, "retry_interval": 2000, "retry_enabled": True},
    }, x, y, height=140)


def features():
    return {
        "file_upload": {
            "enabled": False,
            "allowed_file_extensions": [],
            "allowed_file_types": ["image", "document"],
            "allowed_file_upload_methods": ["local_file", "remote_url"],
            "max_file_upload_limit": 5,
            "number_limits": 1,
        },
        "opening_statement": "",
        "retriever_resource": {"enabled": False},
        "sensitive_word_avoidance": {"enabled": False},
        "speech_to_text": {"enabled": False},
        "suggested_questions": [],
        "suggested_questions_after_answer": {"enabled": False},
        "text_to_speech": {"enabled": False},
    }


def app(mode, name, description, env_vars, graph, dependency=False):
    return {
        "app": {
            "description": description,
            "icon": "📬",
            "icon_background": "#FFEAD5",
            "mode": mode,
            "name": name,
            "use_icon_as_answer_icon": False,
        },
        "dependencies": ([{
            "current_identifier": None,
            "type": "github",
            "value": {
                "repo": f"{AUTHOR}/{PLUGIN}-plugin",
                "version": "0.1.0",
                "package": PLUGIN,
                "github_plugin_unique_identifier": f"{PLUGIN_ID}:0.1.0",
            },
        }] if dependency else []),
        "kind": "app",
        "version": "0.5.0",
        "workflow": {
            "conversation_variables": [],
            "environment_variables": env_vars,
            "features": features(),
            "graph": graph,
        },
    }


# ── shared code snippets ─────────────────────────────────────────────
LOGIN_CARD = """
import json
result = {
    "step": "start",
    "user_code": user_code,
    "verification_uri": verification_uri,
    "expires_in": expires_in,
    "client_label": client_label,
    "message": message,
}
return {"result_json": json.dumps(result, ensure_ascii=False), "signed_in": False}
"""

LOGIN_POLL = """
import json
result = {
    "step": "poll",
    "signed_in": bool(signed_in),
    "status": status,
    "account": account,
}
return {"result_json": json.dumps(result, ensure_ascii=False), "signed_in": bool(signed_in)}
"""

CTX_SCHED = """
import json
ctx = {"source": "schedule", "action": "auto", "letters": "sabc", "days": 0,
       "manual": False, "authorized": True}
return {"ctx_json": json.dumps(ctx, ensure_ascii=False)}
"""

CTX_WEBHOOK = """
import json
ok = bool(token) and str(token) == str(expected)
ctx = {
    "source": "webhook",
    "action": (action or "auto") if ok else "unauthorized",
    "letters": letters or "sabc",
    "days": int(days or 0),
    "manual": True,
    "authorized": ok,
}
return {"ctx_json": json.dumps(ctx, ensure_ascii=False), "authorized": ok}
"""

PARSE_CTX = """
import json
ctx = {}
try:
    ctx = json.loads(ctx_json or "{}")
except Exception:
    ctx = {}
return {
    "source": str(ctx.get("source") or ""),
    "action": str(ctx.get("action") or "auto"),
    "letters": str(ctx.get("letters") or "sabc"),
    "days": int(ctx.get("days") or 0),
    "manual": bool(ctx.get("manual")),
    "authorized": bool(ctx.get("authorized")),
}
"""

PARSE_STATE = """
import json
from datetime import datetime, timedelta, timezone
try:
    st = json.loads(state_json or "{}")
except Exception:
    st = {}
try:
    now = datetime.now(timezone(timedelta(hours=8)))
    today = now.date()
except Exception:
    now = None
    today = None
catchup = True
if today is not None:
    catchup = str(st.get("last_catchup_date") or "") != today.isoformat()
summary_days = max(1, int(summary_days_value or 7))
# scheduled reports: any run between 00:00 and 00:09 local time.
# FORCE_ACTION=report_daily / report_weekly forces one immediately (testing).
forced = str(force_action or "").strip().lower()
report_kind = ""
if forced in ("report_daily", "report_weekly"):
    report_kind = "daily" if forced == "report_daily" else "weekly"
elif now is not None and now.hour == 0 and now.minute < 10:
    weekly_due = (now.weekday() == 6
                  and str(st.get("weekly_report_date") or "") != today.isoformat())
    daily_due = str(st.get("daily_report_date") or "") != today.isoformat()
    if weekly_due:
        report_kind = "weekly"    # weekly wins on Sunday; includes the daily window
    elif daily_due:
        report_kind = "daily"
return {
    "paused": bool(st.get("paused")),
    "last_seen": str(st.get("last_seen") or ""),
    "failed_rounds": int(st.get("failed_rounds") or 0),
    "catchup": bool(catchup),
    "catchup_date": today.isoformat() if (catchup and today is not None) else "",
    "report_due": bool(report_kind),
    "report_kind": report_kind,
    "report_days": summary_days if report_kind == "weekly" else 1,
    "report_letters": "sabc",
    "mark_daily": report_kind in ("daily", "weekly"),
    "mark_weekly": report_kind == "weekly",
}
"""

PLAN_CODE = r"""
import json
from datetime import datetime, timedelta, timezone

def as_list(value):
    if isinstance(value, list):
        return value
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []

def split_terms(text):
    out = []
    for sep in (";", "；", "、", "\n", "|"):
        text = str(text or "").replace(sep, ",")
    for piece in text.split(","):
        piece = piece.strip()
        if piece and piece.lower() not in [x.lower() for x in out]:
            out.append(piece)
    return out

candidates = as_list(candidates)
commands = as_list(controls_commands)
reports = as_list(controls_reports)
names = split_terms(name)
student_id = str(student_id or "").strip()
faculty = split_terms(faculty)
courses = split_terms(courses)
domains = split_terms(school_domains)
urgent_days = int(urgent_days or 14)
english = str(language or "zh").lower().startswith("en")

na = "(not set)" if english else "（未填写）"
rules = []
rules.append("第一步 · 判断这封是不是学校事务邮件（学校/学院/教务/课程/宿舍/图书馆/校方活动，"
             "以及学校采购的外部平台代发，如 Canvas、问卷、报名系统）。私人邮件、商家推广、与学校无关的订阅不算。"
             "发件域名命中 " + ("、".join(domains) or na) + " 的一律算学校邮件。")
rules.append("第二步 · 学校邮件判 S/A/B/C（先判 S）：")
rules.append("- S：需要我做事且有 %d 天内的截止日期（作业/表格/报名/缴费/考试）；活动举办日期不算截止；已过期且无需补的按后续判。" % urgent_days)
rules.append("- A：我参与的课程（%s）、我所在学院/系（%s）、宿舍相关、点名到我（%s / 学号 %s）、"
             "与学业直接相关的官方事务（选课/考试/成绩/报名/缴费/表格/毕业/交换/图书馆）。" % (
                 "、".join(courses) or na, "、".join(faculty) or na,
                 "、".join(names) or na, student_id or na))
rules.append("- B：需要我报名/申请/提交，但不紧急（招聘会/Co-op/工作坊/比赛/交流/科研机会/申研）。")
rules.append("- C：通知型内容，我不需要做任何事（讲座通知、新闻、活动宣传、开放时间、已过期通知）。")
rules.append("判断 B 还是 C 只看：要不要我报名/申请/提交。要 → B；只是告诉我 → C。")
rule_text = "\n".join(rules)

blocks = []
ids = []
for i, mail in enumerate(candidates, 1):
    ids.append(str(mail.get("entryid") or ""))
    sender = (str(mail.get("sender_name") or "").strip() + " <" + str(mail.get("sender") or "") + ">").strip()
    blocks.append("[%d] 主题: %s\n发件人: %s\n正文: %s" % (
        i, mail.get("subject") or "", sender or "(未知发件人)", mail.get("body_head") or "(无正文)"))

prompt = ""
if candidates:
    prompt = (
        "按规则逐封处理，不要写摘要或解释。\n\n" + rule_text +
        "\n\n处理下面 %d 封邮件，只输出一个 JSON 对象："
        "\n{\"items\": [{\"ref\": 1, \"级别\": \"S|A|B|C\", \"截止日期\": \"YYYY-MM-DD 或 null\", \"学校\": true}]}"
        "\n要求：items 数量必须正好 %d 个；ref 必须是下面每封邮件开头的方括号编号（1 到 %d，每封恰好一次）；"
        "不要抄写邮件 id，不要输出 entryid 字段。\n\n" % (
            len(candidates), len(candidates), len(candidates)) +
        "每封邮件格式：[编号] 主题/发件人/正文\n\n" + "\n\n".join(blocks)
    )

control_ids = []
for item in commands + reports:
    eid = str(item.get("entryid") or "")
    if eid:
        control_ids.append(eid)

dry_run = str(dry_run_value or "").strip().lower() in ("1", "true", "yes", "on", "是")

today = datetime.now(timezone(timedelta(hours=8))).date()
return {
    "prompt": prompt,
    "ids_json": json.dumps(ids, ensure_ascii=False),
    "candidate_count": len(candidates),
    "has_candidates": bool(candidates),
    "has_commands": bool(commands),
    "has_controls": bool(commands or reports),
    "control_ids_json": json.dumps(control_ids, ensure_ascii=False),
    "newest_id": str(newest_id or ""),
    "catchup_date": str(catchup_date or ""),
    "dry_run": dry_run,
}
"""

VALIDATE_CODE = r"""
import json
import re
from datetime import datetime, timedelta, timezone

LEVELS = ("S", "A", "B", "C")

def as_list(value):
    if isinstance(value, list):
        return value
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []

def split_terms(text):
    out = []
    for sep in (";", "；", "、", "\n", "|"):
        text = str(text or "").replace(sep, ",")
    for piece in text.split(","):
        piece = piece.strip()
        if piece and piece.lower() not in [x.lower() for x in out]:
            out.append(piece)
    return out

def strip_fences(text):
    text = re.sub(r"```(?:json)?", "", text or "")
    return text.strip()

def parse_json(text):
    cleaned = strip_fences(text)
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start == -1 or end <= start:
            continue
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            continue
    return None

def item_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "mails", "邮件"):
            if isinstance(payload.get(key), list):
                return payload[key]
        lists = [v for v in payload.values() if isinstance(v, list)]
        if len(lists) == 1:
            return lists[0]
    return None

def pick(item, keys):
    for key in keys:
        if isinstance(item, dict) and key in item and item[key] not in (None, ""):
            return item[key]
    return None

def parse_school(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in ("true", "1", "yes", "y", "是", "对", "学校", "school"):
        return True
    if text in ("false", "0", "no", "n", "否", "不是", "非学校", "not_school"):
        return False
    if text.startswith(("不是", "不属于", "不算", "否", "非学校", "not", "no")):
        return False
    if text.startswith(("是", "属于", "算", "yes")):
        return True
    return None

def parse_deadline(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

def is_school_address(address, domains):
    text = str(address or "").strip().lower()
    if "@" not in text:
        return False
    domain = text.rsplit("@", 1)[1].strip().strip(">").strip().rstrip(".")
    for suffix in domains:
        s = str(suffix).strip().lower().lstrip("@").strip(".")
        if s and (domain == s or domain.endswith("." + s)):
            return True
    return False

candidates = as_list(candidates_value)
ids = as_list(ids_json)
payload = parse_json(text)
items = item_list(payload) if payload is not None else None
verdicts = []
failed = 0
if items is None or len(items) != len(ids):
    failed = len(candidates)
else:
    by_id = {}
    bad = False
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            bad = True
            break
        # preferred alignment: the short ref/index printed in the prompt
        ref = item.get("ref")
        if ref is None:
            ref = item.get("index")
        entryid = str(item.get("entryid") or item.get("id") or "").strip()
        target = ""
        if isinstance(ref, int) and 1 <= ref <= len(ids):
            target = ids[ref - 1]
        elif isinstance(ref, str) and ref.strip().isdigit() and 1 <= int(ref) <= len(ids):
            target = ids[int(ref) - 1]
        if not target and entryid:
            if entryid in ids:
                target = entryid
            elif entryid.isdigit() and 1 <= int(entryid) <= len(ids):
                # the model copied the bracketed ref into entryid
                target = ids[int(entryid) - 1]
        if not target and position < len(ids):
            # last resort: same item count -> assume the model kept the order
            target = ids[position]
        if not target or target in by_id:
            bad = True
            break
        by_id[target] = item
    if bad or set(by_id) != set(ids):
        failed = len(candidates)
    else:
        urgent_days = int(urgent_days_value or 14)
        today = datetime.now(timezone(timedelta(hours=8))).date()
        domains = split_terms(school_domains_value)
        faculty = split_terms(faculty_value)
        courses = split_terms(courses_value)
        enrolled = None
        if courses:
            enrolled = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(c) for c in courses) + r")(?![A-Za-z0-9])", re.IGNORECASE)
        for mail in candidates:
            entryid = str(mail.get("entryid") or "")
            item = by_id.get(entryid, {})
            level = str(pick(item, ("级别", "level")) or "").strip().upper()[:1]
            if level not in LEVELS:
                level = "C"
            deadline = parse_deadline(pick(item, ("截止日期", "deadline", "due")))
            school = parse_school(pick(item, ("学校", "school", "is_school")))
            is_school = True if school is None else school
            if not is_school and is_school_address(mail.get("sender"), domains):
                is_school = True
            # deterministic overrides: only raise, never lower
            if is_school:
                haystack = (str(mail.get("subject") or "") + "\n" + str(mail.get("body_head") or ""))
                if enrolled is not None and enrolled.search(haystack) and LEVELS.index(level) > LEVELS.index("A"):
                    level = "A"
                lowered = "\n".join(str(mail.get(k) or "") for k in ("sender_name", "sender", "subject", "body_head")).lower()
                if faculty and LEVELS.index(level) > LEVELS.index("A") and any(term.lower() in lowered for term in faculty):
                    level = "A"
            urgent = False
            if level == "S" and deadline is not None:
                delta = (deadline - today).days
                urgent = 0 <= delta <= urgent_days
            verdicts.append({
                "entryid": entryid,
                "level": level,
                "urgent": urgent,
                "is_school": is_school,
                "categories": mail.get("categories") if isinstance(mail.get("categories"), list) else [],
            })
return {
    "verdicts_json": json.dumps(verdicts, ensure_ascii=False),
    "pending_ids_json": json.dumps(ids, ensure_ascii=False),
    "failed": failed,
    "summary": "parsed %d/%d" % (len(verdicts), len(candidates)),
}
"""

REPORT_PROMPT = r"""
import json

def as_list(value):
    if isinstance(value, list):
        return value
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []

items = as_list(items)
english = str(language or "zh").lower().startswith("en")
blocks = []
for i, mail in enumerate(items, 1):
    body = str(mail.get("body") or "")[:800]
    if english:
        blocks.append("[%d] Subject: %s\nFrom: %s\nBody: %s" % (i, mail.get("subject"), mail.get("sender"), body))
    else:
        blocks.append("[%d] 主题:%s\n发件人:%s\n正文:%s" % (i, mail.get("subject"), mail.get("sender"), body))

if english:
    prompt = ("For each email below, write ONE short line saying what it is and what I need to do.\n"
              "Rules: include deadline/date/course code/amount/venue/material when present; never mention the level or the sender; "
              "no filler; at most about 40 words per line.\n"
              "Output ONE JSON object: {\"points\": [ ... ]} with exactly %d strings, same order as the emails.\n\n" % len(items)
              + "\n\n".join(blocks))
else:
    prompt = ("给下面每封邮件写一句中文要点（说清：这封邮件是什么、要我做什么）。\n"
              "要求：有截止时间/日期/课程代号/金额/地点/材料就写进去；不要写级别和发件人；不要写废话；每封一句，约 40 字。\n"
              "只输出一个 JSON 对象：{\"points\": [...]}，按顺序每封一个字符串，数量必须正好 %d 个。\n\n" % len(items)
              + "\n\n".join(blocks))
return {"prompt": prompt, "item_count": len(items), "has_items": bool(items)}
"""

REPORT_HTML = r"""
import json
import re

LEVEL_COLORS = {"S": "#e67e22", "A": "#8e44ad", "B": "#2980b9", "C": "#7f8c8d"}

def as_list(value):
    if isinstance(value, list):
        return value
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []

def esc(text):
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def parse_points(raw):
    raw = re.sub(r"```(?:json)?", "", raw or "").strip()
    payload = None
    try:
        payload = json.loads(raw)
    except Exception:
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end > start:
            try:
                payload = json.loads(raw[start:end + 1])
            except Exception:
                payload = None
    if isinstance(payload, list):
        return [str(x) for x in payload if isinstance(x, str)]
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
                return [str(x) for x in value]
    return []

items = as_list(items)
points = parse_points(text)
english = str(language or "zh").lower().startswith("en")
labels = {"s": "S", "a": "A", "b": "B", "c": "C"}
letters = "".join(c for c in "sabc" if c in str(letters_value or "sabc").lower()) or "sabc"
window = int(days or 7)
if letters == "sabc":
    label_text = "all levels" if english else "全部"
else:
    label_text = "+".join(labels[c] for c in letters) + (" levels" if english else " 级")
title = ("📬 Email summary（%s）" if english else "📬 邮件总结（%s）") % label_text
subject = ("📬 Email summary (%s) · last %d days" if english else "📬 邮件总结（%s）· 最近%d天") % (label_text, window)

html = ["<html><body style=\"font-family:'Segoe UI','Microsoft YaHei',sans-serif;font-size:14px;color:#222;line-height:1.6;\">",
        "<h2 style='margin:0 0 4px 0;'>%s</h2>" % esc(title),
        "<p style='margin:0 0 8px 0;color:#888;'>%s</p>" % (("%d messages" if english else "共 %d 封") % len(items))]
current = None
for index, mail in enumerate(items):
    level = str(mail.get("level") or "C").upper()[:1]
    if level != current:
        if current is not None:
            html.append("</div>")
        current = level
        html.append("<h3 style='margin:22px 0 10px 0;color:%s;'>【%s】</h3>" % (LEVEL_COLORS.get(level, "#000"), level))
        html.append("<div>")
    line = ["<div>[%s] <b>%s</b></div>" % (level, esc(mail.get("sender")))]
    link = str(mail.get("web_link") or "").strip()
    if link:
        line.append("<div><a href='%s'>%s</a></div>" % (esc(link), esc(mail.get("subject"))))
    else:
        line.append("<div>%s</div>" % esc(mail.get("subject")))
    if index < len(points) and points[index]:
        line.append("<div>%s</div>" % esc(points[index]))
    received = str(mail.get("received") or "")
    if received:
        line.append("<div style='color:#999;font-size:12px;'>%s</div>" % esc(received.replace("T", " ")))
    html.append("<div style='margin:0 0 16px 0;padding-bottom:10px;border-bottom:1px solid #e6e6e6;'>" + "".join(line) + "</div>")
if current is not None:
    html.append("</div>")
html.append("</body></html>")

return {"html": "\n".join(html), "subject": subject, "points_count": len(points)}
"""

CTRL_ADV = """
import json
return {
    "pending_ids_json": "[]",
    "failed": 0,
    "ignored_json": "[]",
    "newest_id": str(newest_id or ""),
    "catchup": False,
    "catchup_date": str(catchup_date or ""),
}
"""

ADV_INPUT = """
import json
def as_list(value):
    if isinstance(value, list):
        return value
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []
return {
    "pending_ids_json": pending_ids_json,
    "failed": int(failed or 0),
    "ignored_json": json.dumps(as_list(ignored_ids), ensure_ascii=False),
    "newest_id": str(newest_id or ""),
    "catchup": bool(catchup),
    "catchup_date": str(catchup_date or ""),
}
"""


# ── login workflow ───────────────────────────────────────────────────
def build_login():
    start = nid(1)
    branch = nid(2)
    tool_start = nid(3)
    card = nid(4)
    tool_poll = nid(5)
    card_poll = nid(6)
    agg_json = nid(7)
    agg_signed = nid(8)
    end = nid(9)

    nodes = [
        node(start, {
            "type": "start",
            "title": "Start",
            "variables": [{
                "type": "select",
                "variable": "action",
                "label": "Action",
                "required": True,
                "options": ["start", "poll"],
            }],
        }, 40, 240, height=118),
        if_else(branch, "Start or poll?", [
            case("case-start", [start, "action"], "is", "start"),
        ], 340, 240),
        tool_node(tool_start, "Start device sign-in", "auth_start", {
            "tenant": {"type": "mixed", "value": "{{#env.TENANT#}}"},
            "client_id": {"type": "mixed", "value": "{{#env.CLIENT_ID#}}"},
        }, 640, 160),
        code_node(card, "Sign-in instructions", [
            {"variable": "user_code", "value_selector": [tool_start, "user_code"]},
            {"variable": "verification_uri", "value_selector": [tool_start, "verification_uri"]},
            {"variable": "expires_in", "value_selector": [tool_start, "expires_in"]},
            {"variable": "client_label", "value_selector": [tool_start, "client_label"]},
            {"variable": "message", "value_selector": [tool_start, "message"]},
        ], LOGIN_CARD, {
            "result_json": {"type": "string"},
            "signed_in": {"type": "boolean"},
        }, 940, 160),
        tool_node(tool_poll, "Poll device sign-in", "auth_poll", {}, 640, 340),
        code_node(card_poll, "Sign-in result", [
            {"variable": "signed_in", "value_selector": [tool_poll, "signed_in"]},
            {"variable": "account", "value_selector": [tool_poll, "account"]},
            {"variable": "status", "value_selector": [tool_poll, "status"]},
        ], LOGIN_POLL, {
            "result_json": {"type": "string"},
            "signed_in": {"type": "boolean"},
        }, 940, 340),
        aggregator(agg_json, "Merge result", [[card, "result_json"], [card_poll, "result_json"]],
                   "string", 1240, 220),
        aggregator(agg_signed, "Merge signed-in", [[card, "signed_in"], [card_poll, "signed_in"]],
                   "boolean", 1240, 360),
        end_node(end, [
            out("result_json", "string", [agg_json, "output"]),
            out("signed_in", "boolean", [agg_signed, "output"]),
        ], 1540, 280),
    ]
    edges = [
        edge(start, branch, "start", "if-else"),
        edge(branch, tool_start, "if-else", "tool", "case-start"),
        edge(branch, tool_poll, "if-else", "tool", "false"),
        edge(tool_start, card, "tool", "code"),
        edge(tool_poll, card_poll, "tool", "code"),
        edge(card, agg_json, "code", "variable-aggregator"),
        edge(card_poll, agg_json, "code", "variable-aggregator"),
        edge(card, agg_signed, "code", "variable-aggregator"),
        edge(card_poll, agg_signed, "code", "variable-aggregator"),
        edge(agg_json, end, "variable-aggregator", "end"),
        edge(agg_signed, end, "variable-aggregator", "end"),
    ]
    graph = {"edges": edges, "nodes": nodes, "viewport": {"x": 0, "y": 0, "zoom": 0.7}}
    env = [env_var("TENANT", "string", ""), env_var("CLIENT_ID", "string", "")]
    return app("workflow", "Email Manager · Login",
               "Device-code sign-in helper. Run with action=start, approve the code in a browser, then run with action=poll.",
               env, graph)


# ── main workflow ────────────────────────────────────────────────────
def build_main():
    sched = "1700000001"
    web = "1700000002"
    c_sched = "1700000003"
    c_web = "1700000004"
    agg_ctx = "1700000005"
    parse_ctx = "1700000006"
    if_authz = "1700000007"
    end_unauth = "1700000008"
    if_sum = "1700000009"
    if_check = "1700000010"
    if_resume = "1700000011"
    check_tool = "1700000012"
    end_check = "1700000013"
    set_resume = "1700000014"
    end_resume = "1700000015"
    if_reset = "1700000090"
    reset_tool = "1700000091"
    end_reset = "1700000092"
    if_logout = "1700000093"
    signout_tool = "1700000094"
    end_logout = "1700000095"
    if_sched = "1700000100"
    recent_sched = "1700000101"
    prompt_sched = "1700000102"
    if_items_sched = "1700000103"
    llm_sched = "1700000104"
    html_sched = "1700000105"
    send_sched = "1700000106"
    mark_sched = "1700000107"
    end_sched = "1700000108"
    auth_status = "1700000020"
    if_signed = "1700000021"
    end_login = "1700000022"
    state_get = "1700000023"
    parse_state = "1700000024"
    if_paused = "1700000025"
    end_paused = "1700000026"
    lock = "1700000027"
    if_lock = "1700000028"
    end_busy = "1700000029"
    collect = "1700000030"
    if_transient = "1700000031"
    unlock_retry = "1700000032"
    end_retry = "1700000033"
    plan = "1700000034"
    if_controls = "1700000035"
    tag = "1700000036"
    if_cmds = "1700000037"
    recent = "1700000038"
    report_prompt = "1700000039"
    if_items = "1700000040"
    llm_report = "1700000041"
    report_html = "1700000042"
    send_report = "1700000043"
    ctrl_adv = "1700000044"
    adv_ctrl = "1700000045"
    unlock_ctrl = "1700000046"
    end_report = "1700000047"
    if_candidates = "1700000048"
    llm_classify = "1700000050"
    validate = "1700000051"
    apply_tool = "1700000052"
    if_apply_transient = "1700000053"
    unlock_apply_err = "1700000054"
    end_apply_err = "1700000055"
    adv_input = "1700000056"
    adv_main = "1700000057"
    unlock_main = "1700000058"
    end_stats = "1700000059"
    end_ctrl = "1700000060"
    adv_report = "1700000061"
    unlock_report = "1700000062"
    # merged login flow (previously workflows/email-manager-login.yml)
    if_login = "1700000070"
    auth_start_manual = "1700000071"
    end_login_code = "1700000072"
    if_login_poll = "1700000073"
    auth_poll_manual = "1700000074"
    end_login_result = "1700000075"
    auth_start_auto = "1700000076"
    if_fresh = "1700000077"
    human_input = "1700000078"
    auth_poll_login = "1700000079"
    if_login_signed = "1700000080"
    end_login_ok = "1700000081"
    end_login_cancel = "1700000082"
    end_login_timeout = "1700000083"
    auth_poll_quick = "1700000084"
    if_quick_signed = "1700000085"
    end_login_waiting = "1700000086"

    run_id = ["sys", "workflow_run_id"]
    nodes = [
        node(sched, {
            "type": "trigger-schedule",
            "title": "Every 5 minutes",
            "mode": "cron",
            "frequency": None,
            "cron_expression": "*/5 * * * *",
            "visual_config": None,
            "timezone": "Asia/Hong_Kong",
        }, 40, 120, height=120),
        node(web, {
            "type": "trigger-webhook",
            "title": "Webhook command",
            "method": "post",
            "content_type": "application/json",
            "headers": [],
            "params": [],
            "body": [
                {"name": "token", "type": "string", "required": True},
                {"name": "action", "type": "string", "required": True},
                {"name": "letters", "type": "string", "required": False},
                {"name": "days", "type": "number", "required": False},
            ],
            "status_code": 200,
            "response_body": "{\"ok\": true}",
            "timeout": 30,
        }, 40, 340, height=140),
        code_node(c_sched, "Schedule context", [], CTX_SCHED,
                  {"ctx_json": {"type": "string"}}, 340, 120, height=120),
        code_node(c_web, "Webhook context", [
            {"variable": "token", "value_selector": [web, "token"]},
            {"variable": "expected", "value_selector": ev("WEBHOOK_TOKEN")},
            {"variable": "action", "value_selector": [web, "action"]},
            {"variable": "letters", "value_selector": [web, "letters"]},
            {"variable": "days", "value_selector": [web, "days"]},
        ], CTX_WEBHOOK, {
            "ctx_json": {"type": "string"},
            "authorized": {"type": "boolean"},
        }, 340, 340, height=180),
        aggregator(agg_ctx, "Merge context", [[c_sched, "ctx_json"], [c_web, "ctx_json"]],
                   "string", 640, 220),
        code_node(parse_ctx, "Parse context", [
            {"variable": "ctx_json", "value_selector": [agg_ctx, "output"]},
        ], PARSE_CTX, {
            "source": {"type": "string"},
            "action": {"type": "string"},
            "letters": {"type": "string"},
            "days": {"type": "number"},
            "manual": {"type": "boolean"},
            "authorized": {"type": "boolean"},
        }, 900, 220, height=160),
        if_else(if_authz, "Authorized?", [
            case("case-authorized", [parse_ctx, "authorized"], "is", "true"),
        ], 1160, 220),
        end_node(end_unauth, [], 1420, 120),
        if_else(if_sum, "Manual summary?", [
            case("case-sum", [parse_ctx, "action"], "is", "sum"),
        ], 1420, 300),
        if_else(if_check, "Manual check?", [
            case("case-check", [parse_ctx, "action"], "is", "check"),
        ], 1420, 480),
        if_else(if_resume, "Resume?", [
            case("case-resume", [parse_ctx, "action"], "is", "resume"),
        ], 1420, 660),
        if_else(if_reset, "Reset baseline?", [
            case("case-reset", [parse_ctx, "action"], "is", "reset"),
        ], 1420, 720),
        if_else(if_logout, "Sign out?", [
            case("case-logout", [parse_ctx, "action"], "is", "logout"),
        ], 1420, 780),
        tool_node(check_tool, "Check mailbox", "check", {}, 1680, 480),
        end_node(end_check, [
            out("signed_in", "boolean", [check_tool, "signed_in"]),
            out("account", "string", [check_tool, "account"]),
            out("inbox_count", "number", [check_tool, "inbox_count"]),
        ], 1960, 480),
        tool_node(set_resume, "Resume processing", "state_set", {
            "update_paused": {"type": "constant", "value": True},
            "paused": {"type": "constant", "value": False},
            "reason": {"type": "constant", "value": "manual resume"},
            "clear_failed": {"type": "constant", "value": True},
        }, 1680, 660),
        end_node(end_resume, [out("paused", "boolean", [set_resume, "paused"])], 1960, 660),
        tool_node(reset_tool, "Reset test baseline", "state_set", {
            "reset_baseline": {"type": "constant", "value": True},
            "clear_failed": {"type": "constant", "value": True},
            "clear_ignored": {"type": "constant", "value": True},
            "reason": {"type": "constant", "value": "manual reset for testing"},
        }, 1680, 720),
        end_node(end_reset, [
            out("paused", "boolean", [reset_tool, "paused"]),
            out("last_seen", "string", [reset_tool, "last_seen"]),
        ], 1960, 720),
        tool_node(signout_tool, "Sign out", "auth_sign_out", {}, 1680, 780),
        end_node(end_logout, [], 1960, 780),
        tool_node(auth_status, "Auth status", "auth_status", {}, 1680, 840),
        if_else(if_signed, "Signed in?", [
            case("case-signed", [auth_status, "signed_in"], "is", "true"),
        ], 1960, 840),
        tool_node(state_get, "Get state", "state_get", {}, 2220, 900),
        code_node(parse_state, "Parse state", [
            {"variable": "state_json", "value_selector": [state_get, "state"]},
            {"variable": "summary_days_value", "value_selector": ev("SUMMARY_DAYS")},
            {"variable": "force_action", "value_selector": ev("FORCE_ACTION")},
        ], PARSE_STATE, {
            "paused": {"type": "boolean"},
            "last_seen": {"type": "string"},
            "failed_rounds": {"type": "number"},
            "catchup": {"type": "boolean"},
            "catchup_date": {"type": "string"},
            "report_due": {"type": "boolean"},
            "report_kind": {"type": "string"},
            "report_days": {"type": "number"},
            "report_letters": {"type": "string"},
            "mark_daily": {"type": "boolean"},
            "mark_weekly": {"type": "boolean"},
        }, 2480, 900, height=260),
        if_else(if_sched, "Scheduled report?", [
            case("case-report", [parse_state, "report_due"], "is", "true"),
        ], 2740, 700),
        tool_node(recent_sched, "Collect report mail", "collect_recent", {
            "days": {"type": "variable", "value": [parse_state, "report_days"]},
            "letters": {"type": "variable", "value": [parse_state, "report_letters"]},
            "max_items": {"type": "constant", "value": 50},
        }, 3000, 700),
        code_node(prompt_sched, "Report prompt", [
            {"variable": "items", "value_selector": [recent_sched, "items"]},
            {"variable": "language", "value_selector": ev("LANGUAGE")},
        ], REPORT_PROMPT, {
            "prompt": {"type": "string"},
            "item_count": {"type": "number"},
            "has_items": {"type": "boolean"},
        }, 3260, 700, height=180),
        if_else(if_items_sched, "Report has mail?", [
            case("case-items", [prompt_sched, "has_items"], "is", "true"),
        ], 3520, 700),
        llm_node(llm_sched, "Write one-liners", "{{#%s.prompt#}}" % prompt_sched, 3780, 700),
        code_node(html_sched, "Build HTML report", [
            {"variable": "text", "value_selector": [llm_sched, "text"]},
            {"variable": "items", "value_selector": [recent_sched, "items"]},
            {"variable": "language", "value_selector": ev("LANGUAGE")},
            {"variable": "letters_value", "value_selector": [parse_state, "report_letters"]},
            {"variable": "days", "value_selector": [parse_state, "report_days"]},
        ], REPORT_HTML, {
            "html": {"type": "string"},
            "subject": {"type": "string"},
            "points_count": {"type": "number"},
        }, 4040, 700, height=220),
        tool_node(send_sched, "Send report", "send_report", {
            "to": {"type": "mixed", "value": "{{#env.RECIPIENT#}}"},
            "subject": {"type": "variable", "value": [html_sched, "subject"]},
            "html": {"type": "variable", "value": [html_sched, "html"]},
        }, 4300, 700),
        tool_node(mark_sched, "Mark report sent", "state_set", {
            "mark_daily_report": {"type": "variable", "value": [parse_state, "mark_daily"]},
            "mark_weekly_report": {"type": "variable", "value": [parse_state, "mark_weekly"]},
            "reason": {"type": "constant", "value": "scheduled report"},
        }, 4560, 700),
        end_node(end_sched, [], 4820, 700),
        if_else(if_paused, "Paused?", [
            case("case-paused", [parse_state, "paused"], "is", "true"),
        ], 2740, 900),
        end_node(end_paused, [], 3000, 800),
        tool_node(lock, "Acquire lock", "state_lock", {
            "owner": {"type": "variable", "value": list(run_id)},
            "ttl_seconds": {"type": "constant", "value": 600},
        }, 3000, 960),
        if_else(if_lock, "Lock acquired?", [
            case("case-locked", [lock, "acquired"], "is", "true"),
        ], 3260, 960),
        end_node(end_busy, [], 3520, 860),
        tool_node(collect, "Collect mail", "collect", {
            "last_seen": {"type": "variable", "value": [parse_state, "last_seen"]},
            "days": {"type": "constant", "value": 7},
            "max_items": {"type": "constant", "value": 20},
            "catchup": {"type": "variable", "value": [parse_state, "catchup"]},
        }, 3520, 1020),
        if_else(if_transient, "Mailbox available?", [
            case("case-ok", [collect, "transient"], "is", "false"),
        ], 3780, 1020),
        tool_node(unlock_retry, "Release lock", "state_unlock", {
            "owner": {"type": "variable", "value": list(run_id)},
        }, 4040, 900),
        end_node(end_retry, [], 4300, 900),
        code_node(plan, "Plan round", [
            {"variable": "candidates", "value_selector": [collect, "candidates"]},
            {"variable": "controls_commands", "value_selector": [collect, "controls_commands"]},
            {"variable": "controls_reports", "value_selector": [collect, "controls_reports"]},
            {"variable": "newest_id", "value_selector": [collect, "newest_id"]},
            {"variable": "catchup_date", "value_selector": [parse_state, "catchup_date"]},
            {"variable": "name", "value_selector": ev("NAME")},
            {"variable": "student_id", "value_selector": ev("STUDENT_ID")},
            {"variable": "school_domains", "value_selector": ev("SCHOOL_DOMAINS")},
            {"variable": "faculty", "value_selector": ev("FACULTY")},
            {"variable": "courses", "value_selector": ev("COURSES")},
            {"variable": "urgent_days", "value_selector": ev("URGENT_DAYS")},
            {"variable": "language", "value_selector": ev("LANGUAGE")},
            {"variable": "dry_run_value", "value_selector": ev("DRY_RUN")},
        ], PLAN_CODE, {
            "prompt": {"type": "string"},
            "ids_json": {"type": "string"},
            "candidate_count": {"type": "number"},
            "has_candidates": {"type": "boolean"},
            "has_commands": {"type": "boolean"},
            "has_controls": {"type": "boolean"},
            "control_ids_json": {"type": "string"},
            "newest_id": {"type": "string"},
            "catchup_date": {"type": "string"},
            "dry_run": {"type": "boolean"},
        }, 4040, 1080, height=260),
        if_else(if_controls, "Control mail?", [
            case("case-controls", [plan, "has_controls"], "is", "true"),
        ], 4340, 1080),
        tool_node(tag, "Tag control mail", "tag", {
            "entryids_json": {"type": "variable", "value": [plan, "control_ids_json"]},
            "names_json": {"type": "constant", "value": "[\"Sum\"]"},
        }, 4600, 1000),
        if_else(if_cmds, "Sum command?", [
            case("case-cmds", [plan, "has_commands"], "is", "true"),
        ], 4600, 1180),
        tool_node(recent, "Collect classified mail", "collect_recent", {
            "days": {"type": "variable", "value": ev("SUMMARY_DAYS")},
            "letters": {"type": "variable", "value": [parse_ctx, "letters"]},
            "max_items": {"type": "constant", "value": 50},
        }, 4860, 1100),
        code_node(report_prompt, "Report prompt", [
            {"variable": "items", "value_selector": [recent, "items"]},
            {"variable": "language", "value_selector": ev("LANGUAGE")},
        ], REPORT_PROMPT, {
            "prompt": {"type": "string"},
            "item_count": {"type": "number"},
            "has_items": {"type": "boolean"},
        }, 4860, 1300, height=180),
        if_else(if_items, "Anything to report?", [
            case("case-items", [report_prompt, "has_items"], "is", "true"),
        ], 5120, 1300),
        llm_node(llm_report, "Write one-liners", "{{#%s.prompt#}}" % report_prompt, 5380, 1300),
        code_node(report_html, "Build HTML report", [
            {"variable": "text", "value_selector": [llm_report, "text"]},
            {"variable": "items", "value_selector": [recent, "items"]},
            {"variable": "language", "value_selector": ev("LANGUAGE")},
            {"variable": "letters_value", "value_selector": ev("LETTERS")},
            {"variable": "days", "value_selector": ev("SUMMARY_DAYS")},
        ], REPORT_HTML, {
            "html": {"type": "string"},
            "subject": {"type": "string"},
            "points_count": {"type": "number"},
        }, 5640, 1300, height=260),
        tool_node(send_report, "Send report", "send_report", {
            "to": {"type": "mixed", "value": "{{#env.RECIPIENT#}}"},
            "subject": {"type": "variable", "value": [report_html, "subject"]},
            "html": {"type": "variable", "value": [report_html, "html"]},
        }, 5900, 1300),
        code_node(ctrl_adv, "Control round result", [
            {"variable": "newest_id", "value_selector": [plan, "newest_id"]},
            {"variable": "catchup_date", "value_selector": [plan, "catchup_date"]},
        ], CTRL_ADV, {
            "pending_ids_json": {"type": "string"},
            "failed": {"type": "number"},
            "ignored_json": {"type": "string"},
            "newest_id": {"type": "string"},
            "catchup": {"type": "boolean"},
            "catchup_date": {"type": "string"},
        }, 6160, 1100, height=180),
        tool_node(adv_ctrl, "Advance baseline", "state_advance", {
            "pending_ids_json": {"type": "variable", "value": [ctrl_adv, "pending_ids_json"]},
            "newest_id": {"type": "variable", "value": [ctrl_adv, "newest_id"]},
            "failed": {"type": "variable", "value": [ctrl_adv, "failed"]},
            "ignored_ids_json": {"type": "variable", "value": [ctrl_adv, "ignored_json"]},
            "catchup": {"type": "variable", "value": [ctrl_adv, "catchup"]},
            "catchup_date": {"type": "variable", "value": [ctrl_adv, "catchup_date"]},
        }, 6420, 1100),
        tool_node(unlock_ctrl, "Release lock", "state_unlock", {
            "owner": {"type": "variable", "value": list(run_id)},
        }, 6680, 1100),
        end_node(end_ctrl, [], 6940, 1040),
        tool_node(adv_report, "Advance after report", "state_advance", {
            "pending_ids_json": {"type": "constant", "value": "[]"},
            "newest_id": {"type": "variable", "value": [plan, "newest_id"]},
            "failed": {"type": "constant", "value": 0},
            "ignored_ids_json": {"type": "constant", "value": "[]"},
            "catchup": {"type": "constant", "value": False},
            "catchup_date": {"type": "constant", "value": ""},
        }, 6160, 1520),
        tool_node(unlock_report, "Release lock", "state_unlock", {
            "owner": {"type": "variable", "value": list(run_id)},
        }, 6420, 1520),
        end_node(end_report, [
            out("subject", "string", [report_html, "subject"]),
            out("points", "number", [report_html, "points_count"]),
        ], 6680, 1520),
        if_else(if_candidates, "New mail?", [
            case("case-candidates", [plan, "has_candidates"], "is", "true"),
        ], 4600, 1360),
        llm_node(llm_classify, "Classify mail", "{{#%s.prompt#}}" % plan, 4860, 1360),
        code_node(validate, "Validate verdicts", [
            {"variable": "text", "value_selector": [llm_classify, "text"]},
            {"variable": "candidates_value", "value_selector": [collect, "candidates"]},
            {"variable": "ids_json", "value_selector": [plan, "ids_json"]},
            {"variable": "school_domains_value", "value_selector": ev("SCHOOL_DOMAINS")},
            {"variable": "faculty_value", "value_selector": ev("FACULTY")},
            {"variable": "courses_value", "value_selector": ev("COURSES")},
            {"variable": "urgent_days_value", "value_selector": ev("URGENT_DAYS")},
        ], VALIDATE_CODE, {
            "verdicts_json": {"type": "string"},
            "pending_ids_json": {"type": "string"},
            "failed": {"type": "number"},
            "summary": {"type": "string"},
        }, 5120, 1360, height=260),
        tool_node(apply_tool, "Write back", "apply", {
            "verdicts_json": {"type": "variable", "value": [validate, "verdicts_json"]},
            "dry_run": {"type": "variable", "value": [plan, "dry_run"]},
        }, 5380, 1360),
        if_else(if_apply_transient, "Write ok?", [
            case("case-ok", [apply_tool, "transient"], "is", "false"),
        ], 5640, 1360),
        tool_node(unlock_apply_err, "Release lock", "state_unlock", {
            "owner": {"type": "variable", "value": list(run_id)},
        }, 5900, 1240),
        end_node(end_apply_err, [], 6160, 1240),
        code_node(adv_input, "Round result", [
            {"variable": "pending_ids_json", "value_selector": [validate, "pending_ids_json"]},
            {"variable": "failed", "value_selector": [apply_tool, "failed"]},
            {"variable": "ignored_ids", "value_selector": [apply_tool, "ignored_ids"]},
            {"variable": "newest_id", "value_selector": [plan, "newest_id"]},
            {"variable": "catchup", "value_selector": [parse_state, "catchup"]},
            {"variable": "catchup_date", "value_selector": [plan, "catchup_date"]},
        ], ADV_INPUT, {
            "pending_ids_json": {"type": "string"},
            "failed": {"type": "number"},
            "ignored_json": {"type": "string"},
            "newest_id": {"type": "string"},
            "catchup": {"type": "boolean"},
            "catchup_date": {"type": "string"},
        }, 5900, 1360, height=200),
        tool_node(adv_main, "Advance baseline", "state_advance", {
            "pending_ids_json": {"type": "variable", "value": [adv_input, "pending_ids_json"]},
            "newest_id": {"type": "variable", "value": [adv_input, "newest_id"]},
            "failed": {"type": "variable", "value": [adv_input, "failed"]},
            "ignored_ids_json": {"type": "variable", "value": [adv_input, "ignored_json"]},
            "catchup": {"type": "variable", "value": [adv_input, "catchup"]},
            "catchup_date": {"type": "variable", "value": [adv_input, "catchup_date"]},
        }, 6160, 1360),
        tool_node(unlock_main, "Release lock", "state_unlock", {
            "owner": {"type": "variable", "value": list(run_id)},
        }, 6420, 1360),
        end_node(end_stats, [
            out("candidates", "number", [plan, "candidate_count"]),
            out("ok", "number", [apply_tool, "ok"]),
            out("failed", "number", [apply_tool, "failed"]),
            out("skipped", "number", [apply_tool, "skipped"]),
            out("last_seen", "string", [adv_main, "last_seen"]),
            out("gave_up", "boolean", [adv_main, "gave_up"]),
        ], 6680, 1360),
        # ── device-code login, merged from the old separate login workflow ──
        # manual path: webhook action=login / login_poll, results in the run outputs
        if_else(if_login, "Manual login?", [
            case("case-login", [parse_ctx, "action"], "is", "login"),
        ], 1420, 800),
        tool_node(auth_start_manual, "Start device sign-in", "auth_start", {
            "tenant": {"type": "variable", "value": ev("TENANT")},
            "client_id": {"type": "variable", "value": ev("CLIENT_ID")},
            "force_new": {"type": "constant", "value": True},
        }, 1680, 800),
        end_node(end_login_code, [
            out("user_code", "string", [auth_start_manual, "user_code"]),
            out("verification_uri", "string", [auth_start_manual, "verification_uri"]),
            out("expires_in", "number", [auth_start_manual, "expires_in"]),
            out("fresh", "boolean", [auth_start_manual, "fresh"]),
        ], 1960, 800),
        if_else(if_login_poll, "Manual login poll?", [
            case("case-login-poll", [parse_ctx, "action"], "is", "login_poll"),
        ], 1420, 1000),
        tool_node(auth_poll_manual, "Poll sign-in", "auth_poll", {}, 1680, 1000),
        end_node(end_login_result, [
            out("signed_in", "boolean", [auth_poll_manual, "signed_in"]),
            out("status", "string", [auth_poll_manual, "status"]),
            out("account", "string", [auth_poll_manual, "account"]),
            out("error", "string", [auth_poll_manual, "error"]),
        ], 1960, 1000),
        # automatic path: a scheduled run that finds no sign-in asks the user by e-mail
        tool_node(auth_start_auto, "Start sign-in", "auth_start", {
            "tenant": {"type": "variable", "value": ev("TENANT")},
            "client_id": {"type": "variable", "value": ev("CLIENT_ID")},
        }, 2220, 1120),
        if_else(if_fresh, "New code?", [
            case("case-fresh", [auth_start_auto, "fresh"], "is", "true"),
        ], 2480, 1120),
        human_input_node(
            human_input, "Device sign-in", 2740, 1000,
            form_content=(
                "## Microsoft sign-in required\n\n"
                "Device code: **{{#%s.user_code#}}**\n\n"
                "Authorization link: {{#%s.verification_uri#}}\n\n"
                "Complete the sign-in in your browser, then click the button below."
                % (auth_start_auto, auth_start_auto)
            ),
            email_subject="Email Manager sign-in: complete the Microsoft device code authorization",
            email_body=(
                "Device code: {{#%s.user_code#}}\n"
                "Authorization link: {{#%s.verification_uri#}}\n\n"
                "After authorizing, open the form below and click \"I have completed the sign-in\":\n{{#url#}}"
                % (auth_start_auto, auth_start_auto)
            ),
            actions=[
                {"id": "done", "title": "I have completed the sign-in", "button_style": "primary"},
                {"id": "cancel", "title": "Cancel", "button_style": "default"},
            ],
            timeout=1, timeout_unit="hour",
        ),
        tool_node(auth_poll_login, "Poll sign-in", "auth_poll", {}, 3080, 1000),
        if_else(if_login_signed, "Signed in?", [
            case("case-login-signed", [auth_poll_login, "signed_in"], "is", "true"),
        ], 3340, 1000),
        end_node(end_login_ok, [], 3600, 900),
        end_node(end_login, [], 3600, 1060),
        end_node(end_login_cancel, [], 3080, 1180),
        end_node(end_login_timeout, [], 3080, 1300),
        tool_node(auth_poll_quick, "Poll pending sign-in", "auth_poll", {}, 2740, 1200),
        if_else(if_quick_signed, "Signed in?", [
            case("case-quick-signed", [auth_poll_quick, "signed_in"], "is", "true"),
        ], 3000, 1200),
        end_node(end_login_waiting, [], 3260, 1300),
    ]

    edges = [
        edge(sched, c_sched, "trigger-schedule", "code"),
        edge(web, c_web, "trigger-webhook", "code"),
        edge(c_sched, agg_ctx, "code", "variable-aggregator"),
        edge(c_web, agg_ctx, "code", "variable-aggregator"),
        edge(agg_ctx, parse_ctx, "variable-aggregator", "code"),
        edge(parse_ctx, if_authz, "code", "if-else"),
        edge(if_authz, end_unauth, "if-else", "end", "false"),
        edge(if_authz, if_login, "if-else", "if-else", "case-authorized"),
        edge(if_login, auth_start_manual, "if-else", "tool", "case-login"),
        edge(if_login, if_login_poll, "if-else", "if-else", "false"),
        edge(auth_start_manual, end_login_code, "tool", "end"),
        edge(if_login_poll, auth_poll_manual, "if-else", "tool", "case-login-poll"),
        edge(if_login_poll, if_sum, "if-else", "if-else", "false"),
        edge(auth_poll_manual, end_login_result, "tool", "end"),
        edge(if_sum, if_check, "if-else", "if-else", "false"),
        edge(if_sum, recent, "if-else", "tool", "case-sum"),
        edge(if_check, check_tool, "if-else", "tool", "case-check"),
        edge(if_check, if_resume, "if-else", "if-else", "false"),
        edge(if_resume, set_resume, "if-else", "tool", "case-resume"),
        edge(if_resume, if_reset, "if-else", "if-else", "false"),
        edge(if_reset, reset_tool, "if-else", "tool", "case-reset"),
        edge(if_reset, if_logout, "if-else", "if-else", "false"),
        edge(if_logout, signout_tool, "if-else", "tool", "case-logout"),
        edge(if_logout, auth_status, "if-else", "tool", "false"),
        edge(signout_tool, end_logout, "tool", "end"),
        edge(reset_tool, end_reset, "tool", "end"),
        edge(set_resume, end_resume, "tool", "end"),
        edge(check_tool, end_check, "tool", "end"),
        edge(auth_status, if_signed, "tool", "if-else"),
        edge(if_signed, auth_start_auto, "if-else", "tool", "false"),
        edge(if_signed, state_get, "if-else", "tool", "case-signed"),
        edge(auth_start_auto, if_fresh, "tool", "if-else"),
        edge(if_fresh, human_input, "if-else", "human-input", "case-fresh"),
        edge(if_fresh, auth_poll_quick, "if-else", "tool", "false"),
        edge(human_input, auth_poll_login, "human-input", "tool", "done"),
        edge(human_input, end_login_cancel, "human-input", "end", "cancel"),
        edge(human_input, end_login_timeout, "human-input", "end", "__timeout"),
        edge(auth_poll_login, if_login_signed, "tool", "if-else"),
        edge(if_login_signed, end_login_ok, "if-else", "end", "case-login-signed"),
        edge(if_login_signed, end_login, "if-else", "end", "false"),
        edge(auth_poll_quick, if_quick_signed, "tool", "if-else"),
        edge(if_quick_signed, end_login_ok, "if-else", "end", "case-quick-signed"),
        edge(if_quick_signed, end_login_waiting, "if-else", "end", "false"),
        edge(state_get, parse_state, "tool", "code"),
        edge(parse_state, if_sched, "code", "if-else"),
        edge(if_sched, recent_sched, "if-else", "tool", "case-report"),
        edge(if_sched, if_paused, "if-else", "if-else", "false"),
        edge(recent_sched, prompt_sched, "tool", "code"),
        edge(prompt_sched, if_items_sched, "code", "if-else"),
        edge(if_items_sched, llm_sched, "if-else", "llm", "case-items"),
        edge(if_items_sched, mark_sched, "if-else", "tool", "false"),
        edge(llm_sched, html_sched, "llm", "code"),
        edge(html_sched, send_sched, "code", "tool"),
        edge(send_sched, mark_sched, "tool", "tool"),
        edge(mark_sched, end_sched, "tool", "end"),
        edge(if_paused, end_paused, "if-else", "end", "case-paused"),
        edge(if_paused, lock, "if-else", "tool", "false"),
        edge(lock, if_lock, "tool", "if-else"),
        edge(if_lock, end_busy, "if-else", "end", "false"),
        edge(if_lock, collect, "if-else", "tool", "case-locked"),
        edge(collect, if_transient, "tool", "if-else"),
        edge(if_transient, unlock_retry, "if-else", "tool", "false"),
        edge(if_transient, plan, "if-else", "code", "case-ok"),
        edge(unlock_retry, end_retry, "tool", "end"),
        edge(plan, if_controls, "code", "if-else"),
        edge(if_controls, tag, "if-else", "tool", "case-controls"),
        edge(if_controls, if_candidates, "if-else", "if-else", "false"),
        edge(tag, if_cmds, "tool", "if-else"),
        edge(if_cmds, recent, "if-else", "tool", "case-cmds"),
        edge(if_cmds, ctrl_adv, "if-else", "code", "false"),
        edge(recent, report_prompt, "tool", "code"),
        edge(report_prompt, if_items, "code", "if-else"),
        edge(if_items, llm_report, "if-else", "llm", "case-items"),
        edge(if_items, ctrl_adv, "if-else", "code", "false"),
        edge(llm_report, report_html, "llm", "code"),
        edge(report_html, send_report, "code", "tool"),
        edge(send_report, adv_report, "tool", "tool"),
        edge(adv_report, unlock_report, "tool", "tool"),
        edge(unlock_report, end_report, "tool", "end"),
        edge(ctrl_adv, adv_ctrl, "code", "tool"),
        edge(adv_ctrl, unlock_ctrl, "tool", "tool"),
        edge(unlock_ctrl, end_ctrl, "tool", "end"),
        edge(if_candidates, llm_classify, "if-else", "llm", "case-candidates"),
        edge(if_candidates, ctrl_adv, "if-else", "code", "false"),
        edge(llm_classify, validate, "llm", "code"),
        edge(validate, apply_tool, "code", "tool"),
        edge(apply_tool, if_apply_transient, "tool", "if-else"),
        edge(if_apply_transient, unlock_apply_err, "if-else", "tool", "false"),
        edge(if_apply_transient, adv_input, "if-else", "code", "case-ok"),
        edge(unlock_apply_err, end_apply_err, "tool", "end"),
        edge(adv_input, adv_main, "code", "tool"),
        edge(adv_main, unlock_main, "tool", "tool"),
        edge(unlock_main, end_stats, "tool", "end"),
    ]

    env = [
        env_var("EMAIL", "string", ""),
        env_var("NAME", "string", ""),
        env_var("STUDENT_ID", "string", ""),
        env_var("SCHOOL_DOMAINS", "string", "ust.hk"),
        env_var("FACULTY", "string", ""),
        env_var("COURSES", "string", ""),
        env_var("DORM_KEYWORDS", "string", "UG Hall, 宿舍"),
        env_var("URGENT_DAYS", "number", 14),
        env_var("CATCHUP_DAYS", "number", 7),
        env_var("SUMMARY_DAYS", "number", 7),
        env_var("LETTERS", "string", "sabc"),
        env_var("RECIPIENT", "string", ""),
        env_var("LANGUAGE", "string", "zh"),
        # Dify environment variables only support string / number / secret.
        # A boolean value_type makes GET /workflows/draft return HTTP 400.
        env_var("DRY_RUN", "string", "false"),
        env_var("WEBHOOK_TOKEN", "secret", ""),
        env_var("TENANT", "string", ""),
        env_var("CLIENT_ID", "string", ""),
    ]
    graph = {"edges": edges, "nodes": nodes, "viewport": {"x": 0, "y": 0, "zoom": 0.5}}
    return app("workflow", "Email Manager · Main",
               "One workflow: classify school mail into S/A/B/C, write categories back, and send HTML summaries on demand.",
               env, graph)


def _fix_end_nodes(dsl):
    """Dify requires every End node to have >=1 output, with unique names."""
    graph = dsl["workflow"]["graph"]
    ends = sorted((n for n in graph["nodes"] if n["data"]["type"] == "end"),
                  key=lambda n: n["id"])
    seen = set()
    for end in ends:
        outputs = end["data"].setdefault("outputs", [])
        if not outputs:
            outputs.append({"variable": "run_id", "value_type": "string",
                            "value_selector": ["sys", "workflow_run_id"]})
        for item in outputs:
            name = item["variable"]
            if name in seen:
                suffix = end["id"][-4:]
                new_name = f"{name}_{suffix}"
                index = 2
                while new_name in seen:
                    new_name = f"{name}_{suffix}_{index}"
                    index += 1
                item["variable"] = new_name
                name = new_name
            seen.add(name)


def _force_context():
    return r"""
import json

action = str(force_action or "").strip().lower()
# Dify environment variables cannot be empty, so "auto" (or any unknown marker
# such as null/none) means "normal scheduled run".
if action in ("", "auto", "none", "null", "-"):
    action = "auto"
letters = str(letters_value or "sabc").strip() or "sabc"
days = int(days_value or 0)
ctx = {
    "source": "schedule",
    "action": action,
    "letters": letters,
    "days": days,
    "manual": action != "auto",
    "authorized": True,
}
return {"ctx_json": json.dumps(ctx, ensure_ascii=False)}
"""


WEB_ID = "1700000002"
C_WEB_ID = "1700000004"
AGG_CTX_ID = "1700000005"
C_SCHED_ID = "1700000003"
PARSE_CTX_ID = "1700000006"


def _remove_nodes(dsl, node_ids):
    graph = dsl["workflow"]["graph"]
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in node_ids]
    graph["edges"] = [e for e in graph["edges"]
                      if e["source"] not in node_ids and e["target"] not in node_ids]


def _find_node(dsl, node_id):
    for node in dsl["workflow"]["graph"]["nodes"]:
        if node["id"] == node_id:
            return node
    raise KeyError(node_id)


def _finalize(dsl):
    """Turn the merged graph into the single accepted workflow.

    * only one Schedule trigger (the imported webhook trigger cannot get a URL
      on Dify Cloud without manual UI work, so it is removed);
    * manual actions come from the FORCE_ACTION environment variable;
    * only two personal values have to be filled in after import.
    """
    # webhook trigger + its context branch are dropped
    _remove_nodes(dsl, {WEB_ID, C_WEB_ID, AGG_CTX_ID})

    # schedule -> env context -> parse context
    sched_code = _find_node(dsl, C_SCHED_ID)
    variables = [
        {"variable": "force_action", "value_selector": ["env", "FORCE_ACTION"]},
        {"variable": "letters_value", "value_selector": ["env", "LETTERS"]},
        {"variable": "days_value", "value_selector": ["env", "SUMMARY_DAYS"]},
    ]
    body = "\n".join("    " + line if line.strip() else ""
                     for line in _force_context().strip("\n").splitlines())
    sched_code["data"].update({
        "title": "Read forced action",
        "variables": variables,
        "code": "def main(%s):\n%s\n" % (
            ", ".join(item["variable"] for item in variables), body),
        "outputs": {"ctx_json": {"type": "string"}},
    })
    dsl["workflow"]["graph"]["edges"].append(
        edge(C_SCHED_ID, PARSE_CTX_ID, "code", "code"))

    parse_ctx = _find_node(dsl, PARSE_CTX_ID)
    parse_ctx["data"]["variables"] = [
        {"variable": "ctx_json", "value_selector": [C_SCHED_ID, "ctx_json"]},
    ]

    # environment variables: drop WEBHOOK_TOKEN, add LETTERS / FORCE_ACTION
    envs = dsl["workflow"].setdefault("environment_variables", [])
    envs[:] = [item for item in envs
               if item.get("name") not in ("WEBHOOK_TOKEN", "LETTERS")]
    envs.append(env_var("LETTERS", "string", "sabc"))
    envs.append(env_var("FORCE_ACTION", "string", ""))
    defaults = {
        "FORCE_ACTION": "auto",
        "LETTERS": "sabc",
        "DRY_RUN": "true",
        "SCHOOL_DOMAINS": "ust.hk",
        "LANGUAGE": "zh",
        "TENANT": "common",
        "EMAIL": "CHANGE_ME@connect.ust.hk",
        "RECIPIENT": "CHANGE_ME@connect.ust.hk",
        "DORM_KEYWORDS": "UG Hall, UGHall, UGHousing, Hall, 宿舍, 宿生, Student Housing, Residence, Dorm",
    }
    for item in envs:
        if item.get("name") in defaults:
            item["value"] = defaults[item["name"]]

    # the only trigger runs every 5 minutes
    for node in dsl["workflow"]["graph"]["nodes"]:
        if node["data"]["type"] == "trigger-schedule":
            node["data"]["title"] = "Every 5 minutes"
            node["data"]["cron_expression"] = "*/5 * * * *"

    _fix_end_nodes(dsl)
    dsl["app"]["name"] = "HKUST_AI_email_manager"
    dsl["app"]["description"] = (
        "Automatic HKUST mailbox assistant: device-code sign-in, S/A/B/C "
        "classification, category write-back, daily/weekly HTML reports and a "
        "manual sum report, all in one Dify workflow."
    )
    return dsl


def main():
    os.makedirs(OUT, exist_ok=True)
    final = _finalize(build_main())
    path = os.path.join(OUT, "HKUST_AI_email_manager.yml")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(final, fh, allow_unicode=True, sort_keys=False, width=1000)
    with open(path, "r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    assert loaded["kind"] == "app"
    print("wrote", path, "nodes=%d edges=%d" % (
        len(loaded["workflow"]["graph"]["nodes"]),
        len(loaded["workflow"]["graph"]["edges"])))

    # Keep exactly one workflow version on disk.
    keep = os.path.basename(path)
    for name in os.listdir(OUT):
        full = os.path.join(OUT, name)
        if name == keep:
            continue
        if os.path.isdir(full):
            shutil.rmtree(full)
            print("removed", full)
        elif name.endswith((".yml", ".yaml")):
            os.remove(full)
            print("removed legacy", full)


if __name__ == "__main__":
    main()
