"""Reset test data: clear categories on the N most recent inbox messages.

Local helper that talks to Microsoft Graph directly (it does NOT go through
Dify), so you can reset the mailbox before/after testing the Dify workflow.

* first run: device-code sign-in (prints a code + link, then waits for you);
  the token is cached in ``build/reset_categories_store.json`` so later runs
  are non-interactive;
* default behaviour: only remove THIS project's labels (S / A / B / C / Sum +
  legacy "S 紧急" etc.), keeping any labels you created yourself;
* ``--all``: clear every category on those messages;
* ``--dry-run``: show what would change, write nothing.

Usage (from the repo root):

    py -3 scripts/reset_categories.py                # clear our labels, latest 30
    py -3 scripts/reset_categories.py --dry-run      # preview
    py -3 scripts/reset_categories.py --all          # clear all categories
    py -3 scripts/reset_categories.py --limit 50

Only the 30 newest messages by ``receivedDateTime`` are touched (or ``--limit``).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = ROOT
STORE_PATH = os.path.join(ROOT, "build", "reset_categories_store.json")

sys.path.insert(0, PLUGIN_DIR)
from lib import graph, mailmeta  # noqa: E402


class FileStorage:
    """Minimal stand-in for Dify's plugin storage (bytes in, bytes out)."""

    def __init__(self, path: str):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self.data = {k: base64.b64decode(v) for k, v in raw.items()}
            except (ValueError, OSError):
                self.data = {}

    def _flush(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({k: base64.b64encode(v).decode("ascii")
                       for k, v in self.data.items()}, fh)

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value
        self._flush()

    def delete(self, key):
        self.data.pop(key, None)
        self._flush()


def sign_in(storage: FileStorage) -> None:
    """Device-code sign-in, printing the code/link and polling until done."""
    info = graph.device_start(storage, force_new=True)
    print("\n=== Microsoft sign-in required ===")
    print("Open:", info["verification_uri"])
    print("Code:", info["user_code"])
    print("Waiting for approval (Ctrl+C to abort)...", flush=True)
    deadline = time.time() + max(120, int(info.get("expires_in") or 900))
    while time.time() < deadline:
        try:
            result = graph.device_poll(storage)
        except graph.AuthRequired as ex:
            print("Sign-in failed:", ex)
            raise SystemExit(1)
        if result.get("signed_in"):
            print("Signed in as:", result.get("account") or "(unknown)")
            return
        time.sleep(5)
    raise SystemExit("Timed out waiting for sign-in approval.")


def access_token(storage: FileStorage) -> str:
    if not graph.signed_in(storage):
        sign_in(storage)
    try:
        return graph._access(storage, require_write=True)
    except graph.AuthRequired:
        sign_in(storage)
        return graph._access(storage, require_write=True)


def clear_categories(limit: int, clear_all: bool, dry_run: bool) -> int:
    storage = FileStorage(STORE_PATH)
    token = access_token(storage)
    account = graph.account(storage)
    print("Account:", account or "(unknown)")

    path = ("/me/messages?$top=%d&$select=id,subject,categories,receivedDateTime"
            "&$orderby=receivedDateTime%%20desc" % max(1, limit))
    payload = graph.graph_call(token, "GET", path)
    messages = payload.get("value") or []
    print("Fetched %d message(s); clearing %s categories\n"
          % (len(messages), "ALL" if clear_all else "project labels only"))

    managed = mailmeta.OUR_CATEGORY_NAMES
    changed = skipped = failed = 0
    for message in messages:
        old = [str(name) for name in message.get("categories") or [] if str(name).strip()]
        if clear_all:
            new = []
        else:
            new = [name for name in old if name not in managed]
        subject = str(message.get("subject") or "")[:70]
        when = str(message.get("receivedDateTime") or "")
        if new == old:
            skipped += 1
            print("  skip  %s  %s  %r" % (when, subject, old))
            continue
        print("  patch %s  %s  %r -> %r" % (when, subject, old, new))
        if dry_run:
            continue
        try:
            graph.graph_call(token, "PATCH", "/me/messages/" + str(message.get("id")),
                             body={"categories": new})
            changed += 1
        except graph.GraphError as ex:
            failed += 1
            print("         FAILED:", ex)
    print("\nchanged=%d skipped=%d failed=%d%s"
          % (changed, skipped, failed, " (dry run, nothing written)" if dry_run else ""))
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=30,
                        help="how many newest messages to scan (default: 30)")
    parser.add_argument("--all", action="store_true",
                        help="clear every category, including your own labels")
    parser.add_argument("--dry-run", action="store_true",
                        help="only print what would be changed")
    parser.add_argument("--sign-out", action="store_true",
                        help="forget the cached token and exit")
    parser.add_argument("--no-login", action="store_true",
                        help="fail instead of starting a device-code sign-in")
    args = parser.parse_args()

    if args.sign_out:
        storage = FileStorage(STORE_PATH)
        graph.sign_out(storage)
        print("Cached token removed:", STORE_PATH)
        return 0
    if args.no_login:
        storage = FileStorage(STORE_PATH)
        if not graph.signed_in(storage):
            print("No cached token in", STORE_PATH, "- run once without --no-login.")
            return 2
    return clear_categories(args.limit, args.all, args.dry_run)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except graph.GraphError as ex:
        print("Graph error:", ex)
        sys.exit(1)
