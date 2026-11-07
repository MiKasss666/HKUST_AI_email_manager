# Prototype Feedback — submission draft

Course: HKUST · Team Chatbot Competition — Milestone 2 (Prototype Feedback)
Deadline: **Wednesday 11 November, 23:59** (FeedbackFruits), worth **15%**.

Deliverables:
1. Working demo link
2. Test log (~300 words)
3. 3–5 sample queries / scenarios for reviewers

---

## 1. Working demo link

Our prototype is **HKUST_AI_email_manager** — a Dify plugin + one Dify workflow that signs in to a
Microsoft 365 mailbox with a device code, classifies school mail into S/A/B/C, writes the categories
back to Outlook, and sends daily / weekly / on-demand HTML reports.

Pick **one** of these as the submitted link (decide before submitting):

- **Option A — Dify Web App link** (if the workflow app can be shared with reviewers)
  `https://cloud.dify.ai/...` ← paste here, verify a reviewer without workspace access can open it
- **Option B — recorded demo (recommended if A is not publicly accessible)**
  a 2–3 minute screen recording: sign-in e-mail → device-code approval → Test Run → Outlook labels
  → `sum sa` command → report e-mail. Upload unlisted (YouTube/Bilibili) or as a GitHub Release asset.
- **Supporting link (always include)**: <https://github.com/MiKasss666/HKUST_AI_email_manager>
  (source, plugin package, workflow DSL, setup guide)

> Reviewers need a link that works for the full review window. If the Dify app requires a Dify
> account, submit the recorded demo as the primary link and the GitHub repo as supporting material.

---

## 2. Test log (~300 words)

Before releasing the prototype we tested it on a real HKUST mailbox, starting in a dry-run mode so
that no mailbox data could be changed.

The biggest constraint came from the existing Outlook integration. The Outlook plugin already
available in Dify cannot satisfy our requirements: when we tried to sign in to a university mailbox
with it, the login request is sent as the Dify application itself, so it requires administrator
approval, which we cannot obtain. For the same reason we could not implement "start processing when
a new mail arrives" — building our own change-notification path would have required much more
consent work than the benefit justified. We therefore wrote our own plugin that signs in with
Microsoft Graph using the device-code flow and controls the mailbox directly, and we chose scheduled
polling: one run every 5 minutes, adjustable by the user.

Another limitation is category creation: in our account the Outlook master category list cannot be
created programmatically (again tied to the Outlook / permission side), so users still create the
S/A/B/C/Sum categories once manually, and the workflow then applies them to messages automatically.

On the processing side, the first version failed at scale: with 30 messages the model could not
handle them in one request and the run failed. We reproduced this and replaced the single large
request with batching — each round classifies at most 20 messages, larger inboxes are processed
across rounds, and a rejected batch is retried without advancing the processing position, so no
message is lost.

We also fixed several integration issues found during testing: environment-variable type errors that
blocked workflow loading, the code-node entry format, long message-id alignment between model output
and Microsoft ids, and a plugin-identifier format error that blocked installation.

What we chose not to fix: real-time mail triggering and automatic category creation, both documented
as known limitations.

---

## 3. Sample queries / scenarios for reviewers

Try these first — each one exercises a feature the prototype was actually built for:

| # | Scenario | What to do | Expected result |
|---|---|---|---|
| 1 | **Assignment due soon** | Have a school mail like *"COMP 1021 Assignment 3 due this Friday"* in the inbox | tagged **S**, red flag (urgent), listed first in the report |
| 2 | **Course/material mail** | A course announcement, e.g. *"MATH1023 lecture video and notes"* | tagged **A** (course-related, nothing to do) |
| 3 | **Application / opportunity** | *"Spring 2027 exchange programme — applications open"* | tagged **B** (action possible, not urgent) |
| 4 | **Newsletter / promotion** | A press release or event digest from the university | tagged **C** (informational only) |
| 5 | **On-demand summary** | Send an e-mail to your own school address with subject **`sum sa`** | next round tags that mail `Sum` and mails back an HTML report of only S and A mails |
| 6 | **Non-school mail** | A commercial promotion from outside the university | left untouched (no category) — the system ignores non-school mail |

Notes for reviewers: classification is rule-driven on top of the model output (school domain,
enrolled courses, faculty, dorm keywords, deadlines), and the classifier is deterministic about
never lowering a level — so a course mail cannot be classified below A.

---

## 4. Team-side checklist before submitting

- [ ] Demo link decided and tested in a **private browser window** (reviewer's view)
- [ ] Test log pasted into FeedbackFruits (~300 words above)
- [ ] 3–5 scenarios pasted / attached
- [ ] Peer feedback on 2 other teams' prototypes (individual, before 11 Nov 23:59)
