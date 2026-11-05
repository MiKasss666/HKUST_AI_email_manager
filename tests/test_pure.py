"""Offline unit tests for the Email Manager plugin library.

Run from the repository root (no network, no Dify runtime needed):

    py -3 -m unittest discover -s plugin/email_manager/tests -v
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from lib import graph, jsonutil, mailmeta, state  # noqa: E402


class FakeStorage:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)

    def exist(self, key):
        return key in self.data


class MailMetaTests(unittest.TestCase):
    def test_parse_sum_command(self):
        self.assertEqual(mailmeta.parse_sum_command("sum"), "sabc")
        self.assertEqual(mailmeta.parse_sum_command("SUM sa"), "sa")
        self.assertEqual(mailmeta.parse_sum_command("  sum SA  "), "sa")
        self.assertEqual(mailmeta.parse_sum_command("sum s"), "s")
        self.assertEqual(mailmeta.parse_sum_command("sum cba"), "abc")
        self.assertIsNone(mailmeta.parse_sum_command("summary"))
        self.assertIsNone(mailmeta.parse_sum_command("re: sum"))
        self.assertIsNone(mailmeta.parse_sum_command(""))

    def test_report_subject(self):
        self.assertTrue(mailmeta.is_report_subject("📬 邮件总结（全部）· 最近7天"))
        self.assertTrue(mailmeta.is_report_subject("📬 Email summary (all levels)"))
        self.assertFalse(mailmeta.is_report_subject("Lecture 12"))

    def test_merge_categories_keeps_user_labels(self):
        merged = mailmeta.merge_categories(["S", "Math", "A 重要", "  "], ["A"])
        self.assertEqual(merged, ["Math", "A"])

    def test_normalize_level(self):
        self.assertEqual(mailmeta.normalize_level("s"), "S")
        self.assertEqual(mailmeta.normalize_level("a"), "A")
        self.assertEqual(mailmeta.normalize_level("Z"), "C")
        self.assertEqual(mailmeta.normalize_level(None), "C")

    def test_parse_school(self):
        self.assertIs(mailmeta.parse_school(True), True)
        self.assertIs(mailmeta.parse_school("false"), False)
        self.assertIs(mailmeta.parse_school("不是学校邮件"), False)
        self.assertIs(mailmeta.parse_school("是学校邮件"), True)
        self.assertIsNone(mailmeta.parse_school("maybe"))

    def test_deadline_and_urgency(self):
        today = datetime.date(2026, 3, 1)
        deadline = mailmeta.parse_deadline("2026-03-05T10:00:00Z")
        self.assertEqual(deadline, datetime.date(2026, 3, 5))
        self.assertTrue(mailmeta.is_urgent("S", deadline, 14, today))
        self.assertFalse(mailmeta.is_urgent("A", deadline, 14, today))
        self.assertFalse(mailmeta.is_urgent("S", datetime.date(2026, 2, 1), 14, today))
        self.assertFalse(mailmeta.is_urgent("S", datetime.date(2026, 4, 1), 14, today))

    def test_body_head_tail(self):
        self.assertEqual(mailmeta.body_head_tail("short", 400, 300), "short")
        long_body = "A" * 500 + "B" * 100 + "C" * 500
        text = mailmeta.body_head_tail(long_body, 400, 300)
        self.assertIn("[tail]", text)
        self.assertIn("C" * 300, text)
        self.assertNotIn("A" * 400 + "A", text)

    def test_verdicts_requires_exact_ids(self):
        payload = {"items": [
            {"entryid": "b", "级别": "s", "截止日期": "2026-03-05", "学校": True},
            {"entryid": "a", "级别": "C", "学校": False},
        ]}
        today = datetime.date(2026, 3, 1)
        out = mailmeta.verdicts_from_payload(payload, ["a", "b"], 14, today)
        self.assertIsNotNone(out)
        self.assertEqual([v["entryid"] for v in out], ["a", "b"])
        self.assertEqual(out[1]["level"], "S")
        self.assertTrue(out[1]["urgent"])
        self.assertFalse(out[0]["is_school"])
        self.assertIsNone(mailmeta.verdicts_from_payload(payload, ["a"], 14, today))
        self.assertIsNone(mailmeta.verdicts_from_payload(payload, ["a", "c"], 14, today))

    def test_verdicts_index_fallback_and_school_default(self):
        payload = [{"index": 1, "level": "B"}, {"index": 2, "level": "A"}]
        out = mailmeta.verdicts_from_payload(payload, ["x", "y"], 14,
                                             datetime.date(2026, 3, 1))
        self.assertEqual([v["entryid"] for v in out], ["x", "y"])
        self.assertTrue(all(v["is_school"] for v in out))

    def test_deterministic_overrides(self):
        mails = [
            {"subject": "COMP 1021 lecture moved", "body": "", "sender_name": "",
             "sender": "a@ust.hk", "categories": []},
            {"subject": "notice", "body": "", "sender_name": "SCI/HOME, School of Science",
             "sender": "advise@ust.hk", "categories": []},
            {"subject": "promo", "body": "", "sender_name": "", "sender": "shop@x.com",
             "categories": []},
        ]
        verdicts = [
            {"entryid": "1", "level": "C", "urgent": False, "is_school": True},
            {"entryid": "2", "level": "B", "urgent": False, "is_school": True},
            {"entryid": "3", "level": "B", "urgent": False, "is_school": False},
        ]
        self.assertEqual(mailmeta.apply_enrolled_override(mails, verdicts, ["COMP 1021"]), 1)
        self.assertEqual(verdicts[0]["level"], "A")
        self.assertEqual(mailmeta.apply_faculty_override(mails, verdicts, ["School of Science"]), 1)
        self.assertEqual(verdicts[1]["level"], "A")
        self.assertEqual(mailmeta.apply_school_override(mails, verdicts, ["ust.hk"]), 0)
        self.assertFalse(verdicts[2]["is_school"])
        self.assertEqual(mailmeta.apply_school_override(
            [{"sender": "x@connect.ust.hk"}], [{"is_school": False}], ["ust.hk"]), 1)


class JsonUtilTests(unittest.TestCase):
    def test_parse_variants(self):
        self.assertEqual(jsonutil.parse_json('{"items": []}'), {"items": []})
        self.assertEqual(jsonutil.parse_json('```json\n[{"a": 1}]\n```'), [{"a": 1}])
        self.assertEqual(jsonutil.parse_json('{"a": 1}\n{"b": 2}'), [{"a": 1}, {"b": 2}])
        self.assertIsNone(jsonutil.parse_json("not json"))

    def test_salvage_truncated(self):
        text = '[{"a": 1}, {"b": 2}, {"c":'
        self.assertEqual(jsonutil.salvage_array(text), [{"a": 1}, {"b": 2}])

    def test_as_text_list(self):
        self.assertEqual(jsonutil.as_text_list({"points": ["a", "b"]}), ["a", "b"])
        self.assertEqual(jsonutil.as_text_list('["x"]'), ["x"])


class StateTests(unittest.TestCase):
    def test_advance_paths(self):
        st = state.default_state()
        st, gave_up = state.advance(st, [], "newest", 0)
        self.assertEqual(st["last_seen"], "newest")
        self.assertFalse(gave_up)

        st = state.default_state()
        st, gave_up = state.advance(st, ["n1", "n2"], "newest", 0)
        self.assertEqual(st["last_seen"], "n2")
        self.assertFalse(gave_up)

        st = state.default_state()
        st, gave_up = state.advance(st, ["n1", "n2"], "newest", 1)
        self.assertEqual(st["last_seen"], "")
        self.assertEqual(st["failed_rounds"], 1)
        self.assertFalse(gave_up)

        st, gave_up = state.advance(st, ["n1", "n2"], "newest", 1)
        st, gave_up = state.advance(st, ["n1", "n2"], "newest", 1)
        self.assertTrue(gave_up)
        self.assertEqual(st["last_seen"], "n2")
        self.assertEqual(st["failed_rounds"], 0)

    def test_advance_catchup_never_rewinds_baseline(self):
        st = state.default_state()
        st["last_seen"] = "newest-known"
        st, gave_up = state.advance(st, ["old-1", "old-2"], "newest-known", 0, catchup=True)
        self.assertEqual(st["last_seen"], "newest-known")
        self.assertFalse(gave_up)
        st["last_seen"] = "newest-known"
        st, gave_up = state.advance(st, ["old-1"], "newest-known", 3, catchup=True)
        self.assertEqual(st["last_seen"], "newest-known")
        self.assertTrue(gave_up)

    def test_lock(self):
        storage = FakeStorage()
        first = state.acquire_lock(storage, "owner-a", 300)
        self.assertTrue(first["acquired"])
        second = state.acquire_lock(storage, "owner-b", 300)
        self.assertFalse(second["acquired"])
        self.assertFalse(state.release_lock(storage, "owner-b"))
        self.assertTrue(state.release_lock(storage, "owner-a"))
        self.assertTrue(state.acquire_lock(storage, "owner-b", 300)["acquired"])

        # an expired lock can be taken over
        st = state.load(storage)
        st["lock_until"] = 0
        state.save(storage, st)
        self.assertTrue(state.acquire_lock(storage, "owner-c", 300)["acquired"])

    def test_ignored(self):
        st = state.default_state()
        added = state.remember_ignored(st, ["a", "b", "a"])
        self.assertEqual(added, ["a", "b"])
        state.remember_ignored(st, ["a"])
        self.assertEqual(st["ignored"][:2], ["a", "b"])

    def test_pause(self):
        storage = FakeStorage()
        state.set_paused(storage, True, "boom")
        self.assertTrue(state.load(storage)["paused"])
        state.set_paused(storage, False)
        self.assertFalse(state.load(storage)["paused"])

    def test_public_view_does_not_leak_full_ignored_list(self):
        st = state.default_state()
        state.remember_ignored(st, ["a" * 120, "b" * 120])
        view = state.public_view(st)
        self.assertNotIn("ignored", view)
        self.assertEqual(view["ignored_count"], 2)


class GraphHelperTests(unittest.TestCase):
    def test_normalize(self):
        raw = {
            "id": "AAMk",
            "subject": "hello",
            "from": {"emailAddress": {"name": "SCI/HOME", "address": "advise@ust.hk"}},
            "receivedDateTime": "2026-03-05T10:00:00Z",
            "categories": ["S", "Math"],
            "webLink": "https://outlook/x",
            "body": {"contentType": "html", "content": "<p>Hi&nbsp;there</p>"},
        }
        msg = graph.normalize(raw)
        self.assertEqual(msg["entryid"], "AAMk")
        self.assertEqual(msg["sender"], "advise@ust.hk")
        self.assertEqual(msg["sender_name"], "SCI/HOME")
        self.assertEqual(msg["categories"], ["S", "Math"])
        self.assertIn("Hi", msg["body"])
        self.assertNotIn("<p>", msg["body"])

    def test_control_mail_detection(self):
        command = {"subject": "sum sa", "categories": []}
        self.assertEqual(graph._mail_controls(command), "command")
        self.assertIsNone(graph._mail_controls(
            {"subject": "sum sa", "categories": ["Sum"]}))
        report = {"subject": "📬 邮件总结（全部）", "categories": []}
        self.assertEqual(graph._mail_controls(report), "report")
        self.assertIsNone(graph._mail_controls(
            {"subject": "📬 邮件总结（全部）", "categories": ["Sum"]}))
        self.assertIsNone(graph._mail_controls({"subject": "normal", "categories": []}))

    def test_token_storage(self):
        storage = FakeStorage()
        self.assertFalse(graph.signed_in(storage))
        graph._set_json(storage, graph.TOKEN_KEY, {
            "access_token": "a", "refresh_token": "r", "expires_at": 9e18,
            "client_id": "c", "scopes": graph.DEFAULT_SCOPES, "account": "me@ust.hk"})
        self.assertTrue(graph.signed_in(storage))
        self.assertEqual(graph.account(storage), "me@ust.hk")
        graph.sign_out(storage)
        self.assertFalse(graph.signed_in(storage))

    def test_current_token_requires_sign_in(self):
        storage = FakeStorage()
        with self.assertRaises(graph.AuthRequired):
            graph.current_token(storage)

    def test_sign_in_url(self):
        url, carries = graph._sign_in_url({"verification_uri": "https://login/device"}, "ABC")
        self.assertTrue(carries)
        self.assertIn("user_code=ABC", url)
        url2, carries2 = graph._sign_in_url(
            {"verification_uri": "https://login/device", "verification_uri_complete": "https://x/ABC"},
            "ABC")
        self.assertTrue(carries2)
        self.assertEqual(url2, "https://x/ABC")

    def test_pending_device_reuse(self):
        storage = FakeStorage()
        self.assertEqual(graph.pending_device(storage), {})
        graph._set_json(storage, graph.DEVICE_KEY, {
            "device_code": "dc", "user_code": "CODE", "verification_uri": "https://x",
            "expires_at": 9e18,
        })
        self.assertEqual(graph.pending_device(storage)["user_code"], "CODE")
        stale = {"device_code": "dc", "user_code": "CODE", "expires_at": 1}
        graph._set_json(storage, graph.DEVICE_KEY, stale)
        self.assertEqual(graph.pending_device(storage), {})

    def test_graph_error_transient(self):
        self.assertTrue(graph.GraphError("x", 0).transient)
        self.assertTrue(graph.GraphError("x", 429).transient)
        self.assertTrue(graph.GraphError("x", 503).transient)
        self.assertFalse(graph.GraphError("x", 403).transient)

    def test_apply_dry_run_and_non_school(self):
        storage = FakeStorage()
        result = graph.apply_verdicts(storage, [
            {"entryid": "a", "level": "S", "urgent": True, "is_school": True},
            {"entryid": "b", "level": "C", "is_school": False},
        ], dry_run=True)
        self.assertEqual(result["ok"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["ignored_ids"], ["b"])
        self.assertFalse(result["transient"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
