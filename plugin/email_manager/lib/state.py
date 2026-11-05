"""Persistent runtime state for the Email Manager plugin.

Stored in the Dify plugin storage (workspace scoped). The state is what makes a
stateless workflow behave like the original desktop watcher:

  last_seen        newest message already dealt with (baseline)
  failed_rounds    consecutive rounds that ended with write failures
  ignored          entry ids judged "not school mail" (never labelled, so they
                   must be remembered to avoid asking the AI again)
  lock_owner/until single-flight lock between overlapping workflow runs
  paused           set after repeated real errors; cleared manually
  last_catchup_date / last_report_at / auth_prompted_at

Pure helpers (``advance`` and friends) take a plain dict so they can be tested
without Dify.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

STATE_KEY = "email_manager_state"
STATE_VERSION = 1
MAX_FAILED_ROUNDS = 3
IGNORED_LIMIT = 1000


def default_state() -> Dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "last_seen": "",
        "failed_rounds": 0,
        "ignored": [],
        "lock_owner": "",
        "lock_until": 0.0,
        "paused": False,
        "last_catchup_date": "",
        "last_report_at": "",
        "auth_prompted_at": "",
        "last_error": "",
        "updated_at": 0.0,
    }


def _merge_defaults(raw: Any) -> Dict[str, Any]:
    state = default_state()
    if isinstance(raw, dict):
        for key, value in state.items():
            if key in raw and isinstance(raw[key], type(value)):
                state[key] = raw[key]
            elif key in raw and value is None:
                state[key] = raw[key]
    return state


def load(storage) -> Dict[str, Any]:
    try:
        blob = storage.get(STATE_KEY)
        if not blob:
            return default_state()
        return _merge_defaults(json.loads(blob.decode("utf-8")))
    except Exception:
        return default_state()


def save(storage, state: Dict[str, Any]) -> None:
    state["version"] = int(state.get("version") or 0) + 1
    state["updated_at"] = time.time()
    storage.set(STATE_KEY, json.dumps(state, ensure_ascii=False).encode("utf-8"))


# ── lock (best-effort single flight; storage has no CAS primitive) ─────
def acquire_lock(storage, owner: str, ttl_seconds: int = 300) -> Dict[str, Any]:
    state = load(storage)
    now = time.time()
    holder = state.get("lock_owner") or ""
    until = float(state.get("lock_until") or 0)
    if until > now and holder and holder != owner:
        return {"acquired": False, "holder": holder, "lock_until": until}
    state["lock_owner"] = owner
    state["lock_until"] = now + max(30, int(ttl_seconds or 300))
    save(storage, state)
    return {"acquired": True, "holder": owner, "lock_until": state["lock_until"]}


def release_lock(storage, owner: str) -> bool:
    state = load(storage)
    if owner and state.get("lock_owner") == owner:
        state["lock_owner"] = ""
        state["lock_until"] = 0
        save(storage, state)
        return True
    if not state.get("lock_owner"):
        state["lock_until"] = 0
        save(storage, state)
        return True
    return False


# ── baseline advance (port of watcher.advance_policy) ────────────────
def advance(
    state: Dict[str, Any],
    pending_ids: List[str],
    newest_id: str,
    failed: int,
    max_failed_rounds: int = MAX_FAILED_ROUNDS,
    catchup: bool = False,
) -> Tuple[Dict[str, Any], bool]:
    """Return (new_state, gave_up). Caller persists it.

    - no pending work: baseline moves to newest_id (control-only round);
    - all succeeded: baseline moves to the oldest processed message;
    - failures and the limit is not reached yet: baseline does NOT move so the
      next round retries exactly the failed ones;
    - failures reached the limit: give up, move the baseline and report.

    A catch-up round must never move the baseline: it intentionally scans behind
    it (unclassified older mail), and moving it to the oldest caught-up message
    would rewind the normal watcher. Only ``last_catchup_date`` changes.
    """
    pending = [str(i) for i in pending_ids if i]
    gave_up = False

    if catchup:
        if failed >= max_failed_rounds:
            gave_up = True
        if not failed:
            state["failed_rounds"] = 0
        return state, gave_up

    if not pending:
        if newest_id:
            state["last_seen"] = str(newest_id)
        state["failed_rounds"] = 0
        return state, gave_up

    oldest = pending[-1]
    if failed:
        rounds = int(state.get("failed_rounds") or 0) + 1
        if rounds < max_failed_rounds:
            state["failed_rounds"] = rounds
            return state, gave_up
        state["last_seen"] = oldest
        state["failed_rounds"] = 0
        gave_up = True
        return state, gave_up

    state["last_seen"] = oldest
    state["failed_rounds"] = 0
    return state, gave_up


def remember_ignored(state: Dict[str, Any], entry_ids: Iterable[str],
                     limit: int = IGNORED_LIMIT) -> List[str]:
    known = set(state.get("ignored") or [])
    fresh: List[str] = []
    for entry_id in entry_ids:
        text = str(entry_id or "")
        if text and text not in known:
            known.add(text)
            fresh.append(text)
    if fresh:
        state["ignored"] = (fresh + list(state.get("ignored") or []))[:limit]
    return fresh


def set_paused(storage, paused: bool, reason: str = "") -> Dict[str, Any]:
    state = load(storage)
    state["paused"] = bool(paused)
    state["last_error"] = str(reason or "")
    if not paused:
        state["failed_rounds"] = 0
    save(storage, state)
    return state


def mark_catchup(state: Dict[str, Any], day: str) -> None:
    state["last_catchup_date"] = str(day or "")


def mark_report(state: Dict[str, Any], at: str) -> None:
    state["last_report_at"] = str(at or "")


def mark_auth_prompt(state: Dict[str, Any], at: str) -> None:
    state["auth_prompted_at"] = str(at or "")


def public_view(state: Dict[str, Any]) -> Dict[str, Any]:
    """State as exposed to the workflow.

    The full ``ignored`` id list is deliberately not returned: the plugin already
    filters on it, and serialising up to 1000 long Graph ids could push the
    workflow variable towards Dify's 200 KB per-variable limit.
    """
    view = {key: value for key, value in state.items() if key != "ignored"}
    view["ignored_count"] = len(state.get("ignored") or [])
    return view
