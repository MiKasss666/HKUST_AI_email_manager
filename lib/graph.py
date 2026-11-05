"""Microsoft Graph plumbing for the Email Manager Dify plugin.

Ported from Email Manager v3.0.0 ``core/graph.py`` with two additions the Dify
environment needs:

* **device-code login lives here** (the original app's device-code flow), with
  the same fallback strategy: a configurable public client id first, then the
  well-known Microsoft public clients. No client secret, no redirect URI and no
  admin consent are involved.
* tokens are persisted in Dify's plugin storage (workspace scoped) instead of a
  local JSON file.

Everything else follows the original semantics:
  - poll headers only; download a body only for mails that are really processed;
  - 429/5xx on GET are retried honouring ``Retry-After``; writes are never retried;
  - ``write_categories`` only replaces this program's own labels;
  - a temporary mailbox problem raises ``MailboxUnavailable`` so the workflow
    can skip the round without advancing its baseline.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import mailmeta
from . import state as state_mod

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
TIMEOUT = 30

TOKEN_MARGIN = 300

# Well-known Microsoft public clients. Used only when the user did not provide
# their own client id; the plugin never ships a client secret.
FALLBACK_CLIENTS: Tuple[Tuple[str, str], ...] = (
    ("14d82eec-204b-4c2f-b7e8-296a70dab67e", "Microsoft Graph Command Line Tools"),
    ("04b07795-8ddb-461a-bbee-02f9e1bf7b46", "Azure CLI"),
    ("1950a258-227b-4e31-a9cf-717495945fc2", "Azure PowerShell"),
)

DEFAULT_SCOPES = "offline_access openid profile User.Read https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send"
PROBE_SCOPES = "offline_access openid profile User.Read https://graph.microsoft.com/Mail.Read"

REQUESTED_SCOPES = DEFAULT_SCOPES
TOKEN_KEY = "email_manager_token"
DEVICE_KEY = "email_manager_device"

SELECT_HEADERS = (
    "id,subject,from,sender,receivedDateTime,categories,isRead,hasAttachments,"
    "bodyPreview,conversationId,webLink"
)
SELECT_BODY = "body,bodyPreview"

RECENT_MAX = 100
BODY_HEAD = 400
BODY_TAIL = 300
RECENT_BODY_CHARS = 900

RETRY_STATUS = (429, 500, 502, 503, 504)
MAX_ATTEMPTS = 3

WRITE_SCOPE_MARK = "Mail.ReadWrite"


class GraphError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status

    @property
    def transient(self) -> bool:
        return self.status == 0 or self.status in RETRY_STATUS or self.status >= 500


class AuthRequired(RuntimeError):
    """No usable credential: the user has to run a device-code sign-in again."""


# ── storage helpers ──────────────────────────────────────────────────
def _get_json(storage, key: str) -> Dict[str, Any]:
    try:
        blob = storage.get(key)
        if not blob:
            return {}
        data = json.loads(blob.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_json(storage, key: str, data: Dict[str, Any]) -> None:
    storage.set(key, json.dumps(data, ensure_ascii=False).encode("utf-8"))


def _del(storage, key: str) -> None:
    try:
        storage.delete(key)
    except Exception:
        pass


# ── HTTP ─────────────────────────────────────────────────────────────
def _decode(raw: bytes) -> Any:
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except Exception:
        return {"raw": text[:600]}


def _http(method: str, url: str, *, data: Optional[bytes] = None,
          headers: Optional[Dict[str, str]] = None) -> Tuple[int, Any, Dict[str, str]]:
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, _decode(response.read()), dict(response.headers)
    except urllib.error.HTTPError as ex:
        try:
            payload = _decode(ex.read())
        except Exception:
            payload = {"raw": ""}
        return ex.code, payload, dict(ex.headers or {})
    except Exception as ex:  # DNS / TLS / connection reset
        return 0, {"raw": f"{type(ex).__name__}: {ex}"}, {}


def _post_form(url: str, fields: Dict[str, str]) -> Tuple[int, Any, Dict[str, str]]:
    body = urllib.parse.urlencode(fields).encode()
    return _http("POST", url, data=body,
                 headers={"Content-Type": "application/x-www-form-urlencoded"})


def _explain(status: int, payload: Any) -> str:
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return f"HTTP {status} {err.get('code') or ''}: {str(err.get('message') or '')[:400]}"
        if payload.get("error_description"):
            return f"HTTP {status}: {str(payload['error_description'])[:400]}"
        if payload.get("raw"):
            return f"HTTP {status}: {payload['raw']}"[:400]
    return f"HTTP {status}: {str(payload)[:300]}"


def _retry_delay(status: int, headers: Dict[str, str], attempt: int) -> float:
    value = (headers or {}).get("Retry-After") or (headers or {}).get("retry-after") or ""
    text = str(value).strip()
    try:
        seconds = float(text)
        if 0 <= seconds <= 120:
            return seconds
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(text)
        if when is not None:
            seconds = (when - datetime.now(timezone.utc)).total_seconds()
            if 0 <= seconds <= 120:
                return float(seconds)
    except (TypeError, ValueError):
        pass
    return float(min(30, 2 ** attempt))


def graph_call(token: str, method: str, path_or_url: str, *,
               body: Optional[dict] = None) -> Any:
    """Call Graph; GET retries on 429/5xx, writes never retry."""
    url = path_or_url if path_or_url.startswith("http") else GRAPH + path_or_url
    headers = {
        "Authorization": "Bearer " + token,
        "Prefer": 'IdType="ImmutableId"',
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    attempts = MAX_ATTEMPTS if method.upper() == "GET" else 1
    last_status, last_payload = 0, None
    for attempt in range(attempts):
        status, payload, response_headers = _http(method, url, data=data, headers=headers)
        if 200 <= status < 300:
            return payload
        last_status, last_payload = status, payload
        retryable = status == 0 or status in RETRY_STATUS
        if not retryable or attempt == attempts - 1:
            break
        time.sleep(_retry_delay(status, response_headers, attempt))
    raise GraphError(_explain(last_status, last_payload), last_status)


# ── device-code authentication ───────────────────────────────────────
def _token_url(tenant: str) -> str:
    return LOGIN.format(tenant=(tenant or "common").strip() or "common") + "/token"


def _device_url(tenant: str) -> str:
    return LOGIN.format(tenant=(tenant or "common").strip() or "common") + "/devicecode"


def _sign_in_url(device: Dict[str, Any], code: str) -> Tuple[str, bool]:
    base = device.get("verification_uri") or "https://login.microsoft.com/device"
    complete = device.get("verification_uri_complete")
    if complete:
        return str(complete), True
    if not code:
        return base, False
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}user_code={urllib.parse.quote(code)}", True


def load_token(storage) -> Dict[str, Any]:
    return _get_json(storage, TOKEN_KEY)


def signed_in(storage) -> bool:
    token = load_token(storage)
    return bool(token.get("refresh_token") or token.get("access_token"))


def account(storage) -> str:
    return str(load_token(storage).get("account") or "")


def _save_token(storage, payload: Dict[str, Any], client_id: str, scopes: str,
                previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    previous = previous or {}
    try:
        expires_in = int(payload.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600
    token = {
        "access_token": payload.get("access_token"),
        "refresh_token": payload.get("refresh_token") or previous.get("refresh_token"),
        "client_id": client_id or previous.get("client_id"),
        "scopes": scopes or previous.get("scopes") or DEFAULT_SCOPES,
        "expires_at": time.time() + max(60, expires_in),
        "account": previous.get("account") or "",
        "tenant": previous.get("tenant") or "",
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    _set_json(storage, TOKEN_KEY, token)
    return token


def pending_device(storage, now: Optional[float] = None) -> Dict[str, Any]:
    """Return the stored device-code request if it is still usable, else {}."""
    pending = _get_json(storage, DEVICE_KEY)
    if not pending.get("device_code"):
        return {}
    if float(pending.get("expires_at") or 0) <= (now if now is not None else time.time()):
        return {}
    return pending


def device_start(storage, tenant: str = "", client_id: str = "",
                 scopes: str = "", force_new: bool = False) -> Dict[str, Any]:
    """Ask Microsoft for a device code (or reuse the still-valid pending one).

    Returns user_code / link / expiry / fresh. ``fresh`` is False when an
    existing code is reused, which lets the workflow avoid sending the same
    login e-mail on every polling round. ``force_new=True`` discards a pending
    code first (used by manual login so a consumed code is never shown again).
    """
    if force_new:
        _del(storage, DEVICE_KEY)
        pending: Dict[str, Any] = {}
    else:
        pending = pending_device(storage)
    if pending:
        remaining = int(max(0, float(pending.get("expires_at") or 0) - time.time()))
        return {
            "user_code": str(pending.get("user_code") or ""),
            "verification_uri": str(pending.get("verification_uri") or ""),
            "expires_in": remaining,
            "client_label": str(pending.get("client_label") or ""),
            "fresh": False,
            "message": "Reusing the pending device code.",
        }

    tenant = (tenant or "common").strip() or "common"
    scopes = (scopes or "").strip() or DEFAULT_SCOPES
    candidates: List[Tuple[str, str]] = []
    if (client_id or "").strip():
        candidates.append((client_id.strip(), "config.json client_id"))
    candidates.extend(FALLBACK_CLIENTS)

    last_error = ""
    for cid, label in candidates:
        status, payload, _headers = _post_form(
            _device_url(tenant), {"client_id": cid, "scope": scopes})
        if status == 200 and isinstance(payload, dict) and payload.get("device_code"):
            code = str(payload.get("user_code") or "")
            sign_in, carries = _sign_in_url(payload, code)
            pending = {
                "device_code": payload.get("device_code"),
                "user_code": code,
                "verification_uri": sign_in,
                "carries_code": carries,
                "interval": int(payload.get("interval") or 5),
                "expires_at": time.time() + int(payload.get("expires_in") or 900),
                "client_id": cid,
                "client_label": label,
                "tenant": tenant,
                "scopes": scopes,
            }
            _set_json(storage, DEVICE_KEY, pending)
            return {
                "user_code": code,
                "verification_uri": sign_in,
                "expires_in": int(payload.get("expires_in") or 900),
                "client_label": label,
                "fresh": True,
                "message": "Open the link, enter the code and approve the permissions.",
            }
        last_error = _explain(status, payload)
    raise AuthRequired(
        "Could not obtain a device code from Microsoft: " + last_error[:300] +
        ". If your tenant blocks user consent for these public clients, the "
        "sign-in cannot be completed without administrator approval."
    )


def device_poll(storage) -> Dict[str, Any]:
    """Poll the token endpoint once. Returns {signed_in, status, account, error}."""
    pending = _get_json(storage, DEVICE_KEY)
    if not pending.get("device_code"):
        raise AuthRequired("No pending device code. Run the sign-in start step first.")
    if float(pending.get("expires_at") or 0) < time.time():
        _del(storage, DEVICE_KEY)
        raise AuthRequired("The device code expired (15 min). Run the sign-in start step again.")

    status, payload, _headers = _post_form(_token_url(pending.get("tenant", "common")), {
        "grant_type": DEVICE_GRANT,
        "client_id": pending.get("client_id"),
        "device_code": pending.get("device_code"),
    })
    if status == 200 and isinstance(payload, dict) and payload.get("access_token"):
        token = _save_token(storage, payload, pending.get("client_id", ""),
                            pending.get("scopes", ""))
        token["tenant"] = pending.get("tenant", "")
        _set_json(storage, TOKEN_KEY, token)
        try:
            me = graph_call(token["access_token"], "GET",
                            "/me?$select=displayName,userPrincipalName,mail,id")
            token["account"] = str(me.get("userPrincipalName") or me.get("mail") or "")
            _set_json(storage, TOKEN_KEY, token)
        except GraphError:
            pass
        _del(storage, DEVICE_KEY)
        return {"signed_in": True, "status": "signed_in", "account": token.get("account", ""),
                "error": ""}

    if status == 0:
        raise MailboxUnavailable(
            "Cannot reach the Microsoft sign-in service: " + _explain(status, payload)[:200])
    error = str((payload or {}).get("error") or "")
    if error == "authorization_pending":
        return {"signed_in": False, "status": "pending", "account": "", "error": ""}
    if error == "slow_down":
        pending["interval"] = int(pending.get("interval") or 5) + 5
        _set_json(storage, DEVICE_KEY, pending)
        return {"signed_in": False, "status": "pending", "account": "", "error": ""}
    if error in ("expired_token", "bad_verification_code", "authorization_declined"):
        _del(storage, DEVICE_KEY)
        raise AuthRequired(
            "Sign-in did not complete (" + error + "). Run the sign-in start step again.")
    raise AuthRequired(
        "Sign-in failed: " + _explain(status, payload)[:300] +
        ". If it says admin approval is required, this tenant does not allow user "
        "consent for the Graph public clients.")


def sign_out(storage) -> None:
    _del(storage, TOKEN_KEY)
    _del(storage, DEVICE_KEY)


def _refresh(storage, token: Dict[str, Any]) -> Dict[str, Any]:
    refresh_token = token.get("refresh_token")
    client_id = token.get("client_id")
    if not refresh_token or not client_id:
        raise AuthRequired("No refresh token. Please sign in again.")
    tenant = token.get("tenant") or "common"
    status, payload, _headers = _post_form(_token_url(tenant), {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
        "scope": token.get("scopes") or DEFAULT_SCOPES,
    })
    if status == 200 and isinstance(payload, dict) and payload.get("access_token"):
        new_token = _save_token(storage, payload, client_id,
                                token.get("scopes") or DEFAULT_SCOPES, previous=token)
        new_token["account"] = token.get("account", "")
        new_token["tenant"] = token.get("tenant", "")
        _set_json(storage, TOKEN_KEY, new_token)
        return new_token
    if status == 0 or status >= 500:
        raise MailboxUnavailable(
            "Cannot reach Microsoft to renew the credential: " + _explain(status, payload)[:200])
    raise AuthRequired(
        "The credential expired and could not be renewed (" +
        _explain(status, payload)[:200] + "). Please sign in again.")


def current_token(storage, *, require_write: bool = True) -> Dict[str, Any]:
    token = load_token(storage)
    if not token.get("access_token") and not token.get("refresh_token"):
        raise AuthRequired("Not signed in. Run the device-code sign-in steps first.")
    now = time.time()
    expires_at = float(token.get("expires_at") or 0)
    if not token.get("access_token") or expires_at - TOKEN_MARGIN <= now:
        token = _refresh(storage, token)
    if require_write and WRITE_SCOPE_MARK not in str(token.get("scopes") or ""):
        raise AuthRequired("The stored credential lacks Mail.ReadWrite. Please sign in again.")
    return token


def _access(storage, *, require_write: bool = True) -> str:
    return str(current_token(storage, require_write=require_write)["access_token"])


# ── Graph mailbox helpers ────────────────────────────────────────────
def me(storage) -> Dict[str, Any]:
    return graph_call(_access(storage, require_write=False), "GET",
                      "/me?$select=displayName,userPrincipalName,mail,id")


def inbox_count(storage) -> int:
    payload = graph_call(_access(storage, require_write=False), "GET",
                         "/me/mailFolders/inbox?$select=totalItemCount,unreadItemCount")
    return int((payload or {}).get("totalItemCount") or 0)


def list_headers(storage, top: int = RECENT_MAX, days: Optional[int] = None) -> List[Dict[str, Any]]:
    params = {"$top": str(int(top)), "$select": SELECT_HEADERS,
              "$orderby": "receivedDateTime desc"}
    if days:
        since = (datetime.now(timezone.utc) - timedelta(days=int(days))) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        params["$filter"] = f"receivedDateTime ge {since}"
    payload = graph_call(_access(storage, require_write=False), "GET",
                         "/me/mailFolders/inbox/messages?" + urllib.parse.urlencode(params))
    return list((payload or {}).get("value") or [])


def fetch_body(storage, message_id: str) -> str:
    if not message_id:
        return ""
    payload = graph_call(
        _access(storage, require_write=False), "GET",
        "/me/messages/" + urllib.parse.quote(message_id, safe="") + "?$select=" + SELECT_BODY)
    return mailmeta.strip_html(_body_text((payload or {}).get("body"))) or \
        str((payload or {}).get("bodyPreview") or "")


def _address_of(value: Any) -> Tuple[str, str]:
    if isinstance(value, dict):
        inner = value.get("emailAddress")
        if isinstance(inner, dict):
            return str(inner.get("name") or ""), str(inner.get("address") or "")
        return str(value.get("name") or ""), str(value.get("address") or "")
    if isinstance(value, str):
        return "", value
    return "", ""


def _body_text(raw: Any) -> str:
    if isinstance(raw, dict):
        content = str(raw.get("content") or "")
        is_html = (raw.get("contentType") or "").lower() == "html"
    elif isinstance(raw, str):
        content, is_html = raw, True
    else:
        return ""
    return mailmeta.strip_html(content) if is_html else content.strip()


def _received_at(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone() \
            .replace(tzinfo=None)
    except Exception:
        return None


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    name, address = _address_of(raw.get("from"))
    if not address:
        alt_name, alt_address = _address_of(raw.get("sender"))
        name, address = name or alt_name, address or alt_address
    categories = raw.get("categories")
    received = _received_at(raw.get("receivedDateTime"))
    body = _body_text(raw.get("body")) or str(raw.get("bodyPreview") or "")
    return {
        "entryid": raw.get("id") or "",
        "subject": raw.get("subject") or "(no subject)",
        "sender_name": name,
        "sender": address,
        "body": body,
        "received": received.isoformat(timespec="minutes") if received else "",
        "categories": list(categories) if isinstance(categories, list) else [],
        "web_link": str(raw.get("webLink") or ""),
    }


def _level_of(categories: Sequence[str]) -> Optional[str]:
    for name in categories:
        if name in mailmeta.LEVELS:
            return name
    return None


def _mail_controls(msg: Dict[str, Any]) -> Optional[str]:
    """Return 'command' / 'report' when this mail is a control mail."""
    subject = str(msg.get("subject") or "")
    categories = mailmeta.category_names(msg.get("categories"))
    if mailmeta.parse_sum_command(subject) is not None:
        return None if mailmeta.SUM_NAME in categories else "command"
    if mailmeta.is_report_subject(subject):
        return None if mailmeta.SUM_NAME in categories else "report"
    return None


def collect(storage, last_seen: str = "", days: int = 7, max_items: int = 30,
            catchup: bool = False) -> Dict[str, Any]:
    """One inbox scan: candidates to classify plus control mails to act on."""
    st = state_mod.load(storage)
    ignored = set(str(i) for i in (st.get("ignored") or []))
    last_seen = str(last_seen or st.get("last_seen") or "")
    max_items = max(1, min(int(max_items or 30), 30))

    headers = list_headers(storage, top=RECENT_MAX, days=days if catchup else (days or 7))
    candidates: List[Dict[str, Any]] = []
    commands: List[Dict[str, Any]] = []
    reports: List[Dict[str, Any]] = []
    newest_id = ""
    for raw in headers:
        msg = normalize(raw)
        if not newest_id:
            newest_id = msg["entryid"]
        if not catchup and last_seen and msg["entryid"] == last_seen:
            break
        categories = mailmeta.category_names(msg.get("categories"))
        control = _mail_controls(msg)
        if control == "command":
            if len(commands) < 5:
                commands.append({"entryid": msg["entryid"], "subject": msg["subject"]})
            continue
        if control == "report":
            if len(reports) < 10:
                reports.append({"entryid": msg["entryid"], "subject": msg["subject"]})
            continue
        if mailmeta.has_our_category(categories):
            continue
        if msg["entryid"] in ignored:
            continue
        if len(candidates) >= max_items:
            continue
        try:
            body = fetch_body(storage, msg["entryid"])
        except GraphError as ex:
            if ex.transient:
                raise MailboxUnavailable(
                    "could not load a message body: " + str(ex)) from ex
            body = ""
        candidates.append({
            "entryid": msg["entryid"],
            "subject": msg["subject"],
            "sender_name": msg["sender_name"],
            "sender": msg["sender"],
            "received": msg["received"],
            "web_link": msg["web_link"],
            "categories": categories,
            "body_head": mailmeta.body_head_tail(body, BODY_HEAD, BODY_TAIL),
        })
    return {
        "candidates": candidates,
        "controls_commands": commands,
        "controls_reports": reports,
        "newest_id": newest_id,
        "oldest_id": candidates[-1]["entryid"] if candidates else "",
    }


def collect_recent(storage, days: int = 7, letters: str = "sabc",
                   max_items: int = 100) -> List[Dict[str, Any]]:
    wanted = "".join(c for c in "sabc" if c in (letters or "sabc").lower()) or "sabc"
    rows: List[Dict[str, Any]] = []
    for raw in list_headers(storage, top=RECENT_MAX, days=max(1, int(days or 7))):
        msg = normalize(raw)
        level = _level_of(msg["categories"])
        if level is None or level.lower() not in wanted:
            continue
        try:
            body = fetch_body(storage, msg["entryid"])
        except GraphError as ex:
            if ex.transient:
                raise MailboxUnavailable(str(ex)) from ex
            body = ""
        rows.append({
            "entryid": msg["entryid"],
            "level": level,
            "subject": msg["subject"],
            "sender": msg["sender_name"] or msg["sender"],
            "received": msg["received"],
            "web_link": msg["web_link"],
            "body": body[:RECENT_BODY_CHARS],
        })
        if len(rows) >= max_items:
            break
    rows.sort(key=lambda item: mailmeta.LEVELS.index(item["level"]))
    return rows


def _set_categories(storage, message_id: str, existing: Sequence[str],
                    names: Sequence[str], flag: Optional[int] = None) -> List[str]:
    if not (message_id or "").strip():
        raise GraphError("no message id to write to")
    merged = mailmeta.merge_categories(existing, names)
    body: Dict[str, Any] = {"categories": merged}
    if flag is not None:
        body["flag"] = {"flagStatus": "flagged" if flag == mailmeta.FLAG_MARKED else "notFlagged"}
    graph_call(_access(storage), "PATCH",
               "/me/messages/" + urllib.parse.quote(message_id, safe=""), body=body)
    return merged


def _fetch_categories(storage, message_id: str) -> List[str]:
    payload = graph_call(_access(storage, require_write=False), "GET",
                         "/me/messages/" + urllib.parse.quote(message_id, safe="") +
                         "?$select=categories")
    return mailmeta.category_names((payload or {}).get("categories"))


def apply_verdicts(storage, verdicts: Sequence[Dict[str, Any]],
                   dry_run: bool = False) -> Dict[str, Any]:
    """Write classification results back (categories + urgent flag).

    Non-school mails are skipped and their ids returned as ``ignored_ids`` so the
    workflow can remember them. Single-mail failures never abort the batch.
    """
    ok = failed = skipped = 0
    ignored_ids: List[str] = []
    errors: List[Dict[str, str]] = []
    transient = False
    for verdict in verdicts or []:
        entryid = str(verdict.get("entryid") or "")
        if not entryid:
            failed += 1
            errors.append({"entryid": "", "error": "missing entryid"})
            continue
        if verdict.get("is_school") is False:
            skipped += 1
            ignored_ids.append(entryid)
            continue
        level = str(verdict.get("level") or "C").upper()[:1]
        if level not in mailmeta.LEVELS:
            level = "C"
        flag = None
        if level == "S":
            flag = mailmeta.FLAG_MARKED if verdict.get("urgent") else mailmeta.FLAG_NONE
        if dry_run:
            ok += 1
            continue
        try:
            existing = verdict.get("categories")
            if not isinstance(existing, list):
                existing = _fetch_categories(storage, entryid)
            _set_categories(storage, entryid, existing, [level], flag)
            ok += 1
        except GraphError as ex:
            failed += 1
            transient = transient or ex.transient
            errors.append({"entryid": entryid, "error": str(ex)[:300]})
        except Exception as ex:
            failed += 1
            errors.append({"entryid": entryid, "error": f"{type(ex).__name__}: {ex}"[:300]})
    return {"ok": ok, "failed": failed, "skipped": skipped,
            "ignored_ids": ignored_ids, "errors": errors, "transient": transient}


def tag_messages(storage, entry_ids: Sequence[str], names: Sequence[str]) -> Dict[str, Any]:
    ok = failed = 0
    errors: List[Dict[str, str]] = []
    transient = False
    for entryid in entry_ids or []:
        entryid = str(entryid or "")
        if not entryid:
            continue
        try:
            existing = _fetch_categories(storage, entryid)
            _set_categories(storage, entryid, existing, names)
            ok += 1
        except GraphError as ex:
            failed += 1
            transient = transient or ex.transient
            errors.append({"entryid": entryid, "error": str(ex)[:300]})
        except Exception as ex:
            failed += 1
            errors.append({"entryid": entryid, "error": f"{type(ex).__name__}: {ex}"[:300]})
    return {"ok": ok, "failed": failed, "errors": errors, "transient": transient}


def send_mail(storage, to: str, subject: str, html: str) -> None:
    if not (to or "").strip():
        raise GraphError("no recipient configured")
    graph_call(_access(storage), "POST", "/me/sendMail", body={
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to.strip()}}],
        },
        "saveToSentItems": True,
    })


def check(storage) -> Dict[str, Any]:
    token = current_token(storage, require_write=True)
    me_info = me(storage)
    return {
        "signed_in": True,
        "account": str(me_info.get("userPrincipalName") or me_info.get("mail") or ""),
        "display_name": str(me_info.get("displayName") or ""),
        "inbox_count": inbox_count(storage),
        "token_expires_in": int(max(0, float(token.get("expires_at") or 0) - time.time())),
    }
