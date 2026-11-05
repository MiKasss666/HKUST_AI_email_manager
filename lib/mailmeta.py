"""Mail domain conventions, ported from Email Manager v3.0.0 core/mailmeta.py.

Pure functions only: no network, no Dify SDK, no third-party imports.
This is the single source of truth for:
  - level names and our own category names
  - the merge rule that preserves the user's own categories
  - report-subject / sum-command recognition
  - model-output normalisation (level / school / deadline / urgent)
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, List, Optional, Sequence

LEVELS = ("S", "A", "B", "C")
SUM_NAME = "Sum"
LEGACY_CATEGORY_NAMES = ("S 紧急", "A 重要", "B 普通", "C 可忽略")
OUR_CATEGORY_NAMES = frozenset(list(LEVELS) + [SUM_NAME] + list(LEGACY_CATEGORY_NAMES))

REPORT_SUBJECT_MARK = "邮件总结"
REPORT_SUBJECT_MARK_EN = "Email summary"
REPORT_SUBJECT_MARKS = (REPORT_SUBJECT_MARK, REPORT_SUBJECT_MARK_EN)

SUM_COMMAND_RE = re.compile(r"^sum(?:\s+([sabc]+))?$", re.IGNORECASE)

# Graph flag.flagStatus values used by this program.
FLAG_NONE = 0
FLAG_MARKED = 2

# Deadline / urgent calculation uses Hong Kong time explicitly. Dify's code
# sandbox timezone is not guaranteed to be Asia/Hong_Kong.
HK_TZ = timezone(timedelta(hours=8))


class MailboxUnavailable(RuntimeError):
    """The mailbox is temporarily unavailable (network / 429 / 5xx / login service).

    The workflow must not advance its baseline for this; it retries next round.
    """


# ── inbox conventions ────────────────────────────────────────────────
def parse_sum_command(subject: str) -> Optional[str]:
    """Return normalised letters ('sa') when the subject is a sum command, else None."""
    match = SUM_COMMAND_RE.match((subject or "").strip())
    if not match:
        return None
    letters = (match.group(1) or "sabc").lower()
    return "".join(char for char in "sabc" if char in letters)


def is_report_subject(subject: str) -> bool:
    text = subject or ""
    return any(mark in text for mark in REPORT_SUBJECT_MARKS)


def category_names(existing: Iterable[str] | str | None) -> List[str]:
    """Normalise a Graph categories value into a clean list."""
    if existing is None:
        return []
    if isinstance(existing, str):
        items = existing.split(",")
    else:
        items = list(existing)
    return [str(name).strip() for name in items if str(name).strip()]


def has_our_category(names: Sequence[str]) -> bool:
    return any(name in LEVELS or name == SUM_NAME for name in names)


def merge_categories(existing: Sequence[str], names: Sequence[str]) -> List[str]:
    """Keep every category the user (or server rules) added; replace only ours."""
    kept = [
        str(name).strip()
        for name in existing
        if str(name).strip() and str(name).strip() not in OUR_CATEGORY_NAMES
    ]
    return kept + [str(name) for name in names]


# ── HTML / text ──────────────────────────────────────────────────────
def strip_html(html: str) -> str:
    """Port of graph._strip_html: Graph HTML body -> readable plain text."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|li|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    for entity, char in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
    ):
        text = text.replace(entity, char)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def body_head_tail(body: str, head_chars: int = 400, tail_chars: int = 300) -> str:
    """Exactly the text that goes to the model: head plus a non-overlapping tail."""
    body = (body or "").strip()
    if not body:
        return ""
    head = body[:head_chars]
    if len(body) <= head_chars:
        return head
    if len(body) <= head_chars + tail_chars:
        tail = body[head_chars:]
    else:
        tail = body[-tail_chars:]
    return head + "\n[tail] " + tail


# ── model output normalisation ───────────────────────────────────────
_LEVEL_KEYS = ("级别", "level")
_DEADLINE_KEYS = ("截止日期", "deadline", "due")
_SCHOOL_KEYS = ("学校", "school", "is_school", "属于学校")
_ITEM_KEYS = ("items", "results", "data", "mails", "邮件", "结果")

_SCHOOL_TRUE = {"true", "1", "yes", "y", "是", "对", "学校", "school"}
_SCHOOL_FALSE = {"false", "0", "no", "n", "否", "不是", "非学校", "not_school"}
_SCHOOL_FALSE_PREFIXES = ("不是", "不属于", "不算", "否", "非学校", "not", "no")
_SCHOOL_TRUE_PREFIXES = ("是", "属于", "算", "yes")


def normalize_level(value: Any) -> str:
    level = str(value or "").strip().upper()[:1]
    return level if level in LEVELS else "C"


def parse_school(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in _SCHOOL_TRUE:
        return True
    if text in _SCHOOL_FALSE:
        return False
    if text.startswith(_SCHOOL_FALSE_PREFIXES):
        return False
    if text.startswith(_SCHOOL_TRUE_PREFIXES):
        return True
    return None


def parse_deadline(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def today_hk() -> date:
    return datetime.now(HK_TZ).date()


def is_urgent(level: str, deadline: Optional[date], urgent_days: int,
              today: Optional[date] = None) -> bool:
    if level != "S" or deadline is None:
        return False
    current = today or today_hk()
    return 0 <= (deadline - current).days <= urgent_days


def _pick(raw: dict, keys: Sequence[str]) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def as_item_list(payload: Any) -> Optional[list]:
    """Accept a bare list, or a dict wrapping the list under a known/only key."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in _ITEM_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    lists = [v for v in payload.values() if isinstance(v, list)]
    return lists[0] if len(lists) == 1 else None


def verdicts_from_payload(payload: Any, expected_entryids: Sequence[str],
                          urgent_days: int,
                          today: Optional[date] = None) -> Optional[List[dict]]:
    """Parse a model JSON payload into verdicts keyed by entryid.

    Returns None when the count or ids do not match exactly: the whole batch is
    then treated as failed, so a missing item can never shift levels onto other
    mails. Items may carry "entryid" (preferred) or "index" (1-based).
    """
    items = as_item_list(payload)
    if items is None or len(items) != len(expected_entryids):
        return None

    expected = [str(e) for e in expected_entryids]
    by_id: dict[str, dict] = {}
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            return None
        entryid = str(item.get("entryid") or item.get("id") or "").strip()
        if not entryid:
            index = item.get("index")
            if isinstance(index, int) and 1 <= index <= len(expected):
                entryid = expected[index - 1]
        if entryid not in expected or entryid in by_id:
            return None
        level = normalize_level(_pick(item, _LEVEL_KEYS))
        deadline = parse_deadline(_pick(item, _DEADLINE_KEYS))
        school = parse_school(_pick(item, _SCHOOL_KEYS))
        by_id[entryid] = {
            "entryid": entryid,
            "level": level,
            "deadline": deadline.isoformat() if deadline else "",
            "urgent": is_urgent(level, deadline, urgent_days, today),
            "is_school": True if school is None else school,
        }
    if set(by_id) != set(expected):
        return None
    return [by_id[e] for e in expected]


# ── deterministic overrides (only ever raise the level) ─────────────
def enrolled_regex(courses: Sequence[str]):
    courses = [c for c in courses if c]
    if not courses:
        return None
    pattern = "|".join(re.escape(c) for c in courses)
    return re.compile(r"(?<![A-Za-z0-9])(" + pattern + r")(?![A-Za-z0-9])", re.IGNORECASE)


def apply_enrolled_override(candidates: Sequence[dict], verdicts: Sequence[dict],
                            courses: Sequence[str]) -> int:
    rx = enrolled_regex(courses)
    if rx is None:
        return 0
    changed = 0
    for mail, verdict in zip(candidates, verdicts):
        haystack = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
        if rx.search(haystack) and LEVELS.index(verdict["level"]) > LEVELS.index("A"):
            verdict["level"] = "A"
            verdict["urgent"] = False
            changed += 1
    return changed


def apply_faculty_override(candidates: Sequence[dict], verdicts: Sequence[dict],
                           terms: Sequence[str]) -> int:
    lowered = [str(t).lower() for t in terms if str(t).strip()]
    if not lowered:
        return 0
    changed = 0
    for mail, verdict in zip(candidates, verdicts):
        if not verdict["is_school"]:
            continue
        if LEVELS.index(verdict["level"]) <= LEVELS.index("A"):
            continue
        haystack = "\n".join(
            str(mail.get(key) or "") for key in ("sender_name", "sender", "subject", "body")
        ).lower()
        if any(term in haystack for term in lowered):
            verdict["level"] = "A"
            verdict["urgent"] = False
            changed += 1
    return changed


def apply_school_override(candidates: Sequence[dict], verdicts: Sequence[dict],
                          school_domains: Sequence[str]) -> int:
    def is_school_address(address: str) -> bool:
        text = str(address or "").strip().lower()
        if "@" not in text:
            return False
        domain = text.rsplit("@", 1)[1].strip().strip(">").strip().rstrip(".")
        if not domain:
            return False
        for suffix in school_domains:
            s = str(suffix).strip().lower().lstrip("@").strip(".")
            if s and (domain == s or domain.endswith("." + s)):
                return True
        return False

    changed = 0
    for mail, verdict in zip(candidates, verdicts):
        if not verdict["is_school"] and is_school_address(mail.get("sender")):
            verdict["is_school"] = True
            changed += 1
    return changed
