# Demo walkthrough — HKUST_AI_email_manager

> For course reviewers / prototype feedback: this page is the guided demo of the prototype.
> Repository: <https://github.com/MiKasss666/HKUST_AI_email_manager>
> Release (plugin + workflow downloads): <https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest>

The prototype is a **Dify plugin + one Dify workflow** that manages a Microsoft 365 (HKUST) mailbox:

1. signs in with a **Microsoft device code** (no admin consent, no Azure app registration);
2. **classifies school mail into S/A/B/C** with a single LLM call per round, plus deterministic rules;
3. **writes the S/A/B/C categories back** to Outlook (and flags urgent S mail);
4. sends **daily / weekly / on-demand HTML reports** (`sum` command by e-mail).

Reviewers without a Dify workspace can evaluate it through this page: the workflow structure, the
example inputs/outputs, and the reproducible steps below. A Dify workspace, the school AI API, and
the plugin are needed to run it end-to-end (see [`docs/DISTRIBUTE.md`](DISTRIBUTE.md)).

---

## 1. What is being demonstrated

| Capability | Where to see it |
|---|---|
| Device-code sign-in without admin approval | `provider/` + `tools/auth_start`, `tools/auth_poll` (plugin) |
| S/A/B/C classification rules | workflow node `Classify mail`, prompt built by `Plan round` |
| Deterministic safety rules (course/faculty/dorm can only raise, never lower, a level) | `Validate verdicts` node |
| Category write-back, preserving user labels | `tools/apply.py` + plugin `lib/mailmeta.py` |
| Daily 00:00 / Sunday 00:00 reports | workflow nodes `Scheduled report?` → `Send report` |
| `sum` command by e-mail | `Plan round` → `Tag control mail` → report nodes |
| Batch safety: ≤20 mails per run, backlog drains over runs, failed batch retried next run | `Collect mail`, `Plan round`, baseline-advance logic |

Workflow size: **86 nodes / 90 edges**, DSL version 0.7.0, a single 5-minute Schedule Trigger.

---

## 2. End-to-end flow (what a run does)

```
Schedule (every 5 min)
  └─ auth_status ─ not signed in ─> send sign-in e-mail (device code + link + form)
                └─ signed in ─> read state ─ scheduled report? (00:00 window)
                                └─ acquire lock ─> collect headers (≤20 candidates)
                                   └─ one LLM call ─> strict validation (ref → message id)
                                      └─ write back categories ─> advance baseline ─> unlock
```

Sample report e-mail subject: `📬 邮件总结（全部）· 最近7天` (the number of days follows `SUMMARY_DAYS`).
Daily report = last 1 day; weekly report = `SUMMARY_DAYS` days; manual report = `LETTERS` levels.

---

## 3. Example input → output

| # | Example mail | Expected category | Why |
|---|---|---|---|
| 1 | `COMP 1021 Assignment 3 due this Friday` | **S** + red flag | action required + deadline inside `URGENT_DAYS` |
| 2 | `MATH1023 (L1) — lecture video and notes` | **A** | enrolled course, nothing to do |
| 3 | `[Open for Application] Exchange Program (Fall 2027)` | **B** | optional application, not urgent |
| 4 | `[Press Release] University Presidents Forum concludes` | **C** | informational only |
| 5 | Commercial promotion from outside the university | *(none)* | not school-related, ignored |
| 6 | Subject `sum sa` sent to your own mailbox | command | next round tags it `Sum` and e-mails an S/A-only report |

Reviewers can use scenarios 1–6 as their test checklist: classification is deterministic for rules
1–5, and the report for 6 is delivered to the mailbox owner.

---

## 4. Reproduce locally (for reviewers who want the artifacts)

1. Download `email_manager.difypkg` + `HKUST_AI_email_manager.yml` from the
   [latest release](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest);
2. Install the plugin in a Dify Cloud workspace (Integrations → Install → Local Package File);
3. Import the workflow (Studio → Import DSL), pick a model, fill `EMAIL` / `RECIPIENT`, Publish;
4. Create the Outlook categories `S`, `A`, `B`, `C`, `Sum` once (Settings → Mail → Categories);
5. Enable the Schedule Trigger in Access Point; the first round sends a sign-in e-mail.
6. Full new-user walkthrough: [`docs/DISTRIBUTE.md`](DISTRIBUTE.md).

Local checks anyone can run (no Dify, no network):

```powershell
py -3 scripts/validate_dsl.py
py -3 scripts/smoke_code_nodes.py
py -3 scripts/smoke_pipeline.py
py -3 -m unittest discover -s tests
```

---

## 5. Known limitations (by design)

- **No real-time "new mail" trigger**: the existing Outlook integration in Dify requires administrator
  approval for its login flow, and a Graph change-subscription trigger would cost far more consent
  work than it returns. The prototype polls every 5 minutes (user-adjustable).
- **Outlook category definitions are created manually once** (S/A/B/C/Sum); Microsoft Graph cannot
  create the master category list for this account, so the workflow only applies categories.
- **At most 20 mails are classified per batch.** A larger backlog is not lost: the first day clears
  up to two batches, and the automatic **daily catch-up** keeps picking up older unclassified mail
  (about 20 per day) until the backlog is gone — no user action is needed, but a very large backlog
  takes days rather than minutes.
- **A batch whose LLM answer cannot be validated** (wrong item count, or a mail missing / duplicated)
  counts as a **failed round**: the batch is retried in the next run, the "last processed" pointer is
  not advanced, and after 3 consecutive failed rounds the workflow skips that batch and continues;
  the failure stays visible in the run log.
- Reports list at most `REPORT_MAX` mails (default 50, effective max 100) — configurable.
