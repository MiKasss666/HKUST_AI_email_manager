"""Generate tool .yaml and .py files for the Email Manager Dify plugin.

Run from the repository root:

    py -3 scripts/gen_tools.py
"""

from __future__ import annotations

import json
import os
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(ROOT, "plugin", "email_manager", "tools")
AUTHOR = "mikasss666"


def pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_")) + "Tool"


SPECS = []


def tool(name, display, zh, llm, params, outputs, body, imports=""):
    SPECS.append(dict(name=name, display=display, zh=zh, llm=llm,
                      params=params, outputs=outputs, body=body, imports=imports))


def p(name, ptype, required, default, en, zh, llm):
    return dict(name=name, ptype=ptype, required=required, default=default,
                en=en, zh=zh, llm=llm)


def o(name, otype, desc):
    return dict(name=name, otype=otype, desc=desc)


# ── authentication ───────────────────────────────────────────────────
tool(
    "auth_status", "Auth Status", "登录状态",
    "Check whether the plugin is signed in to Microsoft Graph and when the token expires.",
    [],
    [o("success", "boolean", "True when the tool finished"),
     o("signed_in", "boolean", "True when a credential is stored"),
     o("account", "string", "Signed-in Microsoft account"),
     o("token_expires_in", "number", "Seconds until the access token expires (0 when unknown)"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    token = graph.load_token(tool.session.storage)
    known = graph.signed_in(tool.session.storage)
    expires = 0
    if token.get("expires_at"):
        expires = int(max(0, float(token.get("expires_at")) - time.time()))
    return {
        "signed_in": bool(known),
        "account": str(token.get("account") or ""),
        "token_expires_in": expires,
    }
    """,
    "import time",
)

tool(
    "auth_start", "Start Device Sign-in", "开始设备码登录",
    "Start Microsoft device-code sign-in and return the code and verification link for the user.",
    [p("tenant", "string", False, "", "Tenant", "租户",
       "Microsoft tenant: common (default), organizations, or a tenant id/domain"),
     p("client_id", "string", False, "", "Client ID", "客户端 ID",
       "Optional own Entra public client id; leave empty to use Microsoft's public clients"),
     p("scopes", "string", False, "", "Scopes", "权限范围",
       "Optional scope override; leave empty for Mail.ReadWrite + Mail.Send + offline_access"),
     p("force_new", "boolean", False, False, "Force New Code", "强制新码",
       "Create a brand-new device code instead of reusing the pending one")],
    [o("success", "boolean", "True when the tool finished"),
     o("user_code", "string", "Code to enter on the Microsoft sign-in page"),
     o("verification_uri", "string", "Sign-in URL (may already contain the code)"),
     o("expires_in", "number", "Device code lifetime in seconds"),
     o("client_label", "string", "Which Microsoft public client was used"),
     o("fresh", "boolean", "True when a new code was created, false when an existing pending code is reused"),
     o("message", "string", "Human instructions"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    return graph.device_start(
        tool.session.storage,
        tenant=str(params.get("tenant") or ""),
        client_id=str(params.get("client_id") or ""),
        scopes=str(params.get("scopes") or ""),
        force_new=bool(params.get("force_new")),
    )
    """,
)

tool(
    "auth_poll", "Poll Device Sign-in", "轮询设备码登录",
    "Poll Microsoft once for the pending device-code sign-in result.",
    [],
    [o("success", "boolean", "True when the tool finished"),
     o("signed_in", "boolean", "True when sign-in completed"),
     o("status", "string", "signed_in / pending"),
     o("account", "string", "Signed-in Microsoft account"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    return graph.device_poll(tool.session.storage)
    """,
)

tool(
    "auth_sign_out", "Sign Out", "退出登录",
    "Forget the stored Microsoft credential for this workspace.",
    [],
    [o("success", "boolean", "True when the tool finished"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    graph.sign_out(tool.session.storage)
    return {}
    """,
)

tool(
    "check", "Check", "自检",
    "Read-only self check: credential, Microsoft account, inbox size.",
    [],
    [o("success", "boolean", "True when the tool finished"),
     o("signed_in", "boolean", "True when signed in"),
     o("account", "string", "Signed-in Microsoft account"),
     o("display_name", "string", "Display name"),
     o("inbox_count", "number", "Messages in the inbox"),
     o("token_expires_in", "number", "Seconds until the access token expires"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    return graph.check(tool.session.storage)
    """,
)

# ── mailbox ──────────────────────────────────────────────────────────
tool(
    "collect", "Collect Mail", "采集待处理邮件",
    "Scan the inbox headers, skip already-processed and control mail, download bodies for candidates, "
    "and return the candidates plus pending control mail (sum commands and untagged reports).",
    [p("last_seen", "string", False, "", "Last seen", "上次基线",
       "Override the stored baseline; leave empty to use the plugin state"),
     p("days", "number", False, 7, "Days", "回溯天数",
       "Only scan messages received in the last N days"),
     p("max_items", "number", False, 30, "Max items", "最多候选",
       "Maximum number of candidate mails to return (1-30)"),
     p("catchup", "boolean", False, False, "Catch-up", "补分类模式",
       "When true, ignore the baseline and scan the whole day window for unclassified mail")],
    [o("success", "boolean", "True when the tool finished"),
     o("transient", "boolean", "True for temporary failures (network/429/5xx) - retry next round"),
     o("candidates", "array", "Mails to classify"),
     o("controls_commands", "array", "Unprocessed sum command mails"),
     o("controls_reports", "array", "Own report mails missing the Sum tag"),
     o("newest_id", "string", "Newest inbox message id"),
     o("oldest_id", "string", "Oldest candidate id (baseline target)"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    return graph.collect(
        tool.session.storage,
        last_seen=str(params.get("last_seen") or ""),
        days=int(params.get("days") or 7),
        max_items=int(params.get("max_items") or 30),
        catchup=bool(params.get("catchup")),
    )
    """,
)

tool(
    "collect_recent", "Collect Classified Mail", "取已分级邮件",
    "Read recently classified mails (S/A/B/C categories) with their bodies, for the summary report.",
    [p("days", "number", False, 7, "Days", "回溯天数", "Only scan messages received in the last N days"),
     p("letters", "string", False, "sabc", "Levels", "级别",
       "Levels to include, e.g. s, sa, sabc"),
     p("max_items", "number", False, 100, "Max items", "最多封数", "Maximum number of mails to return")],
    [o("success", "boolean", "True when the tool finished"),
     o("transient", "boolean", "True for temporary failures"),
     o("items", "array", "Classified mails with body"),
     o("count", "number", "Number of items"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    items = graph.collect_recent(
        tool.session.storage,
        days=int(params.get("days") or 7),
        letters=str(params.get("letters") or "sabc"),
        max_items=int(params.get("max_items") or 100),
    )
    return {"items": items, "count": len(items)}
    """,
)

tool(
    "apply", "Apply Verdicts", "写回分级结果",
    "Write classification results back to the mailbox: merge categories (keep the user's own labels), "
    "flag urgent S mail, skip non-school mail and remember its id.",
    [p("verdicts_json", "string", True, "", "Verdicts JSON", "分级结果 JSON",
       "JSON array of {entryid, level, urgent, is_school, categories?}"),
     p("dry_run", "boolean", False, False, "Dry run", "只判定不写回", "When true no mailbox change is made")],
    [o("success", "boolean", "True when the tool finished"),
     o("transient", "boolean", "True for temporary failures"),
     o("ok", "number", "Mails written"),
     o("failed", "number", "Mails that could not be written"),
     o("skipped", "number", "Non-school mails left untouched"),
     o("ignored_ids", "array[string]", "Ids of skipped non-school mails"),
     o("errors", "array", "Per-mail errors"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    verdicts = _load_json_list(params.get("verdicts_json"))
    result = graph.apply_verdicts(tool.session.storage, verdicts,
                                  dry_run=bool(params.get("dry_run")))
    return result
    """,
    "import json",
)

tool(
    "tag", "Tag Messages", "打标签",
    "Add labels (typically Sum) to messages without touching any user-defined category.",
    [p("entryids_json", "string", True, "", "Entry ids JSON", "邮件 ID JSON",
       "JSON array of message ids"),
     p("names_json", "string", False, '["Sum"]', "Label names JSON", "标签名 JSON",
       "JSON array of label names to add")],
    [o("success", "boolean", "True when the tool finished"),
     o("transient", "boolean", "True for temporary failures"),
     o("ok", "number", "Mails tagged"),
     o("failed", "number", "Mails that could not be tagged"),
     o("errors", "array", "Per-mail errors"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    entryids = _load_json_list(params.get("entryids_json"))
    names = _load_json_list(params.get("names_json")) or ["Sum"]
    return graph.tag_messages(tool.session.storage, entryids, names)
    """,
    "import json",
)

tool(
    "send_report", "Send Report", "发送报告",
    "Send an HTML e-mail to the signed-in mailbox (used for the summary report and alert mails).",
    [p("to", "string", True, "", "To", "收件人", "Recipient e-mail address"),
     p("subject", "string", True, "", "Subject", "主题", "Mail subject"),
     p("html", "string", True, "", "HTML", "HTML 正文", "HTML body")],
    [o("success", "boolean", "True when the tool finished"),
     o("transient", "boolean", "True for temporary failures"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    graph.send_mail(tool.session.storage,
                    str(params.get("to") or ""),
                    str(params.get("subject") or ""),
                    str(params.get("html") or ""))
    return {}
    """,
)

# ── state ────────────────────────────────────────────────────────────
tool(
    "state_get", "Get State", "读取状态",
    "Read the persisted watcher state (baseline, failed rounds, ignored ids, lock, pause flag).",
    [],
    [o("success", "boolean", "True when the tool finished"),
     o("state", "object", "Watcher state"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    return {"state": state.public_view(state.load(tool.session.storage))}
    """,
)

tool(
    "state_lock", "Acquire Lock", "获取运行锁",
    "Best-effort single-flight lock so two overlapping workflow runs do not process the same mails.",
    [p("owner", "string", True, "", "Owner", "持有者", "Usually the workflow run id"),
     p("ttl_seconds", "number", False, 300, "TTL", "锁时长（秒）", "Lock lifetime in seconds")],
    [o("success", "boolean", "True when the tool finished"),
     o("acquired", "boolean", "True when the lock was acquired"),
     o("holder", "string", "Current lock holder"),
     o("lock_until", "number", "Unix timestamp when the lock expires"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    return state.acquire_lock(tool.session.storage,
                              str(params.get("owner") or ""),
                              int(params.get("ttl_seconds") or 300))
    """,
)

tool(
    "state_unlock", "Release Lock", "释放运行锁",
    "Release the workflow run lock.",
    [p("owner", "string", True, "", "Owner", "持有者", "The same value used when acquiring")],
    [o("success", "boolean", "True when the tool finished"),
     o("released", "boolean", "True when the lock is now free"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    return {"released": state.release_lock(tool.session.storage,
                                           str(params.get("owner") or ""))}
    """,
)

tool(
    "state_advance", "Advance Baseline", "推进基线",
    "Persist the round result: advance the baseline only when the round really completed, "
    "remember ignored ids, reset or increment failed rounds and record the catch-up date.",
    [p("pending_ids_json", "string", False, "[]", "Pending ids JSON", "本轮处理 ID JSON",
       "JSON array of ids processed this round, newest first"),
     p("newest_id", "string", False, "", "Newest id", "最新邮件 ID",
       "Newest inbox message id this round (used when no candidates)"),
     p("failed", "number", False, 0, "Failed", "失败封数", "Number of mails that failed this round"),
     p("ignored_ids_json", "string", False, "[]", "Ignored ids JSON", "非学校邮件 ID JSON",
       "JSON array of non-school ids to remember"),
     p("catchup", "boolean", False, False, "Catch-up round", "补分类轮次",
       "When true, the baseline is not modified (catch-up scans older mail)"),
     p("catchup_date", "string", False, "", "Catch-up date", "补分类日期",
       "When set (YYYY-MM-DD), records that the daily catch-up ran")],
    [o("success", "boolean", "True when the tool finished"),
     o("last_seen", "string", "New baseline"),
     o("failed_rounds", "number", "Consecutive failed rounds"),
     o("gave_up", "boolean", "True when the failure limit was reached and the baseline advanced"),
     o("ignored_added", "number", "Newly remembered non-school ids"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    pending_ids = _load_json_list(params.get("pending_ids_json"))
    ignored_ids = _load_json_list(params.get("ignored_ids_json"))
    st = state.load(tool.session.storage)
    added = state.remember_ignored(st, ignored_ids)
    st, gave_up = state.advance(st, pending_ids, str(params.get("newest_id") or ""),
                                int(params.get("failed") or 0),
                                catchup=bool(params.get("catchup")))
    catchup_date = str(params.get("catchup_date") or "").strip()
    if catchup_date:
        state.mark_catchup(st, catchup_date)
    state.save(tool.session.storage, st)
    return {"last_seen": st.get("last_seen", ""),
            "failed_rounds": int(st.get("failed_rounds") or 0),
            "gave_up": bool(gave_up),
            "ignored_added": len(added)}
    """,
    "import json",
)

tool(
    "state_set", "Set State", "设置状态",
    "Pause/resume the automatic processing, clear the failure counter or remember when the login prompt was sent.",
    [p("update_paused", "boolean", False, False, "Update pause flag", "更新暂停标志",
       "When true, the paused flag is written; when false the current flag is kept"),
     p("paused", "boolean", False, False, "Paused", "暂停", "Target pause value (only when update_paused is true)"),
     p("reason", "string", False, "", "Reason", "原因", "Short reason stored for diagnostics"),
     p("clear_failed", "boolean", False, False, "Clear failed rounds", "清零失败轮次",
       "When true, resets the consecutive failure counter"),
     p("reset_baseline", "boolean", False, False, "Reset baseline", "重置基线",
       "When true, clears last_seen so recent mail is processed again (test/reset)"),
     p("clear_ignored", "boolean", False, False, "Clear ignored", "清空忽略列表",
       "When true, clears the remembered ignored (non-school) message ids"),
     p("mark_daily_report", "boolean", False, False, "Mark daily report", "记录日报时间",
       "When true, stores today's date so the midnight daily report is not sent twice"),
     p("mark_weekly_report", "boolean", False, False, "Mark weekly report", "记录周报时间",
       "When true, stores today's date so the Sunday weekly report is not sent twice"),
     p("mark_auth_prompted", "boolean", False, False, "Mark login prompt", "记录登录提示时间",
       "When true, stores the current time as the last device-code prompt (anti-spam)")],
    [o("success", "boolean", "True when the tool finished"),
     o("paused", "boolean", "Current pause flag"),
     o("last_seen", "string", "Current baseline message id (empty after a reset)"),
     o("error", "string", "Why the tool stopped, empty on success")],
    """
    st = state.load(tool.session.storage)
    if bool(params.get("update_paused")):
        st = state.set_paused(tool.session.storage,
                              bool(params.get("paused")),
                              str(params.get("reason") or ""))
    if bool(params.get("clear_failed")):
        st["failed_rounds"] = 0
        state.save(tool.session.storage, st)
    if bool(params.get("reset_baseline")):
        st["last_seen"] = ""
        st["failed_rounds"] = 0
        st["last_catchup_date"] = ""
        st["daily_report_date"] = ""
        st["weekly_report_date"] = ""
        state.save(tool.session.storage, st)
    if bool(params.get("clear_ignored")):
        st["ignored"] = []
        state.save(tool.session.storage, st)
    if bool(params.get("mark_daily_report")):
        st["daily_report_date"] = today
        state.save(tool.session.storage, st)
    if bool(params.get("mark_weekly_report")):
        st["weekly_report_date"] = today
        state.save(tool.session.storage, st)
    if bool(params.get("mark_auth_prompted")):
        state.mark_auth_prompt(st, datetime.now().isoformat(timespec="seconds"))
        state.save(tool.session.storage, st)
    return {"paused": bool(st.get("paused")), "last_seen": str(st.get("last_seen") or "")}
    """,
    "from datetime import datetime, timedelta, timezone\ntoday = datetime.now(timezone(timedelta(hours=8))).date().isoformat()",
)


# ── code generation ──────────────────────────────────────────────────
HEADER = '''"""Auto-generated by scripts/gen_tools.py - do not edit by hand."""
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from lib import graph, state
from lib.outputs import run_tool
{imports}

DECLARED = {declared}


class {cls}(Tool):
    def _invoke(self, tool_parameters: dict) -> ToolInvokeMessage:
        yield from run_tool(self, DECLARED, lambda: _run(self, tool_parameters))


def _load_json_list(value):
    import json
    if isinstance(value, list):
        return value
    text = str(value or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _run(tool, params):
{body}
'''

PARAM_TMPL = """  - name: {name}
    type: {ptype}
    required: {required}
{default}    label:
      en_US: {en}
      zh_Hans: {zh}
    human_description:
      en_US: {en}
      zh_Hans: {zh}
    llm_description: {llm}
    form: llm
"""
OUT_TMPL = """    {name}:
      type: {otype}
      description: {desc}
"""


def q(value) -> str:
    """JSON-quote a scalar so it is always valid YAML (colons, quotes, etc.)."""
    return json.dumps(str(value), ensure_ascii=False)


def yaml_default(param):
    if param["default"] is None or param["default"] == "":
        return ""
    if isinstance(param["default"], bool):
        return "    default: %s\n" % ("true" if param["default"] else "false")
    if isinstance(param["default"], (int, float)):
        return "    default: %s\n" % param["default"]
    return "    default: %s\n" % q(param["default"])


def declared_map(spec):
    lines = []
    for item in spec["outputs"]:
        name, otype = item["name"], item["otype"]
        if otype == "boolean":
            default = "False"
        elif otype == "number":
            default = "0"
        elif otype in ("string",):
            default = '""'
        else:
            default = "[]"
        lines.append('    "%s": %s,' % (name, default))
    return "{\n" + "\n".join(lines) + "\n}"


def main():
    os.makedirs(TOOLS_DIR, exist_ok=True)
    for spec in SPECS:
        params_yaml = ""
        for param in spec["params"]:
            params_yaml += PARAM_TMPL.format(
                name=param["name"], ptype=param["ptype"],
                required="true" if param["required"] else "false",
                default=yaml_default(param), en=q(param["en"]), zh=q(param["zh"]),
                llm=q(param["llm"].replace("\n", " ")),
            )
        outs_yaml = "".join(
            OUT_TMPL.format(name=item["name"], otype=item["otype"], desc=q(item["desc"]))
            for item in spec["outputs"]
        )
        yaml_text = f"""identity:
  name: {spec['name']}
  display_name: {q(spec['display'])}
  author: {AUTHOR}
  label:
    en_US: {q(spec['display'])}
    zh_Hans: {q(spec['zh'])}
description:
  human:
    en_US: {q(spec['llm'])}
    zh_Hans: {q(spec['llm'])}
  llm: {q(spec['llm'])}
parameters:
{params_yaml}output_schema:
  type: object
  properties:
{outs_yaml}extra:
  python:
    source: tools/{spec['name']}.py
"""
        with open(os.path.join(TOOLS_DIR, spec["name"] + ".yaml"), "w", encoding="utf-8") as fh:
            fh.write(yaml_text)

        body = textwrap.dedent(spec["body"]).strip("\n")
        body = "\n".join("    " + line if line.strip() else line for line in body.splitlines())
        py_text = HEADER.format(
            imports=spec["imports"],
            declared=declared_map(spec),
            cls=pascal(spec["name"]),
            body=body,
        )
        with open(os.path.join(TOOLS_DIR, spec["name"] + ".py"), "w", encoding="utf-8") as fh:
            fh.write(py_text)
        print("generated", spec["name"])


if __name__ == "__main__":
    main()
